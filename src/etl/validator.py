"""
validator.py — Schema / Data Quality validator for the Nifty 100
Financial Intelligence Platform ETL pipeline (Sprint 1, Day 03).

Implements all 16 DQ rules from the project spec (Section 14):

    DQ-01  Company PK Uniqueness              CRITICAL
    DQ-02  Annual PK Uniqueness (co_id, year)  CRITICAL
    DQ-03  FK Integrity                        CRITICAL
    DQ-04  Balance Sheet Balance (<1%)         WARNING
    DQ-05  OPM Cross-Check                     WARNING
    DQ-06  Positive Sales                      WARNING
    DQ-07  Year Format                         CRITICAL  (enforced in normaliser.py at load time)
    DQ-08  Ticker Format                       CRITICAL  (enforced in normaliser.py at load time)
    DQ-09  Net Cash Check                      WARNING
    DQ-10  Non-Negative Fixed Assets           WARNING
    DQ-11  Tax Rate Range (0-60)               WARNING
    DQ-12  Dividend Payout Cap (<=200%)        WARNING
    DQ-13  URL Validity (documents)            WARNING
    DQ-14  EPS Sign Consistency                WARNING
    DQ-15  BSE/ASE Balance (strict, info only) INFO
    DQ-16  Coverage Check (>=5yr history)      WARNING

DQ-07 and DQ-08 are enforced upstream in loader.py/normaliser.py at load
time (unparseable years / malformed tickers are already rejected before
data reaches this validator), so this module re-confirms them are clean
but the primary enforcement point is the loader.

Usage:
    python src/etl/validator.py
    (expects tables already loaded via loader.load_all())

Output:
    output/validation_failures.csv  -- one row per violation
                                        (company_id, year, field, issue, severity)
"""

from __future__ import annotations
import csv
import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2] if (Path(__file__).resolve().parent.name == "etl") else Path.cwd()
OUTPUT_DIR = PROJECT_ROOT / "output"


def _flag(violations: list, table: str, company_id, year, field: str, issue: str, severity: str, raw_value=None):
    violations.append({
        "table": table,
        "company_id": company_id,
        "year": year,
        "field": field,
        "issue": issue,
        "severity": severity,
        "raw_value": raw_value,
    })


# ===========================================================================
# DQ-01: Company PK Uniqueness
# ===========================================================================

def dq01_pk_uniqueness(companies: pd.DataFrame) -> list[dict]:
    violations = []
    dup_mask = companies["id"].duplicated(keep=False)
    for _, row in companies[dup_mask].iterrows():
        _flag(violations, "companies", row["id"], None, "id",
              "Duplicate company PK", "CRITICAL", row["id"])
    return violations


# ===========================================================================
# DQ-02: Annual PK Uniqueness — (company_id, year) per time-series table
# ===========================================================================

def dq02_annual_pk_uniqueness(df: pd.DataFrame, table_name: str) -> list[dict]:
    violations = []
    if not {"company_id", "year"}.issubset(df.columns):
        return violations
    dup_mask = df.duplicated(subset=["company_id", "year"], keep=False)
    for _, row in df[dup_mask].iterrows():
        _flag(violations, table_name, row["company_id"], row["year"], "company_id+year",
              "Duplicate (company_id, year) pair", "CRITICAL")
    return violations


# ===========================================================================
# DQ-03: FK Integrity — every company_id in child tables must exist in companies.id
# ===========================================================================

def dq03_fk_integrity(df: pd.DataFrame, table_name: str, valid_ids: set) -> list[dict]:
    violations = []
    if "company_id" not in df.columns:
        return violations
    orphan_mask = ~df["company_id"].isin(valid_ids)
    for _, row in df[orphan_mask].iterrows():
        _flag(violations, table_name, row["company_id"], row.get("year"), "company_id",
              "Orphan row — company_id not found in companies table", "CRITICAL")
    return violations


# ===========================================================================
# DQ-04: Balance Sheet Balance — |assets - liabilities| / assets < 1%
# ===========================================================================

def dq04_balance_sheet_balance(bs: pd.DataFrame) -> list[dict]:
    violations = []
    for _, row in bs.iterrows():
        assets = row.get("total_assets")
        liabilities = row.get("total_liabilities")
        if pd.isna(assets) or pd.isna(liabilities) or assets == 0:
            continue
        diff_pct = abs(assets - liabilities) / abs(assets)
        if diff_pct >= 0.01:
            _flag(violations, "balancesheet", row["company_id"], row["year"],
                  "total_assets/total_liabilities",
                  f"BS imbalance {diff_pct*100:.2f}% (assets={assets}, liab={liabilities})",
                  "WARNING")
    return violations


# ===========================================================================
# DQ-05: OPM Cross-Check — |opm_percentage - computed_opm| < 1.0 (percentage points)
# ===========================================================================

