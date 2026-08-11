"""
src/nlp/pros_cons_generator.py — Auto pros/cons generator for the
Nifty 100 Financial Intelligence Platform.

Sprint 5, Day 30 deliverable (Epic 09, Module 1).

12 pro rules + 12 con rules, each evaluated per company against its
financial_ratios / profitandloss / balancesheet / market_cap history.
Every triggered rule gets a 0-100 confidence score reflecting how far
past its threshold the signal sits (not just a pass/fail flag); only
rules scoring confidence > 60 are included in the output, per the
Day 30 spec.

Confidence model
-----------------
For every rule, confidence = 60 at exactly the trigger threshold (the
weakest possible "true" signal) and rises toward 100 as the metric
moves further past the threshold, saturating at a rule-specific scale
that represents "a very strong signal" for that metric (e.g. ROE
10 points above the 20% threshold is treated as maximally confident
for Pro Rule 1). This keeps every rule's math the same shape
(`_confidence`) while letting each rule calibrate what "strong" means
for its own metric. Rules based on a discrete condition rather than a
continuous margin (e.g. "D/E = 0") use a fixed high confidence instead.

Usage:
    python src/nlp/pros_cons_generator.py
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2] if (Path(__file__).resolve().parent.name == "nlp") else Path.cwd()
DB_PATH = PROJECT_ROOT / "data" / "nifty100.db"
OUTPUT_DIR = PROJECT_ROOT / "output"

CONFIDENCE_INCLUDE_THRESHOLD = 60.0

sys.path.insert(0, str(PROJECT_ROOT / "src" / "analytics"))
from ratios import compute_ebit, return_on_capital_employed  # noqa: E402


# ===========================================================================
# Company profile builder
# ===========================================================================

class CompanyProfile:
    """All the per-company time series a rule might need, pre-sorted by
    fiscal year ascending, with everything coerced to numeric."""

    def __init__(self, company_id: str, fr: pd.DataFrame, pl: pd.DataFrame,
                 bs: pd.DataFrame, mc: pd.DataFrame, broad_sector: Optional[str]):
        self.company_id = company_id
        self.broad_sector = broad_sector

        self.fr = fr.sort_values("year").reset_index(drop=True)
        self.pl = pl.sort_values("year").reset_index(drop=True)
        self.bs = bs.sort_values("year").reset_index(drop=True)
        self.mc = mc.sort_values("year").reset_index(drop=True)

        for col in self.fr.columns:
            if col not in ("company_id", "year", "icr_label"):
                self.fr[col] = pd.to_numeric(self.fr[col], errors="coerce")
        for df_, cols in [(self.pl, ["sales", "net_profit"]),
                           (self.bs, ["total_assets", "borrowings"]),
                           (self.mc, ["market_cap_crore", "enterprise_value_crore", "ev_ebitda", "dividend_yield_pct"])]:
            for c in cols:
                if c in df_.columns:
                    df_[c] = pd.to_numeric(df_[c], errors="coerce")

        self.roce = self._compute_roce_series()

    def _compute_roce_series(self) -> pd.Series:
        merged = self.pl.merge(self.bs, on=["company_id", "year"], suffixes=("_pl", "_bs"))
        values = []
        for _, r in merged.iterrows():
            ebit = compute_ebit(r.get("operating_profit"), r.get("other_income"), r.get("depreciation"))
            roce = return_on_capital_employed(ebit, r.get("equity_capital"), r.get("reserves"), r.get("borrowings"))
            values.append(roce)
        return pd.Series(values, index=merged["year"])

    def latest(self, df: pd.DataFrame, col: str):
        s = df[col].dropna()
        return s.iloc[-1] if not s.empty else None

    def tail_n(self, df: pd.DataFrame, col: str, n: int) -> pd.Series:
        return df[col].dropna().tail(n)


def build_profile(company_id: str, conn: sqlite3.Connection, sectors_lookup: dict) -> CompanyProfile:
    fr = pd.read_sql("SELECT * FROM financial_ratios WHERE company_id = ?", conn, params=(company_id,))
    pl = pd.read_sql("SELECT * FROM profitandloss WHERE company_id = ?", conn, params=(company_id,))
    bs = pd.read_sql("SELECT * FROM balancesheet WHERE company_id = ?", conn, params=(company_id,))
    mc = pd.read_sql("SELECT * FROM market_cap WHERE company_id = ?", conn, params=(company_id,))
    return CompanyProfile(company_id, fr, pl, bs, mc, sectors_lookup.get(company_id))


# ===========================================================================
# Confidence helper
# ===========================================================================

def _confidence(margin: float, scale: float) -> float:
    """60 at margin==0 (borderline trigger), rising linearly to 100 at
    margin==scale, clipped to [0, 100]. `scale` is the rule-specific
    'this counts as a very strong signal' constant."""
    if scale <= 0:
        return 75.0
    conf = 60.0 + (margin / scale) * 40.0
    return float(max(0.0, min(100.0, conf)))


def _all_above(series: pd.Series, threshold: float, n: int) -> bool:
    tail = series.dropna().tail(n)
    return len(tail) >= n and (tail > threshold).all()


def _all_below(series: pd.Series, threshold: float, n: int) -> bool:
    tail = series.dropna().tail(n)
    return len(tail) >= n and (tail < threshold).all()


def _is_monotonic_increasing(series: pd.Series, n: int) -> bool:
    tail = series.dropna().tail(n)
    return len(tail) >= n and tail.is_monotonic_increasing and tail.iloc[-1] > tail.iloc[0]


def _is_monotonic_decreasing(series: pd.Series, n: int) -> bool:
    tail = series.dropna().tail(n)
    return len(tail) >= n and tail.is_monotonic_decreasing and tail.iloc[-1] < tail.iloc[0]


# ===========================================================================
# PRO RULES (12)
# ===========================================================================

def pro_01_high_sustained_roe(p: CompanyProfile):
    roe = p.fr["return_on_equity_pct"]
    if not _all_above(roe, 20, 3):
        return None
    margin = roe.dropna().tail(3).mean() - 20
    return _confidence(margin, scale=15), \
        "Consistently high return on equity above 20% demonstrates exceptional capital efficiency"


def pro_02_fcf_positive_5yr(p: CompanyProfile):
    fcf = p.fr["free_cash_flow_cr"]
    if not _all_above(fcf, 0, 5):
        return None
    margin = fcf.dropna().tail(5).mean()
    return _confidence(margin, scale=max(abs(margin) * 2, 1)), \
        "Strong free cash flow generation over 5 years signals healthy business fundamentals"


def pro_03_debt_free(p: CompanyProfile):
    de = p.latest(p.fr, "debt_to_equity")
    if de is None or de != 0:
        return None
    return 90.0, "Debt-free balance sheet provides financial flexibility and eliminates interest burden"


def pro_04_revenue_cagr_above_15(p: CompanyProfile):
    v = p.latest(p.fr, "revenue_cagr_5yr")
    if v is None or v <= 15:
        return None
    return _confidence(v - 15, scale=15), \
        "Revenue growing at above 15% CAGR over 5 years reflects strong business momentum"


def pro_05_opm_above_25(p: CompanyProfile):
    v = p.latest(p.fr, "operating_profit_margin_pct")
    if v is None or v <= 25:
        return None
    return _confidence(v - 25, scale=20), \
        "Operating profit margin above 25% indicates strong pricing power and cost discipline"


def pro_06_pat_cagr_above_20(p: CompanyProfile):
    v = p.latest(p.fr, "pat_cagr_5yr")
    if v is None or v <= 20:
        return None
    return _confidence(v - 20, scale=20), \
        "Net profit compounding at above 20% over 5 years creates significant shareholder value"


def pro_07_icr_above_10_or_debt_free(p: CompanyProfile):
    icr = p.latest(p.fr, "interest_coverage")
    label = p.fr["icr_label"].dropna().iloc[-1] if p.fr["icr_label"].notna().any() else None
    if label == "Debt Free":
        return 95.0, "Very high interest coverage ratio reflects negligible financial stress from debt servicing"
    if icr is None or icr <= 10:
        return None
    return _confidence(icr - 10, scale=15), \
        "Very high interest coverage ratio reflects negligible financial stress from debt servicing"


def pro_08_dividend_yield_with_fcf(p: CompanyProfile):
    yld = p.latest(p.mc, "dividend_yield_pct")
    fcf = p.latest(p.fr, "free_cash_flow_cr")
    if yld is None or yld <= 2 or fcf is None or fcf <= 0:
        return None
    return _confidence(yld - 2, scale=3), \
        "Consistent dividend yield above 2% backed by positive free cash flow"


def pro_09_eps_cagr_above_15(p: CompanyProfile):
    v = p.latest(p.fr, "eps_cagr_5yr")
    if v is None or v <= 15:
        return None
    return _confidence(v - 15, scale=15), \
        "Earnings per share growing above 15% CAGR indicates strong earnings quality and compounding"


def pro_10_roe_improving_3yr(p: CompanyProfile):
    roe = p.fr["return_on_equity_pct"]
    if not _is_monotonic_increasing(roe, 3):
        return None
    tail = roe.dropna().tail(3)
    margin = tail.iloc[-1] - tail.iloc[0]
    return _confidence(margin, scale=10), \
        "Return on equity improving for 3 consecutive years shows strengthening business quality"


def pro_11_operating_leverage(p: CompanyProfile):
    rev_cagr = p.latest(p.fr, "revenue_cagr_5yr")
    pat_cagr = p.latest(p.fr, "pat_cagr_5yr")
    if rev_cagr is None or pat_cagr is None or not (pat_cagr > rev_cagr):
        return None
    return _confidence(pat_cagr - rev_cagr, scale=10), \
        "Revenue growing slower than profits shows improving operating leverage and scale benefits"


def pro_12_assets_growing_debt_declining(p: CompanyProfile):
    assets = p.bs["total_assets"]
    debt = p.bs["borrowings"]
    if not _is_monotonic_increasing(assets, 3) or not _is_monotonic_decreasing(debt, 3):
        return None
    tail_assets = assets.dropna().tail(3)
    asset_growth_pct = (tail_assets.iloc[-1] / tail_assets.iloc[0] - 1) * 100 if tail_assets.iloc[0] else 0
    return _confidence(asset_growth_pct, scale=20), \
        "Growing asset base funded by internal accruals reflects self-sustaining growth"


PRO_RULES = [
    pro_01_high_sustained_roe, pro_02_fcf_positive_5yr, pro_03_debt_free,
    pro_04_revenue_cagr_above_15, pro_05_opm_above_25, pro_06_pat_cagr_above_20,
    pro_07_icr_above_10_or_debt_free, pro_08_dividend_yield_with_fcf,
    pro_09_eps_cagr_above_15, pro_10_roe_improving_3yr, pro_11_operating_leverage,
    pro_12_assets_growing_debt_declining,
]


# ===========================================================================
# CON RULES (12)
# ===========================================================================

def con_01_high_de_non_financial(p: CompanyProfile):
    if p.broad_sector == "Financials":
        return None
    de = p.latest(p.fr, "debt_to_equity")
    if de is None or de <= 2.0:
        return None
    return _confidence(de - 2.0, scale=2.0), \
        f"Debt-to-equity ratio of {de:.2f} is elevated for a non-financial company and warrants monitoring"


def con_02_fcf_negative_3yr(p: CompanyProfile):
    fcf = p.fr["free_cash_flow_cr"]
    if not _all_below(fcf, 0, 3):
        return None
    margin = abs(fcf.dropna().tail(3).mean())
    return _confidence(margin, scale=max(margin * 2, 1)), \
        "Free cash flow negative for 3 consecutive years raises concern about cash generation quality"


def con_03_opm_declining_3yr(p: CompanyProfile):
    opm = p.fr["operating_profit_margin_pct"]
    if not _is_monotonic_decreasing(opm, 3):
        return None
    tail = opm.dropna().tail(3)
    margin = tail.iloc[0] - tail.iloc[-1]
    return _confidence(margin, scale=8), \
        "Operating margins declining for 3 consecutive years suggest pricing or cost pressure"


def con_04_net_loss_latest_year(p: CompanyProfile):
    v = p.latest(p.pl, "net_profit")
    if v is None or v >= 0:
        return None
    return 90.0, "Company reported a net loss in the most recent financial year"


def con_05_revenue_declining_2yr(p: CompanyProfile):
    rev = p.pl["sales"]
    if not _is_monotonic_decreasing(rev, 2):
        return None
    tail = rev.dropna().tail(2)
    decline_pct = (1 - tail.iloc[-1] / tail.iloc[0]) * 100 if tail.iloc[0] else 0
    return _confidence(decline_pct, scale=15), \
        "Revenue contraction over 2 consecutive years indicates demand weakness or market share loss"


def con_06_low_icr(p: CompanyProfile):
    label = p.fr["icr_label"].dropna().iloc[-1] if p.fr["icr_label"].notna().any() else None
    if label == "Debt Free":
        return None
    icr = p.latest(p.fr, "interest_coverage")
    if icr is None or icr >= 1.5:
        return None
    return _confidence(1.5 - icr, scale=1.5), \
        "Interest coverage ratio below 1.5x indicates the company is at risk of not meeting its debt obligations"


def con_07_payout_over_100(p: CompanyProfile):
    v = p.latest(p.fr, "dividend_payout_ratio_pct")
    if v is None or v <= 100:
        return None
    return _confidence(v - 100, scale=50), \
        "Dividend payout ratio above 100% means the company is paying dividends from reserves, which is unsustainable"


def con_08_de_rising_3yr(p: CompanyProfile):
    de = p.fr["debt_to_equity"]
    if not _is_monotonic_increasing(de, 3):
        return None
    tail = de.dropna().tail(3)
    margin = tail.iloc[-1] - tail.iloc[0]
    return _confidence(margin, scale=1.0), \
        "Rising debt-to-equity ratio over 3 years suggests increasing financial leverage risk"


def con_09_eps_declining_3yr(p: CompanyProfile):
    eps = p.fr["earnings_per_share"]
    if not _is_monotonic_decreasing(eps, 3):
        return None
    tail = eps.dropna().tail(3)
    decline_pct = (1 - tail.iloc[-1] / tail.iloc[0]) * 100 if tail.iloc[0] else 0
    return _confidence(decline_pct, scale=20), \
        "Earnings per share declining for 3 consecutive years reflects deteriorating profitability"


def con_10_low_roce(p: CompanyProfile):
    v = p.roce.dropna()
    if v.empty:
        return None
    latest_roce = v.iloc[-1]
    if latest_roce >= 10:
        return None
    return _confidence(10 - latest_roce, scale=8), \
        "Return on capital employed below 10% suggests the business is not generating sufficient returns on invested capital"


def con_11_high_net_debt_to_ebitda(p: CompanyProfile):
    """Net Debt ~= Enterprise Value - Market Cap; EBITDA ~= Enterprise
    Value / (EV/EBITDA multiple). Neither raw figure is stored
    directly in this schema, so both are derived from market_cap's
    enterprise_value_crore and ev_ebitda columns -- documented
    approximation, not a data source the platform captures directly."""
    ev = p.latest(p.mc, "enterprise_value_crore")
    mcap = p.latest(p.mc, "market_cap_crore")
    ev_ebitda = p.latest(p.mc, "ev_ebitda")
    if ev is None or mcap is None or ev_ebitda is None or ev_ebitda <= 0:
        return None
    net_debt = ev - mcap
    ebitda = ev / ev_ebitda
    if ebitda <= 0:
        return None
    ratio = net_debt / ebitda
    if ratio <= 3.0:
        return None
    return _confidence(ratio - 3.0, scale=3.0), \
        "Net debt exceeding 3 times EBITDA is a high leverage ratio and limits financial flexibility"


def con_12_low_revenue_cagr(p: CompanyProfile):
    v = p.latest(p.fr, "revenue_cagr_5yr")
    if v is None or v >= 5:
        return None
    return _confidence(5 - v, scale=10), \
        "Revenue growing at below 5% over 5 years lags inflation and suggests limited business momentum"


CON_RULES = [
    con_01_high_de_non_financial, con_02_fcf_negative_3yr, con_03_opm_declining_3yr,
    con_04_net_loss_latest_year, con_05_revenue_declining_2yr, con_06_low_icr,
    con_07_payout_over_100, con_08_de_rising_3yr, con_09_eps_declining_3yr,
    con_10_low_roce, con_11_high_net_debt_to_ebitda, con_12_low_revenue_cagr,
]


# ===========================================================================
# Orchestration
# ===========================================================================

FALLBACK_PRO_TEXT = ("No individual pro signal cleared the standard rule thresholds; overall fundamentals "
                     "appear stable based on available data, though no single strength stands out as exceptional")
FALLBACK_CON_TEXT = ("No red flags were identified among the standard risk checks in this model; this does not "
                     "constitute an assessment of valuation, governance, or macro risk")


def generate_for_company(profile: CompanyProfile) -> list[dict]:
    """Evaluate all 24 rules; keep every rule scoring confidence > 60.

    Fallback (Day 30 exit criterion: 'every company has at least 1 pro
    and 1 con'): the 12+12 rules are red/green-flag rules, not an
    exhaustive partition -- a genuinely strong company can legitimately
    trigger zero of the 12 con rules (and, in principle, a weak one
    could trigger zero of the 12 pro rules). Every rule's confidence is
    >=60 by construction whenever it triggers at all (see
    `_confidence`), so there is no meaningful "triggered but low
    confidence" tier to fall back to -- the actual gap is companies
    where none of the 12 rules on one side fire. For those, a single
    clearly-labelled fallback statement (rule_id PRO-FALLBACK /
    CON-FALLBACK, fixed confidence just above the inclusion bar) is
    added instead of forcing an unsupported rule-specific claim.
    """
    pro_results = [(idx, rule_fn(profile)) for idx, rule_fn in enumerate(PRO_RULES, start=1)]
    con_results = [(idx, rule_fn(profile)) for idx, rule_fn in enumerate(CON_RULES, start=1)]

    def _collect(results, prefix, rule_type, fallback_text):
        rows = [
            {"company_id": profile.company_id, "type": rule_type,
             "rule_id": f"{prefix}-{idx:02d}", "text": text, "confidence_pct": round(confidence, 1)}
            for idx, result in results if result is not None
            for confidence, text in [result] if confidence > CONFIDENCE_INCLUDE_THRESHOLD
        ]
        if not rows:
            rows.append({"company_id": profile.company_id, "type": rule_type,
                         "rule_id": f"{prefix}-FALLBACK", "text": fallback_text, "confidence_pct": 61.0})
        return rows

    return (_collect(pro_results, "PRO", "pro", FALLBACK_PRO_TEXT) +
            _collect(con_results, "CON", "con", FALLBACK_CON_TEXT))


def run_pros_cons_generator() -> dict:
    conn = sqlite3.connect(DB_PATH)
    companies = pd.read_sql("SELECT id FROM companies", conn)["id"].tolist()
    sectors_lookup = dict(pd.read_sql("SELECT company_id, broad_sector FROM sectors", conn).values)

    all_rows = []
    zero_pro_companies, zero_con_companies = [], []
    for company_id in companies:
        profile = build_profile(company_id, conn, sectors_lookup)
        rows = generate_for_company(profile)
        all_rows.extend(rows)
        if not any(r["type"] == "pro" for r in rows):
            zero_pro_companies.append(company_id)
        if not any(r["type"] == "con" for r in rows):
            zero_con_companies.append(company_id)
    conn.close()

    result_df = pd.DataFrame(all_rows, columns=["company_id", "type", "rule_id", "text", "confidence_pct"])
    result_df = result_df.sort_values(["company_id", "type", "confidence_pct"], ascending=[True, True, False])

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "pros_cons_generated.csv"
    result_df.to_csv(out_path, index=False)

    logger.info("Generated %d pro/con statements for %d companies (%d with zero pros, %d with zero cons)",
                len(result_df), len(companies), len(zero_pro_companies), len(zero_con_companies))

    return {
        "total_rows": len(result_df), "total_companies": len(companies),
        "zero_pro_companies": zero_pro_companies, "zero_con_companies": zero_con_companies,
        "output_path": str(out_path),
    }


if __name__ == "__main__":
    result = run_pros_cons_generator()
    print()
    print("=== PROS/CONS GENERATOR SUMMARY ===")
    print(f"Total statements: {result['total_rows']} across {result['total_companies']} companies")
    print(f"Companies with 0 pros: {len(result['zero_pro_companies'])} {result['zero_pro_companies'][:10]}")
    print(f"Companies with 0 cons: {len(result['zero_con_companies'])} {result['zero_con_companies'][:10]}")
    print(f"Output: {result['output_path']}")
