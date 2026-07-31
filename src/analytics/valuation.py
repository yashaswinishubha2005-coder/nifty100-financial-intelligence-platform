"""
src/analytics/valuation.py — Valuation module for the Nifty 100
Financial Intelligence Platform.

Sprint 4, Day 26 deliverable (Epic 06, Module 1).

Source data: data/supporting/market_cap.xlsx, ETL-normalised into the
`market_cap` SQLite table by src/etl/loader.py / db_loader.py (ticker
normalisation, year is a plain calendar int 2019-2024 -- see that
table's schema comment in db/schema.sql). Free cash flow comes from
the `financial_ratios` table (Sprint 2, Day 11's free_cash_flow_cr).

Responsibilities:
    - FCF yield %  = free_cash_flow_cr / market_cap_crore x 100, for
      every company's latest available (year, FCF) pair.
    - Sector median P/E, computed per broad_sector, latest calendar
      year only.
    - Overvaluation flag, comparing each company's latest P/E against
      its own sector's median P/E:
          P/E > sector_median x 1.5  -> 'Caution'   (rich vs. peers)
          P/E < sector_median x 0.7  -> 'Discount'  (cheap vs. peers)
          otherwise                   -> 'Fair'
      Companies with no usable P/E (missing, zero, or negative --
      i.e. the company reported a loss) get flag=None ('N/A' in the
      exported Excel) rather than being forced into one of the three
      buckets on meaningless data.
    - output/valuation_summary.xlsx -- all 92 companies.
    - output/valuation_flags.csv -- Caution/Discount companies only.
    - `valuation` SQLite table (db/schema.sql) -- read by the
      dashboard's get_valuation() (src/dashboard/utils/db.py).

Usage:
    python src/analytics/valuation.py
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2] if (Path(__file__).resolve().parent.name == "analytics") else Path.cwd()
DB_PATH = PROJECT_ROOT / "data" / "nifty100.db"
OUTPUT_DIR = PROJECT_ROOT / "output"

CAUTION_MULTIPLIER = 1.5
DISCOUNT_MULTIPLIER = 0.7


def _latest_complete_rows(df: pd.DataFrame, require_col: str) -> pd.DataFrame:
    """Latest `year` row per company_id, preferring rows with a non-null
    `require_col` (skips any trailing incomplete/interim rows)."""
    if df.empty:
        return df
    sorted_df = df.sort_values("year")
    complete = sorted_df[sorted_df[require_col].notna()]
    idx = complete.groupby("company_id").tail(1).index
    missing = set(df["company_id"]) - set(df.loc[idx, "company_id"])
    if missing:
        fallback = sorted_df[sorted_df["company_id"].isin(missing)].groupby("company_id").tail(1).index
        idx = idx.append(fallback)
    return df.loc[idx].reset_index(drop=True)


def fcf_yield_pct(free_cash_flow_cr: Optional[float], market_cap_crore: Optional[float]) -> Optional[float]:
    """FCF Yield % = FCF / Market Cap x 100. None if market cap is
    missing or non-positive (division not meaningful)."""
    if free_cash_flow_cr is None or market_cap_crore is None or market_cap_crore <= 0:
        return None
    if pd.isna(free_cash_flow_cr) or pd.isna(market_cap_crore):
        return None
    return free_cash_flow_cr / market_cap_crore * 100


def classify_valuation(pe_ratio: Optional[float], sector_median_pe: Optional[float]) -> Optional[str]:
    """Caution / Discount / Fair, per the Day 26 thresholds. None
    (-> 'N/A' on export) if either input is missing or the company's
    own P/E is non-positive (a negative P/E means a reported loss, not
    a genuinely cheap valuation)."""
    if pe_ratio is None or sector_median_pe is None:
        return None
    if pd.isna(pe_ratio) or pd.isna(sector_median_pe) or pe_ratio <= 0 or sector_median_pe <= 0:
        return None
    if pe_ratio > sector_median_pe * CAUTION_MULTIPLIER:
        return "Caution"
    if pe_ratio < sector_median_pe * DISCOUNT_MULTIPLIER:
        return "Discount"
    return "Fair"


def build_valuation_table(conn: sqlite3.Connection) -> pd.DataFrame:
    """
    Build the full valuation table: one row per company, using each
    company's latest available market_cap year and latest available
    financial_ratios year (independently -- the two tables don't
    necessarily share the same latest year for every company).
    """
    companies = pd.read_sql("SELECT id AS company_id, company_name FROM companies", conn)
    sectors = pd.read_sql("SELECT company_id, broad_sector FROM sectors", conn)

    mc_all = pd.read_sql("SELECT * FROM market_cap", conn)
    mc_all["year"] = mc_all["year"].astype(str)  # sortable string form of the calendar int
    mc_latest = _latest_complete_rows(mc_all, "pe_ratio")

    fr_all = pd.read_sql("SELECT company_id, year, free_cash_flow_cr FROM financial_ratios", conn)
    fr_all["free_cash_flow_cr"] = pd.to_numeric(fr_all["free_cash_flow_cr"], errors="coerce")
    fr_latest = _latest_complete_rows(fr_all, "free_cash_flow_cr")

    df = (
        companies
        .merge(sectors, on="company_id", how="left")
        .merge(mc_latest[["company_id", "year", "pe_ratio", "pb_ratio", "ev_ebitda", "market_cap_crore"]],
               on="company_id", how="left")
        .merge(fr_latest[["company_id", "free_cash_flow_cr"]], on="company_id", how="left")
    )
    df = df.rename(columns={"year": "valuation_year"})
    df["valuation_year"] = pd.to_numeric(df["valuation_year"], errors="coerce")

    # FCF yield
    df["fcf_yield_pct"] = df.apply(
        lambda r: fcf_yield_pct(r["free_cash_flow_cr"], r["market_cap_crore"]), axis=1
    )

    # Sector median P/E, computed within the *latest calendar year present
    # in market_cap* (2024 for almost every company; a handful of
    # companies' own "latest" row may be an earlier year if 2024 data is
    # missing for them specifically, but the sector benchmark itself is
    # anchored to the dataset's overall latest year for comparability).
    overall_latest_year = mc_latest["year"].astype(float).max()
    sector_pool = mc_latest[mc_latest["year"].astype(float) == overall_latest_year] \
        .merge(sectors, on="company_id", how="left")
    sector_median = sector_pool.groupby("broad_sector")["pe_ratio"].median()
    df["sector_median_pe"] = df["broad_sector"].map(sector_median)

    df["pe_vs_sector_median_pct"] = np.where(
        df["sector_median_pe"].notna() & (df["sector_median_pe"] != 0) & df["pe_ratio"].notna(),
        (df["pe_ratio"] - df["sector_median_pe"]) / df["sector_median_pe"] * 100,
        np.nan,
    )

    # 5-year median P/E per company (up to the last 5 calendar years of market_cap history)
    five_yr_median = (
        mc_all.sort_values("year")
        .groupby("company_id")
        .apply(lambda g: g.tail(5)["pe_ratio"].median(skipna=True))
    )
    df["5yr_median_PE"] = df["company_id"].map(five_yr_median)

    df["flag"] = df.apply(lambda r: classify_valuation(r["pe_ratio"], r["sector_median_pe"]), axis=1)

    return df


def write_valuation_table(conn: sqlite3.Connection, df: pd.DataFrame):
    conn.execute("DELETE FROM valuation")
    insert_df = df.rename(columns={"valuation_year": "year"})[
        ["company_id", "year", "pe_ratio", "pb_ratio", "ev_ebitda", "fcf_yield_pct",
         "sector_median_pe", "pe_vs_sector_median_pct", "flag"]
    ].dropna(subset=["year"])
    insert_df["year"] = insert_df["year"].astype(int)
    insert_df.to_sql("valuation", conn, if_exists="append", index=False)
    conn.commit()
    logger.info("Wrote %d rows to valuation table", len(insert_df))


def export_valuation_summary(df: pd.DataFrame, out_path: Path = OUTPUT_DIR / "valuation_summary.xlsx") -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    export_df = df.rename(columns={
        "broad_sector": "sector", "pe_ratio": "P/E", "pb_ratio": "P/B", "ev_ebitda": "EV/EBITDA",
    })[[
        "company_id", "company_name", "sector", "P/E", "P/B", "EV/EBITDA",
        "fcf_yield_pct", "5yr_median_PE", "pe_vs_sector_median_pct", "flag",
    ]].rename(columns={"fcf_yield_pct": "FCF_yield_pct", "pe_vs_sector_median_pct": "PE_vs_sector_median_pct"})
    export_df["flag"] = export_df["flag"].fillna("N/A")
    export_df.to_excel(out_path, index=False, sheet_name="Valuation Summary")
    logger.info("Wrote %s (%d rows)", out_path, len(export_df))
    return out_path


def export_valuation_flags(df: pd.DataFrame, out_path: Path = OUTPUT_DIR / "valuation_flags.csv") -> Path:
    flagged = df[df["flag"].isin(["Caution", "Discount"])].copy()
    export_df = flagged.rename(columns={
        "broad_sector": "sector", "pe_ratio": "P/E", "pb_ratio": "P/B", "ev_ebitda": "EV/EBITDA",
    })[[
        "company_id", "company_name", "sector", "P/E", "sector_median_pe",
        "pe_vs_sector_median_pct", "fcf_yield_pct", "flag",
    ]].rename(columns={
        "sector_median_pe": "sector_median_PE",
        "pe_vs_sector_median_pct": "PE_vs_sector_median_pct",
        "fcf_yield_pct": "FCF_yield_pct",
    }).sort_values("PE_vs_sector_median_pct", ascending=False)
    export_df.to_csv(out_path, index=False)
    logger.info("Wrote %s (%d flagged companies)", out_path, len(export_df))
    return out_path


def run_valuation() -> dict:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")

    df = build_valuation_table(conn)
    write_valuation_table(conn, df)
    conn.close()

    summary_path = export_valuation_summary(df)
    flags_path = export_valuation_flags(df)

    return {
        "total_companies": len(df),
        "flag_counts": df["flag"].fillna("N/A").value_counts().to_dict(),
        "summary_path": str(summary_path),
        "flags_path": str(flags_path),
    }


if __name__ == "__main__":
    result = run_valuation()
    print()
    print("=== VALUATION MODULE SUMMARY ===")
    print(f"Total companies: {result['total_companies']}")
    for flag, count in result["flag_counts"].items():
        print(f"  {flag:10s} {count:3d} companies")
    print(f"Summary: {result['summary_path']}")
    print(f"Flags:   {result['flags_path']}")
