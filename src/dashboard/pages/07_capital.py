"""
pages/07_capital.py — Capital Allocation Map screen.

Sprint 4, Day 25 deliverable (Epic 05, Module 3).

A Plotly treemap of all companies grouped by their latest-year
capital-allocation pattern (Sprint 2, Day 11's 8-pattern classifier).
Clicking a pattern in the treemap (via st.plotly_chart's on_select)
filters the company list below it to that pattern.
"""

import sys
from pathlib import Path

import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.ui import configure_page  # noqa: E402
from utils.db import get_capital_allocation, get_companies  # noqa: E402

configure_page("Capital Allocation Map", icon="🗺️")
st.title("🗺️ Capital Allocation Map")
st.caption("Every company classified by the sign pattern of its Cash from Operations (CFO), "
           "Cash from Investing (CFI), and Cash from Financing (CFF) — see src/analytics/cashflow_kpis.py.")

alloc = get_capital_allocation()
companies = get_companies()[["company_id", "company_name", "broad_sector"]]
data = alloc.merge(companies, on="company_id", how="left")
data["pattern_label"] = data["pattern_label"].fillna("Unclassified")

pattern_counts = data.groupby("pattern_label")["company_id"].count().reset_index(name="count")

fig = px.treemap(
    data, path=["pattern_label", "company_id"], values=None,
    color="pattern_label", color_discrete_sequence=px.colors.qualitative.Bold,
)
fig.update_traces(root_color="lightgrey")
fig.update_layout(height=520, margin=dict(t=20, b=20, l=10, r=10))

event = st.plotly_chart(fig, use_container_width=True, on_select="rerun", selection_mode="points", key="capital_treemap")

selected_pattern = None
if event and event.get("selection", {}).get("points"):
    point = event["selection"]["points"][0]
    label = point.get("label")
    if label in pattern_counts["pattern_label"].values:
        selected_pattern = label
    else:
        parent_row = data[data["company_id"] == label]
        if not parent_row.empty:
            selected_pattern = parent_row.iloc[0]["pattern_label"]

st.divider()

if selected_pattern is None:
    st.markdown("### All companies")
    st.caption("Click a pattern in the treemap above to filter this list.")
    shown = data
else:
    st.markdown(f"### {selected_pattern} — {len(data[data['pattern_label'] == selected_pattern])} companies")
    shown = data[data["pattern_label"] == selected_pattern]

table = shown[["company_id", "company_name", "broad_sector", "pattern_label"]].rename(columns={
    "company_id": "Ticker", "company_name": "Company", "broad_sector": "Sector", "pattern_label": "Pattern",
}).sort_values("Ticker")
st.dataframe(table, use_container_width=True, hide_index=True)

with st.expander("Pattern definitions"):
    st.markdown(
        """
- **Cash Accumulator** (+CFO, +CFI, +CFF) — generating cash, harvesting investments, and raising more capital.
- **Liquidating Assets** (+CFO, +CFI, −CFF) — funding debt paydown / buybacks by selling investments.
- **Mixed** (+CFO, −CFI, +CFF) — reinvesting operating cash while also raising external capital.
- **Reinvestor** (+CFO, −CFI, −CFF) — strong operations funding growth capex and reducing debt.
- **Shareholder Returns** — a Reinvestor-pattern company whose CFO/PAT ratio exceeds 1.5x, indicating operating cash is being deployed to buybacks/dividends rather than pure reinvestment.
- **Distress Signal** (−CFO, +CFI, +CFF) — burning cash operationally, selling assets, and raising capital.
- **Asset Sale Funded Repayment** (−CFO, +CFI, −CFF) — funding debt repayment via asset sales while operations burn cash.
- **Growth Funded by Debt** (−CFO, −CFI, +CFF) — investing ahead of operating cash generation, funded by new capital.
- **Pre-Revenue** (−CFO, −CFI, −CFF) — cash outflow on every activity.
"""
    )
