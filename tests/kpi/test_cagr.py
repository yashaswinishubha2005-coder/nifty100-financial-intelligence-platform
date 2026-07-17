"""
tests/kpi/test_cagr.py — Day 10 unit tests: CAGR engine and edge cases.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "analytics"))

from cagr import (
    cagr, cagr_from_series, compute_all_cagr_windows,
    DECLINE_TO_LOSS, TURNAROUND, BOTH_NEGATIVE, ZERO_BASE, INSUFFICIENT,
)


class TestCagrFormula:
    def test_normal_positive_growth(self):
        value, flag = cagr(start=100, end=200, n=5)
        assert flag is None
        assert round(value, 2) == round(((200 / 100) ** (1 / 5) - 1) * 100, 2)

    def test_normal_positive_decline_but_still_positive(self):
        value, flag = cagr(start=200, end=100, n=5)
        assert flag is None
        assert value < 0


class TestCagrEdgeCases:
    def test_decline_to_loss(self):
        value, flag = cagr(start=100, end=-50, n=3)
        assert value is None
        assert flag == DECLINE_TO_LOSS

    def test_turnaround(self):
        value, flag = cagr(start=-100, end=50, n=3)
        assert value is None
        assert flag == TURNAROUND

    def test_both_negative(self):
        value, flag = cagr(start=-100, end=-50, n=3)
        assert value is None
        assert flag == BOTH_NEGATIVE

    def test_zero_base(self):
        value, flag = cagr(start=0, end=100, n=3)
        assert value is None
        assert flag == ZERO_BASE

    def test_insufficient_missing_n(self):
        value, flag = cagr(start=100, end=200, n=None)
        assert value is None
        assert flag == INSUFFICIENT

    def test_insufficient_missing_start(self):
        value, flag = cagr(start=None, end=200, n=5)
        assert value is None
        assert flag == INSUFFICIENT


class TestCagrFromSeries:
    def test_5yr_window_normal(self):
        series = [(f"20{y:02d}-03", 100 + y * 20) for y in range(18, 24)]  # 6 points, 5yr span
        value, flag = cagr_from_series(series, window_years=5)
        assert flag is None
        assert value is not None

    def test_insufficient_data_for_window(self):
        series = [("2022-03", 100), ("2023-03", 110)]  # only 2 points, need 6 for 5yr window
        value, flag = cagr_from_series(series, window_years=5)
        assert value is None
        assert flag == INSUFFICIENT

    def test_compute_all_windows_returns_dict_per_window(self):
        series = [(f"20{y:02d}-03", 100 + y * 10) for y in range(10, 24)]  # 14 yrs of data
        results = compute_all_cagr_windows(series, windows=(3, 5, 10))
        assert set(results.keys()) == {3, 5, 10}
        for value, flag in results.values():
            assert flag is None
            assert value is not None
