"""
pages/04_peers.py — Peer Comparison screen.

Sprint 4, Day 24 deliverable (Epic 05, Module 2).

Peer group dropdown (all 11 Sprint 3 peer groups), an 8-axis radar
chart (plotly graph_objects Scatterpolar) for a selected company vs.
its peer group average, and a side-by-side KPI table with the
benchmark company's row highlighted.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.ui import configure_page, fmt  # noqa: E402
from utils.db import get_peers, get_peer_group_names  # noqa: E402

configure_page("Peer Comparison", icon="🧭")
st.title("🧭 Peer Comparison")

groups = get_peer_group_names()
with st.sidebar:
    st.markdown("### Peer Group")
    selected_group = st.selectbox("Peer group (11 total)", groups)

peers = get_peers(selected_group)
if peers.empty:
    st.warning("No companies found in this peer group.")
    st.stop()

company_choice = st.selectbox(
    "Company to compare against the group average",
    [f"{r.company_id} — {r.company_name}" for r in peers.itertuples()],
)
ticker = company_choice.split(" — ")[0]
company_row = peers[peers["company_id"] == ticker].iloc[0]

# --- 8-axis radar: ROE, ROCE, NPM, D/E, FCF, PAT CAGR 5yr, Revenue CAGR
# 5yr, Composite Score -- same axis set as Sprint 3's Day 19 static
# radar charts, min-max normalised within this peer group (D/E
# inverted so a lower ratio still scores higher on the chart). ---
AXES = {
    "ROE": "return_on_equity_pct", "ROCE": "roce_percentage",
    "Net Profit Margin": "net_profit_margin_pct", "D/E": "debt_to_equity",
    "FCF": "free_cash_flow_cr", "PAT CAGR 5yr": "pat_cagr_5yr",
    "Revenue CAGR 5yr": "revenue_cagr_5yr", "Composite Score": "composite_quality_score",
}


def normalise(series, invert=False):
    s = series.astype(float)
    lo, hi = s.min(skipna=True), s.max(skipna=True)
    if pd.isna(lo) or pd.isna(hi) or hi == lo:
        return s.apply(lambda v: 50.0 if pd.notna(v) else 0.0)
    scaled = (s - lo) / (hi - lo) * 100
    return (100 - scaled) if invert else scaled


norm_cols = {}
for axis, col in AXES.items():
    norm_cols[axis] = normalise(peers[col], invert=(axis == "D/E"))
norm_df = pd.DataFrame(norm_cols, index=peers.index)

company_values = norm_df.loc[peers["company_id"] == ticker].iloc[0].tolist()
group_avg_values = norm_df.mean(numeric_only=True).tolist()
axis_labels = list(AXES.keys())

fig = go.Figure()
fig.add_trace(go.Scatterpolar(r=company_values + company_values[:1],
                               theta=axis_labels + axis_labels[:1],
                               fill="toself", name=ticker, line_color="#6D28D9"))
fig.add_trace(go.Scatterpolar(r=group_avg_values + group_avg_values[:1],
                               theta=axis_labels + axis_labels[:1],
                               name="Peer group average", line=dict(color="#F97316", dash="dash")))
fig.update_layout(
    polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
    showlegend=True, height=480, title=f"{ticker} vs. {selected_group} average",
    margin=dict(t=60, b=20, l=40, r=40),
)
st.plotly_chart(fig, use_container_width=True)

st.divider()
st.subheader(f"{selected_group} — all members")

table = peers[["company_id", "company_name", "is_benchmark", "return_on_equity_pct", "roce_percentage",
               "net_profit_margin_pct", "debt_to_equity", "free_cash_flow_cr", "pat_cagr_5yr",
               "revenue_cagr_5yr", "composite_quality_score"]].copy()
table.columns = ["Ticker", "Company", "Benchmark", "ROE %", "ROCE %", "NPM %", "D/E", "FCF (₹ Cr)",
                  "PAT CAGR 5yr %", "Revenue CAGR 5yr %", "Composite Score"]
table["Benchmark"] = table["Benchmark"].map({1: "★ Benchmark", 0: ""})
table = table.round(2)


def _highlight_benchmark(row):
    return ["background-color: #FFD966" if row["Benchmark"] else "" for _ in row]


st.dataframe(table.style.apply(_highlight_benchmark, axis=1), use_container_width=True, hide_index=True)
