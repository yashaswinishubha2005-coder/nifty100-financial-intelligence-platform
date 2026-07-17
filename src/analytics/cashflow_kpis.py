"""
src/analytics/cashflow_kpis.py — Cash flow KPIs and capital allocation
pattern classification for the Nifty 100 Financial Intelligence Platform.

Sprint 2, Day 11 deliverable (Epic 02, Module 2).
"""

from __future__ import annotations
from typing import Optional, Sequence, Tuple

# ===========================================================================
# Free Cash Flow / CapEx / conversion
# ===========================================================================

def free_cash_flow(operating_activity: Optional[float], investing_activity: Optional[float]) -> Optional[float]:
    """FCF = CFO + CFI. Negative values are allowed and meaningful."""
    if operating_activity is None or investing_activity is None:
        return None
    return operating_activity + investing_activity


def cfo_quality_score(cfo_pat_pairs: Sequence[Tuple[Optional[float], Optional[float]]]) -> Tuple[Optional[float], Optional[str]]:
    """
    CFO Quality Score = average(CFO/PAT) over up to the last 5 years of
    (cfo, pat) pairs. Years where PAT == 0 or either value is missing
    are excluded from the average (that single year's ratio is
    undefined, not the whole score).

    Label:  > 1.0        -> 'High Quality'
            0.5 - 1.0     -> 'Moderate'
            < 0.5          -> 'Accrual Risk'

    Returns (score, label). Both None if no valid (cfo, pat) pair with
    PAT != 0 is available in the window.
    """
    window = list(cfo_pat_pairs)[-5:]
    ratios = [cfo / pat for cfo, pat in window if cfo is not None and pat not in (None, 0)]
    if not ratios:
        return None, None
    score = sum(ratios) / len(ratios)
    if score > 1.0:
        label = "High Quality"
    elif score >= 0.5:
        label = "Moderate"
    else:
        label = "Accrual Risk"
    return score, label


def capex_intensity(investing_activity: Optional[float], sales: Optional[float]) -> Tuple[Optional[float], Optional[str]]:
    """
    CapEx Intensity % = abs(investing_activity) / sales x 100.

    Label:  < 3%   -> 'Asset Light'
            3-8%   -> 'Moderate'
            > 8%   -> 'Capital Intensive'

    Returns (value, label). Both None if sales is None or 0.
    """
    if investing_activity is None or sales is None or sales == 0:
        return None, None
    value = abs(investing_activity) / sales * 100
    if value < 3:
        label = "Asset Light"
    elif value <= 8:
        label = "Moderate"
    else:
        label = "Capital Intensive"
    return value, label


def fcf_conversion_rate(fcf: Optional[float], operating_profit: Optional[float]) -> Optional[float]:
    """FCF Conversion Rate % = FCF / operating_profit x 100. None if operating_profit == 0."""
    if fcf is None or operating_profit is None or operating_profit == 0:
        return None
    return fcf / operating_profit * 100


# ===========================================================================
# Capital allocation 8-pattern classifier
# ===========================================================================

# Sign-combo -> base label. Keys are (cfo_sign, cfi_sign, cff_sign) each
# in {+1, -1}; 0 (exactly zero) is treated as +1 ("not a net outflow")
# for classification purposes, since none of the 8 spec'd patterns
# define a zero case explicitly.
_PATTERN_LABELS = {
    (1, 1, 1):   "Cash Accumulator",
    (1, 1, -1):  "Liquidating Assets",
    (1, -1, 1):  "Mixed",
    (1, -1, -1): "Reinvestor",          # see high-CFO/PAT override below
    (-1, 1, 1):  "Distress Signal",
    (-1, 1, -1): "Asset Sale Funded Repayment",  # not explicitly spec'd; documented assumption
    (-1, -1, 1): "Growth Funded by Debt",
    (-1, -1, -1): "Pre-Revenue",
}

# CFO/PAT ratio above which a (+,-,-) company is relabelled from
# 'Reinvestor' to 'Shareholder Returns' (strong operating cash
# generation being deployed into buybacks/dividends/debt paydown
# rather than reinvestment). Not specified numerically in the sprint
# doc -- documented assumption, tune as real data warrants.
SHAREHOLDER_RETURNS_CFO_PAT_THRESHOLD = 1.5


def _sign(x: Optional[float]) -> Optional[int]:
    if x is None:
        return None
    return 1 if x >= 0 else -1


def classify_capital_allocation(cfo: Optional[float], cfi: Optional[float], cff: Optional[float],
                                 cfo_pat_ratio: Optional[float] = None) -> Tuple[Optional[int], Optional[int], Optional[int], Optional[str]]:
    """
    Classify a company-year into one of the capital-allocation patterns
    based on the signs of (CFO, CFI, CFF).

    Returns (cfo_sign, cfi_sign, cff_sign, pattern_label). All None if
    any of cfo/cfi/cff is missing.
    """
    cfo_s, cfi_s, cff_s = _sign(cfo), _sign(cfi), _sign(cff)
    if cfo_s is None or cfi_s is None or cff_s is None:
        return None, None, None, None

    label = _PATTERN_LABELS[(cfo_s, cfi_s, cff_s)]
    if (cfo_s, cfi_s, cff_s) == (1, -1, -1) and cfo_pat_ratio is not None \
            and cfo_pat_ratio > SHAREHOLDER_RETURNS_CFO_PAT_THRESHOLD:
        label = "Shareholder Returns"

    return cfo_s, cfi_s, cff_s, label
