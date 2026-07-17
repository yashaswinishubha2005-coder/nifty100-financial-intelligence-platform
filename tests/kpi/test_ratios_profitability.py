"""
tests/kpi/test_ratios_profitability.py — Day 08 unit tests: profitability ratios.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "analytics"))

from ratios import (
    net_profit_margin, operating_profit_margin, opm_cross_check,
    return_on_equity, return_on_capital_employed, classify_roce_for_sector,
    return_on_assets,
)


class TestNetProfitMargin:
    def test_normal_case(self):
        assert net_profit_margin(net_profit=200, sales=1000) == 20.0

    def test_zero_sales_returns_none(self):
        assert net_profit_margin(net_profit=200, sales=0) is None


class TestOperatingProfitMargin:
    def test_normal_case(self):
        assert operating_profit_margin(operating_profit=300, sales=1000) == 30.0

    def test_zero_sales_returns_none(self):
        assert operating_profit_margin(operating_profit=300, sales=0) is None

    def test_opm_cross_check_mismatch_logged(self, caplog):
        import logging
        caplog.set_level(logging.WARNING)
        diff = opm_cross_check(computed_opm=30.0, source_opm_percentage=25.0, company_id="TCS", year="2023-03")
        assert diff == 5.0
        assert "mismatch" in caplog.text.lower()

    def test_opm_cross_check_within_tolerance_no_log(self, caplog):
        import logging
        caplog.set_level(logging.WARNING)
        diff = opm_cross_check(computed_opm=30.0, source_opm_percentage=30.5, company_id="TCS", year="2023-03")
        assert diff == 0.5
        assert "mismatch" not in caplog.text.lower()


class TestReturnOnEquity:
    def test_normal_case(self):
        assert return_on_equity(net_profit=100, equity_capital=50, reserves=450) == 20.0

    def test_negative_equity_returns_none(self):
        assert return_on_equity(net_profit=100, equity_capital=50, reserves=-500) is None

    def test_zero_equity_returns_none(self):
        assert return_on_equity(net_profit=100, equity_capital=0, reserves=0) is None


class TestReturnOnCapitalEmployed:
    def test_normal_case(self):
        roce = return_on_capital_employed(ebit=200, equity_capital=100, reserves=400, borrowings=500)
        assert round(roce, 2) == 20.0

    def test_zero_capital_employed_returns_none(self):
        assert return_on_capital_employed(ebit=200, equity_capital=0, reserves=0, borrowings=0) is None

    def test_classify_roce_financials_uses_sector_average(self):
        assert classify_roce_for_sector(8.0, "Financials", sector_avg_roce=6.0) == "Strong"
        assert classify_roce_for_sector(4.0, "Financials", sector_avg_roce=6.0) == "Weak"

    def test_classify_roce_non_financials_uses_absolute_threshold(self):
        assert classify_roce_for_sector(20.0, "Industrials") == "Strong"
        assert classify_roce_for_sector(10.0, "Industrials") == "Weak"


class TestReturnOnAssets:
    def test_normal_case(self):
        assert return_on_assets(net_profit=100, total_assets=1000) == 10.0

    def test_zero_total_assets_returns_none(self):
        assert return_on_assets(net_profit=100, total_assets=0) is None