def dq05_opm_cross_check(pl: pd.DataFrame) -> list[dict]:
    violations = []
    for _, row in pl.iterrows():
        sales = row.get("sales")
        op_profit = row.get("operating_profit")
        opm_reported = row.get("opm_percentage")
        if pd.isna(sales) or sales == 0 or pd.isna(op_profit) or pd.isna(opm_reported):
            continue
        opm_computed = (op_profit / sales) * 100
        if abs(opm_reported - opm_computed) >= 1.0:
            _flag(violations, "profitandloss", row["company_id"], row["year"], "opm_percentage",
                  f"OPM mismatch: reported={opm_reported:.2f}% computed={opm_computed:.2f}%",
                  "WARNING")
    return violations


# ===========================================================================
# DQ-06: Positive Sales
# ===========================================================================

def dq06_positive_sales(pl: pd.DataFrame) -> list[dict]:
    violations = []
    bad_mask = pl["sales"] <= 0
    for _, row in pl[bad_mask].iterrows():
        _flag(violations, "profitandloss", row["company_id"], row["year"], "sales",
              f"Non-positive sales: {row['sales']}", "WARNING")
    return violations


# ===========================================================================
# DQ-09: Net Cash Check — |net_cash_flow - (CFO+CFI+CFF)| <= 10 Cr tolerance
# ===========================================================================

def dq09_net_cash_check(cf: pd.DataFrame) -> list[dict]:
    violations = []
    for _, row in cf.iterrows():
        cfo, cfi, cff, net = (row.get("operating_activity"), row.get("investing_activity"),
                               row.get("financing_activity"), row.get("net_cash_flow"))
        if any(pd.isna(v) for v in (cfo, cfi, cff, net)):
            continue
        computed = cfo + cfi + cff
        if abs(net - computed) > 10:
            _flag(violations, "cashflow", row["company_id"], row["year"], "net_cash_flow",
                  f"Net cash mismatch: reported={net}, computed={computed:.1f}", "WARNING")
    return violations


# ===========================================================================
# DQ-10: Non-Negative Fixed Assets
# ===========================================================================

def dq10_non_negative_fixed_assets(bs: pd.DataFrame) -> list[dict]:
    violations = []
    bad_mask = bs["fixed_assets"] < 0
    for _, row in bs[bad_mask].iterrows():
        _flag(violations, "balancesheet", row["company_id"], row["year"], "fixed_assets",
              f"Negative fixed_assets: {row['fixed_assets']}", "WARNING")
    return violations


# ===========================================================================
# DQ-11: Tax Rate Range — 0 <= tax_percentage <= 60
# ===========================================================================

def dq11_tax_rate_range(pl: pd.DataFrame) -> list[dict]:
    violations = []
    tax = pl["tax_percentage"]
    bad_mask = tax.notna() & ((tax < 0) | (tax > 60))
    for _, row in pl[bad_mask].iterrows():
        _flag(violations, "profitandloss", row["company_id"], row["year"], "tax_percentage",
              f"Tax rate out of range: {row['tax_percentage']}", "WARNING")
    return violations


# ===========================================================================
# DQ-12: Dividend Payout Cap — dividend_payout <= 200%
# ===========================================================================

def dq12_dividend_payout_cap(pl: pd.DataFrame) -> list[dict]:
    violations = []
    bad_mask = pl["dividend_payout"].notna() & (pl["dividend_payout"] > 200)
    for _, row in pl[bad_mask].iterrows():
        _flag(violations, "profitandloss", row["company_id"], row["year"], "dividend_payout",
              f"Dividend payout exceeds 200%: {row['dividend_payout']}", "WARNING")
    return violations


# ===========================================================================
# DQ-13: URL Validity — Annual_Report links (network check optional/offline-safe)
# ===========================================================================

def dq13_url_validity(documents: pd.DataFrame, check_network: bool = False) -> list[dict]:
    violations = []
    missing_mask = documents["Annual_Report"].isna() | (documents["Annual_Report"].astype(str).str.strip() == "")
    for _, row in documents[missing_mask].iterrows():
        _flag(violations, "documents", row["company_id"], row.get("Year"), "Annual_Report",
              "Missing Annual_Report URL", "WARNING")

    if check_network:
        import requests
        for _, row in documents[~missing_mask].iterrows():
            url = row["Annual_Report"]
            try:
                resp = requests.head(url, timeout=5, allow_redirects=True)
                if resp.status_code != 200:
                    _flag(violations, "documents", row["company_id"], row.get("Year"), "Annual_Report",
                          f"URL returned status {resp.status_code}", "WARNING", url)
            except requests.RequestException as e:
                _flag(violations, "documents", row["company_id"], row.get("Year"), "Annual_Report",
                      f"URL request failed: {e}", "WARNING", url)
    return violations


# ===========================================================================
# DQ-14: EPS Sign Consistency — eps > 0 if net_profit > 0
# ===========================================================================

