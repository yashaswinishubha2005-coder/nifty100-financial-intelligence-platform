"""
tests/nlp/test_pros_cons_generator.py — Sprint 5, Day 30 unit tests for
src/nlp/pros_cons_generator.py.
"""

import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src" / "nlp"))

from pros_cons_generator import (
    CompanyProfile, _confidence, _all_above, _all_below,
    _is_monotonic_increasing, _is_monotonic_decreasing,
    pro_01_high_sustained_roe, pro_03_debt_free, con_04_net_loss_latest_year,
    con_01_high_de_non_financial, generate_for_company, build_profile,
    PRO_RULES, CON_RULES, CONFIDENCE_INCLUDE_THRESHOLD,
)

DB_PATH = PROJECT_ROOT / "data" / "nifty100.db"


def _make_profile(company_id="TEST", fr_rows=None, pl_rows=None, bs_rows=None, mc_rows=None, broad_sector=None):
    fr = pd.DataFrame(fr_rows or [])
    pl = pd.DataFrame(pl_rows or [])
    bs = pd.DataFrame(bs_rows or [])
    mc = pd.DataFrame(mc_rows or [])
    for df_, cols in [(fr, ["company_id", "year", "return_on_equity_pct", "debt_to_equity",
                             "free_cash_flow_cr", "interest_coverage", "icr_label",
                             "revenue_cagr_5yr", "pat_cagr_5yr", "eps_cagr_5yr",
                             "operating_profit_margin_pct", "dividend_payout_ratio_pct", "earnings_per_share"]),
                       (pl, ["company_id", "year", "sales", "net_profit", "operating_profit", "other_income", "depreciation"]),
                       (bs, ["company_id", "year", "total_assets", "borrowings", "equity_capital", "reserves"]),
                       (mc, ["company_id", "year", "market_cap_crore", "enterprise_value_crore", "ev_ebitda", "dividend_yield_pct"])]:
        for c in cols:
            if c not in df_.columns:
                df_[c] = pd.Series(dtype="object")
    return CompanyProfile(company_id, fr, pl, bs, mc, broad_sector)


# ===========================================================================
# Helper functions
# ===========================================================================

class TestHelpers:
    def test_confidence_at_zero_margin_is_60(self):
        assert _confidence(0, scale=10) == 60.0

    def test_confidence_at_full_scale_is_100(self):
        assert _confidence(10, scale=10) == 100.0

    def test_confidence_clips_above_100(self):
        assert _confidence(1000, scale=10) == 100.0

    def test_all_above_requires_full_window(self):
        assert _all_above(pd.Series([21, 22, 23]), 20, 3) == True  # noqa: E712
        assert _all_above(pd.Series([21, 19, 23]), 20, 3) == False  # noqa: E712
        assert _all_above(pd.Series([21, 22]), 20, 3) == False  # noqa: E712 (not enough years)

    def test_all_below(self):
        assert _all_below(pd.Series([-1, -2, -3]), 0, 3) == True  # noqa: E712
        assert _all_below(pd.Series([-1, 2, -3]), 0, 3) == False  # noqa: E712

    def test_monotonic_increasing(self):
        assert _is_monotonic_increasing(pd.Series([10, 15, 20]), 3) == True  # noqa: E712
        assert _is_monotonic_increasing(pd.Series([10, 20, 15]), 3) == False  # noqa: E712

    def test_monotonic_decreasing(self):
        assert _is_monotonic_decreasing(pd.Series([20, 15, 10]), 3) == True  # noqa: E712
        assert _is_monotonic_decreasing(pd.Series([10, 15, 20]), 3) == False  # noqa: E712


# ===========================================================================
# Individual rules with synthetic data
# ===========================================================================

