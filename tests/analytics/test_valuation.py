"""
tests/analytics/test_valuation.py — Sprint 4, Day 26 unit tests for
src/analytics/valuation.py.

Covers:
    - fcf_yield_pct(): the core FCF / market cap formula and its
      missing/non-positive-denominator guards
    - classify_valuation(): the Caution / Discount / Fair thresholds
      and the None ("N/A") guard for missing or non-positive inputs
    - build_valuation_table() against the real 92-company database:
      row count, required columns, and the Day 28 exit criterion that
      valuation_summary.xlsx has exactly 92 rows

Run with:
    pytest tests/analytics/test_valuation.py -v
"""

import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src" / "analytics"))

from valuation import (
    build_valuation_table, classify_valuation, fcf_yield_pct,
    CAUTION_MULTIPLIER, DISCOUNT_MULTIPLIER,
)

DB_PATH = PROJECT_ROOT / "data" / "nifty100.db"


# ===========================================================================
# fcf_yield_pct
# ===========================================================================

class TestFcfYieldPct:
    def test_basic_calculation(self):
        # FCF 500 Cr on a 10,000 Cr market cap -> 5% yield
        assert fcf_yield_pct(500.0, 10000.0) == pytest.approx(5.0)

    def test_negative_fcf_gives_negative_yield(self):
        assert fcf_yield_pct(-200.0, 10000.0) == pytest.approx(-2.0)

    def test_none_market_cap_returns_none(self):
        assert fcf_yield_pct(500.0, None) is None

    def test_zero_market_cap_returns_none(self):
        assert fcf_yield_pct(500.0, 0.0) is None

    def test_negative_market_cap_returns_none(self):
        assert fcf_yield_pct(500.0, -10.0) is None

    def test_nan_inputs_return_none(self):
        assert fcf_yield_pct(float("nan"), 10000.0) is None
        assert fcf_yield_pct(500.0, float("nan")) is None

    def test_none_fcf_returns_none(self):
        assert fcf_yield_pct(None, 10000.0) is None


# ===========================================================================
# classify_valuation
# ===========================================================================

class TestClassifyValuation:
    def test_caution_when_pe_far_above_sector_median(self):
        # sector median 20, threshold for Caution is > 30 (20 * 1.5)
        assert classify_valuation(35.0, 20.0) == "Caution"

    def test_exactly_at_caution_multiplier_is_not_caution(self):
        # strictly greater-than, not >=
        assert classify_valuation(20.0 * CAUTION_MULTIPLIER, 20.0) == "Fair"

    def test_discount_when_pe_far_below_sector_median(self):
        # sector median 20, threshold for Discount is < 14 (20 * 0.7)
        assert classify_valuation(10.0, 20.0) == "Discount"

    def test_exactly_at_discount_multiplier_is_not_discount(self):
        assert classify_valuation(20.0 * DISCOUNT_MULTIPLIER, 20.0) == "Fair"

    def test_fair_in_between(self):
        assert classify_valuation(22.0, 20.0) == "Fair"

    def test_none_pe_returns_none(self):
        assert classify_valuation(None, 20.0) is None

    def test_none_sector_median_returns_none(self):
        assert classify_valuation(22.0, None) is None

    def test_negative_pe_returns_none_not_discount(self):
        # A negative P/E means a reported loss, not a cheap valuation --
        # must not be misclassified as "Discount".
        assert classify_valuation(-15.0, 20.0) is None

    def test_zero_sector_median_returns_none(self):
        assert classify_valuation(10.0, 0.0) is None


# ===========================================================================
# build_valuation_table — against the real database
# ===========================================================================

class TestBuildValuationTableRealData:
    @staticmethod
    @pytest.fixture(scope="class")
    def valuation_df():
        if not DB_PATH.exists():
            pytest.skip("data/nifty100.db not built yet")
        conn = sqlite3.connect(DB_PATH)
        df = build_valuation_table(conn)
        conn.close()
        return df

    def test_returns_92_companies(self, valuation_df):
        """Day 28 exit criterion: valuation_summary.xlsx has 92 rows."""
        assert len(valuation_df) == 92

    def test_has_all_required_columns(self, valuation_df):
        required = {
            "company_id", "company_name", "broad_sector", "pe_ratio", "pb_ratio",
            "ev_ebitda", "fcf_yield_pct", "5yr_median_PE", "pe_vs_sector_median_pct", "flag",
        }
        assert required.issubset(set(valuation_df.columns))

    def test_flags_are_one_of_the_four_valid_values(self, valuation_df):
        valid = {"Caution", "Discount", "Fair", None}
        assert set(valuation_df["flag"].where(valuation_df["flag"].notna(), None).tolist()) <= valid

    def test_no_duplicate_companies(self, valuation_df):
        assert valuation_df["company_id"].duplicated().sum() == 0

    def test_caution_companies_have_pe_above_sector_median(self, valuation_df):
        caution = valuation_df[valuation_df["flag"] == "Caution"]
        if not caution.empty:
            assert (caution["pe_ratio"] > caution["sector_median_pe"] * CAUTION_MULTIPLIER).all()

    def test_discount_companies_have_pe_below_sector_median(self, valuation_df):
        discount = valuation_df[valuation_df["flag"] == "Discount"]
        if not discount.empty:
            assert (discount["pe_ratio"] < discount["sector_median_pe"] * DISCOUNT_MULTIPLIER).all()
