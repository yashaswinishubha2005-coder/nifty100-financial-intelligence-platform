"""
tests/etl/test_validator.py — Sprint 3, Day 21 deliverable: unit tests
for the 14 DQ rule functions in src/etl/validator.py (DQ-01, DQ-02,
DQ-03, DQ-04, DQ-05, DQ-06, DQ-09, DQ-10, DQ-11, DQ-12, DQ-13, DQ-14,
DQ-15, DQ-16 -- DQ-07/DQ-08 are enforced upstream in normaliser.py and
are covered by tests/etl/test_normaliser.py instead).

Each test builds a small synthetic DataFrame with one clean row and one
row that should trip the rule, then asserts the violation is (or isn't)
flagged with the expected severity.

Run with:
    pytest tests/etl/test_validator.py -v
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "etl"))

from validator import (
    dq01_pk_uniqueness, dq02_annual_pk_uniqueness, dq03_fk_integrity,
    dq04_balance_sheet_balance, dq05_opm_cross_check, dq06_positive_sales,
    dq09_net_cash_check, dq10_non_negative_fixed_assets, dq11_tax_rate_range,
    dq12_dividend_payout_cap, dq13_url_validity, dq14_eps_sign_consistency,
    dq15_strict_balance_info, dq16_coverage_check, run_all_validations,
)


# ===========================================================================
# DQ-01: Company PK Uniqueness (CRITICAL)
# ===========================================================================

class TestDQ01PkUniqueness:
    def test_no_violation_on_unique_ids(self):
        companies = pd.DataFrame({"id": ["TCS", "INFY"]})
        assert dq01_pk_uniqueness(companies) == []

    def test_flags_duplicate_id_as_critical(self):
        companies = pd.DataFrame({"id": ["TCS", "TCS"]})
        violations = dq01_pk_uniqueness(companies)
        assert len(violations) == 2
        assert all(v["severity"] == "CRITICAL" for v in violations)


# ===========================================================================
# DQ-02: Annual PK Uniqueness (company_id, year) (CRITICAL)
# ===========================================================================

class TestDQ02AnnualPkUniqueness:
    def test_no_violation_on_unique_pairs(self):
        df = pd.DataFrame({"company_id": ["TCS", "TCS"], "year": ["2023-03", "2024-03"]})
        assert dq02_annual_pk_uniqueness(df, "profitandloss") == []

    def test_flags_duplicate_company_year_pair(self):
        df = pd.DataFrame({"company_id": ["TCS", "TCS"], "year": ["2023-03", "2023-03"]})
        violations = dq02_annual_pk_uniqueness(df, "profitandloss")
        assert len(violations) == 2
        assert all(v["severity"] == "CRITICAL" for v in violations)


# ===========================================================================
# DQ-03: FK Integrity (CRITICAL)
# ===========================================================================

class TestDQ03FkIntegrity:
    def test_no_violation_when_all_ids_valid(self):
        df = pd.DataFrame({"company_id": ["TCS"], "year": ["2024-03"]})
        assert dq03_fk_integrity(df, "profitandloss", {"TCS", "INFY"}) == []

    def test_flags_orphan_company_id(self):
        df = pd.DataFrame({"company_id": ["GHOST"], "year": ["2024-03"]})
        violations = dq03_fk_integrity(df, "profitandloss", {"TCS", "INFY"})
        assert len(violations) == 1
        assert violations[0]["severity"] == "CRITICAL"


# ===========================================================================
# DQ-04: Balance Sheet Balance (<1%) (WARNING)
# ===========================================================================

class TestDQ04BalanceSheetBalance:
    def test_no_violation_within_tolerance(self):
        bs = pd.DataFrame({"company_id": ["TCS"], "year": ["2024-03"],
                            "total_assets": [1000.0], "total_liabilities": [1005.0]})
        assert dq04_balance_sheet_balance(bs) == []

    def test_flags_imbalance_over_1pct(self):
        bs = pd.DataFrame({"company_id": ["TCS"], "year": ["2024-03"],
                            "total_assets": [1000.0], "total_liabilities": [900.0]})
        violations = dq04_balance_sheet_balance(bs)
        assert len(violations) == 1
        assert violations[0]["severity"] == "WARNING"


# ===========================================================================
# DQ-05: OPM Cross-Check (WARNING)
# ===========================================================================

class TestDQ05OpmCrossCheck:
    def test_no_violation_when_opm_matches(self):
        pl = pd.DataFrame({"company_id": ["TCS"], "year": ["2024-03"],
                            "sales": [1000.0], "operating_profit": [250.0], "opm_percentage": [25.0]})
        assert dq05_opm_cross_check(pl) == []

    def test_flags_opm_mismatch(self):
        pl = pd.DataFrame({"company_id": ["TCS"], "year": ["2024-03"],
                            "sales": [1000.0], "operating_profit": [250.0], "opm_percentage": [10.0]})
        violations = dq05_opm_cross_check(pl)
        assert len(violations) == 1
        assert violations[0]["severity"] == "WARNING"


# ===========================================================================
# DQ-06: Positive Sales (WARNING)
# ===========================================================================

class TestDQ06PositiveSales:
    def test_no_violation_on_positive_sales(self):
        pl = pd.DataFrame({"company_id": ["TCS"], "year": ["2024-03"], "sales": [1000.0]})
        assert dq06_positive_sales(pl) == []

    def test_flags_non_positive_sales(self):
        pl = pd.DataFrame({"company_id": ["TCS"], "year": ["2024-03"], "sales": [0.0]})
        violations = dq06_positive_sales(pl)
        assert len(violations) == 1
        assert violations[0]["severity"] == "WARNING"


# ===========================================================================
# DQ-09: Net Cash Check (WARNING)
# ===========================================================================

class TestDQ09NetCashCheck:
    def test_no_violation_within_10cr_tolerance(self):
        cf = pd.DataFrame({"company_id": ["TCS"], "year": ["2024-03"],
                            "operating_activity": [100.0], "investing_activity": [-40.0],
                            "financing_activity": [-30.0], "net_cash_flow": [30.0]})
        assert dq09_net_cash_check(cf) == []

    def test_flags_net_cash_mismatch(self):
        cf = pd.DataFrame({"company_id": ["TCS"], "year": ["2024-03"],
                            "operating_activity": [100.0], "investing_activity": [-40.0],
                            "financing_activity": [-30.0], "net_cash_flow": [100.0]})
        violations = dq09_net_cash_check(cf)
        assert len(violations) == 1
        assert violations[0]["severity"] == "WARNING"


# ===========================================================================
# DQ-10: Non-Negative Fixed Assets (WARNING)
# ===========================================================================

class TestDQ10NonNegativeFixedAssets:
    def test_no_violation_on_non_negative(self):
        bs = pd.DataFrame({"company_id": ["TCS"], "year": ["2024-03"], "fixed_assets": [500.0]})
        assert dq10_non_negative_fixed_assets(bs) == []

    def test_flags_negative_fixed_assets(self):
        bs = pd.DataFrame({"company_id": ["TCS"], "year": ["2024-03"], "fixed_assets": [-10.0]})
        violations = dq10_non_negative_fixed_assets(bs)
        assert len(violations) == 1
        assert violations[0]["severity"] == "WARNING"


# ===========================================================================
# DQ-11: Tax Rate Range (0-60) (WARNING)
# ===========================================================================

class TestDQ11TaxRateRange:
    def test_no_violation_within_range(self):
        pl = pd.DataFrame({"company_id": ["TCS"], "year": ["2024-03"], "tax_percentage": [25.0]})
        assert dq11_tax_rate_range(pl) == []

    def test_flags_tax_rate_over_60(self):
        pl = pd.DataFrame({"company_id": ["TCS"], "year": ["2024-03"], "tax_percentage": [75.0]})
        violations = dq11_tax_rate_range(pl)
        assert len(violations) == 1
        assert violations[0]["severity"] == "WARNING"


# ===========================================================================
# DQ-12: Dividend Payout Cap (<=200%) (WARNING)
# ===========================================================================

class TestDQ12DividendPayoutCap:
    def test_no_violation_within_cap(self):
        pl = pd.DataFrame({"company_id": ["TCS"], "year": ["2024-03"], "dividend_payout": [100.0]})
        assert dq12_dividend_payout_cap(pl) == []

    def test_flags_payout_over_200pct(self):
        pl = pd.DataFrame({"company_id": ["TCS"], "year": ["2024-03"], "dividend_payout": [250.0]})
        violations = dq12_dividend_payout_cap(pl)
        assert len(violations) == 1
        assert violations[0]["severity"] == "WARNING"


# ===========================================================================
# DQ-13: URL Validity (WARNING)
# ===========================================================================

class TestDQ13UrlValidity:
    def test_no_violation_when_url_present(self):
        documents = pd.DataFrame({"company_id": ["TCS"], "Year": ["2024-03"],
                                   "Annual_Report": ["https://example.com/tcs.pdf"]})
        assert dq13_url_validity(documents, check_network=False) == []

    def test_flags_missing_url(self):
        documents = pd.DataFrame({"company_id": ["TCS"], "Year": ["2024-03"], "Annual_Report": [None]})
        violations = dq13_url_validity(documents, check_network=False)
        assert len(violations) == 1
        assert violations[0]["severity"] == "WARNING"


# ===========================================================================
# DQ-14: EPS Sign Consistency (WARNING)
# ===========================================================================

class TestDQ14EpsSignConsistency:
    def test_no_violation_when_signs_consistent(self):
        pl = pd.DataFrame({"company_id": ["TCS"], "year": ["2024-03"], "net_profit": [500.0], "eps": [10.0]})
        assert dq14_eps_sign_consistency(pl) == []

    def test_flags_non_positive_eps_with_positive_profit(self):
        pl = pd.DataFrame({"company_id": ["TCS"], "year": ["2024-03"], "net_profit": [500.0], "eps": [-1.0]})
        violations = dq14_eps_sign_consistency(pl)
        assert len(violations) == 1
        assert violations[0]["severity"] == "WARNING"


# ===========================================================================
# DQ-15: BSE/ASE Balance (strict, informational only) (INFO)
# ===========================================================================

class TestDQ15StrictBalanceInfo:
    def test_no_violation_when_exactly_equal(self):
        bs = pd.DataFrame({"company_id": ["TCS"], "year": ["2024-03"],
                            "total_assets": [1000.0], "total_liabilities": [1000.0]})
        assert dq15_strict_balance_info(bs) == []

    def test_flags_any_strict_mismatch_as_info(self):
        bs = pd.DataFrame({"company_id": ["TCS"], "year": ["2024-03"],
                            "total_assets": [1000.0], "total_liabilities": [999.99]})
        violations = dq15_strict_balance_info(bs)
        assert len(violations) == 1
        assert violations[0]["severity"] == "INFO"


# ===========================================================================
# DQ-16: Coverage Check (>=5yr history) (WARNING)
# ===========================================================================

class TestDQ16CoverageCheck:
    def test_no_violation_with_5_plus_years(self):
        years = [f"{y}-03" for y in range(2020, 2025)]
        pl = pd.DataFrame({"company_id": ["TCS"] * 5, "year": years})
        bs = pd.DataFrame({"company_id": ["TCS"] * 5, "year": years})
        cf = pd.DataFrame({"company_id": ["TCS"] * 5, "year": years})
        assert dq16_coverage_check(pl, bs, cf, {"TCS"}) == []

    def test_flags_insufficient_history(self):
        years = [f"{y}-03" for y in range(2022, 2025)]  # only 3 years
        pl = pd.DataFrame({"company_id": ["TCS"] * 3, "year": years})
        bs = pd.DataFrame({"company_id": ["TCS"] * 3, "year": years})
        cf = pd.DataFrame({"company_id": ["TCS"] * 3, "year": years})
        violations = dq16_coverage_check(pl, bs, cf, {"TCS"})
        assert len(violations) == 1
        assert violations[0]["severity"] == "WARNING"


# ===========================================================================
# Orchestration: run_all_validations against the real, loaded dataset
# ===========================================================================

class TestRunAllValidationsAgainstRealDb:
    """Day 21 exit criterion: run all 14 DQ rule functions end-to-end and
    confirm 0 CRITICAL failures on the actual loaded dataset."""

    @staticmethod
    @pytest.fixture(scope="class")
    def loaded_tables():
        db_path = Path(__file__).resolve().parents[2] / "data" / "nifty100.db"
        if not db_path.exists():
            pytest.skip("data/nifty100.db not built yet")
        import sqlite3
        conn = sqlite3.connect(db_path)
        tables = {
            name: pd.read_sql(f"SELECT * FROM {name}", conn)
            for name in ["companies", "profitandloss", "balancesheet", "cashflow", "documents"]
        }
        conn.close()
        # db_loader.py renames documents.Year/Annual_Report -> report_year/
        # annual_report_url on the way into SQLite (see TABLE_MAP); rename
        # back to the loader's raw column names that validator.py expects.
        tables["documents"] = tables["documents"].rename(
            columns={"report_year": "Year", "annual_report_url": "Annual_Report"})
        return tables

    def test_zero_critical_violations_on_real_data(self, loaded_tables):
        violations = run_all_validations(loaded_tables, check_urls_online=False)
        critical = [v for v in violations if v["severity"] == "CRITICAL"]
        assert critical == [], f"Found {len(critical)} CRITICAL DQ violations: {critical[:5]}"
