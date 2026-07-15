"""
normaliser.py — Ticker and Year normalisation utilities for the
Nifty 100 Financial Intelligence Platform ETL pipeline.

Implements:
    normalize_ticker(raw_id) -> str | None
    normalize_year(raw_year) -> str | None   (returns 'YYYY-MM' or None)

Design notes
------------
normalize_year() is deliberately conservative: it returns None (and the
caller is expected to log + reject the row per DQ-07) for anything that
is not a genuine annual fiscal-year label. Observed in the real dataset
(not just the spec's illustrative examples):

    'TTM'            -> Trailing Twelve Months, not a fiscal year -> None
    '2024.5'         -> malformed numeric                          -> None
    'Mar 2016 9m'    -> partial/stub period (9-month year)         -> None
    'Mar 2023 15'    -> data-entry typo                            -> None
    '2013'           -> bare year, no month -> assume March FY close
    'Mar 2014'       -> Month YYYY
    'Mar-13'         -> Mon-YY
    'Dec 2012'       -> Month YYYY (Dec year-end company, e.g. NESTLEIND)
    'FY23'           -> FY prefix
"""

from __future__ import annotations
import re
import logging

logger = logging.getLogger(__name__)

_MONTH_MAP = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}

# Patterns tried in order. Each returns (month, year) strings or None.
_PAT_MONTH_YYYY = re.compile(r"^\s*([A-Za-z]{3})[a-z]*\s+(\d{4})\s*$")          # 'Mar 2014', 'March 2014'
_PAT_MONTH_DASH_YY = re.compile(r"^\s*([A-Za-z]{3})-(\d{2})\s*$")               # 'Mar-13'
_PAT_BARE_YEAR = re.compile(r"^\s*(\d{4})\s*$")                                  # '2013'
_PAT_FY_PREFIX = re.compile(r"^\s*FY[-\s]?(\d{2,4})\s*$", re.IGNORECASE)         # 'FY23', 'FY2023'
_PAT_ALREADY_NORM = re.compile(r"^\s*(\d{4})-(\d{2})\s*$")                       # '2023-03'

# Known non-annual / malformed labels to explicitly reject (not silently
# force-parsed). Extend this set as new anomalies are discovered.
_REJECT_EXACT = {"ttm", "n/a", "na", "-", ""}

# Known ticker typos found during Day 06 manual review, mapped to the
# correct company_id in companies.xlsx. 'AGTL' appears 7x in cashflow.xlsx
# but does not exist in companies.xlsx; 'ATGL' (Adani Total Gas Ltd) *does*
# exist and was showing 0yr of cashflow coverage in DQ-16 -- a letter
# transposition, not a genuinely orphaned row. Extend this map as new
# typos are discovered rather than silently dropping/force-matching others.
_TICKER_ALIASES = {"AGTL": "ATGL"}


def normalize_year(raw_year, default_month: str = "03") -> str | None:
    """
    Normalise a raw fiscal-year label to 'YYYY-MM'.

    Returns None if the value is not a genuine single fiscal-year label
    (e.g. 'TTM', partial-year stubs, malformed values). Callers should
    treat None as DQ-07 'reject row, log raw value'.

    default_month: fiscal year-end month to assume for bare-year values
        (e.g. '2013' -> '2013-03'). Defaults to March, the most common
        Indian fiscal year-end in this dataset.
    """
    if raw_year is None:
        return None

    s = str(raw_year).strip()
    if not s:
        return None

    s_lower = s.lower()
    if s_lower in _REJECT_EXACT:
        logger.warning("normalize_year: rejected non-annual label %r", raw_year)
        return None

    # Reject anything with extra trailing tokens like '9m', '15', etc.
    # A clean label should not contain more than "Month Year" or similar.
    # Detect by checking for extra whitespace-separated tokens beyond 2.
    tokens = s.split()
    if len(tokens) > 2:
        logger.warning("normalize_year: rejected malformed/partial-period label %r", raw_year)
        return None

    # Already normalised: 'YYYY-MM'
    m = _PAT_ALREADY_NORM.match(s)
    if m:
        year, month = m.group(1), m.group(2)
        return f"{year}-{month}"

    # 'Mar 2014' / 'March 2014'
    m = _PAT_MONTH_YYYY.match(s)
    if m:
        mon_raw, year = m.group(1).lower(), m.group(2)
        month = _MONTH_MAP.get(mon_raw)
        if month is None:
            logger.warning("normalize_year: unrecognised month token in %r", raw_year)
            return None
        return f"{year}-{month}"

    # 'Mar-13'
    m = _PAT_MONTH_DASH_YY.match(s)
    if m:
        mon_raw, yy = m.group(1).lower(), m.group(2)
        month = _MONTH_MAP.get(mon_raw)
        if month is None:
            logger.warning("normalize_year: unrecognised month token in %r", raw_year)
            return None
        # 2-digit year: assume 20xx (dataset spans 2010-2024)
        year = f"20{yy}"
        return f"{year}-{month}"

    # 'FY23' / 'FY2023'
    m = _PAT_FY_PREFIX.match(s)
    if m:
        yy = m.group(1)
        year = yy if len(yy) == 4 else f"20{yy}"
        return f"{year}-{default_month}"

    # Bare year: '2013'
    m = _PAT_BARE_YEAR.match(s)
    if m:
        year = m.group(1)
        return f"{year}-{default_month}"

    # Malformed numeric like '2024.5' or anything else unmatched
    logger.warning("normalize_year: unparseable value %r -> PARSE_ERROR", raw_year)
    return None


def normalize_ticker(raw_id) -> str | None:
    """
    Normalise a company ticker: strip whitespace, uppercase.
    Reject (return None) if resulting length is outside 2-12 chars
    per DQ-08, or if the raw value is missing/empty.
    """
    if raw_id is None:
        return None
    s = str(raw_id).strip().upper()
    if not s or s.upper() in {"MISSING", "NAN", "NONE"}:
        return None
    if s in _TICKER_ALIASES:
        logger.info("normalize_ticker: corrected known typo %r -> %r", s, _TICKER_ALIASES[s])
        s = _TICKER_ALIASES[s]
    if not (2 <= len(s) <= 12):
        logger.warning("normalize_ticker: length out of range for %r", raw_id)
        return None
    return s