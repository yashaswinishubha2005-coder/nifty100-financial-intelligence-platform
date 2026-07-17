"""
src/analytics/cagr.py — CAGR (Compound Annual Growth Rate) engine for the
Nifty 100 Financial Intelligence Platform.

Sprint 2, Day 10 deliverable (Epic 02, Module 2).

CAGR formula: ((end / start) ** (1/n) - 1) * 100

Six edge cases are handled explicitly (per spec) rather than letting a
negative base raise a domain error on fractional exponentiation:

    start   end     result
    ------  ------  -------------------------------------------
    +       +       computed normally
    +       -       None, flag DECLINE_TO_LOSS
    -       +       None, flag TURNAROUND
    -       -       None, flag BOTH_NEGATIVE
    0       any     None, flag ZERO_BASE
    (< n years of data available)  None, flag INSUFFICIENT

Every CAGR value is returned alongside its flag as a (value, flag) pair
so the caller can store both in separate columns (e.g.
`revenue_cagr_5yr` / `revenue_cagr_5yr_flag`), with flag=None meaning
"computed normally, no edge case".
"""

from __future__ import annotations
from typing import Optional, Sequence, Tuple

# Flags
DECLINE_TO_LOSS = "DECLINE_TO_LOSS"
TURNAROUND = "TURNAROUND"
BOTH_NEGATIVE = "BOTH_NEGATIVE"
ZERO_BASE = "ZERO_BASE"
INSUFFICIENT = "INSUFFICIENT"

CagrResult = Tuple[Optional[float], Optional[str]]


def cagr(start: Optional[float], end: Optional[float], n: Optional[int]) -> CagrResult:
    """
    Compute CAGR % between `start` and `end` over `n` years.
    Returns (value, flag) -- flag is None when computed normally.
    """
    if start is None or end is None or n is None or n <= 0:
        return None, INSUFFICIENT

    if start == 0:
        return None, ZERO_BASE
    if start > 0 and end < 0:
        return None, DECLINE_TO_LOSS
    if start < 0 and end > 0:
        return None, TURNAROUND
    if start < 0 and end < 0:
        return None, BOTH_NEGATIVE
    if start < 0 and end == 0:
        # base was a loss, ended flat at zero -- treat as a turnaround-adjacent
        # case (no longer a loss) rather than a bogus positive-looking ratio
        return None, TURNAROUND

    # start > 0 and end >= 0 here
    value = ((end / start) ** (1.0 / n) - 1) * 100
    return value, None


def cagr_from_series(series: Sequence[Tuple[str, Optional[float]]], window_years: int) -> CagrResult:
    """
    Compute CAGR over the last `window_years` years of a (year_label,
    value) series, sorted ascending by year_label (e.g. 'YYYY-MM'
    fiscal labels). Uses the earliest and latest points within the
    trailing window: series[-1] is "end", the point exactly
    `window_years` back is "start".

    Returns (value, flag). flag=INSUFFICIENT if fewer than
    `window_years` + 1 data points are available.
    """
    clean = [(y, v) for y, v in series if v is not None]
    clean.sort(key=lambda t: t[0])

    if len(clean) < window_years + 1:
        return None, INSUFFICIENT

    start_year, start_val = clean[-(window_years + 1)]
    end_year, end_val = clean[-1]
    return cagr(start_val, end_val, window_years)


def compute_all_cagr_windows(series: Sequence[Tuple[str, Optional[float]]],
                              windows: Sequence[int] = (3, 5, 10)) -> dict:
    """
    Convenience wrapper: compute CAGR for every window in `windows`
    (default 3/5/10-year) from a single (year, value) series.
    Returns {window: (value, flag), ...}.
    """
    return {w: cagr_from_series(series, w) for w in windows}
