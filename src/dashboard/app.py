"""
src/dashboard/app.py — Streamlit entry point for the Nifty 100
Financial Intelligence Platform dashboard.

Sprint 4, Day 22 deliverable (Epic 05, Module 1).

Run with:
    streamlit run src/dashboard/app.py

Streamlit's classic multipage mode auto-discovers every script in a
pages/ directory that sits *next to* the entrypoint script and lists
them in the sidebar automatically, in filename order -- which is why
pages/ lives at src/dashboard/pages/ (sibling to this file) rather than
at the repository root: that's what makes `streamlit run
src/dashboard/app.py` actually pick up all 8 screens without any
explicit st.navigation() wiring. This file itself is a short landing
screen; pages/01_home.py is the real "Home" dashboard screen.
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.ui import configure_page, fmt  # noqa: E402
from utils.db import get_companies, get_latest_ratios_universe  # noqa: E402

configure_page("Welcome", icon="📈")

st.title("📈 Nifty 100 Financial Intelligence Platform")
st.caption("Bluestock Fintech · Data Analyst Internship · Sprint 4 Dashboard")

st.markdown(
    """
Use the **sidebar** to navigate between the eight screens:

1. **Home** — headline KPIs across the Nifty 100 universe
2. **Company Profile** — deep dive into a single company
3. **Screener** — interactive, threshold-based stock screener
4. **Peer Comparison** — a company vs. its sector peer group
5. **Trend Analysis** — multi-metric trends over up to 10 years
6. **Sector Analysis** — sector-level bubble charts and medians
7. **Capital Allocation Map** — 92 companies grouped by capital-allocation pattern
8. **Annual Reports** — annual report links per company
"""
)

try:
    companies = get_companies()
    universe = get_latest_ratios_universe()
    c1, c2, c3 = st.columns(3)
    c1.metric("Companies covered", len(companies))
    c2.metric("Sectors", companies["broad_sector"].nunique())
    c3.metric("Peer groups", 11)
    st.success(f"Connected to nifty100.db — {len(universe)} companies loaded.")
except Exception as exc:  # pragma: no cover - defensive UI guard
    st.error(f"Could not connect to the database: {exc}")

st.info("👈 Pick a screen from the sidebar to get started.")
