r"""
src/nlp/parser.py — Analysis text parser for the Nifty 100 Financial
Intelligence Platform.

Sprint 5, Day 29 deliverable (Epic 09, Module 1).

The `analysis` table (loaded from analysis.xlsx by Sprint 1's ETL
pipeline) stores four free-text columns -- compounded_sales_growth,
compounded_profit_growth, stock_price_cagr, roe -- each holding
inconsistently-spaced strings like "10 Years: 21%" or "5 Years:
24%". This module extracts (period_years, value_pct) pairs from that
text with a single regex, logs anything that doesn't match, and
cross-checks the parsed 5-year figures against the Ratio Engine's own
computed CAGR (Sprint 2, Day 10) for divergence.

Regex: r'(\d+)\s*Years?:?\s*([\d.]+)%'  (per the Day 29 spec, verbatim)

This intentionally does NOT match entries like "TTM: 43%" or "Last
Year: 12%" -- those have no leading digit-Years token, so they fall
through to output/nlp_parse_failures.csv rather than being silently
dropped or force-matched with a fabricated period.

Note on output filename: the Day 29 spec names the failure log
output/parse_failures.csv, but that filename is already used by
Sprint 1's ETL loader (src/etl/loader.py) for row-level rejects during
the raw data load -- a different, earlier pipeline stage. Reusing it
here would silently overwrite Sprint 1's audit trail every time this
module runs. This module writes to output/nlp_parse_failures.csv
instead; documented here rather than left as a silent collision.

Usage:
    python src/nlp/parser.py
"""

from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path
from typing import Optional

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2] if (Path(__file__).resolve().parent.name == "nlp") else Path.cwd()
DB_PATH = PROJECT_ROOT / "data" / "nifty100.db"
OUTPUT_DIR = PROJECT_ROOT / "output"

PATTERN = re.compile(r"(\d+)\s*Years?:?\s*([\d.]+)%")

TARGET_FIELDS = ["compounded_sales_growth", "compounded_profit_growth", "stock_price_cagr", "roe"]

# Cross-validation (Day 29): only compounded_sales_growth and
# compounded_profit_growth at period_years == 5 map onto a Ratio
# Engine column that actually exists (revenue_cagr_5yr / pat_cagr_5yr
# in financial_ratios). stock_price_cagr has no Ratio Engine
# equivalent (the platform doesn't compute a price CAGR), and roe's
# "N Years: X%" figure is a trailing multi-year average rather than a
# single-year snapshot, so it isn't directly comparable to
# financial_ratios.return_on_equity_pct either. Both are still parsed
# and exported, just not cross-validated.
CROSS_VALIDATE_MAP = {
    ("compounded_sales_growth", 5): "revenue_cagr_5yr",
    ("compounded_profit_growth", 5): "pat_cagr_5yr",
}
DIVERGENCE_THRESHOLD_PCT = 5.0


def parse_field_value(text) -> Optional[tuple[int, float]]:
    """Extract (period_years, value_pct) from one text cell, or None if
    the text doesn't match the Day 29 pattern (e.g. 'TTM: 43%',
    'Last Year: 12%', or missing/NaN)."""
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return None
    m = PATTERN.search(str(text))
    if not m:
        return None
    return int(m.group(1)), float(m.group(2))


