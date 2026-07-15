"""
db_loader.py — Builds nifty100.db (SQLite) from the 12 normalised source
tables produced by loader.load_all().

Day 04-05 deliverable, Sprint 1, Module 1 (features 1.4-1.6).

Responsibilities:
    - Create db/schema.sql structure in data/nifty100.db
    - Enforce FK integrity per DQ-03: rows whose company_id has no match
      in `companies` are rejected (not inserted) and logged — this is the
      spec's own prescribed action for a CRITICAL DQ-03 violation.
    - Column renaming to match the schema (e.g. documents.Year -> report_year,
      documents.Annual_Report -> annual_report_url)
    - Verify PRAGMA foreign_key_check returns 0 rows after load (AC-03)
    - Write/refresh output/load_audit.csv with final per-table row counts

Usage:
    python src/etl/db_loader.py
"""

from __future__ import annotations
import csv
import logging
import sqlite3
from pathlib import Path

import pandas as pd

from loader import load_all

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2] if (Path(__file__).resolve().parent.name == "etl") else Path.cwd()
DB_PATH = PROJECT_ROOT / "data" / "nifty100.db"
SCHEMA_PATH = PROJECT_ROOT / "db" / "schema.sql"
OUTPUT_DIR = PROJECT_ROOT / "output"

# Map loader table name -> (sqlite table name, column rename dict, insert columns)
TABLE_MAP = {
    "companies": {
        "sqlite_table": "companies",
        "rename": {},
        "columns": ["id", "company_logo", "company_name", "chart_link", "about_company",
                    "website", "nse_profile", "bse_profile", "face_value", "book_value",
                    "roce_percentage", "roe_percentage"],
    },
    "profitandloss": {
        "sqlite_table": "profitandloss",
        "rename": {},
        "columns": ["company_id", "year", "sales", "expenses", "operating_profit",
                    "opm_percentage", "other_income", "interest", "depreciation",
                    "profit_before_tax", "tax_percentage", "net_profit", "eps", "dividend_payout"],
    },
    "balancesheet": {
        "sqlite_table": "balancesheet",
        "rename": {},
        "columns": ["company_id", "year", "equity_capital", "reserves", "borrowings",
                    "other_liabilities", "total_liabilities", "fixed_assets", "cwip",
                    "investments", "other_asset", "total_assets"],
    },
    "cashflow": {
        "sqlite_table": "cashflow",
        "rename": {},
        "columns": ["company_id", "year", "operating_activity", "investing_activity",
                    "financing_activity", "net_cash_flow"],
    },
    "analysis": {
        "sqlite_table": "analysis",
        "rename": {},
        "columns": ["company_id", "compounded_sales_growth", "compounded_profit_growth",
                    "stock_price_cagr", "roe"],
    },
    "documents": {
        "sqlite_table": "documents",
        "rename": {"Year": "report_year", "Annual_Report": "annual_report_url"},
        "columns": ["company_id", "report_year", "annual_report_url"],
    },
    "prosandcons": {
        "sqlite_table": "prosandcons",
        "rename": {},
        "columns": ["company_id", "pros", "cons"],
    },
    "sectors": {
        "sqlite_table": "sectors",
        "rename": {},
        "columns": ["company_id", "broad_sector", "sub_sector", "index_weight_pct", "market_cap_category"],
    },
    "stock_prices": {
        "sqlite_table": "stock_prices",
        "rename": {},
        "columns": ["company_id", "date", "open_price", "high_price", "low_price",
                    "close_price", "volume", "adjusted_close"],
    },
    "market_cap": {
        "sqlite_table": "market_cap",
        "rename": {},
        "columns": ["company_id", "year", "market_cap_crore", "enterprise_value_crore",
                    "pe_ratio", "pb_ratio", "ev_ebitda", "dividend_yield_pct"],
    },
    "financial_ratios": {
        "sqlite_table": "financial_ratios",
        "rename": {},
        "columns": ["company_id", "year", "net_profit_margin_pct", "operating_profit_margin_pct",
                    "return_on_equity_pct", "debt_to_equity", "interest_coverage", "asset_turnover",
                    "free_cash_flow_cr", "capex_cr", "earnings_per_share", "book_value_per_share",
                    "dividend_payout_ratio_pct", "total_debt_cr", "cash_from_operations_cr"],
    },
    "peer_groups": {
        "sqlite_table": "peer_groups",
        "rename": {},
        "columns": ["peer_group_name", "company_id", "is_benchmark"],
    },
}

# Load order matters: companies MUST load first (FK parent for everything else)
LOAD_ORDER = ["companies", "profitandloss", "balancesheet", "cashflow", "analysis",
              "documents", "prosandcons", "sectors", "stock_prices", "market_cap",
              "financial_ratios", "peer_groups"]


def build_schema(conn: sqlite3.Connection):
    sql = SCHEMA_PATH.read_text()
    conn.executescript(sql)
    logger.info("Schema created: 12 tables + indexes.")


