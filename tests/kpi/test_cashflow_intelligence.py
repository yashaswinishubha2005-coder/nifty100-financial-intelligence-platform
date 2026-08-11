"""
tests/kpi/test_cashflow_intelligence.py — Sprint 5, Day 31-32 unit
tests for the new functions added to src/analytics/cashflow_kpis.py
and the new src/analytics/capital_allocation_report.py.

(Sprint 2's original cashflow_kpis.py functions are already covered by
tests/kpi/test_cashflow.py; this file only covers the Sprint 5
additions.)
"""

import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src" / "analytics"))

from cashflow_kpis import (
    distress_signal_flag, deleveraging_flag, fcf_cagr,
    build_cashflow_intelligence_table, run_cashflow_intelligence,
)
from capital_allocation_report import (
    verify_completeness, distribution_summary, find_pattern_changes,
)

DB_PATH = PROJECT_ROOT / "data" / "nifty100.db"


class TestDistressSignalFlag:
    def test_triggers_on_negative_cfo_positive_cff(self):
        assert distress_signal_flag(-100, 50) is True

    def test_does_not_trigger_on_positive_cfo(self):
        assert distress_signal_flag(100, 50) is False

    def test_does_not_trigger_on_negative_cff(self):
        assert distress_signal_flag(-100, -50) is False

    def test_none_inputs_return_false(self):
        assert distress_signal_flag(None, 50) is False
        assert distress_signal_flag(-100, None) is False


class TestDeleveragingFlag:
    def test_triggers_on_negative_cff_and_declining_borrowings(self):
        assert deleveraging_flag(-50, 800, 1000) is True

    def test_does_not_trigger_on_rising_borrowings(self):
        assert deleveraging_flag(-50, 1200, 1000) is False

    def test_does_not_trigger_on_positive_cff(self):
        assert deleveraging_flag(50, 800, 1000) is False

    def test_none_inputs_return_false(self):
        assert deleveraging_flag(None, 800, 1000) is False


class TestFcfCagr:
    def test_computes_cagr_over_5_years(self):
        # doubling every year for 5 years from a positive base
        series = [100, 120, 140, 160, 180, 200]
        result = fcf_cagr(series, window_years=5)
        assert result is not None
        assert result == pytest.approx(14.87, abs=0.5)

    def test_insufficient_years_returns_none(self):
        assert fcf_cagr([100, 120], window_years=5) is None


class TestCapitalAllocationVerifyAndDistribution:
    def test_verify_completeness_detects_missing_company(self):
        df = pd.DataFrame({"company_id": ["AAA", "BBB"], "year": ["2024-03", "2024-03"],
                            "pattern_label": ["Reinvestor", "Mixed"]})
        result = verify_completeness(df, {"AAA", "BBB", "CCC"})
        assert result["missing_companies"] == ["CCC"]

    def test_distribution_summary_uses_latest_non_null_row(self):
        # AAA's true latest row (2024-09) has a null pattern -- the
        # summary must fall back to the 2024-03 row, not drop AAA.
        df = pd.DataFrame({
            "company_id": ["AAA", "AAA", "BBB"],
            "year": ["2024-03", "2024-09", "2024-03"],
            "pattern_label": ["Reinvestor", None, "Mixed"],
        })
        dist = distribution_summary(df)
        assert dist["company_count"].sum() == 2
        assert set(dist["pattern_label"]) == {"Reinvestor", "Mixed"}

    def test_find_pattern_changes_detects_transition(self):
        df = pd.DataFrame({
            "company_id": ["AAA"] * 3,
            "year": ["2022-03", "2023-03", "2024-03"],
            "pattern_label": ["Reinvestor", "Reinvestor", "Distress Signal"],
        })
        changes = find_pattern_changes(df)
        assert len(changes) == 1
        assert changes.iloc[0]["from_pattern"] == "Reinvestor"
        assert changes.iloc[0]["to_pattern"] == "Distress Signal"

    def test_find_pattern_changes_no_transition_is_empty(self):
        df = pd.DataFrame({
            "company_id": ["AAA"] * 3,
            "year": ["2022-03", "2023-03", "2024-03"],
            "pattern_label": ["Reinvestor", "Reinvestor", "Reinvestor"],
        })
        assert find_pattern_changes(df).empty


class TestCashflowIntelligenceRealData:
    """Day 32/34 exit criterion: cashflow_intelligence.xlsx has 92 rows
    with all required columns."""

    @staticmethod
    @pytest.fixture(scope="class")
    def table():
        if not DB_PATH.exists():
            pytest.skip("data/nifty100.db not built yet")
        conn = sqlite3.connect(DB_PATH)
        result = build_cashflow_intelligence_table(conn)
        conn.close()
        return result

    def test_returns_92_companies(self, table):
        assert len(table) == 92

    def test_has_all_required_columns(self, table):
        required = {"company_id", "sector", "cfo_quality_score", "cfo_quality_label",
                    "capex_intensity_pct", "capex_label", "fcf_cagr_5yr", "fcf_conversion_pct",
                    "distress_flag", "deleveraging_flag", "capital_allocation_label"}
        assert required.issubset(set(table.columns))

    def test_cfo_quality_labels_are_valid(self, table):
        valid = {"High Quality", "Moderate", "Accrual Risk", None}
        labels = set(table["cfo_quality_label"].where(table["cfo_quality_label"].notna(), None))
        assert labels <= valid

    def test_capex_labels_are_valid(self, table):
        valid = {"Asset Light", "Moderate", "Capital Intensive", None}
        labels = set(table["capex_label"].where(table["capex_label"].notna(), None))
        assert labels <= valid
