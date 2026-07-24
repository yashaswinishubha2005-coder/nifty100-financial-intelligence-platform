"""
src/analytics/peer.py — Peer percentile ranking engine for the Nifty 100
Financial Intelligence Platform.

Sprint 3, Days 18-20 (Epic 04, Module 2).

Responsibilities:
    Day 18  Load peer_groups.xlsx and compute PERCENT_RANK for 10 metrics
            within each of 11 peer groups. Populate the peer_percentiles
            table in SQLite. Companies with no peer group return the
            message "No peer group assigned" instead of raising an error.
    Day 19  Radar/polar chart per company in a peer group (8 axes), PNG
            to reports/radar_charts/. Companies with no peer group get a
            standalone single-metric chart vs. the Nifty 100 average.
    Day 20  output/peer_comparison.xlsx: 11 sheets (one per peer group),
            percentile-colour-coded, benchmark row highlighted gold, and
            a peer-group-median summary row.

Usage:
    python src/analytics/peer.py
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from openpyxl.styles import Font, PatternFill

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2] if (Path(__file__).resolve().parent.name == "analytics") else Path.cwd()
DB_PATH = PROJECT_ROOT / "data" / "nifty100.db"
OUTPUT_DIR = PROJECT_ROOT / "output"
RADAR_DIR = PROJECT_ROOT / "reports" / "radar_charts"

NO_PEER_GROUP_MESSAGE = "No peer group assigned"

# Day 18: the 10 ranked metrics. `inverse=True` means lower raw value is
# better (D/E), so its percentile is computed as (1 - PERCENT_RANK).
METRICS = {
    "ROE":                 {"column": "return_on_equity_pct",  "inverse": False},
    "ROCE":                {"column": "roce_percentage",        "inverse": False},
    "Net Profit Margin":   {"column": "net_profit_margin_pct",  "inverse": False},
    "D/E":                  {"column": "debt_to_equity",         "inverse": True},
    "FCF":                  {"column": "free_cash_flow_cr",       "inverse": False},
    "PAT CAGR 5yr":        {"column": "pat_cagr_5yr",           "inverse": False},
    "Revenue CAGR 5yr":    {"column": "revenue_cagr_5yr",       "inverse": False},
    "EPS CAGR 5yr":        {"column": "eps_cagr_5yr",           "inverse": False},
    "Interest Coverage":   {"column": "interest_coverage",       "inverse": False},
    "Asset Turnover":       {"column": "asset_turnover",          "inverse": False},
}

# Day 19 radar chart axes (8), pulling from the same universe frame.
RADAR_AXES = ["ROE", "ROCE", "Net Profit Margin", "D/E", "FCF Score", "PAT CAGR 5yr", "Revenue CAGR 5yr", "Composite Score"]


# ===========================================================================
# Universe builder (latest complete year per company, mirrors
# src/screener/engine.py's build_universe but kept independent here to
# avoid a cross-package import between analytics <-> screener)
# ===========================================================================

def _latest_complete_rows(df: pd.DataFrame, require_col: str) -> pd.DataFrame:
    if df.empty:
        return df
    sorted_df = df.sort_values("year")
    complete = sorted_df[sorted_df[require_col].notna()]
    idx = complete.groupby("company_id").tail(1).index
    missing = set(df["company_id"]) - set(df.loc[idx, "company_id"])
    if missing:
        fallback = sorted_df[sorted_df["company_id"].isin(missing)].groupby("company_id").tail(1).index
        idx = idx.append(fallback)
    return df.loc[idx].reset_index(drop=True)


def build_peer_universe(conn: sqlite3.Connection) -> pd.DataFrame:
    """Latest-year snapshot per company (financial_ratios + companies.roce_percentage),
    used as the source for percentile ranking and radar charts."""
    fr = pd.read_sql("SELECT * FROM financial_ratios", conn)
    for col in fr.columns:
        if col not in ("company_id", "year", "icr_label"):
            fr[col] = pd.to_numeric(fr[col], errors="coerce")
    fr = _latest_complete_rows(fr, "return_on_equity_pct")

    companies = pd.read_sql("SELECT id AS company_id, company_name, roce_percentage FROM companies", conn)
    df = fr.merge(companies, on="company_id", how="left")

    # Debt-free companies: ICR treated as best possible (very large finite
    # sentinel here, rather than inf, so downstream min/max normalisation
    # for the radar chart doesn't blow up).
    finite_max = df.loc[df["icr_label"] != "Debt Free", "interest_coverage"].max()
    sentinel = (finite_max if pd.notna(finite_max) else 100.0) * 2
    df["interest_coverage_effective"] = np.where(df["icr_label"] == "Debt Free", sentinel, df["interest_coverage"])

    return df


# ===========================================================================
# Day 18 — PERCENT_RANK within peer group
# ===========================================================================

def _percent_rank(series: pd.Series) -> pd.Series:
    """SQL-style PERCENT_RANK = (rank - 1) / (n - 1), min-tie method,
    scaled to 0-100. NaN values stay NaN. n==1 -> 100 (trivially top of a
    group of one, nothing to rank against)."""
    valid = series.dropna()
    if valid.empty:
        return pd.Series(np.nan, index=series.index)
    n = len(valid)
    if n == 1:
        result = pd.Series(np.nan, index=series.index)
        result[valid.index] = 100.0
        return result
    ranks = valid.rank(method="min", ascending=True)
    pct = (ranks - 1) / (n - 1) * 100
    result = pd.Series(np.nan, index=series.index)
    result[valid.index] = pct
    return result


def compute_peer_percentiles(universe: pd.DataFrame, peer_groups: pd.DataFrame) -> pd.DataFrame:
    """
    Day 18: compute PERCENT_RANK for all 10 METRICS within each peer
    group. Returns a long-form DataFrame with columns:
        company_id, peer_group_name, metric, value, percentile_rank, year
    Companies with no peer_groups row simply don't appear here (handled
    separately by `lookup_company_percentiles` -> NO_PEER_GROUP_MESSAGE).
    """
    merged = peer_groups.merge(universe, on="company_id", how="inner")
    rows = []

    for peer_group_name, grp in merged.groupby("peer_group_name"):
        for metric_name, meta in METRICS.items():
            col = meta["column"]
            values = grp["interest_coverage_effective"] if metric_name == "Interest Coverage" else grp[col]
            if meta["inverse"]:
                pct_rank = _percent_rank(-values)
            else:
                pct_rank = _percent_rank(values)
            for (_, row), val, rank in zip(grp.iterrows(), values, pct_rank):
                rows.append({
                    "company_id": row["company_id"],
                    "peer_group_name": peer_group_name,
                    "metric": metric_name,
                    "value": None if pd.isna(val) else float(val),
                    "percentile_rank": None if pd.isna(rank) else float(rank),
                    "year": row["year"],
                })

    return pd.DataFrame(rows)


def lookup_company_percentiles(company_id: str, percentiles: pd.DataFrame) -> "pd.DataFrame | str":
    """Per-company convenience lookup. Returns NO_PEER_GROUP_MESSAGE
    (str) for companies not in any peer group, per Day 18 spec, instead
    of raising an error."""
    rows = percentiles[percentiles["company_id"] == company_id]
    if rows.empty:
        return NO_PEER_GROUP_MESSAGE
    return rows


def write_peer_percentiles_table(conn: sqlite3.Connection, percentiles: pd.DataFrame):
    """Populate the peer_percentiles SQLite table (schema in db/schema.sql)."""
    conn.execute("DELETE FROM peer_percentiles")
    percentiles[["company_id", "peer_group_name", "metric", "value", "percentile_rank", "year"]] \
        .to_sql("peer_percentiles", conn, if_exists="append", index=False)
    conn.commit()
    logger.info("Wrote %d rows to peer_percentiles", len(percentiles))


# ===========================================================================
# Day 19 — Radar charts
# ===========================================================================

def _radar_axis_values(row: pd.Series, group_stats: dict[str, tuple[float, float]]) -> list[float]:
    """Min-max normalise each of the 8 radar axes to 0-100 using the peer
    group's (min, max) for that axis, so the chart is readable regardless
    of each metric's native scale. D/E is inverted (lower raw = higher
    score) before normalising, consistent with the Day 18 percentile
    convention. Missing values plot as 0."""
    values = []
    for axis in RADAR_AXES:
        raw = row.get(_AXIS_TO_FIELD[axis])
        lo, hi = group_stats.get(axis, (0.0, 1.0))
        if raw is None or (isinstance(raw, float) and np.isnan(raw)):
            values.append(0.0)
            continue
        if axis == "D/E":
            raw = -raw
        if hi == lo:
            values.append(50.0)
        else:
            values.append(max(0.0, min(100.0, (raw - lo) / (hi - lo) * 100)))
    return values


_AXIS_TO_FIELD = {
    "ROE": "return_on_equity_pct",
    "ROCE": "roce_percentage",
    "Net Profit Margin": "net_profit_margin_pct",
    "D/E": "debt_to_equity",
    "FCF Score": "free_cash_flow_cr",
    "PAT CAGR 5yr": "pat_cagr_5yr",
    "Revenue CAGR 5yr": "revenue_cagr_5yr",
    "Composite Score": "composite_quality_score",
}


def _group_axis_stats(grp: pd.DataFrame) -> dict[str, tuple[float, float]]:
    stats = {}
    for axis, field in _AXIS_TO_FIELD.items():
        series = grp[field].astype(float)
        if axis == "D/E":
            series = -series
        stats[axis] = (series.min(skipna=True), series.max(skipna=True))
    return stats


def _draw_radar(company_label: str, company_values: list[float], avg_values: list[float],
                 axes_labels: list[str], out_path: Path):
    n = len(axes_labels)
    angles = [i / n * 2 * np.pi for i in range(n)]
    angles += angles[:1]
    company_vals = company_values + company_values[:1]
    avg_vals = avg_values + avg_values[:1]

    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(axes_labels, fontsize=10)
    ax.set_ylim(0, 100)
    ax.set_yticks([25, 50, 75, 100])
    ax.set_yticklabels(["25", "50", "75", "100"], fontsize=7)

    ax.plot(angles, company_vals, color="#2E5090", linewidth=2, label=company_label)
    ax.fill(angles, company_vals, color="#2E5090", alpha=0.25)

    ax.plot(angles, avg_vals, color="#C0504D", linewidth=1.5, linestyle="--", label="Peer group average")

    ax.set_title(company_label, fontsize=13, fontweight="bold", pad=20)
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def generate_radar_charts(universe: pd.DataFrame, peer_groups: pd.DataFrame,
                            out_dir: Path = RADAR_DIR) -> list[Path]:
    """Day 19: one radar PNG per company that belongs to a peer group
    (filled polygon = company, dashed outline = peer group average),
    plus a standalone single-metric chart (Composite Score vs. Nifty 100
    average) for companies with no peer group assignment."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []

    merged = peer_groups.merge(universe, on="company_id", how="inner")
    for peer_group_name, grp in merged.groupby("peer_group_name"):
        stats = _group_axis_stats(grp)

        # Peer-group average axis values = mean of each axis's own
        # normalised 0-100 value across the group (not the normalised
        # mean of raw values), so the dashed overlay is directly
        # comparable to each company's filled polygon.
        per_company_axis_values = {
            row["company_id"]: _radar_axis_values(row, stats) for _, row in grp.iterrows()
        }
        avg_values = list(np.mean(list(per_company_axis_values.values()), axis=0))

        for _, row in grp.iterrows():
            company_values = per_company_axis_values[row["company_id"]]
            label = f"{row['company_id']} ({peer_group_name})"
            out_path = out_dir / f"{row['company_id']}_radar.png"
            _draw_radar(label, company_values, avg_values, RADAR_AXES, out_path)
            written.append(out_path)

    # Standalone charts for companies with no peer group
    assigned = set(peer_groups["company_id"])
    unassigned = universe[~universe["company_id"].isin(assigned)]
    nifty_avg = universe["composite_quality_score"].astype(float).mean(skipna=True)
    for _, row in unassigned.iterrows():
        out_path = out_dir / f"{row['company_id']}_radar.png"
        _draw_standalone_chart(row["company_id"], row.get("composite_quality_score"), nifty_avg, out_path)
        written.append(out_path)

    logger.info("Wrote %d radar/standalone charts to %s", len(written), out_dir)
    return written