class TestIndividualRules:
    def test_pro_01_triggers_on_sustained_high_roe(self):
        p = _make_profile(fr_rows=[
            {"company_id": "TEST", "year": "2022-03", "return_on_equity_pct": 22},
            {"company_id": "TEST", "year": "2023-03", "return_on_equity_pct": 25},
            {"company_id": "TEST", "year": "2024-03", "return_on_equity_pct": 30},
        ])
        result = pro_01_high_sustained_roe(p)
        assert result is not None
        confidence, text = result
        assert confidence > CONFIDENCE_INCLUDE_THRESHOLD
        assert "return on equity" in text.lower()

    def test_pro_01_does_not_trigger_below_threshold(self):
        p = _make_profile(fr_rows=[
            {"company_id": "TEST", "year": "2022-03", "return_on_equity_pct": 15},
            {"company_id": "TEST", "year": "2023-03", "return_on_equity_pct": 15},
            {"company_id": "TEST", "year": "2024-03", "return_on_equity_pct": 15},
        ])
        assert pro_01_high_sustained_roe(p) is None

    def test_pro_03_debt_free_exact_zero(self):
        p = _make_profile(fr_rows=[{"company_id": "TEST", "year": "2024-03", "debt_to_equity": 0}])
        assert pro_03_debt_free(p) is not None

    def test_pro_03_does_not_trigger_on_nonzero_de(self):
        p = _make_profile(fr_rows=[{"company_id": "TEST", "year": "2024-03", "debt_to_equity": 0.1}])
        assert pro_03_debt_free(p) is None

    def test_con_04_triggers_on_net_loss(self):
        p = _make_profile(pl_rows=[{"company_id": "TEST", "year": "2024-03", "net_profit": -100}])
        assert con_04_net_loss_latest_year(p) is not None

    def test_con_04_does_not_trigger_on_profit(self):
        p = _make_profile(pl_rows=[{"company_id": "TEST", "year": "2024-03", "net_profit": 100}])
        assert con_04_net_loss_latest_year(p) is None

    def test_con_01_skips_financials_sector(self):
        p = _make_profile(fr_rows=[{"company_id": "TEST", "year": "2024-03", "debt_to_equity": 5.0}],
                           broad_sector="Financials")
        assert con_01_high_de_non_financial(p) is None

    def test_con_01_triggers_for_non_financials(self):
        p = _make_profile(fr_rows=[{"company_id": "TEST", "year": "2024-03", "debt_to_equity": 5.0}],
                           broad_sector="Industrials")
        result = con_01_high_de_non_financial(p)
        assert result is not None
        assert "5.00" in result[1]


# ===========================================================================
# generate_for_company — fallback / coverage guarantee
# ===========================================================================

class TestGenerateForCompanyFallback:
    def test_company_with_no_triggered_rules_still_gets_pro_and_con(self):
        # A profile with essentially no data should trigger nothing, but
        # must still get exactly one pro and one con via the fallback.
        p = _make_profile()
        rows = generate_for_company(p)
        pros = [r for r in rows if r["type"] == "pro"]
        cons = [r for r in rows if r["type"] == "con"]
        assert len(pros) >= 1
        assert len(cons) >= 1
        assert pros[0]["rule_id"] == "PRO-FALLBACK"
        assert cons[0]["rule_id"] == "CON-FALLBACK"

    def test_all_rows_reference_valid_rule_ids(self):
        p = _make_profile(fr_rows=[
            {"company_id": "TEST", "year": "2024-03", "return_on_equity_pct": 30, "debt_to_equity": 0},
        ])
        rows = generate_for_company(p)
        valid_ids = {f"PRO-{i:02d}" for i in range(1, 13)} | {f"CON-{i:02d}" for i in range(1, 13)} | \
                    {"PRO-FALLBACK", "CON-FALLBACK"}
        assert all(r["rule_id"] in valid_ids for r in rows)


# ===========================================================================
# Real-data exit criterion: every company has >=1 pro and >=1 con
# ===========================================================================

class TestRealDataCoverage:
    def test_every_company_has_at_least_one_pro_and_one_con(self):
        if not DB_PATH.exists():
            pytest.skip("data/nifty100.db not built yet")
        conn = sqlite3.connect(DB_PATH)
        companies = pd.read_sql("SELECT id FROM companies", conn)["id"].tolist()
        sectors_lookup = dict(pd.read_sql("SELECT company_id, broad_sector FROM sectors", conn).values)

        missing_pro, missing_con = [], []
        for company_id in companies[:15]:  # sample for test speed; full run covered by the module's own CLI output
            profile = build_profile(company_id, conn, sectors_lookup)
            rows = generate_for_company(profile)
            if not any(r["type"] == "pro" for r in rows):
                missing_pro.append(company_id)
            if not any(r["type"] == "con" for r in rows):
                missing_con.append(company_id)
        conn.close()
        assert missing_pro == []
        assert missing_con == []

    def test_all_confidences_above_inclusion_threshold(self):
        if not DB_PATH.exists():
            pytest.skip("data/nifty100.db not built yet")
        conn = sqlite3.connect(DB_PATH)
        sectors_lookup = dict(pd.read_sql("SELECT company_id, broad_sector FROM sectors", conn).values)
        profile = build_profile("TCS", conn, sectors_lookup)
        conn.close()
        rows = generate_for_company(profile)
        assert all(r["confidence_pct"] > CONFIDENCE_INCLUDE_THRESHOLD for r in rows)
