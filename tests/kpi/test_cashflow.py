"""
tests/kpi/test_cashflow_kpis.py — Day 11 unit tests: cash flow KPIs & capital allocation.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "analytics"))

from cashflow_kpis import (
    free_cash_flow, cfo_quality_score, capex_intensity, fcf_conversion_rate,
    classify_capital_allocation,
)


class TestFreeCashFlow:
    def test_normal_case(self):
        assert free_cash_flow(operating_activity=500, investing_activity=-200) == 300

    def test_negative_fcf_allowed(self):
        assert free_cash_flow(operating_activity=100, investing_activity=-300) == -200


class TestCfoQualityScore:
    def test_high_quality(self):
        pairs = [(120, 100)] * 5
        score, label = cfo_quality_score(pairs)
        assert score == 1.2
        assert label == "High Quality"

    def test_moderate(self):
        pairs = [(70, 100)] * 5
        score, label = cfo_quality_score(pairs)
        assert label == "Moderate"

    def test_accrual_risk(self):
        pairs = [(30, 100)] * 5
        score, label = cfo_quality_score(pairs)
        assert label == "Accrual Risk"

    def test_pat_zero_years_excluded_from_average(self):
        pairs = [(120, 100), (50, 0), (120, 100)]
        score, label = cfo_quality_score(pairs)
        assert score == 1.2  # the PAT=0 year is excluded, not averaged in as 0/0
        assert label == "High Quality"

    def test_all_pat_zero_returns_none(self):
        pairs = [(50, 0), (60, 0)]
        score, label = cfo_quality_score(pairs)
        assert score is None
        assert label is None


class TestCapexIntensity:
    def test_asset_light(self):
        value, label = capex_intensity(investing_activity=-20, sales=1000)
        assert value == 2.0
        assert label == "Asset Light"

    def test_moderate(self):
        value, label = capex_intensity(investing_activity=-50, sales=1000)
        assert value == 5.0
        assert label == "Moderate"

    def test_capital_intensive(self):
        value, label = capex_intensity(investing_activity=-150, sales=1000)
        assert value == 15.0
        assert label == "Capital Intensive"


class TestFcfConversionRate:
    def test_normal_case(self):
        assert fcf_conversion_rate(fcf=150, operating_profit=300) == 50.0

    def test_zero_operating_profit_returns_none(self):
        assert fcf_conversion_rate(fcf=150, operating_profit=0) is None


class TestCapitalAllocationClassifier:
    def test_cash_accumulator(self):
        cfo_s, cfi_s, cff_s, label = classify_capital_allocation(cfo=100, cfi=50, cff=30)
        assert (cfo_s, cfi_s, cff_s) == (1, 1, 1)
        assert label == "Cash Accumulator"

    def test_reinvestor(self):
        _, _, _, label = classify_capital_allocation(cfo=100, cfi=-50, cff=-30, cfo_pat_ratio=0.8)
        assert label == "Reinvestor"

    def test_shareholder_returns_override(self):
        _, _, _, label = classify_capital_allocation(cfo=100, cfi=-50, cff=-30, cfo_pat_ratio=2.0)
        assert label == "Shareholder Returns"

    def test_distress_signal(self):
        _, _, _, label = classify_capital_allocation(cfo=-100, cfi=50, cff=30)
        assert label == "Distress Signal"

    def test_growth_funded_by_debt(self):
        _, _, _, label = classify_capital_allocation(cfo=-50, cfi=-100, cff=200)
        assert label == "Growth Funded by Debt"

    def test_pre_revenue(self):
        _, _, _, label = classify_capital_allocation(cfo=-20, cfi=-30, cff=-10)
        assert label == "Pre-Revenue"

    def test_missing_input_returns_all_none(self):
        result = classify_capital_allocation(cfo=None, cfi=50, cff=30)
        assert result == (None, None, None, None)
