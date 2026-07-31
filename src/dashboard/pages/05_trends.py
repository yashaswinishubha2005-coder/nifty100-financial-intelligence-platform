"""
pages/05_trends.py — Trend Analysis screen.

Sprint 4, Day 25 deliverable (Epic 05, Module 3).

Company search box, a multi-metric selector (overlay up to 3 metrics
on one chart), and a 10-year line chart with a YoY % change annotation
on every data point.
"""

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.ui import configure_page  # noqa: E402
from utils.db import get_companies, get_ratios, get_roce_series, get_pl  # noqa: E402

configure_page("Trend Analysis", icon="📈")
st.title("📈 Trend Analysis")

companies = get_companies()
options = [f"{r.company_id} — {r.company_name}" for r in companies.itertuples()]

with st.sidebar:
    st.markdown("### Company")
    search_text = st.text_input("Search company name or ticker", "")

filtered = [o for o in options if search_text.strip().lower() in o.lower()] if search_text.strip() else options
if not filtered:
    st.warning("Ticker not found — please try another")
    st.stop()

choice = st.selectbox("Company", filtered)
ticker = choice.split(" — ")[0]

METRICS = {
    "ROE %": ("ratios", "return_on_equity_pct"),
    "ROCE %": ("roce", "roce_pct"),
    "Net Profit Margin %": ("ratios", "net_profit_margin_pct"),
    "Operating Profit Margin %": ("ratios", "operating_profit_margin_pct"),
    "D/E": ("ratios", "debt_to_equity"),
    "Free Cash Flow (₹ Cr)": ("ratios", "free_cash_flow_cr"),
    "Revenue (₹ Cr)": ("pl", "sales"),
    "Net Profit (₹ Cr)": ("pl", "net_profit"),
    "EPS (₹)": ("ratios", "earnings_per_share"),
}

selected_metrics = st.multiselect(
    "Metrics to overlay (up to 3)", list(METRICS.keys()),
    default=["ROE %", "Revenue (₹ Cr)"], max_selections=3,
)

if not selected_metrics:
    st.info("Select at least one metric to plot.")
    st.stop()

ratios_hist = get_ratios(ticker).tail(10)
roce_hist = get_roce_series(ticker).tail(10)
pl_hist = get_pl(ticker).tail(10)

fig = go.Figure()
colors = ["#6D28D9", "#F97316", "#1E1B4B"]

for i, metric_label in enumerate(selected_metrics):
    source, col = METRICS[metric_label]
    if source == "ratios":
        df = ratios_hist[["year", col]].rename(columns={col: "value"})
    elif source == "roce":
        df = roce_hist.rename(columns={"roce_pct": "value"})
    else:
        df = pl_hist[["year", col]].rename(columns={col: "value"})

    df = df.dropna(subset=["value"])
    if df.empty:
        st.caption(f"No data available for {metric_label}.")
        continue

    yoy_pct = df["value"].pct_change() * 100
    annotations = [f"{v:+.1f}%" if pd.notna(v) else "" for v in yoy_pct]

    fig.add_trace(go.Scatter(
        x=df["year"], y=df["value"], name=metric_label, mode="lines+markers+text",
        text=annotations, textposition="top center", textfont=dict(size=10),
        line=dict(color=colors[i % len(colors)]),
    ))

fig.update_layout(height=480, title=f"{ticker} — trend over the last 10 years",
                   margin=dict(t=60, b=20, l=20, r=20), hovermode="x unified")
st.plotly_chart(fig, use_container_width=True)
st.caption("Annotations show year-over-year % change for each metric at each data point.")
