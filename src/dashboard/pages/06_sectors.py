"""
pages/06_sectors.py — Sector Analysis screen.

Sprint 4, Day 25 deliverable (Epic 05, Module 3).

Sector dropdown, a bubble chart (X = Revenue, Y = ROE, bubble size =
Market Cap, colour = sub-sector) via Plotly Express scatter, and a
sector-median KPI bar chart below it.
"""

import sys
from pathlib import Path

import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.ui import configure_page  # noqa: E402
from utils.db import get_latest_ratios_universe, get_latest_pl_snapshot  # noqa: E402

configure_page("Sector Analysis", icon="🏭")
st.title("🏭 Sector Analysis")

universe = get_latest_ratios_universe()
sales = get_latest_pl_snapshot()[["company_id", "sales"]]
data = universe.merge(sales, on="company_id", how="left")

sectors = sorted(data["broad_sector"].dropna().unique().tolist())
with st.sidebar:
    st.markdown("### Sector")
    selected_sector = st.selectbox("Broad sector", sectors)

sector_data = data[data["broad_sector"] == selected_sector].copy()
sector_data = sector_data.dropna(subset=["sales", "return_on_equity_pct", "market_cap_crore"])

st.subheader(f"{selected_sector} — Revenue vs. ROE")
if sector_data.empty:
    st.info("Not enough data to plot this sector (missing Revenue, ROE, or Market Cap).")
else:
    fig = px.scatter(
        sector_data, x="sales", y="return_on_equity_pct", size="market_cap_crore",
        color="sub_sector", hover_name="company_name",
        labels={"sales": "Revenue (₹ Cr)", "return_on_equity_pct": "ROE %", "market_cap_crore": "Market Cap (₹ Cr)"},
        size_max=55,
    )
    fig.update_layout(height=480, margin=dict(t=20, b=20, l=20, r=20))
    st.plotly_chart(fig, use_container_width=True)

st.divider()
st.subheader(f"{selected_sector} — Median KPIs")

kpi_cols = {
    "return_on_equity_pct": "ROE %", "operating_profit_margin_pct": "OPM %",
    "debt_to_equity": "D/E", "pe_ratio": "P/E", "revenue_cagr_5yr": "Revenue CAGR 5yr %",
}
medians = data[data["broad_sector"] == selected_sector][list(kpi_cols.keys())].median(skipna=True)
median_df = medians.rename(index=kpi_cols).reset_index()
median_df.columns = ["Metric", "Median"]

fig2 = px.bar(median_df, x="Metric", y="Median", color="Metric",
              color_discrete_sequence=px.colors.sequential.Purples_r)
fig2.update_layout(height=360, showlegend=False, margin=dict(t=20, b=20, l=20, r=20))
st.plotly_chart(fig2, use_container_width=True)

st.caption(f"{len(data[data['broad_sector'] == selected_sector])} companies in {selected_sector}.")
