"""
src/dashboard/utils/ui.py — Shared UI helpers for the Nifty 100
Financial Intelligence Platform Streamlit dashboard.

Not one of the Day 22 spec's explicitly-named files, but factored out
to avoid repeating page-config boilerplate and None/NaN-safe formatting
across all 8 screens (the Day 27 exit criterion requires every screen
to show 'N/A' instead of crashing on a missing metric).
"""

from __future__ import annotations

import math
from typing import Optional

import streamlit as st

BRAND_INDIGO = "#1E1B4B"
BRAND_PURPLE = "#6D28D9"
BRAND_ORANGE = "#F97316"
BRAND_GREEN = "#15803D"
BRAND_RED = "#B91C1C"

_CSS = f"""
<style>
    div[data-testid="stMetric"] {{
        background-color: #F8F7FC;
        border: 1px solid #E5E1F7;
        border-radius: 10px;
        padding: 12px 14px 8px 14px;
    }}
    div[data-testid="stMetricLabel"] {{ color: {BRAND_PURPLE}; font-weight: 600; }}
    h1, h2, h3 {{ color: {BRAND_INDIGO}; }}
    .n100-badge-pos {{
        display: inline-block; background-color: #DCFCE7; color: {BRAND_GREEN};
        border-radius: 6px; padding: 4px 10px; margin: 3px 0; font-size: 0.9rem;
    }}
    .n100-badge-neg {{
        display: inline-block; background-color: #FEE2E2; color: {BRAND_RED};
        border-radius: 6px; padding: 4px 10px; margin: 3px 0; font-size: 0.9rem;
    }}
    .n100-badge-warn {{
        display: inline-block; background-color: #FEF3C7; color: #92400E;
        border-radius: 6px; padding: 3px 9px; margin: 2px 0; font-size: 0.85rem;
    }}
</style>
"""

_PAGE_CONFIGURED = False


def configure_page(page_title: str, icon: str = "📊"):
    """Call once at the top of every page (each page in Streamlit's
    classic pages/ multipage mode is its own script run, so
    set_page_config must be called again per page -- Streamlit only
    errors if it's called *twice within the same run*, not once per
    page across different pages)."""
    st.set_page_config(
        page_title=f"{page_title} · Nifty 100 Analytics",
        page_icon=icon,
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(_CSS, unsafe_allow_html=True)


def fmt(value, decimals: int = 2, suffix: str = "", prefix: str = "") -> str:
    """None/NaN-safe numeric formatter. Returns 'N/A' for None, NaN, or
    non-numeric input instead of raising -- required by the Day 27 exit
    criterion ('if a metric is None or NaN, display N/A')."""
    if value is None:
        return "N/A"
    try:
        f = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if math.isnan(f) or math.isinf(f):
        return "N/A"
    return f"{prefix}{f:,.{decimals}f}{suffix}"


def badge_list(items: list[str], positive: bool = True):
    """Render a vertical list of green-check / red-cross badges."""
    cls = "n100-badge-pos" if positive else "n100-badge-neg"
    icon = "✅" if positive else "❌"
    for item in items:
        st.markdown(f'<div class="{cls}">{icon} {item}</div>', unsafe_allow_html=True)


def flag_badge(flag: Optional[str]) -> str:
    """Small inline HTML badge for valuation / report-availability flags."""
    if flag in (None, "N/A") or (isinstance(flag, float) and math.isnan(flag)):
        return '<span class="n100-badge-warn">N/A</span>'
    color_map = {"Caution": "n100-badge-warn", "Discount": "n100-badge-pos",
                 "Fair": "n100-badge-pos", "Report unavailable": "n100-badge-neg"}
    return f'<span class="{color_map.get(flag, "n100-badge-warn")}">{flag}</span>'
