"""
src/reports/tearsheet.py — 2-page company tearsheet PDF generator.

Sprint 5, Days 33-34 deliverable (Epic 08, Module 1).

Page 1: navy header bar (company name + ticker) -> 6 KPI tiles (2 rows
of 3) -> 10-year Revenue/Net Profit bar chart + ROE/ROCE dual-axis line
chart, side by side.

Page 2: Balance Sheet composition stacked bar + Cash Flow waterfall,
side by side -> Pros section (green bullets) -> Cons section (red
bullets) -> Capital Allocation badge.

Every text-bearing table cell uses a reportlab Paragraph (not a raw
string) so long company names, sector labels, and NLP-generated
pros/cons text wrap within their column instead of overflowing --
the Day 33 "all table columns must use WORDWRAP" requirement.

Usage:
    python src/reports/tearsheet.py TCS                 # single company, prints to reports/tearsheets/
    python src/reports/tearsheet.py --batch              # all 92 companies (Day 34)
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
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2] if (Path(__file__).resolve().parent.name == "reports") else Path.cwd()
DB_PATH = PROJECT_ROOT / "data" / "nifty100.db"
OUTPUT_DIR = PROJECT_ROOT / "output"
TEARSHEETS_DIR = PROJECT_ROOT / "reports" / "tearsheets"

MIN_YEARS_REQUIRED = 3

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chart_helpers as ch  # noqa: E402

sys.path.insert(0, str(PROJECT_ROOT / "src" / "nlp"))
from pros_cons_generator import CompanyProfile  # noqa: E402 (reused for the ROCE time series helper)

NAVY = colors.HexColor("#1E1B4B")
PURPLE = colors.HexColor("#6D28D9")
ORANGE = colors.HexColor("#F97316")
GREEN = colors.HexColor("#15803D")
GREEN_BG = colors.HexColor("#DCFCE7")
RED = colors.HexColor("#B91C1C")
RED_BG = colors.HexColor("#FEE2E2")
TILE_BG = colors.HexColor("#F3F4F6")
GOLD = colors.HexColor("#FFD966")

STYLES = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=STYLES["Normal"], fontSize=8, leading=10, wordWrap="CJK")
TILE_LABEL = ParagraphStyle("tile_label", parent=STYLES["Normal"], fontSize=7.5, textColor=colors.HexColor("#6B7280"), wordWrap="CJK")
TILE_VALUE = ParagraphStyle("tile_value", parent=STYLES["Normal"], fontSize=13, textColor=NAVY, fontName="Helvetica-Bold", wordWrap="CJK")
HEADER_NAME = ParagraphStyle("header_name", parent=STYLES["Normal"], fontSize=18, textColor=colors.white, fontName="Helvetica-Bold", wordWrap="CJK")
HEADER_SUB = ParagraphStyle("header_sub", parent=STYLES["Normal"], fontSize=10, textColor=colors.HexColor("#C7C3F0"), wordWrap="CJK")
SECTION_TITLE = ParagraphStyle("section_title", parent=STYLES["Normal"], fontSize=11, textColor=NAVY, fontName="Helvetica-Bold", spaceAfter=4)
PRO_TEXT = ParagraphStyle("pro_text", parent=BODY, textColor=colors.HexColor("#166534"))
CON_TEXT = ParagraphStyle("con_text", parent=BODY, textColor=colors.HexColor("#991B1B"))


def _fmt(value, decimals=2, suffix="") -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "N/A"
    try:
        return f"{float(value):,.{decimals}f}{suffix}"
    except (TypeError, ValueError):
        return "N/A"


# ===========================================================================
# Data assembly
# ===========================================================================

def load_company_data(company_id: str, conn: sqlite3.Connection) -> Optional[dict]:
    company_row = pd.read_sql("SELECT id, company_name FROM companies WHERE id = ?", conn, params=(company_id,))
    if company_row.empty:
        return None
    sector_row = pd.read_sql("SELECT broad_sector, sub_sector FROM sectors WHERE company_id = ?", conn, params=(company_id,))

    fr = pd.read_sql("SELECT * FROM financial_ratios WHERE company_id = ? ORDER BY year", conn, params=(company_id,))
    for col in fr.columns:
        if col not in ("company_id", "year", "icr_label"):
            fr[col] = pd.to_numeric(fr[col], errors="coerce")
    pl = pd.read_sql("SELECT * FROM profitandloss WHERE company_id = ? ORDER BY year", conn, params=(company_id,))
    bs = pd.read_sql("SELECT * FROM balancesheet WHERE company_id = ? ORDER BY year", conn, params=(company_id,))
    cf = pd.read_sql("SELECT * FROM cashflow WHERE company_id = ? ORDER BY year", conn, params=(company_id,))
    mc = pd.read_sql("SELECT * FROM market_cap WHERE company_id = ? ORDER BY year", conn, params=(company_id,))

    n_years = max(len(fr), len(pl))
    if n_years < MIN_YEARS_REQUIRED:
        return {"insufficient_data": True, "years_available": n_years}

    profile = CompanyProfile(company_id, fr, pl, bs, mc, sector_row["broad_sector"].iloc[0] if not sector_row.empty else None)

    return {
        "insufficient_data": False,
        "company_id": company_id,
        "company_name": company_row["company_name"].iloc[0],
        "broad_sector": sector_row["broad_sector"].iloc[0] if not sector_row.empty else "N/A",
        "sub_sector": sector_row["sub_sector"].iloc[0] if not sector_row.empty else "N/A",
        "fr": fr, "pl": pl, "bs": bs, "cf": cf, "mc": mc, "roce": profile.roce,
    }


# ===========================================================================
# Page builders
# ===========================================================================

def _header_bar(data: dict, doc_width: float):
    tbl = Table(
        [[Paragraph(f"{data['company_name']}", HEADER_NAME)],
         [Paragraph(f"{data['company_id']}  \u00b7  {data['broad_sector']} / {data['sub_sector']}", HEADER_SUB)]],
        colWidths=[doc_width],
    )
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, 0), 10),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
        ("TOPPADDING", (0, 1), (-1, 1), 2),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 10),
    ]))
    return tbl


def _kpi_tiles(data: dict, doc_width: float):
    fr = data["fr"]
    latest = fr.dropna(subset=["return_on_equity_pct"]).tail(1)
    latest = latest.iloc[0] if not latest.empty else (fr.iloc[-1] if not fr.empty else pd.Series(dtype=object))
    latest_roce = data["roce"].dropna().tail(1)
    latest_roce_val = latest_roce.iloc[0] if not latest_roce.empty else None

    tiles = [
        ("ROE", _fmt(latest.get("return_on_equity_pct"), suffix="%")),
        ("ROCE", _fmt(latest_roce_val, suffix="%")),
        ("Net Profit Margin", _fmt(latest.get("net_profit_margin_pct"), suffix="%")),
        ("D/E", _fmt(latest.get("debt_to_equity"))),
        ("Revenue CAGR 5yr", _fmt(latest.get("revenue_cagr_5yr"), suffix="%")),
        ("FCF (Rs. Cr)", _fmt(latest.get("free_cash_flow_cr"), decimals=0)),
    ]
    col_w = doc_width / 3
    cell_data = []
    for row_tiles in (tiles[:3], tiles[3:]):
        row = []
        for label, value in row_tiles:
            row.append(Table([[Paragraph(label, TILE_LABEL)], [Paragraph(value, TILE_VALUE)]], colWidths=[col_w - 12]))
        cell_data.append(row)

    tbl = Table(cell_data, colWidths=[col_w] * 3, rowHeights=[0.62 * inch] * 2)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), TILE_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.white),
        ("INNERGRID", (0, 0), (-1, -1), 3, colors.white),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return tbl


def _charts_row(img1: "io.BytesIO", img2: "io.BytesIO", doc_width: float):
    col_w = doc_width / 2 - 4
    im1 = Image(img1, width=col_w, height=col_w * 0.46)
    im2 = Image(img2, width=col_w, height=col_w * 0.46)
    tbl = Table([[im1, im2]], colWidths=[doc_width / 2, doc_width / 2])
    tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return tbl


def _pros_cons_section(company_id: str, pros_cons_df: pd.DataFrame, doc_width: float):
    rows = pros_cons_df[pros_cons_df["company_id"] == company_id] if pros_cons_df is not None else pd.DataFrame()
    pros = rows[rows["type"] == "pro"].sort_values("confidence_pct", ascending=False).head(5)
    cons = rows[rows["type"] == "con"].sort_values("confidence_pct", ascending=False).head(5)

    elements = [Paragraph("Pros", ParagraphStyle("pros_head", parent=SECTION_TITLE, textColor=GREEN))]
    if pros.empty:
        elements.append(Paragraph("No pro signals available.", BODY))
    else:
        for _, r in pros.iterrows():
            elements.append(Paragraph(f"\u2713 {r['text']} ({r['confidence_pct']:.0f}% confidence)", PRO_TEXT))
    elements.append(Spacer(1, 8))
    elements.append(Paragraph("Cons", ParagraphStyle("cons_head", parent=SECTION_TITLE, textColor=RED)))
    if cons.empty:
        elements.append(Paragraph("No con signals available.", BODY))
    else:
        for _, r in cons.iterrows():
            elements.append(Paragraph(f"\u2717 {r['text']} ({r['confidence_pct']:.0f}% confidence)", CON_TEXT))
    return elements


def _capital_allocation_badge(company_id: str, capital_df: pd.DataFrame, doc_width: float):
    label = "N/A"
    if capital_df is not None:
        rows = capital_df[(capital_df["company_id"] == company_id) & capital_df["pattern_label"].notna()]
        if not rows.empty:
            label = rows.sort_values("year").iloc[-1]["pattern_label"]
    tbl = Table([[Paragraph(f"Capital Allocation Pattern:  <b>{label}</b>", BODY)]], colWidths=[doc_width])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GOLD),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return tbl


# ===========================================================================
# Orchestration
# ===========================================================================

def generate_tearsheet(company_id: str, conn: sqlite3.Connection, pros_cons_df: pd.DataFrame,
                        capital_df: pd.DataFrame, out_dir: Path = TEARSHEETS_DIR) -> Optional[Path]:
    data = load_company_data(company_id, conn)
    if data is None:
        logger.warning("%s: not found in companies table, skipping", company_id)
        return None
    if data["insufficient_data"]:
        logger.info("%s: only %d year(s) of data (<%d), skipping", company_id, data["years_available"], MIN_YEARS_REQUIRED)
        return None

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{company_id}_tearsheet.pdf"

    doc = SimpleDocTemplate(str(out_path), pagesize=A4,
                             leftMargin=0.5 * inch, rightMargin=0.5 * inch,
                             topMargin=0.4 * inch, bottomMargin=0.4 * inch)
    doc_width = A4[0] - 1.0 * inch

    fr, pl, bs, cf = data["fr"], data["pl"], data["bs"], data["cf"]

    # --- Page 1 ---
    rev_profit_img = ch.revenue_net_profit_bar(
        pl["year"].tail(10).tolist(), pl["sales"].tail(10).tolist(), pl["net_profit"].tail(10).tolist())

    # ROE (financial_ratios) and ROCE (computed from pl+bs) don't
    # necessarily share the same year coverage -- align both on a
    # single outer-joined year index before charting so the x-axis and
    # both y-series always have matching lengths.
    roe_series = fr.set_index("year")["return_on_equity_pct"]
    roce_aligned = pd.DataFrame({"roe": roe_series}).join(data["roce"].rename("roce"), how="outer").sort_index().tail(10)
    roe_roce_img = ch.roe_roce_dual_axis(
        roce_aligned.index.tolist(), roce_aligned["roe"].tolist(), roce_aligned["roce"].tolist())

    story = [
        _header_bar(data, doc_width),
        Spacer(1, 10),
        _kpi_tiles(data, doc_width),
        Spacer(1, 10),
        _charts_row(rev_profit_img, roe_roce_img, doc_width),
        PageBreak(),
    ]

    # --- Page 2 ---
    bs_c = bs.tail(10)
    other_liab = bs_c["total_liabilities"] - bs_c["equity_capital"].fillna(0) - bs_c["reserves"].fillna(0) - bs_c["borrowings"].fillna(0)
    bs_img = ch.balance_sheet_stacked_bar(
        bs_c["year"].tolist(),
        (bs_c["equity_capital"].fillna(0) + bs_c["reserves"].fillna(0)).tolist(),
        bs_c["borrowings"].tolist(), other_liab.tolist())

    latest_cf = cf.tail(1)
    if not latest_cf.empty:
        r = latest_cf.iloc[0]
        cf_img = ch.cashflow_waterfall(r.get("operating_activity"), r.get("investing_activity"),
                                        r.get("financing_activity"), r.get("net_cash_flow"))
    else:
        cf_img = ch.cashflow_waterfall(None, None, None, None)

    story += [
        _charts_row(bs_img, cf_img, doc_width),
        Spacer(1, 12),
        *_pros_cons_section(company_id, pros_cons_df, doc_width),
        Spacer(1, 10),
        _capital_allocation_badge(company_id, capital_df, doc_width),
    ]

    doc.build(story)
    return out_path


def run_batch() -> dict:
    conn = sqlite3.connect(DB_PATH)
    companies = pd.read_sql("SELECT id FROM companies ORDER BY id", conn)["id"].tolist()

    pros_cons_path = OUTPUT_DIR / "pros_cons_generated.csv"
    pros_cons_df = pd.read_csv(pros_cons_path) if pros_cons_path.exists() else pd.DataFrame(
        columns=["company_id", "type", "rule_id", "text", "confidence_pct"])
    capital_path = OUTPUT_DIR / "capital_allocation.csv"
    capital_df = pd.read_csv(capital_path) if capital_path.exists() else pd.DataFrame(
        columns=["company_id", "year", "pattern_label"])

    generated, skipped = [], []
    for company_id in companies:
        path = generate_tearsheet(company_id, conn, pros_cons_df, capital_df)
        if path is None:
            data = load_company_data(company_id, conn)
            years = data["years_available"] if data and data.get("insufficient_data") else 0
            skipped.append({"company_id": company_id, "reason": "insufficient_data", "years_available": years})
        else:
            generated.append(path)
    conn.close()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    skipped_path = OUTPUT_DIR / "skipped_tearsheets.csv"
    pd.DataFrame(skipped, columns=["company_id", "reason", "years_available"]).to_csv(skipped_path, index=False)

    logger.info("Generated %d tearsheets, skipped %d (see %s)", len(generated), len(skipped), skipped_path)
    return {"generated": len(generated), "skipped": len(skipped), "skipped_path": str(skipped_path),
            "generated_paths": generated}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--batch":
        result = run_batch()
        print()
        print("=== TEARSHEET BATCH GENERATION SUMMARY ===")
        print(f"Generated: {result['generated']}")
        print(f"Skipped:   {result['skipped']} (see {result['skipped_path']})")
    elif len(sys.argv) > 1:
        ticker = sys.argv[1]
        conn = sqlite3.connect(DB_PATH)
        pros_cons_path = OUTPUT_DIR / "pros_cons_generated.csv"
        pros_cons_df = pd.read_csv(pros_cons_path) if pros_cons_path.exists() else None
        capital_path = OUTPUT_DIR / "capital_allocation.csv"
        capital_df = pd.read_csv(capital_path) if capital_path.exists() else None
        path = generate_tearsheet(ticker, conn, pros_cons_df, capital_df)
        conn.close()
        print(f"Generated: {path}" if path else "Skipped (insufficient data)")
    else:
        print("Usage: python src/reports/tearsheet.py <TICKER> | --batch")
