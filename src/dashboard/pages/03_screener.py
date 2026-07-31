"""
pages/03_screener.py — Screener screen.

Sprint 4, Day 24 deliverable (Epic 05, Module 2).

10 metric sliders + 6 preset buttons that auto-fill them, a live
results table, a result-count label, and a CSV download button. Reuses
src/screener/engine.py's universe + composite score (via
utils.db.get_screener_universe) so numbers match Sprint 3's
screener_output.xlsx.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.ui import configure_page  # noqa: E402
from utils.db import get_screener_universe  # noqa: E402

configure_page("Screener", icon="🔎")
st.title("🔎 Financial Screener")

universe, config = get_screener_universe()

# Slider name -> (column in universe, direction 'min'/'max')
SLIDERS = {
    "ROE min":              ("return_on_equity_pct", "min"),
    "D/E max":               ("debt_to_equity", "max"),
    "FCF min":               ("free_cash_flow_cr", "min"),
    "Revenue CAGR min":     ("revenue_cagr_5yr", "min"),
    "PAT CAGR min":          ("pat_cagr_5yr", "min"),
    "OPM min":               ("operating_profit_margin_pct", "min"),
    "P/E max":               ("pe_ratio", "max"),
    "P/B max":               ("pb_ratio", "max"),
    "Dividend Yield min":   ("dividend_yield_pct", "min"),
    "ICR min":               ("interest_coverage_for_filter", "min"),
}

# Reasonable finite bounds per slider (ICR uses a capped max since
# debt-free companies carry +inf in interest_coverage_for_filter --
# they always pass regardless of the slider's finite ceiling).
BOUNDS = {}
for label, (col, direction) in SLIDERS.items():
    finite = universe[col].replace([np.inf, -np.inf], np.nan).dropna()
    if finite.empty:
        BOUNDS[label] = (0.0, 100.0)
        continue
    lo = float(np.floor(finite.quantile(0.02)))
    hi = float(np.ceil(finite.quantile(0.98)))
    if col == "interest_coverage_for_filter":
        hi = min(hi, 50.0)
    if hi <= lo:
        hi = lo + 1.0
    BOUNDS[label] = (lo, hi)

NO_OP_DEFAULT = {label: (BOUNDS[label][0] if direction == "min" else BOUNDS[label][1])
                 for label, (_, direction) in SLIDERS.items()}

PRESET_LABELS = {
    "quality_compounder": "Quality",
    "value_pick": "Value",
    "growth_accelerator": "Growth",
    "dividend_champion": "Dividend",
    "debt_free_blue_chip": "Debt-Free",
    "turnaround_watch": "Turnaround",
}

# Reverse map: config metric key -> slider label, so a preset's filter
# thresholds can populate the matching slider(s). Presets may reference
# metrics with no corresponding slider (e.g. Debt-Free Blue Chip's
# `sales` threshold) -- those are simply not represented by a slider.
METRIC_KEY_TO_SLIDER = {
    "roe": "ROE min", "de": "D/E max", "fcf": "FCF min",
    "revenue_cagr_5yr": "Revenue CAGR min", "pat_cagr_5yr": "PAT CAGR min",
    "opm": "OPM min", "pe": "P/E max", "pb": "P/B max",
    "dividend_yield": "Dividend Yield min", "icr": "ICR min",
}


def _apply_preset(preset_key: str):
    filters = config["presets"][preset_key]["filters"]
    values = dict(NO_OP_DEFAULT)
    for metric_key, condition in filters.items():
        slider_label = METRIC_KEY_TO_SLIDER.get(metric_key)
        if slider_label is None:
            continue
        lo, hi = BOUNDS[slider_label]
        if "min" in condition:
            values[slider_label] = max(lo, min(hi, condition["min"]))
        elif "max" in condition:
            values[slider_label] = max(lo, min(hi, condition["max"]))
        elif "eq" in condition:
            values[slider_label] = max(lo, min(hi, condition["eq"]))
    for label, val in values.items():
        st.session_state[f"scr_{label}"] = val


st.markdown("**Presets** — click to auto-fill the sliders in the sidebar:")
preset_cols = st.columns(len(PRESET_LABELS))
for col, (preset_key, label) in zip(preset_cols, PRESET_LABELS.items()):
    col.button(label, on_click=_apply_preset, args=(preset_key,), use_container_width=True)

def _reset_filters():
    for label in SLIDERS:
        st.session_state[f"scr_{label}"] = NO_OP_DEFAULT[label]


with st.sidebar:
    st.markdown("### Filters")
    slider_values = {}
    for label, (col, direction) in SLIDERS.items():
        lo, hi = BOUNDS[label]
        st.session_state.setdefault(f"scr_{label}", NO_OP_DEFAULT[label])
        slider_values[label] = st.slider(label, lo, hi, key=f"scr_{label}")
    st.button("Reset filters", on_click=_reset_filters)

# --- Apply filters live -----------------------------------------------------
mask = pd.Series(True, index=universe.index)
for label, (col, direction) in SLIDERS.items():
    threshold = slider_values[label]
    series = universe[col]
    if direction == "min":
        m = series >= threshold
    else:
        m = series <= threshold
    mask &= m.fillna(False)

results = universe.loc[mask].sort_values("composite_quality_score", ascending=False)

st.markdown(f"### {len(results)} companies match your filters")

display_cols = ["company_id", "company_name", "broad_sector", "composite_quality_score"] + \
    [col for col, _ in SLIDERS.values()]
display_cols = list(dict.fromkeys(display_cols))  # de-dup (interest_coverage_for_filter appears once)
display = results[display_cols].rename(columns={
    "company_id": "Ticker", "company_name": "Company", "broad_sector": "Sector",
    "composite_quality_score": "Composite Score",
    "return_on_equity_pct": "ROE %", "debt_to_equity": "D/E", "free_cash_flow_cr": "FCF (₹ Cr)",
    "revenue_cagr_5yr": "Revenue CAGR 5yr %", "pat_cagr_5yr": "PAT CAGR 5yr %",
    "operating_profit_margin_pct": "OPM %", "pe_ratio": "P/E", "pb_ratio": "P/B",
    "dividend_yield_pct": "Dividend Yield %", "interest_coverage_for_filter": "ICR",
}).round(2)

st.dataframe(display, use_container_width=True, hide_index=True)

csv_bytes = display.to_csv(index=False).encode("utf-8")
st.download_button("⬇️ Download results as CSV", data=csv_bytes,
                    file_name="screener_results.csv", mime="text/csv")
