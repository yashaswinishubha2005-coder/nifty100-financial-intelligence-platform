"""
src/reports/portfolio_summary.py — Portfolio Summary PDF.

Sprint 5, Day 35 deliverable (Epic 08, Module 1).

One page per company, alphabetical by ticker: company name, sector,
top 6 KPIs (ROE, ROCE, Net Profit Margin, D/E, Revenue CAGR 5yr, FCF),
each with a trend arrow comparing the latest year to the prior year:
    up (\u25b2)    -> improved
    down (\u25bc)   -> declined
    flat (\u25b6)   -> within 2% either way

"Improved" is direction-aware: for ROE/ROCE/NPM/Revenue CAGR/FCF, a
higher value is an improvement (up = green); for D/E, a *lower* value
is the improvement (so a falling D/E gets an up/green arrow too, not a
down/red one) -- flagged explicitly per metric via the `inverse` flag
in KPI_METRICS rather than assuming "higher = better" uniformly.

Usage:
    python src/reports/portfolio_summary.py
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2] if (Path(__file__).resolve().parent.name == "reports") else Path.cwd()
DB_PATH = PROJECT_ROOT / "data" / "nifty100.db"
PORTFOLIO_DIR = PROJECT_ROOT / "reports" / "portfolio"

NAVY = colors.HexColor("#1E1B4B")
GREEN = colors.HexColor("#15803D")
RED = colors.HexColor("#B91C1C")
GREY = colors.HexColor("#6B7280")
TILE_BG = colors.HexColor("#F3F4F6")

STYLES = getSampleStyleSheet()
HEADER_NAME = ParagraphStyle("header_name", parent=STYLES["Normal"], fontSize=20, textColor=colors.white, fontName="Helvetica-Bold", wordWrap="CJK")
HEADER_SUB = ParagraphStyle("header_sub", parent=STYLES["Normal"], fontSize=11, textColor=colors.HexColor("#C7C3F0"), wordWrap="CJK")
TILE_LABEL = ParagraphStyle("tile_label", parent=STYLES["Normal"], fontSize=9, textColor=GREY, wordWrap="CJK")
TILE_VALUE = ParagraphStyle("tile_value", parent=STYLES["Normal"], fontSize=16, textColor=NAVY, fontName="Helvetica-Bold", wordWrap="CJK")
ARROW_UP = ParagraphStyle("arrow_up", parent=STYLES["Normal"], fontSize=14, textColor=GREEN, fontName="Helvetica-Bold")
ARROW_DOWN = ParagraphStyle("arrow_down", parent=STYLES["Normal"], fontSize=14, textColor=RED, fontName="Helvetica-Bold")
ARROW_FLAT = ParagraphStyle("arrow_flat", parent=STYLES["Normal"], fontSize=14, textColor=GREY, fontName="Helvetica-Bold")

FLAT_THRESHOLD_PCT = 2.0

KPI_METRICS = [
    ("return_on_equity_pct", "ROE", "%", False),
    ("_roce", "ROCE", "%", False),
    ("net_profit_margin_pct", "Net Profit Margin", "%", False),
    ("debt_to_equity", "D/E", "", True),   # inverse: lower is an improvement
    ("revenue_cagr_5yr", "Revenue CAGR 5yr", "%", False),
    ("free_cash_flow_cr", "FCF (Rs. Cr)", "", False),
]


def _fmt(value, suffix="") -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "N/A"
    try:
        return f"{float(value):,.2f}{suffix}"
    except (TypeError, ValueError):
        return "N/A"


def trend_arrow(latest: Optional[float], prior: Optional[float], inverse: bool = False) -> tuple:
    """Returns (symbol, style). Direction-aware: `inverse=True` means a
    *lower* value is the improvement (used for D/E)."""
    if latest is None or prior is None or pd.isna(latest) or pd.isna(prior) or prior == 0:
        return "\u2013", ARROW_FLAT
    pct_change = (latest - prior) / abs(prior) * 100
    if abs(pct_change) <= FLAT_THRESHOLD_PCT:
        return "\u25b6", ARROW_FLAT
    improved = (pct_change > 0) != inverse
    return ("\u25b2", ARROW_UP) if improved else ("\u25bc", ARROW_DOWN)


def _company_page(company_id: str, name: str, sector: str, sub_sector: str,
                   latest: pd.Series, prior: pd.Series, roce_latest: Optional[float],
                   roce_prior: Optional[float], doc_width: float) -> list:
    header = Table(
        [[Paragraph(name, HEADER_NAME)], [Paragraph(f"{company_id}  \u00b7  {sector} / {sub_sector}", HEADER_SUB)]],
        colWidths=[doc_width],
    )
    header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("LEFTPADDING", (0, 0), (-1, -1), 16),
        ("TOPPADDING", (0, 0), (-1, 0), 14), ("BOTTOMPADDING", (0, 0), (-1, 0), 3),
        ("TOPPADDING", (0, 1), (-1, 1), 3), ("BOTTOMPADDING", (0, 1), (-1, 1), 14),
    ]))

    col_w = doc_width / 3
    tiles = []
    for col, label, suffix, inverse in KPI_METRICS:
        if col == "_roce":
            latest_val, prior_val = roce_latest, roce_prior
        else:
            latest_val = latest.get(col) if latest is not None else None
            prior_val = prior.get(col) if prior is not None else None
        symbol, style = trend_arrow(latest_val, prior_val, inverse=inverse)
        tile = Table([
            [Paragraph(label, TILE_LABEL)],
            [Table([[Paragraph(_fmt(latest_val, suffix), TILE_VALUE), Paragraph(symbol, style)]],
                   colWidths=[col_w - 50, 40])],
        ], colWidths=[col_w - 14])
        tiles.append(tile)

    tile_rows = [tiles[0:3], tiles[3:6]]
    tile_table = Table(tile_rows, colWidths=[col_w] * 3, rowHeights=[0.85 * inch] * 2)
    tile_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), TILE_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.white),
        ("INNERGRID", (0, 0), (-1, -1), 3, colors.white),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    return [header, Spacer(1, 12), tile_table]


def run_portfolio_summary(out_dir: Path = PORTFOLIO_DIR) -> dict:
    conn = sqlite3.connect(DB_PATH)
    companies = pd.read_sql("SELECT id, company_name FROM companies ORDER BY id", conn)
    sectors = pd.read_sql("SELECT company_id, broad_sector, sub_sector FROM sectors", conn).set_index("company_id")

    sys.path.insert(0, str(PROJECT_ROOT / "src" / "nlp"))
    from pros_cons_generator import CompanyProfile

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "portfolio_summary.pdf"
    doc = SimpleDocTemplate(str(out_path), pagesize=A4,
                             leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                             topMargin=0.6 * inch, bottomMargin=0.6 * inch)
    doc_width = A4[0] - 1.2 * inch

    story = []
    included = 0
    for i, row in companies.iterrows():
        company_id, name = row["id"], row["company_name"]
        fr = pd.read_sql("SELECT * FROM financial_ratios WHERE company_id = ? ORDER BY year", conn, params=(company_id,))
        if fr.empty:
            continue
        for col in fr.columns:
            if col not in ("company_id", "year", "icr_label"):
                fr[col] = pd.to_numeric(fr[col], errors="coerce")

        pl = pd.read_sql("SELECT * FROM profitandloss WHERE company_id = ? ORDER BY year", conn, params=(company_id,))
        bs = pd.read_sql("SELECT * FROM balancesheet WHERE company_id = ? ORDER BY year", conn, params=(company_id,))
        mc = pd.read_sql("SELECT * FROM market_cap WHERE company_id = ? ORDER BY year", conn, params=(company_id,))
        sector_row = sectors.loc[company_id] if company_id in sectors.index else None

        profile = CompanyProfile(company_id, fr, pl, bs, mc,
                                  sector_row["broad_sector"] if sector_row is not None else None)
        roce = profile.roce.dropna()
        roce_latest = roce.iloc[-1] if len(roce) >= 1 else None
        roce_prior = roce.iloc[-2] if len(roce) >= 2 else None

        latest_row = fr.dropna(subset=["return_on_equity_pct"]).tail(1)
        latest = latest_row.iloc[0] if not latest_row.empty else fr.iloc[-1]
        prior_candidates = fr[fr["year"] < latest["year"]]
        prior = prior_candidates.iloc[-1] if not prior_candidates.empty else None

        story += _company_page(
            company_id, name,
            sector_row["broad_sector"] if sector_row is not None else "N/A",
            sector_row["sub_sector"] if sector_row is not None else "N/A",
            latest, prior, roce_latest, roce_prior, doc_width,
        )
        included += 1
        if i < len(companies) - 1:
            story.append(PageBreak())

    conn.close()
    doc.build(story)
    logger.info("Wrote %s (%d company pages)", out_path, included)
    return {"companies_included": included, "output_path": str(out_path)}


if __name__ == "__main__":
    result = run_portfolio_summary()
    print()
    print("=== PORTFOLIO SUMMARY SUMMARY ===")
    print(f"Companies included: {result['companies_included']}")
    print(f"Output: {result['output_path']}")
