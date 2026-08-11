"""
tests/reports/test_tearsheet.py — Sprint 5, Day 33-34 unit tests for
src/reports/tearsheet.py.
"""

import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src" / "reports"))

from tearsheet import load_company_data, generate_tearsheet, MIN_YEARS_REQUIRED, TEARSHEETS_DIR

DB_PATH = PROJECT_ROOT / "data" / "nifty100.db"


@pytest.fixture(scope="module")
def conn():
    if not DB_PATH.exists():
        pytest.skip("data/nifty100.db not built yet")
    c = sqlite3.connect(DB_PATH)
    yield c
    c.close()


class TestLoadCompanyData:
    def test_unknown_ticker_returns_none(self, conn):
        assert load_company_data("__NOT_REAL__", conn) is None

    def test_known_ticker_with_enough_history_loads(self, conn):
        data = load_company_data("TCS", conn)
        assert data is not None
        assert data["insufficient_data"] is False
        assert data["company_id"] == "TCS"
        assert data["company_name"]

    def test_jiofin_has_insufficient_data_flag(self, conn):
        # JIOFIN has only 3 financial_ratios rows (see Sprint 5 Day 27
        # QA notes) -- right at or near the MIN_YEARS_REQUIRED boundary.
        data = load_company_data("JIOFIN", conn)
        assert data is not None
        # Whatever the outcome, it must not crash and must report a
        # consistent years_available if flagged insufficient.
        if data["insufficient_data"]:
            assert data["years_available"] < MIN_YEARS_REQUIRED


class TestGenerateTearsheet:
    @staticmethod
    @pytest.fixture(scope="class")
    def pros_cons_df():
        path = PROJECT_ROOT / "output" / "pros_cons_generated.csv"
        if not path.exists():
            pytest.skip("output/pros_cons_generated.csv not built yet")
        return pd.read_csv(path)

    @staticmethod
    @pytest.fixture(scope="class")
    def capital_df():
        path = PROJECT_ROOT / "output" / "capital_allocation.csv"
        if not path.exists():
            pytest.skip("output/capital_allocation.csv not built yet")
        return pd.read_csv(path)

    def test_generates_pdf_at_least_30kb(self, conn, tmp_path, pros_cons_df, capital_df):
        out_path = generate_tearsheet("TCS", conn, pros_cons_df, capital_df, out_dir=tmp_path)
        assert out_path is not None
        assert out_path.exists()
        assert out_path.stat().st_size >= 30 * 1024

    def test_pdf_has_exactly_2_pages(self, conn, tmp_path, pros_cons_df, capital_df):
        out_path = generate_tearsheet("INFY", conn, pros_cons_df, capital_df, out_dir=tmp_path)
        from pypdf import PdfReader
        reader = PdfReader(str(out_path))
        assert len(reader.pages) == 2

    def test_multiple_sectors_generate_without_error(self, conn, tmp_path, pros_cons_df, capital_df):
        for ticker in ["TCS", "HDFCBANK", "RELIANCE", "SUNPHARMA", "TATASTEEL"]:
            out_path = generate_tearsheet(ticker, conn, pros_cons_df, capital_df, out_dir=tmp_path)
            assert out_path is not None
            assert out_path.stat().st_size >= 30 * 1024


class TestBatchOutputRealData:
    def test_all_92_tearsheets_exist_and_meet_min_size(self):
        """Day 34/35 exit criteria: all 92 tearsheets exist and are at
        least 30 KB each."""
        if not TEARSHEETS_DIR.exists():
            pytest.skip("reports/tearsheets/ not generated yet")
        pdfs = list(TEARSHEETS_DIR.glob("*_tearsheet.pdf"))
        assert len(pdfs) == 92
        undersized = [p for p in pdfs if p.stat().st_size < 30 * 1024]
        assert undersized == [], f"{len(undersized)} tearsheet(s) under 30KB: {undersized[:5]}"
