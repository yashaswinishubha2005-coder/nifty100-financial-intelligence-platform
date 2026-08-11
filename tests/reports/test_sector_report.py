"""
tests/reports/test_sector_report.py — Sprint 5, Day 34 unit tests for
src/reports/sector_report.py.
"""

import sqlite3
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src" / "reports"))

from sector_report import load_sector_universe, generate_sector_report, SECTOR_DIR

DB_PATH = PROJECT_ROOT / "data" / "nifty100.db"


@pytest.fixture(scope="module")
def universe():
    if not DB_PATH.exists():
        pytest.skip("data/nifty100.db not built yet")
    conn = sqlite3.connect(DB_PATH)
    result = load_sector_universe(conn)
    conn.close()
    return result


class TestLoadSectorUniverse:
    def test_covers_exactly_11_peer_groups(self, universe):
        assert universe["peer_group_name"].nunique() == 11

    def test_covers_56_peer_group_members(self, universe):
        assert len(universe) == 56


class TestGenerateSectorReport:
    def test_generates_pdf_for_a_group(self, universe, tmp_path):
        group_df = universe[universe["peer_group_name"] == "IT Services"]
        out_path = generate_sector_report("IT Services", group_df, out_dir=tmp_path)
        assert out_path.exists()
        assert out_path.stat().st_size > 1024

    def test_handles_group_with_missing_metrics_gracefully(self, universe, tmp_path):
        # Steel or another small group may have NaN cells (e.g. missing
        # ROCE for a member) -- must not crash, N/A should render instead.
        group_df = universe[universe["peer_group_name"] == "Steel"]
        out_path = generate_sector_report("Steel", group_df, out_dir=tmp_path)
        assert out_path.exists()


class TestSectorReportBatchOutput:
    def test_all_11_sector_pdfs_exist(self):
        if not SECTOR_DIR.exists():
            pytest.skip("reports/sector/ not generated yet")
        pdfs = list(SECTOR_DIR.glob("*_report.pdf"))
        assert len(pdfs) == 11
