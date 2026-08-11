"""
src/reports/chart_helpers.py — Shared matplotlib chart generators for
the Sprint 5 PDF reports (tearsheet.py, sector_report.py,
portfolio_summary.py).

Every function returns an in-memory PNG (io.BytesIO) rather than
writing a temp file to disk, so batch generation across 92 companies +
11 sectors doesn't leave hundreds of stray image files behind. Not one
of the Day 33 spec's explicitly-named files, but factored out since
all three Day 33-35 report types need the same handful of chart types.
"""

from __future__ import annotations

import io
from typing import Optional, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

NAVY = "#1E1B4B"
PURPLE = "#6D28D9"
ORANGE = "#F97316"
GREEN = "#15803D"
RED = "#B91C1C"
GREY = "#9CA3AF"


def _to_png_bytes(fig) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def revenue_net_profit_bar(years: Sequence[str], revenue: Sequence[Optional[float]],
                            net_profit: Sequence[Optional[float]], figsize=(5.6, 2.6)) -> io.BytesIO:
    """Grouped bar chart: Revenue and Net Profit side by side per year."""
    fig, ax = plt.subplots(figsize=figsize)
    x = np.arange(len(years))
    width = 0.38
    ax.bar(x - width / 2, [v if v is not None else 0 for v in revenue], width, label="Revenue (\u20b9 Cr)", color=PURPLE)
    ax.bar(x + width / 2, [v if v is not None else 0 for v in net_profit], width, label="Net Profit (\u20b9 Cr)", color=ORANGE)
    ax.set_xticks(x)
    ax.set_xticklabels(years, fontsize=7, rotation=45, ha="right")
    ax.tick_params(axis="y", labelsize=7)
    ax.legend(fontsize=7, loc="upper left")
    ax.set_title("Revenue vs. Net Profit", fontsize=9, fontweight="bold", color=NAVY)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    return _to_png_bytes(fig)


def roe_roce_dual_axis(years: Sequence[str], roe: Sequence[Optional[float]],
                        roce: Sequence[Optional[float]], figsize=(5.6, 2.6)) -> io.BytesIO:
    """Dual-axis line chart: ROE (left axis) and ROCE (right axis)."""
    fig, ax1 = plt.subplots(figsize=figsize)
    ax2 = ax1.twinx()
    ax1.plot(years, roe, marker="o", markersize=3, color=PURPLE, label="ROE %", linewidth=1.6)
    ax2.plot(years, roce, marker="s", markersize=3, color=ORANGE, label="ROCE %", linewidth=1.6, linestyle="--")
    ax1.set_ylabel("ROE %", fontsize=7, color=PURPLE)
    ax2.set_ylabel("ROCE %", fontsize=7, color=ORANGE)
    ax1.tick_params(axis="x", labelsize=7, rotation=45)
    ax1.tick_params(axis="y", labelsize=7, colors=PURPLE)
    ax2.tick_params(axis="y", labelsize=7, colors=ORANGE)
    ax1.set_title("ROE vs. ROCE", fontsize=9, fontweight="bold", color=NAVY)
    for spine in ("top",):
        ax1.spines[spine].set_visible(False)
        ax2.spines[spine].set_visible(False)
    fig.tight_layout()
    return _to_png_bytes(fig)


def balance_sheet_stacked_bar(years: Sequence[str], equity: Sequence[Optional[float]],
                               borrowings: Sequence[Optional[float]],
                               other_liabilities: Sequence[Optional[float]], figsize=(5.6, 2.6)) -> io.BytesIO:
    """Stacked bar: Equity + Borrowings + Other Liabilities by year."""
    fig, ax = plt.subplots(figsize=figsize)
    equity_v = np.array([v if v is not None else 0 for v in equity])
    borrow_v = np.array([v if v is not None else 0 for v in borrowings])
    other_v = np.array([v if v is not None else 0 for v in other_liabilities])
    ax.bar(years, equity_v, label="Equity (\u20b9 Cr)", color=NAVY)
    ax.bar(years, borrow_v, bottom=equity_v, label="Borrowings (\u20b9 Cr)", color=RED)
    ax.bar(years, other_v, bottom=equity_v + borrow_v, label="Other Liabilities (\u20b9 Cr)", color=GREY)
    ax.set_xticks(range(len(years)))
    ax.set_xticklabels(years, fontsize=7, rotation=45, ha="right")
    ax.tick_params(axis="y", labelsize=7)
    ax.legend(fontsize=6.5, loc="upper left")
    ax.set_title("Balance Sheet Composition", fontsize=9, fontweight="bold", color=NAVY)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    return _to_png_bytes(fig)


def cashflow_waterfall(cfo: Optional[float], cfi: Optional[float], cff: Optional[float],
                        net_cash_flow: Optional[float], figsize=(5.6, 2.6)) -> io.BytesIO:
    """Waterfall: CFO -> CFI -> CFF -> Net Cash Flow for the latest year."""
    labels = ["CFO", "CFI", "CFF", "Net Cash Flow"]
    values = [cfo or 0, cfi or 0, cff or 0, net_cash_flow if net_cash_flow is not None else (cfo or 0) + (cfi or 0) + (cff or 0)]

    fig, ax = plt.subplots(figsize=figsize)
    running = 0.0
    for i, (label, val) in enumerate(zip(labels, values)):
        if label == "Net Cash Flow":
            bottom = 0
            height = val
            color = NAVY
        else:
            bottom = min(running, running + val)
            height = abs(val)
            color = GREEN if val >= 0 else RED
            running += val
        ax.bar(i, height, bottom=bottom, color=color, width=0.6)
        ax.annotate(f"{val:,.0f}", xy=(i, bottom + height / 2 if label != 'Net Cash Flow' else height / 2),
                    ha="center", va="center", fontsize=7, color="white", fontweight="bold")
    ax.axhline(0, color="black", linewidth=0.6)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=7)
    ax.tick_params(axis="y", labelsize=7)
    ax.set_title("Cash Flow Waterfall (latest year, \u20b9 Cr)", fontsize=9, fontweight="bold", color=NAVY)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    return _to_png_bytes(fig)


def sector_median_kpi_bar(labels: Sequence[str], values: Sequence[Optional[float]], figsize=(6.5, 2.6)) -> io.BytesIO:
    fig, ax = plt.subplots(figsize=figsize)
    ax.bar(labels, [v if v is not None else 0 for v in values], color=PURPLE)
    ax.tick_params(axis="x", labelsize=7, rotation=20)
    ax.tick_params(axis="y", labelsize=7)
    ax.set_title("Sector Median KPIs", fontsize=9, fontweight="bold", color=NAVY)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    return _to_png_bytes(fig)
