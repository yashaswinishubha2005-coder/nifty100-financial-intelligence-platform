"""
src/analytics/ratios.py — Profitability, leverage, and efficiency ratio
formulas for the Nifty 100 Financial Intelligence Platform.

Sprint 2, Day 08-09 deliverable (Epic 02, Module 2).

Every function here takes plain numeric inputs (already joined from
profitandloss / balancesheet / cashflow / companies) and returns either
a float or None -- never raises on a bad denominator. Division-by-zero
and invalid-domain cases are handled explicitly per the sprint spec
rather than relying on exceptions, so the ratio engine can populate a
whole table without special-casing every row.

Sign convention: `borrowings`, `investments`, `equity_capital`,
`reserves` etc. are passed in exactly as stored in balancesheet /
profitandloss (crore, as-reported).
"""

from __future__ import annotations
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _safe_div(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    """Return numerator/denominator, or None if either operand is missing
    or the denominator is exactly zero."""
    if numerator is None or denominator is None:
        return None
    if denominator == 0:
        return None
    return numerator / denominator


# ===========================================================================
# Day 08 — Profitability ratios
# ===========================================================================

def net_profit_margin(net_profit: Optional[float], sales: Optional[float]) -> Optional[float]:
    """Net Profit Margin % = net_profit / sales x 100. None if sales == 0."""
    if net_profit is None or sales is None or sales == 0:
        return None
    return net_profit / sales * 100


def operating_profit_margin(operating_profit: Optional[float], sales: Optional[float]) -> Optional[float]:
    """Operating Profit Margin % = operating_profit / sales x 100. None if sales == 0."""
    if operating_profit is None or sales is None or sales == 0:
        return None
    return operating_profit / sales * 100


def opm_cross_check(computed_opm: Optional[float], source_opm_percentage: Optional[float],
                     company_id: str = "", year: str = "", tolerance_pct: float = 1.0) -> Optional[float]:
    """
    Cross-check the computed OPM against the source `opm_percentage` field.
    Returns the absolute difference (in percentage points) and logs a
    warning if it exceeds `tolerance_pct`. Returns None if either input
    is missing (nothing to compare).
    """
    if computed_opm is None or source_opm_percentage is None:
        return None
    diff = abs(computed_opm - source_opm_percentage)
    if diff > tolerance_pct:
        logger.warning(
            "OPM cross-check mismatch: %s %s computed=%.2f source=%.2f diff=%.2f (> %.1f pp tolerance)",
            company_id, year, computed_opm, source_opm_percentage, diff, tolerance_pct,
        )
    return diff


def return_on_equity(net_profit: Optional[float], equity_capital: Optional[float],
                      reserves: Optional[float]) -> Optional[float]:
    """ROE % = net_profit / (equity_capital + reserves) x 100.
    None if equity_capital + reserves <= 0 (including negative equity)."""
    if net_profit is None or equity_capital is None or reserves is None:
        return None
    denom = equity_capital + reserves
    if denom <= 0:
        return None
    return net_profit / denom * 100


def return_on_capital_employed(ebit: Optional[float], equity_capital: Optional[float],
                                reserves: Optional[float], borrowings: Optional[float]) -> Optional[float]:
    """ROCE % = EBIT / (equity_capital + reserves + borrowings) x 100.
    None if capital employed <= 0.

    Note: for companies in the Financials broad_sector, callers should
    interpret this value against a *sector-relative* benchmark (peer
    average ROCE) rather than a fixed absolute threshold -- banks/NBFCs
    structurally run low ROCE because "borrowings" (customer deposits /
    wholesale funding) dominates capital employed. See
    `classify_roce_for_sector` below; the formula itself is unchanged.
    """
    if ebit is None or equity_capital is None or reserves is None or borrowings is None:
        return None
    capital_employed = equity_capital + reserves + borrowings
    if capital_employed <= 0:
        return None
    return ebit / capital_employed * 100


def classify_roce_for_sector(roce_pct: Optional[float], broad_sector: Optional[str],
                              sector_avg_roce: Optional[float] = None,
                              absolute_threshold: float = 15.0) -> Optional[str]:
    """
    Classify a company's ROCE as 'Strong' / 'Weak' relative to an
    appropriate benchmark: for Financials, compare against the
    sector-average ROCE (structurally different capital structure);
    for every other sector, compare against a fixed absolute threshold.
    Returns None if roce_pct is None or (for Financials) no sector
    average is available.
    """
    if roce_pct is None:
        return None
    if broad_sector == "Financials":
        if sector_avg_roce is None:
            return None
        return "Strong" if roce_pct >= sector_avg_roce else "Weak"
    return "Strong" if roce_pct >= absolute_threshold else "Weak"


def return_on_assets(net_profit: Optional[float], total_assets: Optional[float]) -> Optional[float]:
    """ROA % = net_profit / total_assets x 100. None if total_assets == 0."""
    if net_profit is None or total_assets is None or total_assets == 0:
        return None
    return net_profit / total_assets * 100


# ===========================================================================
# Day 09 — Leverage & efficiency ratios
# ===========================================================================

def debt_to_equity(borrowings: Optional[float], equity_capital: Optional[float],
                    reserves: Optional[float]) -> Optional[float]:
    """D/E = borrowings / (equity_capital + reserves).
    Returns 0.0 (not None) if borrowings == 0 (debt-free company), even
    if equity+reserves is otherwise unusable. Returns None if borrowings
    is non-zero but equity+reserves <= 0 (division is not meaningful)."""
    if borrowings is None:
        return None
    if borrowings == 0:
        return 0.0
    if equity_capital is None or reserves is None:
        return None
    denom = equity_capital + reserves
    if denom <= 0:
        return None
    return borrowings / denom


def high_leverage_flag(de_ratio: Optional[float], broad_sector: Optional[str]) -> bool:
    """True if D/E > 5 and the company is NOT in the Financials sector
    (high leverage is structurally normal for banks/NBFCs/insurers)."""
    if de_ratio is None:
        return False
    if broad_sector == "Financials":
        return False
    return de_ratio > 5


def interest_coverage(operating_profit: Optional[float], other_income: Optional[float],
                       interest: Optional[float]) -> Optional[float]:
    """ICR = (operating_profit + other_income) / interest. None if interest == 0."""
    if operating_profit is None or interest is None:
        return None
    if interest == 0:
        return None
    oi = other_income or 0
    return (operating_profit + oi) / interest


def icr_label(icr: Optional[float]) -> Optional[str]:
    """Display label for ICR. 'Debt Free' when ICR is None because
    interest expense is zero; None (no label) otherwise."""
    return "Debt Free" if icr is None else None


def icr_risk_flag(icr: Optional[float], threshold: float = 1.5) -> bool:
    """True if ICR is not None and below `threshold` (at risk of not
    covering interest payments). Debt-free companies (ICR=None) are not
    at risk, so this is False for them."""
    if icr is None:
        return False
    return icr < threshold


def net_debt(borrowings: Optional[float], investments: Optional[float]) -> Optional[float]:
    """Net Debt = borrowings - investments (investments used as a liquid-asset proxy)."""
    if borrowings is None or investments is None:
        return None
    return borrowings - investments


def asset_turnover(sales: Optional[float], total_assets: Optional[float]) -> Optional[float]:
    """Asset Turnover = sales / total_assets. None if total_assets == 0."""
    if sales is None or total_assets is None or total_assets == 0:
        return None
    return sales / total_assets


# ===========================================================================
# Derived helpers used by the Day 12 population driver below
# ===========================================================================

def compute_ebit(operating_profit: Optional[float], other_income: Optional[float],
                  depreciation: Optional[float]) -> Optional[float]:
    """
    EBIT (earnings before interest & tax) = operating_profit + other_income
    - depreciation. Derived from this dataset's P&L structure, where
    profit_before_tax = operating_profit + other_income - interest - depreciation,
    i.e. EBIT = profit_before_tax + interest = operating_profit + other_income - depreciation.
    """
    if operating_profit is None or other_income is None or depreciation is None:
        return None
    return operating_profit + other_income - depreciation


def compute_book_value_per_share(equity_capital: Optional[float], reserves: Optional[float],
                                  face_value: Optional[float]) -> Optional[float]:
    """
    Book Value per Share = (equity_capital + reserves) / shares_outstanding,
    where shares_outstanding is derived from equity_capital / face_value
    (equity_capital = shares_outstanding x face_value, both already in the
    same currency unit in this dataset). Equivalent form used here avoids
    a separate shares-outstanding lookup:
        BVPS = (equity_capital + reserves) / equity_capital * face_value
    None if equity_capital or face_value is missing/zero.
    """
    if equity_capital is None or reserves is None or face_value is None or equity_capital == 0:
        return None
    return (equity_capital + reserves) / equity_capital * face_value


def compute_composite_quality_score(roe_pct: Optional[float], icr: Optional[float],
                                     cfo_quality_label: Optional[str]) -> Optional[float]:
    """
    Composite Quality Score (0-100): a weighted blend of profitability,
    balance-sheet safety, and cash flow quality. Not specified by an
    exact formula in the sprint spec -- documented design choice:

        profitability (40%): clamp(ROE, 0, 30) / 30 * 100
        safety (30%):        ICR is None (debt-free) or ICR >= 3 -> 100
                              ICR <= 1.5 -> 0, linear in between
        cash quality (30%):  'High Quality' -> 100, 'Moderate' -> 60,
                              'Accrual Risk' -> 20

    Any component that can't be computed (missing input) is dropped and
    the remaining weights are renormalised. Returns None if none of the
    three components can be computed.
    """
    components = []  # (weight, score)

    if roe_pct is not None:
        profitability = max(0.0, min(roe_pct, 30.0)) / 30.0 * 100
        components.append((0.40, profitability))

    if icr is None:
        # None here is ambiguous (debt-free vs missing data); the caller
        # is expected to pass icr=None only for genuinely debt-free
        # companies (interest == 0) per interest_coverage()'s contract,
        # so treat it as maximal safety.
        components.append((0.30, 100.0))
    else:
        if icr >= 3:
            safety = 100.0
        elif icr <= 1.5:
            safety = 0.0
        else:
            safety = (icr - 1.5) / (3 - 1.5) * 100
        components.append((0.30, safety))

    cash_map = {"High Quality": 100.0, "Moderate": 60.0, "Accrual Risk": 20.0}
    if cfo_quality_label in cash_map:
        components.append((0.30, cash_map[cfo_quality_label]))

    if not components:
        return None
    total_weight = sum(w for w, _ in components)
    return sum(w * s for w, s in components) / total_weight


# ===========================================================================
# Day 12-13 — population driver: computes every KPI for all company-years
# and writes them into the financial_ratios table, output/capital_allocation.csv,
# and output/ratio_edge_cases.log. Entry point for `make ratios`.
# ===========================================================================

def populate_financial_ratios_table() -> dict:
    import csv
    import sqlite3
    import sys as _sys
    from pathlib import Path

    _analytics_dir = Path(__file__).resolve().parent
    if str(_analytics_dir) not in _sys.path:
        _sys.path.insert(0, str(_analytics_dir))
    from cagr import cagr_from_series
    from cashflow_kpis import free_cash_flow, cfo_quality_score, classify_capital_allocation

    project_root = _analytics_dir.parents[1] if _analytics_dir.parent.name == "src" else Path.cwd()
    db_path = project_root / "data" / "nifty100.db"
    output_dir = project_root / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    companies = {r["id"]: dict(r) for r in conn.execute(
        "SELECT id, face_value, roce_percentage, roe_percentage FROM companies")}
    sectors = {r["company_id"]: r["broad_sector"] for r in conn.execute(
        "SELECT company_id, broad_sector FROM sectors")}

    pl = {}
    for r in conn.execute("SELECT * FROM profitandloss"):
        pl[(r["company_id"], r["year"])] = dict(r)
    bs = {}
    for r in conn.execute("SELECT * FROM balancesheet"):
        bs[(r["company_id"], r["year"])] = dict(r)
    cf = {}
    for r in conn.execute("SELECT * FROM cashflow"):
        cf[(r["company_id"], r["year"])] = dict(r)

    company_years = {}
    for cid, year in list(pl.keys()) + list(bs.keys()) + list(cf.keys()):
        company_years.setdefault(cid, set()).add(year)

    edge_cases = []
    capital_allocation_rows = []
    ratio_rows = []
    opm_mismatch_count = 0
    opm_mismatches_by_company = {}  # company_id -> list of diffs (pp)

    for cid, years in company_years.items():
        if cid not in companies:
            continue  # DQ-03: shouldn't happen post-FK-enforcement, but stay safe
        years_sorted = sorted(years)
        face_value = companies[cid].get("face_value")
        broad_sector = sectors.get(cid)

        # Build this company's full sales/net_profit/eps series once for CAGR + CFO quality
        sales_series = [(y, pl.get((cid, y), {}).get("sales")) for y in years_sorted]
        pat_series = [(y, pl.get((cid, y), {}).get("net_profit")) for y in years_sorted]
        eps_series = [(y, pl.get((cid, y), {}).get("eps")) for y in years_sorted]
        cfo_series = [(y, cf.get((cid, y), {}).get("operating_activity")) for y in years_sorted]

        for i, year in enumerate(years_sorted):
            p = pl.get((cid, year), {})
            b = bs.get((cid, year), {})
            c = cf.get((cid, year), {})

            sales, net_profit = p.get("sales"), p.get("net_profit")
            operating_profit, opm_source = p.get("operating_profit"), p.get("opm_percentage")
            other_income, interest, depreciation = p.get("other_income"), p.get("interest"), p.get("depreciation")
            eps, dividend_payout = p.get("eps"), p.get("dividend_payout")
            equity_capital, reserves, borrowings = b.get("equity_capital"), b.get("reserves"), b.get("borrowings")
            investments, total_assets = b.get("investments"), b.get("total_assets")
            operating_activity, investing_activity = c.get("operating_activity"), c.get("investing_activity")
            financing_activity = c.get("financing_activity")

            npm = net_profit_margin(net_profit, sales)
            opm = operating_profit_margin(operating_profit, sales)
            opm_diff = opm_cross_check(opm, opm_source, company_id=cid, year=year)
            if opm_diff is not None and opm_diff > 1.0:
                opm_mismatch_count += 1
                opm_mismatches_by_company.setdefault(cid, []).append(opm_diff)
            roe = return_on_equity(net_profit, equity_capital, reserves)
            ebit = compute_ebit(operating_profit, other_income, depreciation)
            roce = return_on_capital_employed(ebit, equity_capital, reserves, borrowings)
            de = debt_to_equity(borrowings, equity_capital, reserves)
            hlf = high_leverage_flag(de, broad_sector)
            icr = interest_coverage(operating_profit, other_income, interest)
            icr_lbl = icr_label(icr)
            icr_risk = icr_risk_flag(icr)
            at = asset_turnover(sales, total_assets)
            fcf = free_cash_flow(operating_activity, investing_activity)
            capex_cr = abs(investing_activity) if investing_activity is not None else None
            bvps = compute_book_value_per_share(equity_capital, reserves, face_value)

            # trailing-5yr CFO/PAT window ending at this year, for composite score
            window_end = i + 1
            window_start = max(0, window_end - 5)
            cfo_pat_pairs = [
                (cf.get((cid, y), {}).get("operating_activity"), pl.get((cid, y), {}).get("net_profit"))
                for y in years_sorted[window_start:window_end]
            ]
            _, cfo_quality_lbl = cfo_quality_score(cfo_pat_pairs)

            rev_cagr, rev_flag = cagr_from_series(sales_series[:window_end], 5)
            pat_cagr, pat_flag = cagr_from_series(pat_series[:window_end], 5)
            eps_cagr, eps_flag = cagr_from_series(eps_series[:window_end], 5)

            composite = compute_composite_quality_score(roe, icr, cfo_quality_lbl)

            ratio_rows.append({
                "company_id": cid, "year": year,
                "net_profit_margin_pct": npm, "operating_profit_margin_pct": opm,
                "return_on_equity_pct": roe, "debt_to_equity": de, "interest_coverage": icr,
                "asset_turnover": at, "free_cash_flow_cr": fcf, "capex_cr": capex_cr,
                "earnings_per_share": eps, "book_value_per_share": bvps,
                "dividend_payout_ratio_pct": dividend_payout, "total_debt_cr": borrowings,
                "cash_from_operations_cr": operating_activity,
                "revenue_cagr_5yr": rev_cagr, "revenue_cagr_5yr_flag": rev_flag,
                "pat_cagr_5yr": pat_cagr, "pat_cagr_5yr_flag": pat_flag,
                "eps_cagr_5yr": eps_cagr, "eps_cagr_5yr_flag": eps_flag,
                "composite_quality_score": composite,
                "icr_label": icr_lbl, "high_leverage_flag": int(hlf), "icr_risk_flag": int(icr_risk),
            })

            # Capital allocation pattern (Day 11 deliverable)
            cfo_pat_ratio = (operating_activity / net_profit) if (operating_activity is not None
                             and net_profit not in (None, 0)) else None
            cfo_s, cfi_s, cff_s, pattern = classify_capital_allocation(
                operating_activity, investing_activity, financing_activity, cfo_pat_ratio)
            capital_allocation_rows.append({
                "company_id": cid, "year": year, "cfo_sign": cfo_s, "cfi_sign": cfi_s,
                "cff_sign": cff_s, "pattern_label": pattern,
            })

            # Day 13: bank ROCE/ROE carve-out cross-check against companies.xlsx
            # pre-computed fields. companies.roce_percentage/roe_percentage are
            # single latest-year snapshots (not a time series), so only compare
            # against each company's most recent year -- comparing every
            # historical year against a single latest-year snapshot would flag
            # normal year-over-year variation as a false anomaly.
            is_latest_year = (year == years_sorted[-1])
            if is_latest_year:
                if broad_sector == "Financials":
                    source_roce = companies[cid].get("roce_percentage")
                    if roce is not None and source_roce is not None and abs(roce - source_roce) > 5:
                        edge_cases.append({
                            "company_id": cid, "year": year, "check": "ROCE",
                            "computed": round(roce, 2), "source": source_roce,
                            "diff": round(abs(roce - source_roce), 2),
                            "category": "formula discrepancy (bank ROCE structurally low vs pre-computed source)",
                        })
                source_roe = companies[cid].get("roe_percentage")
                if roe is not None and source_roe is not None and abs(roe - source_roe) > 5:
                    edge_cases.append({
                        "company_id": cid, "year": year, "check": "ROE",
                        "computed": round(roe, 2), "source": source_roe,
                        "diff": round(abs(roe - source_roe), 2),
                        "category": "data source issue (source roe_percentage appears stale/anomalous)",
                    })

    # --- Write financial_ratios table -------------------------------------
    cols = list(ratio_rows[0].keys()) if ratio_rows else []
    for col in cols:
        try:
            conn.execute(f"ALTER TABLE financial_ratios ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists (schema.sql already declares it)
    conn.execute("DELETE FROM financial_ratios")
    placeholders = ", ".join(["?"] * len(cols))
    conn.executemany(
        f"INSERT INTO financial_ratios ({', '.join(cols)}) VALUES ({placeholders})",
        [[row[c] for c in cols] for row in ratio_rows],
    )
    conn.commit()
    final_count = conn.execute("SELECT COUNT(*) FROM financial_ratios").fetchone()[0]
    conn.close()

    # --- Write output/capital_allocation.csv --------------------------------
    ca_path = output_dir / "capital_allocation.csv"
    with open(ca_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["company_id", "year", "cfo_sign", "cfi_sign", "cff_sign", "pattern_label"])
        writer.writeheader()
        writer.writerows(capital_allocation_rows)

    # --- Write output/ratio_edge_cases.log -----------------------------------
    log_path = output_dir / "ratio_edge_cases.log"
    with open(log_path, "w") as f:
        f.write(f"# ratio_edge_cases.log — {len(edge_cases)} ROE/ROCE anomalies (latest year, computed vs source, diff > 5pp)\n")
        f.write("# category is one of: data source issue | version difference | formula discrepancy\n\n")
        for e in sorted(edge_cases, key=lambda x: (-x["diff"])):
            f.write(
                f"{e['company_id']:12} {e['year']:8} {e['check']:5} "
                f"computed={e['computed']:>8} source={e['source']:>8} diff={e['diff']:>6}  "
                f"[{e['category']}]\n"
            )

        f.write(f"\n\n# --- OPM cross-check anomalies: {len(opm_mismatches_by_company)} companies, "
                 f"{opm_mismatch_count} company-years with |computed - source opm_percentage| > 1pp ---\n")
        f.write("# category: data source issue -- opm_percentage values for these companies are\n")
        f.write("# off by 100x-1000x the expected percentage scale (diffs run into the thousands\n")
        f.write("# of 'percentage points'), i.e. the source field holds an absolute rupee-crore\n")
        f.write("# figure for these companies/years, not a genuine percentage. Concentrated in\n")
        f.write("# Financials (banks/NBFCs/insurers) but also present for a few non-Financials\n")
        f.write("# names (COALINDIA, HINDALCO, HINDUNILVR, CIPLA, INDIGO, HEROMOTOCO). The ratio\n")
        f.write("# engine's own computed operating_profit_margin_pct is used for analytics;\n")
        f.write("# opm_percentage is not usable for these companies. Not fixable by the loader --\n")
        f.write("# flagged for the data-source owner.\n\n")
        for cid, diffs in sorted(opm_mismatches_by_company.items(), key=lambda kv: -max(kv[1])):
            f.write(
                f"{cid:12} sector={sectors.get(cid, '?'):24} "
                f"years_affected={len(diffs):2} min_diff={min(diffs):>10.1f} max_diff={max(diffs):>10.1f}  "
                f"[data source issue]\n"
            )

    return {
        "financial_ratios_rows": final_count,
        "capital_allocation_rows": len(capital_allocation_rows),
        "edge_cases": len(edge_cases),
        "opm_mismatches": opm_mismatch_count,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    result = populate_financial_ratios_table()
    print()
    print("=== RATIO ENGINE SUMMARY ===")
    print(f"financial_ratios rows: {result['financial_ratios_rows']}")
    print(f"capital_allocation.csv rows: {result['capital_allocation_rows']}")
    print(f"ratio_edge_cases.log entries (latest-year ROE/ROCE only): {result['edge_cases']}")
    print(f"OPM cross-check mismatches (>1pp, all years, console-logged): {result['opm_mismatches']}")
