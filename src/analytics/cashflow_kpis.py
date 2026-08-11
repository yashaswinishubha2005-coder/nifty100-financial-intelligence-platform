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


# ===========================================================================
# Sprint 5, Day 31 (Epic 07, Module 1) — Cash Flow Intelligence
# ===========================================================================
# The functions above (free_cash_flow, cfo_quality_score, capex_intensity,
# classify_capital_allocation) were all built in Sprint 2, Day 11 and are
# reused as-is. This section adds the two new Day 31 signals that build
# a distress/deleveraging *flag* on top of the existing sign-based
# pattern classifier, plus the orchestration that assembles
# output/cashflow_intelligence.xlsx and output/distress_alerts.csv.

def distress_signal_flag(cfo: Optional[float], cff: Optional[float]) -> bool:
    """True if CFO < 0 AND CFF > 0 in the latest year (raising cash
    from financing while operations burn cash). Deliberately broader
    than the 'Distress Signal' capital-allocation pattern above, which
    also requires CFI > 0 -- this flag is the literal Day 31 condition
    on CFO/CFF alone, independent of what investing activity shows."""
    if cfo is None or cff is None:
        return False
    return cfo < 0 and cff > 0


def deleveraging_flag(cff: Optional[float], borrowings_current: Optional[float],
                       borrowings_prior: Optional[float]) -> bool:
    """True if CFF < 0 AND borrowings declined year-over-year (actively
    paying down debt, not just returning cash via dividends/buybacks
    funded some other way)."""
    if cff is None or borrowings_current is None or borrowings_prior is None:
        return False
    return cff < 0 and borrowings_current < borrowings_prior


def fcf_cagr(fcf_series_oldest_to_newest: Sequence[Optional[float]], window_years: int = 5) -> Optional[float]:
    """5-year FCF CAGR, delegating to src/analytics/cagr.py's
    cagr_from_series so the same base-vs-negative/zero edge-case
    handling (Sprint 2, Day 10) applies to FCF as it does to Revenue/
    PAT/EPS. `fcf_series_oldest_to_newest` is a plain list of FCF
    values; a synthetic ascending year label is attached since
    cagr_from_series expects (year, value) pairs but only uses year
    ordinality, not the literal label."""
    import sys as _sys
    from pathlib import Path as _Path
    analytics_dir = str(_Path(__file__).resolve().parent)
    if analytics_dir not in _sys.path:
        _sys.path.insert(0, analytics_dir)
    from cagr import cagr_from_series

    series = list(enumerate(fcf_series_oldest_to_newest))
    value, _flag = cagr_from_series(series, window_years=window_years)
    return value


