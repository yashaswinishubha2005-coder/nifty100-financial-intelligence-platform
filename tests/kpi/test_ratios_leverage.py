"""
tests/kpi/test_ratios_leverage.py — Day 09 unit tests: leverage & efficiency ratios.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "analytics"))

from ratios import (
    debt_to_equity, high_leverage_flag, interest_coverage, icr_label,
    icr_risk_flag, net_debt, asset_turnover,
)


class TestDebtToEquity:
    def test_normal_case(self):
        assert debt_to_equity(borrowings=200, equity_capital=100, reserves=300) == 0.5

    def test_debt_free_returns_zero_not_none(self):
        assert debt_to_equity(borrowings=0, equity_capital=100, reserves=300) == 0.0

    def test_nonzero_debt_with_negative_equity_returns_none(self):
        assert debt_to_equity(borrowings=200, equity_capital=100, reserves=-500) is None


class TestHighLeverageFlag:
    def test_flag_true_for_non_financials_over_5(self):
        assert high_leverage_flag(de_ratio=6.0, broad_sector="Industrials") is True

    def test_flag_suppressed_for_financials(self):
        assert high_leverage_flag(de_ratio=9.0, broad_sector="Financials") is False

    def test_flag_false_when_below_threshold(self):
        assert high_leverage_flag(de_ratio=2.0, broad_sector="Industrials") is False


class TestInterestCoverage:
    def test_normal_case(self):
        assert interest_coverage(operating_profit=300, other_income=20, interest=100) == 3.2

    def test_interest_zero_returns_none(self):
        assert interest_coverage(operating_profit=300, other_income=20, interest=0) is None

    def test_icr_label_is_debt_free_when_icr_none(self):
        icr = interest_coverage(operating_profit=300, other_income=20, interest=0)
        assert icr is None
        assert icr_label(icr) == "Debt Free"

    def test_icr_label_none_when_icr_present(self):
        icr = interest_coverage(operating_profit=300, other_income=20, interest=100)
        assert icr_label(icr) is None

    def test_icr_risk_flag_below_threshold(self):
        assert icr_risk_flag(1.2) is True
        assert icr_risk_flag(2.0) is False
        assert icr_risk_flag(None) is False  # debt-free companies are not "at risk"


class TestNetDebtAndAssetTurnover:
    def test_net_debt_normal_case(self):
        assert net_debt(borrowings=500, investments=200) == 300

    def test_asset_turnover_normal_case(self):
        assert asset_turnover(sales=1000, total_assets=500) == 2.0

    def test_asset_turnover_zero_assets_returns_none(self):
        assert asset_turnover(sales=1000, total_assets=0) is None
