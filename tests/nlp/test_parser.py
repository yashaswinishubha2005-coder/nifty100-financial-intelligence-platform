"""
tests/nlp/test_parser.py — Sprint 5, Day 29 unit tests for
src/nlp/parser.py.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src" / "nlp"))

from parser import parse_field_value, parse_analysis_table, cross_validate, DIVERGENCE_THRESHOLD_PCT

DB_PATH = PROJECT_ROOT / "data" / "nifty100.db"


class TestParseFieldValue:
    def test_standard_format(self):
        assert parse_field_value("10 Years: 21%") == (10, 21.0)

    def test_extra_whitespace(self):
        assert parse_field_value("     5 Years:       8%") == (5, 8.0)

    def test_no_colon(self):
        assert parse_field_value("3 Years 13%") == (3, 13.0)

    def test_decimal_value(self):
        assert parse_field_value("5 Years: 21.5%") == (5, 21.5)

    def test_ttm_does_not_match(self):
        assert parse_field_value("TTM: 43%") is None

    def test_last_year_does_not_match(self):
        assert parse_field_value("Last Year: 12%") is None

    def test_negative_percentage_does_not_match(self):
        # [\d.]+ does not include '-', so a negative value is a real failure
        assert parse_field_value("1 Year: -2%") is None

    def test_none_returns_none(self):
        assert parse_field_value(None) is None

    def test_nan_returns_none(self):
        assert parse_field_value(float("nan")) is None


class TestParseAnalysisTable:
    def test_splits_matches_and_failures(self):
        df = pd.DataFrame([
            {"company_id": "AAA", "compounded_sales_growth": "10 Years: 21%",
             "compounded_profit_growth": "TTM: 5%", "stock_price_cagr": None, "roe": "5 Years: 14%"},
        ])
        parsed, failures = parse_analysis_table(df)
        assert len(parsed) == 2  # sales growth + roe
        assert len(failures) == 1  # profit growth (TTM)
        assert set(parsed["metric_type"]) == {"compounded_sales_growth", "roe"}
        assert failures.iloc[0]["metric_type"] == "compounded_profit_growth"

    def test_empty_cell_is_not_a_failure(self):
        df = pd.DataFrame([{"company_id": "AAA", "compounded_sales_growth": None,
                             "compounded_profit_growth": None, "stock_price_cagr": None, "roe": None}])
        parsed, failures = parse_analysis_table(df)
        assert parsed.empty
        assert failures.empty


class TestCrossValidate:
    def test_flags_large_divergence(self):
        parsed = pd.DataFrame([
            {"company_id": "AAA", "metric_type": "compounded_sales_growth", "period_years": 5, "value_pct": 20.0},
        ])
        fr = pd.DataFrame([{"company_id": "AAA", "year": "2024-03", "revenue_cagr_5yr": 5.0, "pat_cagr_5yr": None}])
        result = cross_validate(parsed, fr)
        assert len(result) == 1
        assert result.iloc[0]["flagged"] is True or result.iloc[0]["flagged"] == True  # noqa: E712
        assert result.iloc[0]["divergence_pp"] == pytest.approx(15.0)

    def test_does_not_flag_small_divergence(self):
        parsed = pd.DataFrame([
            {"company_id": "AAA", "metric_type": "compounded_sales_growth", "period_years": 5, "value_pct": 20.0},
        ])
        fr = pd.DataFrame([{"company_id": "AAA", "year": "2024-03", "revenue_cagr_5yr": 19.0, "pat_cagr_5yr": None}])
        result = cross_validate(parsed, fr)
        assert result.iloc[0]["flagged"] == False  # noqa: E712

    def test_period_years_without_ratio_engine_equivalent_is_skipped(self):
        # stock_price_cagr has no Ratio Engine column to compare against
        parsed = pd.DataFrame([
            {"company_id": "AAA", "metric_type": "stock_price_cagr", "period_years": 5, "value_pct": 20.0},
        ])
        fr = pd.DataFrame([{"company_id": "AAA", "year": "2024-03", "revenue_cagr_5yr": 19.0, "pat_cagr_5yr": None}])
        result = cross_validate(parsed, fr)
        assert result.empty


class TestParserAgainstRealData:
    def test_produces_output_with_expected_columns(self):
        if not DB_PATH.exists():
            pytest.skip("data/nifty100.db not built yet")
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        analysis_df = pd.read_sql("SELECT * FROM analysis", conn)
        conn.close()
        parsed, failures = parse_analysis_table(analysis_df)
        assert list(parsed.columns) == ["company_id", "metric_type", "period_years", "value_pct"]
        assert list(failures.columns) == ["company_id", "metric_type", "raw_text"]
        assert len(parsed) + len(failures) > 0
