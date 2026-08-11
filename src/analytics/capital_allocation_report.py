"""
src/analytics/capital_allocation_report.py — Capital Allocation Report.

Sprint 5, Day 32 deliverable (Epic 07, Module 1).

Three things, all built on top of Sprint 2's output/capital_allocation.csv
(one row per company-year, from src/analytics/ratios.py's per-year
capital_allocation_pattern classification -- see
src/analytics/cashflow_kpis.py:classify_capital_allocation):

    1. Verify completeness: every one of the 92 companies has at least
       one classified year (a company can legitimately have fewer than
       92 x N rows if some years lack CFO/CFI/CFF data, but zero rows
       for a company would be a real gap).
    2. A distribution summary: how many companies are in each of the 8
       (well, 8 spec'd + 2 documented extensions -- see
       cashflow_kpis.py's _PATTERN_LABELS) patterns in the latest year.
    3. output/pattern_changes.csv: every company whose pattern changed
       from one fiscal year to the next, anywhere in its history (not
       just the latest transition), so an analyst can see e.g. "moved
       from Reinvestor to Distress Signal" and when.

Usage:
    python src/analytics/capital_allocation_report.py
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2] if (Path(__file__).resolve().parent.name == "analytics") else Path.cwd()
OUTPUT_DIR = PROJECT_ROOT / "output"
CAPITAL_ALLOCATION_CSV = OUTPUT_DIR / "capital_allocation.csv"


def verify_completeness(df: pd.DataFrame, expected_company_ids: set) -> dict:
    covered = set(df["company_id"].unique())
    missing = expected_company_ids - covered
    return {
        "expected_companies": len(expected_company_ids),
        "covered_companies": len(covered),
        "missing_companies": sorted(missing),
        "total_rows": len(df),
        "rows_with_null_pattern": int(df["pattern_label"].isna().sum()),
    }


def distribution_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Count of companies in each pattern for the latest year each
    company has a *classified* row. Many companies carry a trailing
    interim fiscal-year row (e.g. '2024-09') where CFO/CFI/CFF -- and
    therefore pattern_label -- are null; this selects the latest row
    with a non-null pattern_label per company instead of the literal
    max(year), the same fix applied throughout this pipeline (see
    src/screener/engine.py's _latest_year_rows for the original
    discovery of this data characteristic)."""
    classified = df.dropna(subset=["pattern_label"]).sort_values("year")
    latest = classified.groupby("company_id").tail(1)
    counts = latest["pattern_label"].value_counts().reset_index()
    counts.columns = ["pattern_label", "company_count"]
    return counts.sort_values("company_count", ascending=False).reset_index(drop=True)


def find_pattern_changes(df: pd.DataFrame) -> pd.DataFrame:
    """Every year-over-year pattern transition for every company,
    across their full history (e.g. a company that was 'Reinvestor' in
    2021, 2022, 2023 then 'Distress Signal' in 2024 produces one row:
    2023->2024, Reinvestor -> Distress Signal)."""
    rows = []
    for company_id, grp in df.sort_values("year").groupby("company_id"):
        grp = grp.dropna(subset=["pattern_label"])
        labels = grp["pattern_label"].tolist()
        years = grp["year"].tolist()
        for i in range(1, len(labels)):
            if labels[i] != labels[i - 1]:
                rows.append({
                    "company_id": company_id,
                    "from_year": years[i - 1], "to_year": years[i],
                    "from_pattern": labels[i - 1], "to_pattern": labels[i],
                })
    return pd.DataFrame(rows, columns=["company_id", "from_year", "to_year", "from_pattern", "to_pattern"])


def run_capital_allocation_report(companies_df: "pd.DataFrame | None" = None) -> dict:
    if not CAPITAL_ALLOCATION_CSV.exists():
        raise FileNotFoundError(
            f"{CAPITAL_ALLOCATION_CSV} not found -- run src/analytics/ratios.py first (Sprint 2, Day 11)."
        )
    df = pd.read_csv(CAPITAL_ALLOCATION_CSV)

    if companies_df is None:
        import sqlite3
        conn = sqlite3.connect(PROJECT_ROOT / "data" / "nifty100.db")
        expected_ids = set(pd.read_sql("SELECT id FROM companies", conn)["id"])
        conn.close()
    else:
        expected_ids = set(companies_df["id"])

    completeness = verify_completeness(df, expected_ids)
    distribution = distribution_summary(df)
    changes = find_pattern_changes(df)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    changes_path = OUTPUT_DIR / "pattern_changes.csv"
    changes.to_csv(changes_path, index=False)

    logger.info("Completeness: %d/%d companies covered (%d missing), %d total rows",
                completeness["covered_companies"], completeness["expected_companies"],
                len(completeness["missing_companies"]), completeness["total_rows"])
    logger.info("Wrote %s (%d pattern transitions across %d companies)",
                changes_path, len(changes), changes["company_id"].nunique() if not changes.empty else 0)

    return {
        "completeness": completeness,
        "distribution": distribution,
        "changes": changes,
        "changes_path": str(changes_path),
    }


if __name__ == "__main__":
    result = run_capital_allocation_report()
    print()
    print("=== CAPITAL ALLOCATION REPORT SUMMARY ===")
    c = result["completeness"]
    print(f"Coverage: {c['covered_companies']}/{c['expected_companies']} companies, {c['total_rows']} rows")
    if c["missing_companies"]:
        print(f"Missing: {c['missing_companies']}")
    print()
    print("Latest-year pattern distribution:")
    print(result["distribution"].to_string(index=False))
    print()
    print(f"Pattern changes: {len(result['changes'])} transitions -> {result['changes_path']}")
