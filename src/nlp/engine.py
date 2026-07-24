"""
src/screener/engine.py — Financial screener engine for the Nifty 100
Financial Intelligence Platform.

Sprint 3, Days 15-17 (Epic 03, Module 3).

Responsibilities:
    Day 15  Load config/screener_config.yaml + build the screener universe
            (latest-year snapshot per company, joined across financial_ratios,
            sectors, market_cap, profitandloss) and apply threshold filters
            for all 15 filterable metrics.
    Day 16  6 preset screeners (Quality Compounder, Value Pick, Growth
            Accelerator, Dividend Champion, Debt-Free Blue Chip,
            Turnaround Watch).
    Day 17  Composite quality score (0-100): 35% Profitability + 30% Cash
            Quality + 20% Growth + 15% Leverage, P10/P90 winsorised, plus a
            sector-relative version. Export output/screener_output.xlsx,
            one colour-coded sheet per preset.

Usage:
    python src/screener/engine.py
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import yaml
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2] if (Path(__file__).resolve().parent.name == "screener") else Path.cwd()
DB_PATH = PROJECT_ROOT / "data" / "nifty100.db"
CONFIG_PATH = PROJECT_ROOT / "config" / "screener_config.yaml"
OUTPUT_DIR = PROJECT_ROOT / "output"

sys.path.insert(0, str(PROJECT_ROOT / "src" / "analytics"))
from cagr import cagr_from_series          # noqa: E402
from cashflow_kpis import cfo_quality_score  # noqa: E402


# ===========================================================================
# Config loading
# ===========================================================================

def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


# ===========================================================================
# Day 15 — universe builder
# ===========================================================================

def _latest_year_rows(df: pd.DataFrame, group_col: str = "company_id", year_col: str = "year",
                        require_complete_col: Optional[str] = None) -> pd.DataFrame:
    """Keep only the most recent `year` row per company_id (string years
    sort correctly, 'YYYY-MM'). Some companies carry a trailing interim
    stub row (e.g. a part-year update) where most ratio columns are NULL;
    when `require_complete_col` is given, the latest row *with a non-null
    value in that column* is preferred, falling back to the true latest
    row only if every row is null there."""
    if df.empty:
        return df
    sorted_df = df.sort_values(year_col)
    if require_complete_col is not None and require_complete_col in df.columns:
        complete = sorted_df[sorted_df[require_complete_col].notna()]
        idx = complete.groupby(group_col).tail(1).index
        missing_companies = set(df[group_col]) - set(df.loc[idx, group_col])
        if missing_companies:
            fallback = sorted_df[sorted_df[group_col].isin(missing_companies)].groupby(group_col).tail(1).index
            idx = idx.append(fallback)
    else:
        idx = sorted_df.groupby(group_col).tail(1).index
    return df.loc[idx].reset_index(drop=True)


def _revenue_cagr_3yr(pl: pd.DataFrame) -> pd.Series:
    """Compute trailing 3-year revenue CAGR per company from the full
    profitandloss sales history, using the same cagr.py engine as the
    5yr CAGR already stored in financial_ratios."""
    out = {}
    for company_id, grp in pl.groupby("company_id"):
        series = list(zip(grp["year"], grp["sales"]))
        value, _flag = cagr_from_series(series, window_years=3)
        out[company_id] = value
    return pd.Series(out, name="revenue_cagr_3yr")


def _de_declining_flag(fr: pd.DataFrame) -> pd.Series:
    """True if the latest year's D/E is lower than the prior year's D/E
    for that company (fewer than 2 years of history -> False, not a
    hard error, per Day 16 Turnaround Watch spec)."""
    out = {}
    for company_id, grp in fr.sort_values("year").groupby("company_id"):
        de = grp["debt_to_equity"].tolist()
        if len(de) < 2 or pd.isna(de[-1]) or pd.isna(de[-2]):
            out[company_id] = False
        else:
            out[company_id] = de[-1] < de[-2]
    return pd.Series(out, name="de_declining")


def build_universe(conn: Optional[sqlite3.Connection] = None) -> pd.DataFrame:
    """
    Build the screener universe: one row per company (latest fiscal
    year) with every column referenced by config/screener_config.yaml,
    plus the derived fields (revenue_cagr_3yr, de_declining, D/E-skip
    flag for Financials, ICR-as-infinity handling).
    """
    own_conn = conn is None
    if own_conn:
        conn = sqlite3.connect(DB_PATH)

    companies = pd.read_sql("SELECT id AS company_id, company_name, roce_percentage FROM companies", conn)
    sectors = pd.read_sql("SELECT company_id, broad_sector, sub_sector FROM sectors", conn)
    fr_all = pd.read_sql("SELECT * FROM financial_ratios", conn)
    for col in fr_all.columns:
        if col not in ("company_id", "year", "icr_label"):
            fr_all[col] = pd.to_numeric(fr_all[col], errors="coerce")
    mc_all = pd.read_sql("SELECT * FROM market_cap", conn)
    pl_all = pd.read_sql("SELECT company_id, year, sales, net_profit, dividend_payout FROM profitandloss", conn)

    if own_conn:
        conn.close()

    fr = _latest_year_rows(fr_all, require_complete_col="return_on_equity_pct")
    mc_all["year"] = mc_all["year"].astype(str)
    mc = _latest_year_rows(mc_all, require_complete_col="pe_ratio")
    pl = _latest_year_rows(pl_all, require_complete_col="sales")

    revenue_cagr_3yr = _revenue_cagr_3yr(pl_all)
    de_declining = _de_declining_flag(fr_all)

    df = (
        companies
        .merge(sectors, on="company_id", how="left")
        .merge(fr, on="company_id", how="left", suffixes=("", "_fr"))
        .merge(mc[["company_id", "market_cap_crore", "pe_ratio", "pb_ratio", "dividend_yield_pct"]],
               on="company_id", how="left")
        .merge(pl[["company_id", "sales", "net_profit", "dividend_payout"]], on="company_id", how="left")
    )
    df["revenue_cagr_3yr"] = df["company_id"].map(revenue_cagr_3yr)
    df["de_declining"] = df["company_id"].map(de_declining).fillna(False)
    df["dividend_payout_ratio_pct"] = df["dividend_payout"]

    # ICR filter: "Debt Free" (icr_label == 'Debt Free', interest_coverage
    # is NULL because there's no interest expense) always passes any ICR
    # minimum threshold -> represent as +inf for filtering purposes.
    df["interest_coverage_for_filter"] = np.where(
        df["icr_label"] == "Debt Free", np.inf, df["interest_coverage"]
    )

    return df


# ===========================================================================
# Day 15 — generic threshold filter engine
# ===========================================================================

def apply_filters(df: pd.DataFrame, filters: dict, metrics_cfg: dict, special_rules: dict) -> pd.DataFrame:
    """
    Apply a preset's `filters` dict (metric_key -> {min/max/eq/positive/declining: value})
    against `df`, using metrics_cfg for the column-source lookup.
    Returns the filtered DataFrame (rows that pass ALL filters).
    """
    mask = pd.Series(True, index=df.index)

    for metric_key, condition in filters.items():
        meta = metrics_cfg[metric_key]
        column = meta["column"]

        # ICR uses the +inf-for-debt-free column when the filter is a min threshold
        if metric_key == "icr" and special_rules.get("icr_debt_free_is_infinity", True):
            series = df["interest_coverage_for_filter"]
        elif metric_key == "revenue_cagr_3yr":
            series = df["revenue_cagr_3yr"]
        else:
            series = df[column]

        if "min" in condition:
            m = series >= condition["min"]
        elif "max" in condition:
            m = series <= condition["max"]
        elif "eq" in condition:
            m = series == condition["eq"]
        elif condition.get("positive"):
            m = series > 0
        elif condition.get("declining"):
            m = df["de_declining"] if metric_key == "de" else (series.diff() < 0)
        else:
            raise ValueError(f"Unrecognised filter condition for {metric_key}: {condition}")

        # Missing data never passes a threshold filter
        m = m.fillna(False)

        # D/E filter auto-skips companies in the Financials sector (Day 15 special case)
        if metric_key == "de" and special_rules.get("de_skips_financials_sector", True):
            m = m | (df["broad_sector"] == "Financials")

        mask &= m

    return df.loc[mask].copy()


# ===========================================================================
# Day 16 — 6 preset screeners
# ===========================================================================

def run_preset(df: pd.DataFrame, preset_key: str, config: dict) -> pd.DataFrame:
    preset = config["presets"][preset_key]
    result = apply_filters(df, preset["filters"], config["metrics"], config["special_rules"])
    sort_col = "composite_quality_score" if "composite_quality_score" in result.columns else "return_on_equity_pct"
    return result.sort_values(sort_col, ascending=False)


def run_all_presets(df: pd.DataFrame, config: dict) -> dict[str, pd.DataFrame]:
    return {key: run_preset(df, key, config) for key in config["presets"]}


# ===========================================================================
# Day 17 — composite quality score
# ===========================================================================

def _winsorised_scale(series: pd.Series, lower_pct: float, upper_pct: float, inverse: bool = False) -> pd.Series:
    """Clip `series` to its [lower_pct, upper_pct] percentile range, then
    min-max scale the clipped values to 0-100. `inverse=True` flips the
    scale so a *lower* raw value scores *higher* (used for D/E)."""
    s = series.astype(float)
    valid = s.dropna()
    if valid.empty:
        return pd.Series(np.nan, index=series.index)

    lo, hi = np.nanpercentile(valid, lower_pct), np.nanpercentile(valid, upper_pct)
    clipped = s.clip(lower=lo, upper=hi)

    if hi == lo:
        scaled = pd.Series(50.0, index=series.index)
        scaled[s.isna()] = np.nan
        return scaled

    scaled = (clipped - lo) / (hi - lo) * 100
    if inverse:
        scaled = 100 - scaled
    return scaled


def _build_score_inputs(df: pd.DataFrame, conn: sqlite3.Connection) -> pd.DataFrame:
    """Compute the composite-score-only derived fields not already in the
    universe: fcf_cagr_5yr, cfo_pat_ratio, fcf_positive_flag."""
    fr_all = pd.read_sql("SELECT company_id, year, free_cash_flow_cr FROM financial_ratios", conn)
    fr_all["free_cash_flow_cr"] = pd.to_numeric(fr_all["free_cash_flow_cr"], errors="coerce")
    pl_all = pd.read_sql("SELECT company_id, year, net_profit FROM profitandloss", conn)
    cf_all = pd.read_sql("SELECT company_id, year, operating_activity FROM cashflow", conn)

    fcf_cagr, cfo_pat_ratio, fcf_positive = {}, {}, {}

    for company_id, grp in fr_all.groupby("company_id"):
        series = list(zip(grp["year"], grp["free_cash_flow_cr"]))
        value, _flag = cagr_from_series(series, window_years=5)
        fcf_cagr[company_id] = value
        latest = grp.sort_values("year")["free_cash_flow_cr"].iloc[-1] if not grp.empty else None
        fcf_positive[company_id] = 1.0 if (latest is not None and pd.notna(latest) and latest > 0) else 0.0

    cfo_by_co = cf_all.groupby("company_id")
    pat_by_co = pl_all.groupby("company_id")
    for company_id in fr_all["company_id"].unique():
        cfo_grp = cfo_by_co.get_group(company_id).sort_values("year") if company_id in cfo_by_co.groups else pd.DataFrame()
        pat_grp = pat_by_co.get_group(company_id).sort_values("year") if company_id in pat_by_co.groups else pd.DataFrame()
        merged = cfo_grp.merge(pat_grp, on=["company_id", "year"], how="inner")
        pairs = list(zip(merged["operating_activity"], merged["net_profit"]))
        score, _label = cfo_quality_score(pairs)
        cfo_pat_ratio[company_id] = score

    out = df[["company_id"]].copy()
    out["fcf_cagr_5yr"] = out["company_id"].map(fcf_cagr)
    out["cfo_pat_ratio"] = out["company_id"].map(cfo_pat_ratio)
    out["fcf_positive_flag"] = out["company_id"].map(fcf_positive)
    return out


def compute_composite_scores(df: pd.DataFrame, config: dict, conn: sqlite3.Connection) -> pd.DataFrame:
    """
    Composite quality score (0-100 scale):
        35% Profitability  (ROE 15% + ROCE 10% + NPM 10%)
        30% Cash Quality   (FCF CAGR 15% + CFO/PAT ratio 10% + FCF positive flag 5%)
        20% Growth         (Revenue CAGR 10% + PAT CAGR 10%)
        15% Leverage       (D/E score 10% + ICR score 5%)

    Each component is P10/P90-winsorised then min-max scaled to 0-100
    before weighting. Adds `composite_quality_score` (global) and
    `composite_quality_score_sector_relative` (percentile rank of the
    global score within the company's broad_sector, 0-100) to `df`.
    """
    cfg = config["composite_score"]
    lo_pct, hi_pct = cfg["winsorisation"]["lower_percentile"], cfg["winsorisation"]["upper_percentile"]

    extra = _build_score_inputs(df, conn)
    work = df.merge(extra, on="company_id", how="left")

    # ICR score: Debt Free -> 100 directly (best possible), else winsorised scale
    icr_score_raw = _winsorised_scale(work["interest_coverage"], lo_pct, hi_pct)
    icr_score = icr_score_raw.where(work["icr_label"] != "Debt Free", 100.0)

    component_scores = {
        "roe":               _winsorised_scale(work["return_on_equity_pct"], lo_pct, hi_pct),
        "roce":              _winsorised_scale(work["roce_percentage"], lo_pct, hi_pct),
        "npm":                _winsorised_scale(work["net_profit_margin_pct"], lo_pct, hi_pct),
        "fcf_cagr":           _winsorised_scale(work["fcf_cagr_5yr"], lo_pct, hi_pct),
        "cfo_pat_ratio":      _winsorised_scale(work["cfo_pat_ratio"], lo_pct, hi_pct),
        "fcf_positive_flag": work["fcf_positive_flag"] * 100,
        "revenue_cagr":       _winsorised_scale(work["revenue_cagr_5yr"], lo_pct, hi_pct),
        "pat_cagr":            _winsorised_scale(work["pat_cagr_5yr"], lo_pct, hi_pct),
        "de_score":            _winsorised_scale(work["debt_to_equity"], lo_pct, hi_pct, inverse=True),
        "icr_score":           icr_score,
    }

    weights = {
        "roe": 0.15, "roce": 0.10, "npm": 0.10,
        "fcf_cagr": 0.15, "cfo_pat_ratio": 0.10, "fcf_positive_flag": 0.05,
        "revenue_cagr": 0.10, "pat_cagr": 0.10,
        "de_score": 0.10, "icr_score": 0.05,
    }

    total_weighted = pd.Series(0.0, index=work.index)
    total_weight_used = pd.Series(0.0, index=work.index)
    for key, weight in weights.items():
        s = component_scores[key]
        available = s.notna()
        total_weighted += s.fillna(0) * weight * available
        total_weight_used += weight * available

    composite = np.where(total_weight_used > 0, total_weighted / total_weight_used, np.nan)
    df = df.copy()
    df["composite_quality_score"] = composite

    # Sector-relative: percentile rank of composite score within broad_sector
    df["composite_quality_score_sector_relative"] = (
        df.groupby("broad_sector")["composite_quality_score"]
          .rank(pct=True, na_option="keep") * 100
    )

    return df


# ===========================================================================
# Day 17 — Excel export
# ===========================================================================

_PRESET_THRESHOLD_COLUMNS = {
    "quality_compounder":  ["return_on_equity_pct", "debt_to_equity", "free_cash_flow_cr", "revenue_cagr_5yr"],
    "value_pick":           ["pe_ratio", "pb_ratio", "debt_to_equity", "dividend_yield_pct"],
    "growth_accelerator":   ["pat_cagr_5yr", "revenue_cagr_5yr", "debt_to_equity"],
    "dividend_champion":    ["dividend_yield_pct", "dividend_payout_ratio_pct", "free_cash_flow_cr"],
    "debt_free_blue_chip":  ["debt_to_equity", "return_on_equity_pct", "sales"],
    "turnaround_watch":     ["revenue_cagr_3yr", "free_cash_flow_cr", "de_declining"],
}

_KPI_COLUMNS = [
    "company_id", "company_name", "broad_sector", "sub_sector",
    "return_on_equity_pct", "roce_percentage", "net_profit_margin_pct",
    "operating_profit_margin_pct", "debt_to_equity", "interest_coverage",
    "asset_turnover", "free_cash_flow_cr", "earnings_per_share",
    "dividend_payout_ratio_pct", "dividend_yield_pct", "pe_ratio", "pb_ratio",
    "market_cap_crore", "revenue_cagr_5yr", "pat_cagr_5yr", "eps_cagr_5yr",
    "composite_quality_score",
]


def _preset_passes(row: pd.Series, preset_key: str, config: dict) -> dict[str, bool]:
    """Per-column pass/fail against the preset's own thresholds, for cell colour-coding."""
    preset = config["presets"][preset_key]
    metrics_cfg = config["metrics"]
    passes = {}
    for metric_key, condition in preset["filters"].items():
        col = metrics_cfg[metric_key]["column"]
        val = row.get("revenue_cagr_3yr" if metric_key == "revenue_cagr_3yr" else col)
        if metric_key == "icr":
            val = row.get("interest_coverage_for_filter")
        ok = False
        if val is not None and not (isinstance(val, float) and np.isnan(val)):
            if "min" in condition:
                ok = val >= condition["min"]
            elif "max" in condition:
                ok = val <= condition["max"]
            elif "eq" in condition:
                ok = val == condition["eq"]
            elif condition.get("positive"):
                ok = val > 0
            elif condition.get("declining"):
                ok = bool(row.get("de_declining")) if metric_key == "de" else False
        elif metric_key == "de" and config["special_rules"].get("de_skips_financials_sector") \
                and row.get("broad_sector") == "Financials":
            ok = True
        passes[col if col in row.index else metric_key] = ok
    return passes


def export_screener_output(preset_results: dict[str, pd.DataFrame], config: dict,
                            out_path: Path = OUTPUT_DIR / "screener_output.xlsx") -> Path:
    """Day 17: one sheet per preset, 20 KPI columns, sorted by composite
    score descending, with green/red cell colour-coding on the preset's
    own threshold columns."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    export_cfg = config.get("export", {})
    pass_fill = PatternFill(start_color=export_cfg.get("pass_fill_color", "C6EFCE"),
                             end_color=export_cfg.get("pass_fill_color", "C6EFCE"), fill_type="solid")
    fail_fill = PatternFill(start_color=export_cfg.get("fail_fill_color", "FFC7CE"),
                             end_color=export_cfg.get("fail_fill_color", "FFC7CE"), fill_type="solid")
    header_font = Font(bold=True)

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        for preset_key, result in preset_results.items():
            label = config["presets"][preset_key]["label"]
            cols = [c for c in _KPI_COLUMNS if c in result.columns]
            sheet_df = result[cols].reset_index(drop=True)
            sheet_name = label[:31]
            sheet_df.to_excel(writer, sheet_name=sheet_name, index=False)

            ws = writer.sheets[sheet_name]
            for c_idx, col_name in enumerate(cols, start=1):
                ws.cell(row=1, column=c_idx).font = header_font
                ws.column_dimensions[get_column_letter(c_idx)].width = max(14, len(col_name) + 2)

            threshold_cols = set(_PRESET_THRESHOLD_COLUMNS.get(preset_key, []))
            for r_idx, (_, row) in enumerate(result.iterrows(), start=2):
                passes = _preset_passes(row, preset_key, config)
                for c_idx, col_name in enumerate(cols, start=1):
                    if col_name in threshold_cols and col_name in passes:
                        cell = ws.cell(row=r_idx, column=c_idx)
                        cell.fill = pass_fill if passes[col_name] else fail_fill

    logger.info("Wrote %s (%d preset sheets)", out_path, len(preset_results))
    return out_path


# ===========================================================================
# Orchestration
# ===========================================================================

def run_screener() -> dict:
    config = load_config()
    conn = sqlite3.connect(DB_PATH)

    universe = build_universe(conn)
    universe = compute_composite_scores(universe, config, conn)
    conn.close()

    presets = run_all_presets(universe, config)
    for key, result in presets.items():
        label = config["presets"][key]["label"]
        logger.info("Preset %-22s -> %3d companies (universe=%d)", label, len(result), len(universe))

    export_path = export_screener_output(presets, config)
    return {"universe_size": len(universe), "presets": {k: len(v) for k, v in presets.items()}, "export_path": str(export_path)}


if __name__ == "__main__":
    result = run_screener()
    print()
    print("=== SCREENER RUN SUMMARY ===")
    print(f"Universe size: {result['universe_size']}")
    for key, count in result["presets"].items():
        print(f"  {key:22s} {count:3d} companies")
    print(f"Output: {result['export_path']}")
