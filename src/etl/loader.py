"""
loader.py — Excel file loader for the Nifty 100 Financial Intelligence
Platform ETL pipeline (Sprint 1, Module 1, Day 02).

Responsibilities (per project spec, Section 9, Module 1):
    1.1 Excel file loader with header=1 support for core files
    1.2 Ticker normaliser applied to every table
    1.3 Year label standardiser applied to every time-series table
    1.7 Load audit log (rows_in, rows_out, rejected, runtime)

Core files (data/raw/) use header=1 -- row 0 is a title/metadata row,
row 1 is the real header row. Supplementary files (data/supporting/)
use header=0 -- no title row.

This module does NOT write to SQLite yet (that's Day 04). It focuses on:
    - loading every raw file into a clean, normalised DataFrame
    - applying normalize_ticker() to company_id / id columns
    - applying normalize_year() to year columns (renaming to 'year' as
      the standard column name across tables)
    - logging load statistics per file to output/load_audit.csv
    - logging rejected rows (bad ticker or unparseable year) to
      output/parse_failures.csv (per DQ-07 / DQ-08)
"""

from __future__ import annotations
import csv
import logging
import time
from pathlib import Path

import pandas as pd

from normaliser import normalize_ticker, normalize_year

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration: file -> (relative path, header row, ticker col, year col)
# year col of None means the file has no per-row year (e.g. companies.xlsx,
# prosandcons.xlsx have no year field to normalise).
# ---------------------------------------------------------------------------

CORE_FILES = {
    "companies":     {"path": "data/raw/companies.xlsx",     "header": 1, "ticker_col": "id",         "year_col": None},
    "profitandloss": {"path": "data/raw/profitandloss.xlsx", "header": 1, "ticker_col": "company_id",  "year_col": "year"},
    "balancesheet":  {"path": "data/raw/balancesheet.xlsx",  "header": 1, "ticker_col": "company_id",  "year_col": "year"},
    "cashflow":      {"path": "data/raw/cashflow.xlsx",      "header": 1, "ticker_col": "company_id",  "year_col": "year"},
    "analysis":      {"path": "data/raw/analysis.xlsx",      "header": 1, "ticker_col": "company_id",  "year_col": None},
    "documents":     {"path": "data/raw/documents.xlsx",     "header": 1, "ticker_col": "company_id",  "year_col": None, "dedup_subset": ["company_id", "Year"], "prefer_notna": "Annual_Report"},  # 'Year' col handled separately (int, not fiscal label)
    "prosandcons":   {"path": "data/raw/prosandcons.xlsx",   "header": 1, "ticker_col": "company_id",  "year_col": None},
}

SUPPORTING_FILES = {
    "sectors":          {"path": "data/supporting/sectors.xlsx",          "header": 0, "ticker_col": "company_id", "year_col": None},
    "stock_prices":     {"path": "data/supporting/stock_prices.xlsx",     "header": 0, "ticker_col": "company_id", "year_col": None},  # has 'date', not fiscal 'year'
    "market_cap":       {"path": "data/supporting/market_cap.xlsx",       "header": 0, "ticker_col": "company_id", "year_col": None},  # 'year' here is calendar int, not fiscal label
    "financial_ratios": {"path": "data/supporting/financial_ratios.xlsx", "header": 0, "ticker_col": "company_id", "year_col": "year"},  # FIX (Day 06): raw labels are fiscal ('Mar 2014' etc), same as P&L/BS/CF -- must be normalised to YYYY-MM and deduped, else joins to those tables silently fail and 119 dup (company_id, year) rows survive
    "peer_groups":      {"path": "data/supporting/peer_groups.xlsx",      "header": 0, "ticker_col": "company_id", "year_col": None},
}

ALL_FILES = {**CORE_FILES, **SUPPORTING_FILES}

PROJECT_ROOT = Path(__file__).resolve().parents[2] if (Path(__file__).resolve().parent.name == "etl") else Path.cwd()
OUTPUT_DIR = PROJECT_ROOT / "output"


def _resolve(path_str: str) -> Path:
    """Resolve a relative data path against the project root."""
    p = Path(path_str)
    if p.is_absolute():
        return p
    return PROJECT_ROOT / p