def build_cashflow_intelligence_table(conn) -> "pd.DataFrame":
    """
    Day 31/32 driver: one row per company with CFO quality, CapEx
    intensity, FCF CAGR/conversion, distress + deleveraging flags, and
    latest-year capital allocation pattern. Reuses the Sprint 2
    functions above rather than re-deriving the same math.
    """
    import pandas as pd

    companies = pd.read_sql("SELECT id AS company_id FROM companies", conn)
    sectors = pd.read_sql("SELECT company_id, broad_sector FROM sectors", conn)
    pl = pd.read_sql("SELECT company_id, year, sales, net_profit, operating_profit FROM profitandloss", conn)
    bs = pd.read_sql("SELECT company_id, year, borrowings FROM balancesheet", conn)
    cf = pd.read_sql("SELECT company_id, year, operating_activity, investing_activity, financing_activity FROM cashflow", conn)

    for df_, cols in [(pl, ["sales", "net_profit", "operating_profit"]),
                       (bs, ["borrowings"]),
                       (cf, ["operating_activity", "investing_activity", "financing_activity"])]:
        for c in cols:
            df_[c] = pd.to_numeric(df_[c], errors="coerce")

    rows = []
    for company_id in companies["company_id"]:
        pl_c = pl[pl.company_id == company_id].sort_values("year")
        bs_c = bs[bs.company_id == company_id].sort_values("year")
        cf_c = cf[cf.company_id == company_id].sort_values("year")

        merged = cf_c.merge(pl_c, on=["company_id", "year"], how="inner").merge(
            bs_c, on=["company_id", "year"], how="left")
        if merged.empty:
            continue

        merged["fcf"] = merged.apply(
            lambda r: free_cash_flow(r["operating_activity"], r["investing_activity"]), axis=1)

        cfo_pat_pairs = list(zip(merged["operating_activity"], merged["net_profit"]))
        cfo_score, cfo_label = cfo_quality_score(cfo_pat_pairs)

        latest = merged.iloc[-1]
        capex_pct, capex_label = capex_intensity(latest["investing_activity"], latest["sales"])

        fcf_cagr_5yr = fcf_cagr(merged["fcf"].tolist(), window_years=5)

        latest_fcf = merged["fcf"].dropna().iloc[-1] if merged["fcf"].notna().any() else None
        fcf_conv_pct = fcf_conversion_rate(latest_fcf, latest["operating_profit"])

        distress = distress_signal_flag(latest["operating_activity"], latest["financing_activity"])

        borrowings_prior = merged["borrowings"].iloc[-2] if len(merged) >= 2 else None
        deleveraging = deleveraging_flag(latest["financing_activity"], latest.get("borrowings"), borrowings_prior)

        cfo_pat_ratio_latest = (latest["operating_activity"] / latest["net_profit"]
                                 if latest["net_profit"] not in (None, 0) and pd.notna(latest["net_profit"]) else None)
        _, _, _, capital_allocation_label = classify_capital_allocation(
            latest["operating_activity"], latest["investing_activity"], latest["financing_activity"],
            cfo_pat_ratio_latest)

        rows.append({
            "company_id": company_id,
            "sector": sectors.set_index("company_id")["broad_sector"].get(company_id),
            "cfo_quality_score": round(cfo_score, 3) if cfo_score is not None else None,
            "cfo_quality_label": cfo_label,
            "capex_intensity_pct": round(capex_pct, 2) if capex_pct is not None else None,
            "capex_label": capex_label,
            "fcf_cagr_5yr": round(fcf_cagr_5yr, 2) if fcf_cagr_5yr is not None else None,
            "fcf_conversion_pct": round(fcf_conv_pct, 2) if fcf_conv_pct is not None else None,
            "distress_flag": distress,
            "deleveraging_flag": deleveraging,
            "capital_allocation_label": capital_allocation_label,
            "_latest_cfo": latest["operating_activity"], "_latest_cff": latest["financing_activity"],
            "_latest_net_profit": latest["net_profit"],
        })

    return pd.DataFrame(rows)


def run_cashflow_intelligence():
    """Day 31/32 entry point: writes output/cashflow_intelligence.xlsx
    and output/distress_alerts.csv."""
    import logging
    import sqlite3
    from pathlib import Path

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)

    project_root = Path(__file__).resolve().parents[2] if (Path(__file__).resolve().parent.name == "analytics") else Path.cwd()
    db_path = project_root / "data" / "nifty100.db"
    output_dir = project_root / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    table = build_cashflow_intelligence_table(conn)
    conn.close()

    export_cols = ["company_id", "sector", "cfo_quality_score", "cfo_quality_label",
                   "capex_intensity_pct", "capex_label", "fcf_cagr_5yr", "fcf_conversion_pct",
                   "distress_flag", "deleveraging_flag", "capital_allocation_label"]
    export_df = table[export_cols]
    xlsx_path = output_dir / "cashflow_intelligence.xlsx"
    export_df.to_excel(xlsx_path, index=False, sheet_name="Cash Flow Intelligence")

    distress = table[table["distress_flag"]][
        ["company_id", "sector", "_latest_cfo", "_latest_cff", "_latest_net_profit"]
    ].rename(columns={"_latest_cfo": "cfo", "_latest_cff": "cff", "_latest_net_profit": "net_profit"})
    alerts_path = output_dir / "distress_alerts.csv"
    distress.to_csv(alerts_path, index=False)

    logger.info("Wrote %s (%d rows)", xlsx_path, len(export_df))
    logger.info("Wrote %s (%d distress alerts)", alerts_path, len(distress))

    return {
        "total_companies": len(export_df),
        "distress_count": len(distress),
        "deleveraging_count": int(table["deleveraging_flag"].sum()),
        "xlsx_path": str(xlsx_path),
        "alerts_path": str(alerts_path),
        "table": table,
    }


if __name__ == "__main__":
    result = run_cashflow_intelligence()
    print()
    print("=== CASH FLOW INTELLIGENCE SUMMARY ===")
    print(f"Total companies: {result['total_companies']}")
    print(f"Distress signals: {result['distress_count']}")
    print(f"Deleveraging companies: {result['deleveraging_count']}")
    print(f"Output: {result['xlsx_path']}")
    print(f"Output: {result['alerts_path']}")
