"""
tests/reports/test_portfolio_summary.py — Sprint 5, Day 35 unit tests
for src/reports/portfolio_summary.py.
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src" / "reports"))

from portfolio_summary import trend_arrow, ARROW_UP, ARROW_DOWN, ARROW_FLAT, FLAT_THRESHOLD_PCT, PORTFOLIO_DIR

DB_PATH = PROJECT_ROOT / "data" / "nifty100.db"


class TestTrendArrow:
    def test_higher_value_is_up_for_normal_metric(self):
        symbol, style = trend_arrow(20.0, 15.0, inverse=False)
        assert symbol == "\u25b2"
        assert style is ARROW_UP

    def test_lower_value_is_down_for_normal_metric(self):
        symbol, style = trend_arrow(10.0, 15.0, inverse=False)
        assert symbol == "\u25bc"
        assert style is ARROW_DOWN

    def test_lower_value_is_up_for_inverse_metric(self):
        # D/E falling from 2.0 to 1.0 is an *improvement* -> up arrow
        symbol, style = trend_arrow(1.0, 2.0, inverse=True)
        assert symbol == "\u25b2"
        assert style is ARROW_UP

    def test_higher_value_is_down_for_inverse_metric(self):
        symbol, style = trend_arrow(2.0, 1.0, inverse=True)
        assert symbol == "\u25bc"
        assert style is ARROW_DOWN

    def test_within_2pct_is_flat(self):
        symbol, style = trend_arrow(100.5, 100.0, inverse=False)
        assert symbol == "\u25b6"
        assert style is ARROW_FLAT

    def test_just_over_2pct_is_not_flat(self):
        symbol, style = trend_arrow(103.0, 100.0, inverse=False)
        assert symbol != "\u25b6"

    def test_missing_prior_returns_dash(self):
        symbol, style = trend_arrow(20.0, None)
        assert symbol == "\u2013"
        assert style is ARROW_FLAT

    def test_missing_latest_returns_dash(self):
        symbol, style = trend_arrow(None, 20.0)
        assert symbol == "\u2013"

    def test_zero_prior_returns_dash_not_divide_by_zero(self):
        symbol, style = trend_arrow(5.0, 0.0)
        assert symbol == "\u2013"


class TestPortfolioSummaryBatchOutput:
    def test_pdf_has_92_pages(self):
        if not (PORTFOLIO_DIR / "portfolio_summary.pdf").exists():
            pytest.skip("reports/portfolio/portfolio_summary.pdf not generated yet")
        from pypdf import PdfReader
        reader = PdfReader(str(PORTFOLIO_DIR / "portfolio_summary.pdf"))
        assert len(reader.pages) == 92
