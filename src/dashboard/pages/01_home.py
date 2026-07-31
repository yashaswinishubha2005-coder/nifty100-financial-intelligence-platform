"""
pages/01_home.py — Home screen.

Sprint 4, Day 23 deliverable (Epic 05, Module 2).

6 summary KPI tiles, a sector-breakdown donut chart, a top-5-by-
composite-score table, and a sidebar year selector (2019-2024,
matching market_cap's native calendar-year range) that all of the
above respond to.

Note on sector count: the spec's Day 23 bullet describes "11 sectors"
for the donut chart, but the actual `sectors.broad_sector`
classification in this dataset has 10 distinct values (11 is the peer
*group* count from Sprint 3, a different classification). The chart
below renders however many broad sectors are actually present rather
than hard-coding an incorrect count.
"""

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.ui import configure_page, fmt, BRAND_PURPLE, BRAND_ORANGE  # noqa: E402
from utils.db import get_latest_ratios_universe, get_ratios  # noqa: E402

configure_page("Home", icon="🏠")
st.title("🏠 Home")

YEARS = list(range(2019, 2025))
with st.sidebar:
    st.markdown("### Filters")
    selected_year = st.selectbox("Fiscal year", YEARS, index=len(YEARS) - 1)
    st.caption("Metrics below use each company's fiscal-year ratios matched to the selected calendar year.")

universe = get_latest_ratios_universe()

# --- Rebuild the KPI universe for the selected year (per-company ratios
# for that specific year rather than each company's own latest year) ---
rows = []
for company_id in universe["company_id"]:
    yr_df = get_ratios(company_id, year=selected_year)
    if yr_df.empty:
        continue
    row = yr_df.iloc[-1].to_dict()
    row["company_id"] = company_id
    rows.append(row)
year_ratios = pd.DataFrame(rows)

market = universe[["company_id", "company_name", "broad_sector", "pe_ratio", "composite_quality_score"]]
year_view = year_ratios.merge(market, on="company_id", how="left") if not year_ratios.empty else universe

if year_view.empty:
    st.warning("No data available for the selected year.")
    year_view = universe

# --- 6 KPI tiles ---------------------------------------------------------
avg_roe = year_view["return_on_equity_pct"].astype(float).mean(skipna=True) if "return_on_equity_pct" in year_view else None
median_pe = year_view["pe_ratio"].astype(float).median(skipna=True) if "pe_ratio" in year_view else None
median_de = year_view["debt_to_equity"].astype(float).median(skipna=True) if "debt_to_equity" in year_view else None
total_companies = universe["company_id"].nunique()
median_rev_cagr = year_view["revenue_cagr_5yr"].astype(float).median(skipna=True) if "revenue_cagr_5yr" in year_view else None
debt_free_count = int((year_view.get("icr_label") == "Debt Free").sum()) if "icr_label" in year_view else 0

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Average ROE", fmt(avg_roe, suffix="%"))
c2.metric("Median P/E", fmt(median_pe, suffix="x"))
c3.metric("Median D/E", fmt(median_de))
c4.metric("Total Companies", total_companies)
c5.metric("Median Revenue CAGR 5yr", fmt(median_rev_cagr, suffix="%"))
c6.metric("Debt-Free Companies", debt_free_count)

st.divider()

col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader("Sector Breakdown")
    sector_counts = universe.groupby("broad_sector")["company_id"].nunique().reset_index(name="companies")
    fig = px.pie(
        sector_counts, names="broad_sector", values="companies", hole=0.55,
        color_discrete_sequence=px.colors.sequential.Purples_r,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(showlegend=False, margin=dict(t=10, b=10, l=10, r=10), height=380)
    st.plotly_chart(fig, use_container_width=True)

with col_right:
    st.subheader("Top 5 by Composite Quality Score")
    top5 = universe.dropna(subset=["composite_quality_score"]) \
        .sort_values("composite_quality_score", ascending=False).head(5)
    display = top5[["company_id", "company_name", "broad_sector", "composite_quality_score"]].copy()
    display["composite_quality_score"] = display["composite_quality_score"].round(1)
    display.columns = ["Ticker", "Company", "Sector", "Composite Score"]
    st.dataframe(display, use_container_width=True, hide_index=True)

st.caption(f"Snapshot year: {selected_year} · {len(year_view)} of {total_companies} companies have data for this year.")