def load_excel_file(name: str, cfg: dict) -> tuple[pd.DataFrame, dict]:
    """
    Load a single Excel file, apply ticker/year normalisation, and
    return (clean_dataframe, stats_dict).

    stats_dict keys: table, rows_in, rows_out, rejected, runtime_s
    """
    start = time.time()
    path = _resolve(cfg["path"])
    rejected_rows: list[dict] = []

    if not path.exists():
        logger.error("File not found: %s", path)
        return pd.DataFrame(), {
            "table": name, "rows_in": 0, "rows_out": 0,
            "rejected": 0, "runtime_s": 0.0, "error": "FILE_NOT_FOUND",
        }

    df = pd.read_excel(path, header=cfg["header"])
    rows_in = len(df)

    # --- Ticker normalisation -------------------------------------------------
    ticker_col = cfg["ticker_col"]
    if ticker_col in df.columns:
        original = df[ticker_col]
        df[ticker_col] = original.map(normalize_ticker)
        bad_ticker_mask = df[ticker_col].isna()
        for idx in df.index[bad_ticker_mask]:
            rejected_rows.append({
                "table": name, "row_index": idx, "field": ticker_col,
                "raw_value": original.loc[idx], "issue": "INVALID_TICKER",
                "severity": "CRITICAL",
            })
        df = df[~bad_ticker_mask]
    else:
        logger.warning("%s: expected ticker column '%s' not found", name, ticker_col)

    # --- Year normalisation (only for tables with a fiscal-year label col) ----
    year_col = cfg["year_col"]
    if year_col and year_col in df.columns:
        original_year = df[year_col]
        normalised = original_year.map(normalize_year)
        bad_year_mask = normalised.isna()
        for idx in df.index[bad_year_mask]:
            rejected_rows.append({
                "table": name, "row_index": idx, "field": year_col,
                "raw_value": original_year.loc[idx], "issue": "UNPARSEABLE_YEAR",
                "severity": "CRITICAL",
            })
        df = df[~bad_year_mask].copy()
        df[year_col] = normalised[~bad_year_mask]

    # --- Deduplication on (company_id, year) where applicable -----------------
    if year_col and ticker_col in df.columns and year_col in df.columns:
        before = len(df)
        df = df.drop_duplicates(subset=[ticker_col, year_col], keep="last")
        dup_count = before - len(df)
        if dup_count:
            logger.info("%s: removed %d duplicate (%s, %s) rows", name, dup_count, ticker_col, year_col)

    # --- Explicit dedup_subset (for tables whose year field isn't a fiscal
    # label normalised above, e.g. documents.Year is a plain calendar int) ----
    dedup_subset = cfg.get("dedup_subset")
    if dedup_subset and set(dedup_subset).issubset(df.columns):
        before = len(df)
        prefer_col = cfg.get("prefer_notna")
        if prefer_col and prefer_col in df.columns:
            # keep the row with a non-null value in prefer_col when duplicates
            # differ only in that column (e.g. a null Annual_Report vs a real one)
            df = df.sort_values(by=prefer_col, key=lambda s: s.isna(), kind="stable")
        df = df.drop_duplicates(subset=dedup_subset, keep="first")
        dup_count = before - len(df)
        if dup_count:
            logger.info("%s: removed %d duplicate %s rows (dedup_subset)", name, dup_count, dedup_subset)

    rows_out = len(df)
    runtime_s = round(time.time() - start, 3)

    stats = {
        "table": name,
        "rows_in": rows_in,
        "rows_out": rows_out,
        "rejected": len(rejected_rows),
        "runtime_s": runtime_s,
        "error": "",
    }

    return df, {"stats": stats, "rejected_rows": rejected_rows}


def load_all() -> dict[str, pd.DataFrame]:
    """
    Load all 12 source files (7 core + 5 supplementary), apply
    normalisation, write load_audit.csv and parse_failures.csv to
    output/, and return a dict of {table_name: DataFrame}.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    tables: dict[str, pd.DataFrame] = {}
    audit_rows: list[dict] = []
    all_rejected: list[dict] = []

    for name, cfg in ALL_FILES.items():
        logger.info("Loading %s ...", name)
        df, result = load_excel_file(name, cfg)
        tables[name] = df

        if "stats" in result:
            audit_rows.append({**result["stats"], "timestamp": pd.Timestamp.now().isoformat()})
            all_rejected.extend(result["rejected_rows"])
        else:
            audit_rows.append({**result, "timestamp": pd.Timestamp.now().isoformat()})

        stats = result.get("stats", result)
        logger.info(
            "  %s: rows_in=%s rows_out=%s rejected=%s runtime=%ss",
            name, stats.get("rows_in"), stats.get("rows_out"),
            stats.get("rejected"), stats.get("runtime_s"),
        )

    # --- Write load_audit.csv --------------------------------------------------
    audit_path = OUTPUT_DIR / "load_audit.csv"
    with open(audit_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["table", "rows_in", "rows_out", "rejected", "runtime_s", "error", "timestamp"]
        )
        writer.writeheader()
        writer.writerows(audit_rows)
    logger.info("Wrote %s (%d rows)", audit_path, len(audit_rows))

    # --- Write parse_failures.csv (rejected rows) -------------------------------
    failures_path = OUTPUT_DIR / "parse_failures.csv"
    with open(failures_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["table", "row_index", "field", "raw_value", "issue", "severity"]
        )
        writer.writeheader()
        writer.writerows(all_rejected)
    logger.info("Wrote %s (%d rejected rows)", failures_path, len(all_rejected))

    total_critical = sum(1 for r in all_rejected if r["severity"] == "CRITICAL")
    logger.info("Load complete. %d tables loaded. %d total rejected rows (%d CRITICAL).",
                len(tables), len(all_rejected), total_critical)

    return tables


if __name__ == "__main__":
    load_all()