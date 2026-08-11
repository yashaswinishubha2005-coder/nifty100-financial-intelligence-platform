"""
src/dashboard/utils/db.py — Shared, cached SQLite data-access layer for
the Nifty 100 Financial Intelligence Platform Streamlit dashboard.

Sprint 4, Day 22 deliverable (Epic 05, Module 1).

Every query function is decorated with @st.cache_data(ttl=600) so that
repeated navigation between screens (and Streamlit's rerun-on-every-
interaction model) doesn't re-hit SQLite on every widget change. The
underlying sqlite3 connection itself is cached separately with
@st.cache_resource (a connection object is not a plain, hashable value
and must not be re-created on every cached-data call).

Design notes
------------
Several source tables carry two different notions of "year":
    - financial_ratios.year / profitandloss.year / balancesheet.year /
      cashflow.year are *fiscal* labels normalised to 'YYYY-MM' by the
      Sprint 1 ETL pipeline (see src/etl/normaliser.py).
    - market_cap.year is a plain *calendar* year integer (2019-2024).
The Home screen's year selector (Day 23) is calendar-based (2019-2024,
matching market_cap's native range). get_latest_ratios_universe() and
get_ratios() accept an optional calendar `year` and match it against
the fiscal label by prefix (`year LIKE 'YYYY%'`), falling back to the
most recent fiscal year at or before that calendar year when a company
has no exact-year row -- documented simplification, not a strict
fiscal/calendar crosswalk.

Several companies carry a trailing interim data row (e.g. '2024-09')
where most ratio columns are NULL (see src/screener/engine.py's
_latest_year_rows for the original discovery of this). The same
"latest complete row" selection is reused here so dashboard KPI tiles
don't silently show blank values for the most recent fiscal year.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DB_PATH = PROJECT_ROOT / "data" / "nifty100.db"


@st.cache_resource
def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _read_sql(query: str, params: tuple = ()) -> pd.DataFrame:
    return pd.read_sql(query, _get_connection(), params=params)


def _latest_complete_rows(df: pd.DataFrame, require_col: str,
                           group_col: str = "company_id", year_col: str = "year") -> pd.DataFrame:
    """Latest `year` row per company, preferring rows where `require_col`
    is not null (skips trailing interim stub rows). See module docstring."""
    if df.empty:
        return df
    sorted_df = df.sort_values(year_col)
    complete = sorted_df[sorted_df[require_col].notna()]
    idx = complete.groupby(group_col).tail(1).index
    missing = set(df[group_col]) - set(df.loc[idx, group_col])
    if missing:
        fallback = sorted_df[sorted_df[group_col].isin(missing)].groupby(group_col).tail(1).index
        idx = idx.append(fallback)
    return df.loc[idx].reset_index(drop=True)


# ===========================================================================
# Day 22 — required loader functions
# ===========================================================================

@st.cache_data(ttl=600)
def get_companies() -> pd.DataFrame:
    """All 92 companies joined with sector classification."""
    return _read_sql("""
        SELECT c.id AS company_id, c.company_name, c.about_company, c.website,
               c.nse_profile, c.bse_profile, c.face_value, c.book_value,
               c.roce_percentage, c.roe_percentage,
               s.broad_sector, s.sub_sector, s.index_weight_pct, s.market_cap_category
        FROM companies c
        LEFT JOIN sectors s ON s.company_id = c.id
        ORDER BY c.company_name
    """)


@st.cache_data(ttl=600)
def get_ratios(ticker: str, year: Optional[int] = None) -> pd.DataFrame:
    """Financial ratio history for one company. If `year` (calendar int)
    is given, returns only the row matching that fiscal year (by 'YYYY%'
    prefix, falling back to the latest fiscal year at or before it);
    otherwise returns the full multi-year history sorted ascending."""
    df = _read_sql("SELECT * FROM financial_ratios WHERE company_id = ? ORDER BY year", (ticker,))
    if year is None or df.empty:
        return df
    exact = df[df["year"].str.startswith(str(year))]
    if not exact.empty:
        return exact
    earlier = df[df["year"] <= f"{year}-12"]
    return earlier.tail(1) if not earlier.empty else df.tail(1)


@st.cache_data(ttl=600)
def get_pl(ticker: str) -> pd.DataFrame:
    """Profit & Loss history for one company, ascending by fiscal year."""
    return _read_sql("SELECT * FROM profitandloss WHERE company_id = ? ORDER BY year", (ticker,))


@st.cache_data(ttl=600)
def get_bs(ticker: str) -> pd.DataFrame:
    """Balance sheet history for one company, ascending by fiscal year."""
    return _read_sql("SELECT * FROM balancesheet WHERE company_id = ? ORDER BY year", (ticker,))


@st.cache_data(ttl=600)
def get_cf(ticker: str) -> pd.DataFrame:
    """Cash flow statement history for one company, ascending by fiscal year."""
    return _read_sql("SELECT * FROM cashflow WHERE company_id = ? ORDER BY year", (ticker,))


@st.cache_data(ttl=600)
def get_sectors() -> pd.DataFrame:
    """The full sectors table (one row per company)."""
    return _read_sql("SELECT * FROM sectors")


@st.cache_data(ttl=600)
def get_peers(group_name: str) -> pd.DataFrame:
    """Companies in `group_name` joined with their latest-year ratios,
    company name, and is_benchmark flag."""
    members = _read_sql(
        "SELECT company_id, is_benchmark FROM peer_groups WHERE peer_group_name = ?", (group_name,)
    )
    if members.empty:
        return members
    ratios = get_latest_ratios_universe()
    merged = members.merge(ratios, on="company_id", how="left")
    return merged.sort_values("composite_quality_score", ascending=False, na_position="last")


@st.cache_data(ttl=600)
def get_valuation(ticker: str) -> pd.DataFrame:
    """Valuation row(s) for one company from the `valuation` table
    (populated by src/analytics/valuation.py, Day 26)."""
    return _read_sql("SELECT * FROM valuation WHERE company_id = ? ORDER BY year", (ticker,))


# ===========================================================================
# Additional helpers used across screens (not in the Day 22 required
# list verbatim, but needed to implement Days 23-25 without duplicating
# SQL in every page file)
# ===========================================================================

@st.cache_data(ttl=600)
def get_prosandcons(ticker: str) -> pd.DataFrame:
    """Pros/cons bullet rows for one company. Most companies (88/92)
    have none -- callers must handle an empty result gracefully."""
    return _read_sql("SELECT pros, cons FROM prosandcons WHERE company_id = ?", (ticker,))


@st.cache_data(ttl=600)
def get_documents(ticker: str) -> pd.DataFrame:
    """Annual report links for one company. Some annual_report_url
    values are the literal string 'Null' (a data-source artifact, not a
    genuine SQL NULL) -- normalised to real NaN here so callers can use
    a single `.isna()` check."""
    df = _read_sql(
        "SELECT report_year, annual_report_url FROM documents WHERE company_id = ? ORDER BY report_year DESC",
        (ticker,),
    )
    if not df.empty:
        df["annual_report_url"] = df["annual_report_url"].replace({"Null": None, "null": None, "": None})
    return df


@st.cache_data(ttl=600)
def get_capital_allocation() -> pd.DataFrame:
    """Latest-year capital-allocation pattern per company, from
    output/capital_allocation.csv (Sprint 2, Day 11 deliverable)."""
    path = PROJECT_ROOT / "output" / "capital_allocation.csv"
    if not path.exists():
        return pd.DataFrame(columns=["company_id", "year", "pattern_label"])
    df = pd.read_csv(path)
    return _latest_complete_rows(df, "pattern_label")


@st.cache_data(ttl=600)
def get_latest_ratios_universe() -> pd.DataFrame:
    """The core 92-company, latest-complete-year snapshot used by the
    Home and Screener screens: companies + sectors + financial_ratios
    + market_cap, one row per company."""
    companies = get_companies()

    fr_all = _read_sql("SELECT * FROM financial_ratios")
    for col in fr_all.columns:
        if col not in ("company_id", "year", "icr_label"):
            fr_all[col] = pd.to_numeric(fr_all[col], errors="coerce")
    fr = _latest_complete_rows(fr_all, "return_on_equity_pct")

    mc_all = _read_sql("SELECT * FROM market_cap")
    mc_all["year"] = mc_all["year"].astype(str)
    mc = _latest_complete_rows(mc_all, "pe_ratio")

    val = _read_sql("SELECT company_id, fcf_yield_pct, flag AS valuation_flag FROM valuation")

    df = (
        companies
        .merge(fr, on="company_id", how="left", suffixes=("", "_fr"))
        .merge(mc[["company_id", "market_cap_crore", "pe_ratio", "pb_ratio", "dividend_yield_pct", "ev_ebitda"]],
               on="company_id", how="left")
        .merge(val, on="company_id", how="left")
    )
    df["interest_coverage_for_filter"] = df["interest_coverage"].where(
        df["icr_label"] != "Debt Free", other=float("inf")
    )
    return df


@st.cache_data(ttl=600)
def get_peer_percentiles(company_id: str) -> pd.DataFrame:
    """Percentile-rank rows for one company (from Sprint 3's
    peer_percentiles table), used by the Peer Comparison radar chart."""
    return _read_sql("SELECT * FROM peer_percentiles WHERE company_id = ?", (company_id,))


@st.cache_data(ttl=600)
def get_peer_group_names() -> list[str]:
    df = _read_sql("SELECT DISTINCT peer_group_name FROM peer_groups ORDER BY peer_group_name")
    return df["peer_group_name"].tolist()


@st.cache_data(ttl=600)
def get_screener_universe() -> tuple[pd.DataFrame, dict]:
    """The Sprint 3 screener engine's universe + composite quality score
    (src/screener/engine.py's build_universe + compute_composite_scores),
    reused as-is so the Screener screen's numbers match
    output/screener_output.xlsx exactly rather than recomputing a
    second, slightly different composite score.

    Returns a `(universe, config)` tuple, not a single DataFrame.
    """
    import importlib
    import importlib.util
    import sys

    # db.py lives under src/dashboard/utils; the project root is three
    # levels above the file and the screener package is two levels above.
    PROJECT_ROOT = Path(__file__).resolve().parents[3]
    SCREENER_ROOT = Path(__file__).resolve().parents[2] / "screener"

    # Keep the screener package importable for the runtime loader.
    if str(SCREENER_ROOT) not in sys.path:
        sys.path.insert(0, str(SCREENER_ROOT))

    # The screener engine may live under src/screener/engine.py; prefer a
    # dynamic import so static tooling and runtime both see the same file.
    try:
        screener_engine = importlib.import_module("engine")
    except ModuleNotFoundError:
        engine_spec = importlib.util.spec_from_file_location(
            "engine", SCREENER_ROOT / "engine.py"
        )
        if engine_spec is None or engine_spec.loader is None:
            raise
        screener_engine = importlib.util.module_from_spec(engine_spec)
        engine_spec.loader.exec_module(screener_engine)

    conn = _get_connection()
    config = screener_engine.load_config()
    universe = screener_engine.build_universe(conn)
    universe = screener_engine.compute_composite_scores(universe, config, conn)
    return universe, config


@st.cache_data(ttl=600)
def get_latest_pl_snapshot() -> pd.DataFrame:
    """Latest-complete-year Sales and Net Profit per company, used by
    the Sector Analysis bubble chart's Revenue axis (financial_ratios
    doesn't carry a raw Sales figure, only derived ratios)."""
    pl = _read_sql("SELECT company_id, year, sales, net_profit FROM profitandloss")
    return _latest_complete_rows(pl, "sales")


@st.cache_data(ttl=600)
def get_roce_series(ticker: str) -> pd.DataFrame:
    """Per-year ROCE for one company, computed on the fly from
    profitandloss + balancesheet using the Sprint 2 formula
    (src/analytics/ratios.py's compute_ebit + return_on_capital_employed).

    financial_ratios does not persist a per-year ROCE column -- Sprint
    2's ratio engine only computed ROCE transiently for a Day-13
    latest-year cross-check against companies.roce_percentage (a single
    snapshot value), not as a stored time series. The Company Profile
    and Trend Analysis screens need multi-year ROCE, so it is
    recomputed here using the same formula rather than left as a gap.
    """
    import sys
    src_root = PROJECT_ROOT / "src" / "analytics"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    from ratios import compute_ebit, return_on_capital_employed  # local import: keeps db.py import-light for pages that don't need it

    pl = get_pl(ticker)
    bs = get_bs(ticker)
    if pl.empty or bs.empty:
        return pd.DataFrame(columns=["year", "roce_pct"])

    merged = pl.merge(bs, on=["company_id", "year"], suffixes=("_pl", "_bs"))
    rows = []
    for _, r in merged.iterrows():
        ebit = compute_ebit(r.get("operating_profit"), r.get("other_income"), r.get("depreciation"))
        roce = return_on_capital_employed(ebit, r.get("equity_capital"), r.get("reserves"), r.get("borrowings"))
        rows.append({"year": r["year"], "roce_pct": roce})
    return pd.DataFrame(rows)