def parse_analysis_table(analysis_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Parse every (company, field) cell in `analysis_df` for the 4 target
    fields. Returns (parsed_df, failures_df):
        parsed_df   -> company_id, metric_type, period_years, value_pct
        failures_df -> company_id, metric_type, raw_text
    """
    parsed_rows = []
    failure_rows = []

    for _, row in analysis_df.iterrows():
        company_id = row["company_id"]
        for field in TARGET_FIELDS:
            raw_text = row.get(field)
            if raw_text is None or (isinstance(raw_text, float) and pd.isna(raw_text)):
                continue  # genuinely empty cell, not a parse failure
            result = parse_field_value(raw_text)
            if result is None:
                failure_rows.append({"company_id": company_id, "metric_type": field, "raw_text": raw_text})
            else:
                period_years, value_pct = result
                parsed_rows.append({
                    "company_id": company_id, "metric_type": field,
                    "period_years": period_years, "value_pct": value_pct,
                })

    parsed_df = pd.DataFrame(parsed_rows, columns=["company_id", "metric_type", "period_years", "value_pct"])
    failures_df = pd.DataFrame(failure_rows, columns=["company_id", "metric_type", "raw_text"])
    return parsed_df, failures_df


def cross_validate(parsed_df: pd.DataFrame, financial_ratios_df: pd.DataFrame) -> pd.DataFrame:
    """
    For every parsed row whose (metric_type, period_years) has a Ratio
    Engine equivalent (CROSS_VALIDATE_MAP), compare against that
    company's *latest* value for the matching financial_ratios column
    and flag rows where the absolute difference exceeds
    DIVERGENCE_THRESHOLD_PCT (percentage points, not relative %).
    """
    fr = financial_ratios_df.copy()
    for col in set(CROSS_VALIDATE_MAP.values()):
        fr[col] = pd.to_numeric(fr[col], errors="coerce")
    latest_fr = fr.sort_values("year").groupby("company_id").tail(1).set_index("company_id")

    rows = []
    for _, row in parsed_df.iterrows():
        key = (row["metric_type"], row["period_years"])
        ratio_col = CROSS_VALIDATE_MAP.get(key)
        if ratio_col is None or row["company_id"] not in latest_fr.index:
            continue
        computed = latest_fr.loc[row["company_id"], ratio_col]
        if pd.isna(computed):
            continue
        divergence = abs(row["value_pct"] - computed)
        rows.append({
            "company_id": row["company_id"], "metric_type": row["metric_type"],
            "period_years": row["period_years"], "parsed_value_pct": row["value_pct"],
            "computed_value_pct": round(float(computed), 2), "divergence_pp": round(divergence, 2),
            "flagged": divergence > DIVERGENCE_THRESHOLD_PCT,
        })
    return pd.DataFrame(rows)


def run_parser() -> dict:
    conn = sqlite3.connect(DB_PATH)
    analysis_df = pd.read_sql("SELECT * FROM analysis", conn)
    financial_ratios_df = pd.read_sql("SELECT company_id, year, revenue_cagr_5yr, pat_cagr_5yr FROM financial_ratios", conn)
    conn.close()

    parsed_df, failures_df = parse_analysis_table(analysis_df)
    validation_df = cross_validate(parsed_df, financial_ratios_df)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    parsed_path = OUTPUT_DIR / "analysis_parsed.csv"
    failures_path = OUTPUT_DIR / "nlp_parse_failures.csv"
    validation_path = OUTPUT_DIR / "analysis_cross_validation.csv"

    parsed_df.to_csv(parsed_path, index=False)
    failures_df.to_csv(failures_path, index=False)
    validation_df.to_csv(validation_path, index=False)

    logger.info("Parsed %d rows, %d failures, %d cross-validated (%d flagged)",
                len(parsed_df), len(failures_df), len(validation_df),
                int(validation_df["flagged"].sum()) if not validation_df.empty else 0)

    return {
        "parsed_rows": len(parsed_df), "failure_rows": len(failures_df),
        "validation_rows": len(validation_df),
        "flagged_rows": int(validation_df["flagged"].sum()) if not validation_df.empty else 0,
        "parsed_path": str(parsed_path), "failures_path": str(failures_path),
        "validation_path": str(validation_path),
    }


if __name__ == "__main__":
    result = run_parser()
    print()
    print("=== ANALYSIS PARSER SUMMARY ===")
    print(f"Parsed rows:       {result['parsed_rows']}")
    print(f"Parse failures:    {result['failure_rows']}")
    print(f"Cross-validated:   {result['validation_rows']} ({result['flagged_rows']} flagged >5pp divergence)")
    print(f"Output: {result['parsed_path']}")
    print(f"Output: {result['failures_path']}")
    print(f"Output: {result['validation_path']}")
