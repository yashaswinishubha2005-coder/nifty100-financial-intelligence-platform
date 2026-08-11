"""
src/reports/sector_report.py — Sector PDF report generator.

Sprint 5, Day 34 deliverable (Epic 08, Module 1).

One PDF per "sector" with a summary page (median KPIs) followed by a
table of every member company with 8 metrics each.

Note on "sector" vs "peer group": the Day 34 spec asks for "11 sector
PDFs", but this dataset's actual broad_sector classification
(sectors.broad_sector) has only 10 distinct values -- 11 is the count
of Sprint 3's peer groups (Automobiles, Consumer Finance, FMCG, IT
Services, Life Insurance, Oil & Gas, Pharmaceuticals, Power &
Utilities, Private Banks, Public Sector Banks, Steel), a different,
finer-grained classification (see src/dashboard/pages/06_sectors.py's
docstring for the same 10-vs-11 discrepancy noted in Sprint 4). Since
the spec's literal count (11) only matches the peer-group
classification, this module generates one PDF per Sprint 3 peer group.

Usage:
    python src/reports/sector_report.py
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2] if (Path(__file__).resolve().parent.name == "reports") else Path.cwd()
DB_PATH = PROJECT_ROOT / "data" / "nifty100.db"
SECTOR_DIR = PROJECT_ROOT / "reports" / "sector"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chart_helpers as ch  # noqa: E402

NAVY = colors.HexColor("#1E1B4B")
PURPLE = colors.HexColor("#6D28D9")
LIGHT_GREY = colors.HexColor("#F3F4F6")

STYLES = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=STYLES["Normal"], fontSize=8, leading=10, wordWrap="CJK")
HEADER_NAME = ParagraphStyle("header_name", parent=STYLES["Normal"], fontSize=18, textColor=colors.white, fontName="Helvetica-Bold", wordWrap="CJK")
HEADER_SUB = ParagraphStyle("header_sub", parent=STYLES["Normal"], fontSize=10, textColor=colors.HexColor("#C7C3F0"), wordWrap="CJK")
CELL = ParagraphStyle("cell", parent=STYLES["Normal"], fontSize=7.5, leading=9, wordWrap="CJK")
CELL_HEADER = ParagraphStyle("cell_header", parent=CELL, textColor=colors.white, fontName="Helvetica-Bold")

METRIC_COLUMNS = [
    ("return_on_equity_pct", "ROE %"), ("roce_percentage", "ROCE %"),
    ("net_profit_margin_pct", "NPM %"), ("debt_to_equity", "D/E"),
    ("free_cash_flow_cr", "FCF (Cr)"), ("revenue_cagr_5yr", "Rev CAGR 5y %"),
    ("pat_cagr_5yr", "PAT CAGR 5y %"), ("composite_quality_score", "Composite"),
]


def _fmt(value, decimals=2) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "N/A"
    try:
        return f"{float(value):,.{decimals}f}"
    except (TypeError, ValueError):
        return "N/A"


def load_sector_universe(conn: sqlite3.Connection) -> pd.DataFrame:
    """Reuses the Sprint 3 screener engine's universe (latest-complete-
    year financial_ratios + composite score) joined to peer_groups, so
    this report's numbers match output/screener_output.xlsx and
    output/peer_comparison.xlsx rather than a third, independently
    recomputed universe."""
    screener_root = PROJECT_ROOT / "src" / "screener"
    if str(screener_root) not in sys.path:
        sys.path.insert(0, str(screener_root))
    import engine as screener_engine

    config = screener_engine.load_config()
    universe = screener_engine.build_universe(conn)
    universe = screener_engine.compute_composite_scores(universe, config, conn)

    peer_groups = pd.read_sql("SELECT peer_group_name, company_id, is_benchmark FROM peer_groups", conn)
    return peer_groups.merge(universe, on="company_id", how="left")


def _header_bar(title: str, subtitle: str, doc_width: float):
    tbl = Table([[Paragraph(title, HEADER_NAME)], [Paragraph(subtitle, HEADER_SUB)]], colWidths=[doc_width])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, 0), 10), ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
        ("TOPPADDING", (0, 1), (-1, 1), 2), ("BOTTOMPADDING", (0, 1), (-1, 1), 10),
    ]))
    return tbl


def generate_sector_report(peer_group_name: str, group_df: pd.DataFrame, out_dir: Path = SECTOR_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_name = peer_group_name.replace(" ", "_").replace("&", "and")
    out_path = out_dir / f"{safe_name}_report.pdf"

    doc = SimpleDocTemplate(str(out_path), pagesize=landscape(A4),
                             leftMargin=0.5 * inch, rightMargin=0.5 * inch,
                             topMargin=0.4 * inch, bottomMargin=0.4 * inch)
    doc_width = landscape(A4)[0] - 1.0 * inch

    medians = group_df[[c for c, _ in METRIC_COLUMNS]].median(numeric_only=True, skipna=True)
    chart_metrics = [(c, label) for c, label in METRIC_COLUMNS if c != "free_cash_flow_cr"]
    median_chart = ch.sector_median_kpi_bar(
        [label for _, label in chart_metrics], [medians.get(c) for c, _ in chart_metrics], figsize=(9, 2.6))
    median_fcf = medians.get("free_cash_flow_cr")

    story = [
        _header_bar(peer_group_name, f"Sector Report \u00b7 {len(group_df)} companies", doc_width),
        Spacer(1, 10),
        Image(median_chart, width=doc_width, height=doc_width * (2.6 / 9)),
        Paragraph(f"Median FCF: Rs. {_fmt(median_fcf, 0)} Cr &nbsp;&nbsp;(shown separately -- its Rs. Cr scale "
                  f"dwarfs the percentage/ratio metrics above on a shared axis)",
                  ParagraphStyle("fcf_note", parent=BODY, fontSize=8, textColor=colors.HexColor("#6B7280"))),
        Spacer(1, 14),
        Paragraph(f"<b>All {len(group_df)} companies in {peer_group_name}</b>",
                  ParagraphStyle("sec", parent=BODY, fontSize=11, textColor=NAVY)),
        Spacer(1, 6),
    ]

    header_row = [Paragraph("Ticker", CELL_HEADER), Paragraph("Company", CELL_HEADER)] + \
        [Paragraph(label, CELL_HEADER) for _, label in METRIC_COLUMNS]
    table_rows = [header_row]
    for _, row in group_df.sort_values("composite_quality_score", ascending=False, na_position="last").iterrows():
        name = row.get("company_name", row["company_id"])
        if row.get("is_benchmark"):
            name = f"\u2605 {name}"
        cells = [Paragraph(row["company_id"], CELL), Paragraph(str(name), CELL)] + \
            [Paragraph(_fmt(row.get(c)), CELL) for c, _ in METRIC_COLUMNS]
        table_rows.append(cells)

    col_widths = [0.7 * inch, 1.7 * inch] + [(doc_width - 2.4 * inch) / len(METRIC_COLUMNS)] * len(METRIC_COLUMNS)
    tbl = Table(table_rows, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PURPLE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D1D5DB")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(tbl)

    doc.build(story)
    return out_path


def run_batch() -> dict:
    conn = sqlite3.connect(DB_PATH)
    universe = load_sector_universe(conn)
    conn.close()

    generated = []
    for peer_group_name, group_df in universe.groupby("peer_group_name"):
        path = generate_sector_report(peer_group_name, group_df)
        generated.append(path)
        logger.info("Wrote %s (%d companies)", path, len(group_df))

    return {"generated": len(generated), "paths": generated}


if __name__ == "__main__":
    result = run_batch()
    print()
    print("=== SECTOR REPORT BATCH SUMMARY ===")
    print(f"Generated: {result['generated']} sector PDFs in {SECTOR_DIR}")
