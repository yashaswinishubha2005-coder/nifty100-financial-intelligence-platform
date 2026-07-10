"""
tests/etl/test_normalise.py — Unit tests for normalize_year() and
normalize_ticker() (src/etl/normaliser.py).

Per project spec (Day 02 deliverable): 35+ tests total —
20 for normalize_year(), 15 for normalize_ticker().

Run with:
    pytest tests/etl/test_normalise.py -v
"""

import sys
from pathlib import Path

# Allow running pytest from project root without package install
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "etl"))

from normaliser import normalize_year, normalize_ticker


# ===========================================================================
# normalize_year() — 20+ tests
# ===========================================================================

class TestNormalizeYearStandardFormats:
    """Formats explicitly documented in the project spec's edge-case table."""

    def test_month_dash_yy(self):
        assert normalize_year("Mar-23") == "2023-03"

    def test_month_space_yyyy(self):
        assert normalize_year("Mar 2014") == "2014-03"

    def test_month_space_yyyy_with_space_prefix(self):
        assert normalize_year("Mar 23") is None  # 'Mar 23' is 2-digit year, not in spec's accepted set -> should reject, not misparse as 2023

    def test_full_month_name(self):
        assert normalize_year("March-2023") is None  # not a supported pattern; ensures we don't silently misparse

    def test_bare_integer_year(self):
        assert normalize_year("2023") == "2023-03"  # assume March FY close per spec

    def test_fy_prefix(self):
        assert normalize_year("FY23") == "2023-03"

    def test_fy_prefix_full_year(self):
        assert normalize_year("FY2023") == "2023-03"

    def test_december_year_end(self):
        assert normalize_year("Dec-22") == "2022-12"

    def test_december_year_end_space_format(self):
        assert normalize_year("Dec 2012") == "2012-12"

    def test_june_year_end(self):
        assert normalize_year("Jun-23") == "2023-06"

    def test_already_normalised_passthrough(self):
        assert normalize_year("2023-03") == "2023-03"

    def test_garbage_input_rejected(self):
        assert normalize_year("xyz") is None

    def test_none_input_rejected(self):
        assert normalize_year(None) is None

    def test_empty_string_rejected(self):
        assert normalize_year("") is None


class TestNormalizeYearRealDataAnomalies:
    """
    Anomalies discovered when running normalize_year() against the
    ACTUAL uploaded dataset (not just the spec's illustrative examples).
    These are the reason DQ-07 exists: reject and log, don't guess.
    """

    def test_ttm_is_rejected_not_a_fiscal_year(self):
        # Trailing Twelve Months -- appears 100+ times in profitandloss.xlsx
        assert normalize_year("TTM") is None

    def test_ttm_case_insensitive(self):
        assert normalize_year("ttm") is None

    def test_malformed_decimal_year_rejected(self):
        # Found in balancesheet.xlsx: '2024.5'
        assert normalize_year("2024.5") is None

    def test_partial_period_9m_rejected(self):
        # Found in profitandloss.xlsx: 'Mar 2016 9m' (9-month stub period)
        assert normalize_year("Mar 2016 9m") is None

    def test_typo_extra_token_rejected(self):
        # Found in profitandloss.xlsx: 'Mar 2023 15' (data entry typo)
        assert normalize_year("Mar 2023 15") is None

    def test_september_year_end(self):
        # Found in balancesheet.xlsx: 'Sep 2024' -- some companies have
        # non-March, non-December fiscal year ends
        assert normalize_year("Sep 2024") == "2024-09"

    def test_all_real_month_dash_yy_values(self):
        # Every Mar-YY value actually present in cashflow.xlsx
        for yy, expected in [
            ("13", "2013"), ("14", "2014"), ("15", "2015"), ("16", "2016"),
            ("17", "2017"), ("18", "2018"), ("19", "2019"), ("20", "2020"),
            ("21", "2021"), ("22", "2022"), ("23", "2023"), ("24", "2024"),
        ]:
            assert normalize_year(f"Mar-{yy}") == f"{expected}-03"


class TestNormalizeYearWhitespaceHandling:

    def test_leading_trailing_whitespace_stripped(self):
        assert normalize_year("  Mar-23  ") == "2023-03"

    def test_whitespace_only_rejected(self):
        assert normalize_year("   ") is None


# ===========================================================================
# normalize_ticker() — 15+ tests
# ===========================================================================

class TestNormalizeTickerBasic:

    def test_already_uppercase(self):
        assert normalize_ticker("TCS") == "TCS"

    def test_lowercase_converted(self):
        assert normalize_ticker("tcs") == "TCS"

    def test_mixed_case_converted(self):
        assert normalize_ticker("TcS") == "TCS"

    def test_leading_trailing_whitespace_stripped(self):
        assert normalize_ticker("  ABB  ") == "ABB"

    def test_internal_whitespace_not_stripped(self):
        # Should not silently mangle a ticker with internal content
        result = normalize_ticker(" M&M ")
        assert result == "M&M"


class TestNormalizeTickerSpecialCharacters:

    def test_hyphenated_ticker_preserved(self):
        assert normalize_ticker("BAJAJ-AUTO") == "BAJAJ-AUTO"

    def test_hyphenated_ticker_lowercase(self):
        assert normalize_ticker("bajaj-auto") == "BAJAJ-AUTO"

    def test_ampersand_ticker_preserved(self):
        assert normalize_ticker("M&M") == "M&M"

    def test_ampersand_ticker_lowercase(self):
        assert normalize_ticker("m&m") == "M&M"


class TestNormalizeTickerRejection:

    def test_none_rejected(self):
        assert normalize_ticker(None) is None

    def test_missing_literal_rejected(self):
        assert normalize_ticker("MISSING") is None

    def test_empty_string_rejected(self):
        assert normalize_ticker("") is None

    def test_whitespace_only_rejected(self):
        assert normalize_ticker("   ") is None

    def test_too_short_rejected(self):
        # DQ-08: length must be 2-12 chars
        assert normalize_ticker("X") is None

    def test_too_long_rejected(self):
        # DQ-08: length must be 2-12 chars
        assert normalize_ticker("A" * 13) is None

    def test_minimum_valid_length_accepted(self):
        assert normalize_ticker("AB") == "AB"

    def test_maximum_valid_length_accepted(self):
        assert normalize_ticker("A" * 12) == "A" * 12


class TestNormalizeTickerRealData:
    """Every real ticker format style actually present in companies.xlsx."""

    def test_standard_ticker(self):
        assert normalize_ticker("RELIANCE") == "RELIANCE"

    def test_numeric_free_ticker(self):
        assert normalize_ticker("HDFCBANK") == "HDFCBANK"

    def test_short_valid_ticker(self):
        assert normalize_ticker("itc") == "ITC"