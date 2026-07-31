"""
pages/08_reports.py — Annual Reports screen.

Sprint 4, Day 25 deliverable (Epic 05, Module 3).

Company search box, list of available annual report years with
clickable BSE PDF links. Each link's reachability is checked with a
short-timeout HEAD request; a failed or non-200 response shows a red
"Report unavailable" badge instead of the link (network access may be
restricted in some deployment environments, so failures are treated as
"unavailable", not a crash).
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.ui import configure_page, flag_badge  # noqa: E402
from utils.db import get_companies, get_documents  # noqa: E402

configure_page("Annual Reports", icon="📄")
st.title("📄 Annual Reports")

companies = get_companies()
options = [f"{r.company_id} — {r.company_name}" for r in companies.itertuples()]

with st.sidebar:
    st.markdown("### Company")
    search_text = st.text_input("Search company name or ticker", "")
    check_links = st.checkbox("Check link availability (network request)", value=False)

filtered = [o for o in options if search_text.strip().lower() in o.lower()] if search_text.strip() else options
if not filtered:
    st.warning("Ticker not found — please try another")
    st.stop()

choice = st.selectbox("Company", filtered)
ticker = choice.split(" — ")[0]

docs = get_documents(ticker)

if docs.empty or docs["annual_report_url"].isna().all():
    st.info("No annual report links available for this company.")
    st.stop()


@st.cache_data(ttl=600)
def _check_url(url: str) -> bool:
    try:
        import requests
        resp = requests.head(url, timeout=5, allow_redirects=True)
        return resp.status_code == 200
    except Exception:
        return False


st.markdown(f"### {ticker} — {len(docs)} filing year(s) on record")

for _, row in docs.iterrows():
    year = row["report_year"]
    url = row["annual_report_url"]
    cols = st.columns([1, 3, 2])
    cols[0].markdown(f"**{year}**")

    if url is None or (isinstance(url, float)):
        cols[1].markdown(flag_badge("Report unavailable"), unsafe_allow_html=True)
        continue

    if check_links:
        with st.spinner(f"Checking {year}..."):
            ok = _check_url(url)
        if ok:
            cols[1].markdown(f"[Open Annual Report]({url})")
        else:
            cols[1].markdown(flag_badge("Report unavailable"), unsafe_allow_html=True)
    else:
        cols[1].markdown(f"[Open Annual Report]({url})")