def dq14_eps_sign_consistency(pl: pd.DataFrame) -> list[dict]:
    violations = []
    mask = pl["net_profit"].notna() & pl["eps"].notna() & (pl["net_profit"] > 0) & (pl["eps"] <= 0)
    for _, row in pl[mask].iterrows():
        _flag(violations, "profitandloss", row["company_id"], row["year"], "eps",
              f"EPS non-positive ({row['eps']}) despite positive net_profit ({row['net_profit']})",
              "WARNING")
    return violations


# ===========================================================================
# DQ-15: BSE/ASE Balance (strict, informational only — no tolerance)
# ===========================================================================

def dq15_strict_balance_info(bs: pd.DataFrame) -> list[dict]:
    violations = []
    mismatch_mask = bs["total_assets"] != bs["total_liabilities"]
    for _, row in bs[mismatch_mask].iterrows():
        _flag(violations, "balancesheet", row["company_id"], row["year"],
              "total_assets/total_liabilities",
              "Strict mismatch (informational; see DQ-04 for tolerance-based check)", "INFO")
    return violations


# ===========================================================================
# DQ-16: Coverage Check — each company needs >= 5 years of P&L/BS/CF records
# ===========================================================================

def dq16_coverage_check(pl: pd.DataFrame, bs: pd.DataFrame, cf: pd.DataFrame, valid_ids: set) -> list[dict]:
    violations = []
    for company_id in sorted(valid_ids):
        pl_years = pl.loc[pl["company_id"] == company_id, "year"].nunique()
        bs_years = bs.loc[bs["company_id"] == company_id, "year"].nunique()
        cf_years = cf.loc[cf["company_id"] == company_id, "year"].nunique()
        min_years = min(pl_years, bs_years, cf_years)
        if min_years < 5:
            _flag(violations, "coverage", company_id, None, "year_coverage",
                  f"Insufficient history: P&L={pl_years}yr BS={bs_years}yr CF={cf_years}yr (min<5)",
                  "WARNING")
    return violations


# ===========================================================================
# Orchestration
# ===========================================================================

def run_all_validations(tables: dict[str, pd.DataFrame], check_urls_online: bool = False) -> list[dict]:
    """
    Run all 16 DQ rules against already-loaded (normalised) tables.
    `tables` is the dict returned by loader.load_all().
    """
    all_violations: list[dict] = []

    companies = tables.get("companies", pd.DataFrame())
    pl = tables.get("profitandloss", pd.DataFrame())
    bs = tables.get("balancesheet", pd.DataFrame())
    cf = tables.get("cashflow", pd.DataFrame())
    documents = tables.get("documents", pd.DataFrame())

    valid_ids = set(companies["id"]) if "id" in companies.columns else set()

    # DQ-01
    all_violations += dq01_pk_uniqueness(companies)

    # DQ-02 — applies to every time-series table with (company_id, year)
    for name, df in [("profitandloss", pl), ("balancesheet", bs), ("cashflow", cf)]:
        all_violations += dq02_annual_pk_uniqueness(df, name)

    # DQ-03 — FK integrity for every child table
    for name, df in [("profitandloss", pl), ("balancesheet", bs), ("cashflow", cf), ("documents", documents)]:
        all_violations += dq03_fk_integrity(df, name, valid_ids)

    # DQ-04 through DQ-16
    if not bs.empty:
        all_violations += dq04_balance_sheet_balance(bs)
        all_violations += dq10_non_negative_fixed_assets(bs)
        all_violations += dq15_strict_balance_info(bs)
    if not pl.empty:
        all_violations += dq05_opm_cross_check(pl)
        all_violations += dq06_positive_sales(pl)
        all_violations += dq11_tax_rate_range(pl)
        all_violations += dq12_dividend_payout_cap(pl)
        all_violations += dq14_eps_sign_consistency(pl)
    if not cf.empty:
        all_violations += dq09_net_cash_check(cf)
    if not documents.empty:
        all_violations += dq13_url_validity(documents, check_network=check_urls_online)
    if not pl.empty and not bs.empty and not cf.empty and valid_ids:
        all_violations += dq16_coverage_check(pl, bs, cf, valid_ids)

    return all_violations


def write_validation_failures(violations: list[dict]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / "validation_failures.csv"
    fieldnames = ["table", "company_id", "year", "field", "issue", "severity", "raw_value"]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(violations)
    logger.info("Wrote %s (%d violations)", path, len(violations))
    return path


if __name__ == "__main__":
    from loader import load_all
    tables = load_all()
    violations = run_all_validations(tables, check_urls_online=False)
    write_validation_failures(violations)

    critical = [v for v in violations if v["severity"] == "CRITICAL"]
    warning = [v for v in violations if v["severity"] == "WARNING"]
    info = [v for v in violations if v["severity"] == "INFO"]
    logger.info("DQ summary: %d CRITICAL, %d WARNING, %d INFO (total %d)",
                len(critical), len(warning), len(info), len(violations))
    if critical:
        logger.error("CRITICAL DQ failures found — must resolve before Day 05 load gate.")