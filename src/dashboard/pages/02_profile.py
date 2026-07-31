"""
pages/02_profile.py — Company Profile screen.

Sprint 4, Day 23 deliverable (Epic 05, Module 2).

Search box with autocomplete (a Streamlit selectbox, which natively
filters its option list as the user types -- the closest native
equivalent to a type-ahead dropdown), company card, 6 KPI tiles, a
10-year Revenue/Net Profit bar chart, an ROE/ROCE dual-axis line
chart, and pros/cons badges.
"""

import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.ui import configure_page, fmt, badge_list  # noqa: E402
from utils.db import (  # noqa: E402
    get_companies, get_pl, get_ratios, get_roce_series, get_prosandcons,
)

configure_page("Company Profile", icon="🏢")
st.title("🏢 Company Profile")

companies = get_companies()
options = [f"{row.company_id} — {row.company_name}" for row in companies.itertuples()]

with st.sidebar:
    st.markdown("### Search")
    search_text = st.text_input("Company name or ticker", "")

filtered = [o for o in options if search_text.strip().lower() in o.lower()] if search_text.strip() else options

if not filtered:
    st.warning("Ticker not found — please try another")
    st.stop()

choice = st.selectbox("Select a company", filtered)
ticker = choice.split(" — ")[0]

row = companies[companies["company_id"] == ticker]
if row.empty:
    st.warning("Ticker not found — please try another")
    st.stop()
row = row.iloc[0]

# --- Company card ---------------------------------------------------------
st.subheader(f"{row['company_name']} ({ticker})")
card_cols = st.columns([2, 1])
with card_cols[0]:
    st.markdown(f"**Sector:** {row['broad_sector'] or 'N/A'}  |  **Sub-sector:** {row['sub_sector'] or 'N/A'}")
    st.markdown(f"**NSE Ticker:** {ticker}")
    about = row.get("about_company")
    st.write(about if isinstance(about, str) and about.strip() else "No company description available.")
with card_cols[1]:
    if isinstance(row.get("website"), str) and row["website"].strip():
        st.link_button("Company Website", row["website"])
    if isinstance(row.get("nse_profile"), str) and row["nse_profile"].strip():
        st.link_button("NSE Profile", row["nse_profile"])

st.divider()

# --- 6 KPI tiles (latest year) --------------------------------------------
ratio_hist = get_ratios(ticker)
latest = ratio_hist.dropna(subset=["return_on_equity_pct"]).tail(1)
latest = latest.iloc[0] if not latest.empty else (ratio_hist.iloc[-1] if not ratio_hist.empty else None)

roce_series = get_roce_series(ticker)
latest_roce = roce_series.dropna(subset=["roce_pct"]).tail(1)
latest_roce_val = latest_roce["roce_pct"].iloc[0] if not latest_roce.empty else None

k1, k2, k3, k4, k5, k6 = st.columns(6)
if latest is not None:
    k1.metric("ROE", fmt(latest.get("return_on_equity_pct"), suffix="%"))
    k2.metric("ROCE", fmt(latest_roce_val, suffix="%"))
    k3.metric("Net Profit Margin", fmt(latest.get("net_profit_margin_pct"), suffix="%"))
    k4.metric("D/E", fmt(latest.get("debt_to_equity")))
    k5.metric("Revenue CAGR 5yr", fmt(latest.get("revenue_cagr_5yr"), suffix="%"))
    k6.metric("FCF (₹ Cr)", fmt(latest.get("free_cash_flow_cr"), decimals=0))
else:
    for c in (k1, k2, k3, k4, k5, k6):
        c.metric("—", "N/A")

st.divider()

# --- 10-year Revenue / Net Profit bar chart --------------------------------
pl = get_pl(ticker).tail(10)
if not pl.empty:
    fig = go.Figure()
    fig.add_bar(x=pl["year"], y=pl["sales"], name="Revenue (₹ Cr)", marker_color="#6D28D9")
    fig.add_bar(x=pl["year"], y=pl["net_profit"], name="Net Profit (₹ Cr)", marker_color="#F97316")
    fig.update_layout(barmode="group", height=380, title="Revenue vs. Net Profit (last 10 years)",
                       margin=dict(t=50, b=20, l=10, r=10))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No Profit & Loss history available for this company.")

# --- ROE / ROCE dual-axis line chart ---------------------------------------
roe_hist = ratio_hist[["year", "return_on_equity_pct"]].tail(10)
roce_hist = roce_series.tail(10)
if not roe_hist.empty or not roce_hist.empty:
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=roe_hist["year"], y=roe_hist["return_on_equity_pct"],
                               name="ROE %", mode="lines+markers", line=dict(color="#6D28D9")))
    fig2.add_trace(go.Scatter(x=roce_hist["year"], y=roce_hist["roce_pct"],
                               name="ROCE %", mode="lines+markers", line=dict(color="#F97316"), yaxis="y2"))
    fig2.update_layout(
        height=380, title="ROE vs. ROCE (last 10 years)", margin=dict(t=50, b=20, l=10, r=10),
        yaxis=dict(title="ROE %"), yaxis2=dict(title="ROCE %", overlaying="y", side="right"),
    )
    st.plotly_chart(fig2, use_container_width=True)
else:
    st.info("No ROE/ROCE history available for this company.")

st.divider()

# --- Pros / cons badges -----------------------------------------------------
st.subheader("Pros & Cons")
pc = get_prosandcons(ticker)
pros = [p for p in pc["pros"].dropna().tolist() if str(p).strip().lower() != "nan"]
cons = [c for c in pc["cons"].dropna().tolist() if str(c).strip().lower() != "nan"]

if not pros and not cons:
    st.caption("No pros/cons data available for this company.")
else:
    pc1, pc2 = st.columns(2)
    with pc1:
        if pros:
            badge_list(pros, positive=True)
    with pc2:
        if cons:
            badge_list(cons, positive=False)