def _draw_standalone_chart(company_id: str, company_value: Optional[float], nifty_avg: float, out_path: Path):
    """Single-metric standalone bar chart (Composite Score) for
    companies with NO_PEER_GROUP_MESSAGE, benchmarked against the
    Nifty 100 average, per Day 19 spec."""
    company_value = 0.0 if company_value is None or pd.isna(company_value) else float(company_value)
    fig, ax = plt.subplots(figsize=(4, 5))
    bars = ax.bar([company_id, "Nifty 100 Avg"], [company_value, nifty_avg],
                  color=["#2E5090", "#999999"])
    ax.set_ylabel("Composite Quality Score")
    ax.set_title(f"{company_id}\n({NO_PEER_GROUP_MESSAGE})", fontsize=11, fontweight="bold")
    for bar in bars:
        height = bar.get_height()
        ax.annotate(f"{height:.1f}", xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3), textcoords="offset points", ha="center", fontsize=9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


# ===========================================================================
# Day 20 — peer_comparison.xlsx
# ===========================================================================

def export_peer_comparison(universe: pd.DataFrame, peer_groups: pd.DataFrame, percentiles: pd.DataFrame,
                             out_path: Path = OUTPUT_DIR / "peer_comparison.xlsx") -> Path:
    """11 sheets (one per peer group): company_id, company_name, + 20
    metric columns, + percentile rank per metric. Percentile cells
    colour-coded green (>=75th), yellow (25th-75th), red (<=25th).
    Benchmark row highlighted gold. Summary row = peer group median."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    green = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    yellow = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
    red = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
    gold = PatternFill(start_color="FFD966", end_color="FFD966", fill_type="solid")
    header_font = Font(bold=True)

    metric_value_cols = [f"{name} (value)" for name in METRICS]
    metric_pct_cols = [f"{name} (pctile)" for name in METRICS]
    all_cols = ["company_id", "company_name"] + metric_value_cols + metric_pct_cols  # 2 + 10 + 10 = 22 (>= 20 KPI cols per spec)

    merged = peer_groups.merge(universe, on="company_id", how="inner")

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        for peer_group_name, grp in merged.groupby("peer_group_name"):
            grp_pct = percentiles[percentiles["peer_group_name"] == peer_group_name]

            sheet_rows = []
            for _, row in grp.iterrows():
                record = {"company_id": row["company_id"], "company_name": row["company_name"]}
                for metric_name, meta in METRICS.items():
                    val_row = grp_pct[(grp_pct["company_id"] == row["company_id"]) & (grp_pct["metric"] == metric_name)]
                    record[f"{metric_name} (value)"] = val_row["value"].iloc[0] if not val_row.empty else None
                    record[f"{metric_name} (pctile)"] = val_row["percentile_rank"].iloc[0] if not val_row.empty else None
                sheet_rows.append(record)
            sheet_df = pd.DataFrame(sheet_rows)[all_cols]

            sheet_name = peer_group_name[:31]
            sheet_df.to_excel(writer, sheet_name=sheet_name, index=False)
            ws = writer.sheets[sheet_name]

            for c_idx in range(1, len(all_cols) + 1):
                ws.cell(row=1, column=c_idx).font = header_font
                ws.column_dimensions[ws.cell(row=1, column=c_idx).column_letter].width = 16

            benchmark_ids = set(grp.loc[grp["is_benchmark"] == 1, "company_id"]) \
                if "is_benchmark" in grp.columns else set()

            for r_idx, (_, sheet_row) in enumerate(sheet_df.iterrows(), start=2):
                is_benchmark = sheet_row["company_id"] in benchmark_ids
                for c_idx, col_name in enumerate(all_cols, start=1):
                    cell = ws.cell(row=r_idx, column=c_idx)
                    if is_benchmark:
                        cell.fill = gold
                    elif col_name in metric_pct_cols:
                        pct = sheet_row[col_name]
                        if pd.notna(pct):
                            if pct >= 75:
                                cell.fill = green
                            elif pct <= 25:
                                cell.fill = red
                            else:
                                cell.fill = yellow

            # Summary row: peer group median for each metric
            summary_row_idx = len(sheet_df) + 2
            ws.cell(row=summary_row_idx, column=1, value="MEDIAN").font = header_font
            for c_idx, col_name in enumerate(all_cols[2:], start=3):
                median_val = sheet_df[col_name].median(skipna=True)
                ws.cell(row=summary_row_idx, column=c_idx, value=None if pd.isna(median_val) else round(median_val, 2))

    logger.info("Wrote %s (%d peer-group sheets)", out_path, merged["peer_group_name"].nunique())
    return out_path


# ===========================================================================
# Orchestration
# ===========================================================================

def run_peer_analysis() -> dict:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")

    universe = build_peer_universe(conn)
    peer_groups = pd.read_sql("SELECT peer_group_name, company_id, is_benchmark FROM peer_groups", conn)

    percentiles = compute_peer_percentiles(universe, peer_groups)
    write_peer_percentiles_table(conn, percentiles)

    radar_paths = generate_radar_charts(universe, peer_groups)
    export_path = export_peer_comparison(universe, peer_groups, percentiles)

    conn.close()

    return {
        "peer_groups": peer_groups["peer_group_name"].nunique(),
        "percentile_rows": len(percentiles),
        "radar_charts": len(radar_paths),
        "export_path": str(export_path),
    }


if __name__ == "__main__":
    result = run_peer_analysis()
    print()
    print("=== PEER ANALYSIS RUN SUMMARY ===")
    print(f"Peer groups: {result['peer_groups']}")
    print(f"peer_percentiles rows: {result['percentile_rows']}")
    print(f"Radar/standalone charts: {result['radar_charts']}")
    print(f"Output: {result['export_path']}")