def insert_table(conn: sqlite3.Connection, table_name: str, df: pd.DataFrame,
                  valid_company_ids: set) -> dict:
    """
    Insert a normalised DataFrame into its SQLite table, enforcing FK
    integrity per DQ-03: rows with company_id not in valid_company_ids
    are rejected and logged (not inserted).
    """
    cfg = TABLE_MAP[table_name]
    sqlite_table = cfg["sqlite_table"]

    if df.empty:
        return {"table": sqlite_table, "rows_in": 0, "rows_out": 0, "fk_rejected": 0}

    df = df.rename(columns=cfg["rename"]).copy()

    rows_in = len(df)
    fk_rejected_rows = []

    # FK enforcement (skip for the companies table itself, it's the parent)
    if table_name != "companies" and "company_id" in df.columns:
        orphan_mask = ~df["company_id"].isin(valid_company_ids)
        fk_rejected_rows = df.loc[orphan_mask, "company_id"].tolist()
        df = df[~orphan_mask]

    # Keep only columns that exist in the schema, in the right order
    available_cols = [c for c in cfg["columns"] if c in df.columns]
    df_to_insert = df[available_cols]

    df_to_insert.to_sql(sqlite_table, conn, if_exists="append", index=False)

    rows_out = len(df_to_insert)
    return {
        "table": sqlite_table,
        "rows_in": rows_in,
        "rows_out": rows_out,
        "fk_rejected": len(fk_rejected_rows),
        "fk_rejected_sample": sorted(set(fk_rejected_rows))[:10],
    }


def build_database() -> dict:
    """
    Full Day 04-05 pipeline: load all 12 files (via loader.load_all,
    which already applies ticker/year normalisation + dedup), create
    the SQLite schema, insert every table with FK enforcement, and
    verify PRAGMA foreign_key_check returns 0 rows.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Fresh build every run (idempotent, per spec's make load semantics)
    if DB_PATH.exists():
        DB_PATH.unlink()
        logger.info("Removed existing %s for fresh rebuild.", DB_PATH)

    logger.info("=== Step 1: Load and normalise all 12 source files ===")
    tables = load_all()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")

    logger.info("=== Step 2: Build schema ===")
    build_schema(conn)

    logger.info("=== Step 3: Insert data (FK-enforced) ===")
    valid_company_ids = set(tables["companies"]["id"]) if "companies" in tables else set()

    insert_stats = []
    for table_name in LOAD_ORDER:
        df = tables.get(table_name, pd.DataFrame())
        stats = insert_table(conn, table_name, df, valid_company_ids)
        insert_stats.append(stats)
        logger.info(
            "  %-18s rows_in=%-6d rows_out=%-6d fk_rejected=%d",
            stats["table"], stats["rows_in"], stats["rows_out"], stats["fk_rejected"],
        )
        if stats["fk_rejected"]:
            logger.warning("    sample rejected company_ids: %s", stats["fk_rejected_sample"])

    conn.commit()

    logger.info("=== Step 4: Verify FK integrity ===")
    fk_check = conn.execute("PRAGMA foreign_key_check;").fetchall()
    if fk_check:
        logger.error("PRAGMA foreign_key_check found %d violations (should be 0): %s",
                      len(fk_check), fk_check[:5])
    else:
        logger.info("PRAGMA foreign_key_check: 0 rows. FK integrity CLEAN.")

    logger.info("=== Step 5: Row count summary ===")
    row_counts = {}
    for table_name in LOAD_ORDER:
        sqlite_table = TABLE_MAP[table_name]["sqlite_table"]
        count = conn.execute(f"SELECT COUNT(*) FROM {sqlite_table}").fetchone()[0]
        row_counts[sqlite_table] = count
        logger.info("  %-18s %d rows", sqlite_table, count)

    conn.close()

    # Write updated load_audit.csv reflecting the DB build
    audit_path = OUTPUT_DIR / "load_audit.csv"
    with open(audit_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["table", "rows_in", "rows_out", "fk_rejected", "final_db_count"])
        writer.writeheader()
        for stats in insert_stats:
            writer.writerow({
                "table": stats["table"],
                "rows_in": stats["rows_in"],
                "rows_out": stats["rows_out"],
                "fk_rejected": stats["fk_rejected"],
                "final_db_count": row_counts.get(stats["table"], 0),
            })
    logger.info("Wrote %s", audit_path)

    return {
        "db_path": str(DB_PATH),
        "row_counts": row_counts,
        "fk_check_violations": len(fk_check),
        "insert_stats": insert_stats,
    }


if __name__ == "__main__":
    result = build_database()
    print()
    print("=== BUILD SUMMARY ===")
    print(f"Database: {result['db_path']}")
    print(f"FK check violations: {result['fk_check_violations']}")
    print(f"companies table row count: {result['row_counts'].get('companies')}")