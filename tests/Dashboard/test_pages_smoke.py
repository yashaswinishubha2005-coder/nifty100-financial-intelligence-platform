"""
tests/dashboard/test_pages_smoke.py — Sprint 4, Day 27 deliverable:
automated smoke tests for every dashboard screen, using Streamlit's
official headless testing harness (streamlit.testing.v1.AppTest) so
"all 8 screens load without errors for any of the 92 tickers" is a
regression test, not just a one-time manual QA pass.

These tests run each page's actual Python (no browser, no server) and
assert `at.exception` is empty after each interaction. This is the
same technique used for interactive manual QA during Sprint 4 Day 27.

Run with:
    pytest tests/dashboard/ -v
(slower than the rest of the suite -- ~370 page runs across all
tickers/sectors/peer-groups; expect a low double-digit number of
seconds.)
"""

import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PAGES_DIR = PROJECT_ROOT / "src" / "dashboard" / "pages"
APP_PATH = PROJECT_ROOT / "src" / "dashboard" / "app.py"
DB_PATH = PROJECT_ROOT / "data" / "nifty100.db"

try:
    from streamlit.testing.v1 import AppTest
except ImportError:  # pragma: no cover
    AppTest = None

pytestmark = [
    pytest.mark.skipif(not DB_PATH.exists(), reason="data/nifty100.db not built yet"),
    pytest.mark.skipif(AppTest is None, reason="streamlit.testing.v1.AppTest not available"),
]


@pytest.fixture(scope="module")
def all_tickers():
    conn = sqlite3.connect(DB_PATH)
    tickers = pd.read_sql("SELECT id FROM companies", conn)["id"].tolist()
    conn.close()
    return tickers


@pytest.fixture(scope="module")
def all_sectors():
    conn = sqlite3.connect(DB_PATH)
    sectors = pd.read_sql("SELECT DISTINCT broad_sector FROM sectors WHERE broad_sector IS NOT NULL", conn)
    conn.close()
    return sectors["broad_sector"].tolist()


@pytest.fixture(scope="module")
def all_peer_groups():
    conn = sqlite3.connect(DB_PATH)
    groups = pd.read_sql("SELECT DISTINCT peer_group_name FROM peer_groups", conn)
    conn.close()
    return groups["peer_group_name"].tolist()


# ===========================================================================
# Default load — every page and app.py, no interaction
# ===========================================================================

PAGE_FILES = sorted(PAGES_DIR.glob("*.py")) if PAGES_DIR.exists() else []


class TestDefaultLoad:
    def test_app_entrypoint_loads_without_exceptions(self):
        at = AppTest.from_file(str(APP_PATH))
        at.run(timeout=30)
        assert not list(at.exception)

    @pytest.mark.parametrize("page_path", PAGE_FILES, ids=lambda p: p.name)
    def test_page_loads_without_exceptions(self, page_path):
        at = AppTest.from_file(str(page_path))
        at.run(timeout=30)
        assert not list(at.exception), f"{page_path.name} raised: {list(at.exception)}"

    def test_exactly_8_pages_present(self):
        """Day 22 deliverable: pages/01_home.py through 08_reports.py."""
        assert len(PAGE_FILES) == 8


# ===========================================================================
# Day 27 exit criterion: all 8 screens load without errors for any of
# the 92 tickers (ticker-driven pages only: Profile, Trends, Reports)
# ===========================================================================

class TestAllTickersOnTickerDrivenScreens:
    @pytest.mark.parametrize("page_name", ["02_profile.py", "05_trends.py", "08_reports.py"])
    def test_all_92_tickers_load_without_exceptions(self, page_name, all_tickers):
        assert len(all_tickers) == 92
        failures = []
        for ticker in all_tickers:
            at = AppTest.from_file(str(PAGES_DIR / page_name))
            at.run(timeout=30)
            at.sidebar.text_input[0].set_value(ticker).run(timeout=30)
            if list(at.exception):
                failures.append((ticker, list(at.exception)))
        assert not failures, f"{page_name}: {len(failures)} ticker(s) raised exceptions: {failures[:3]}"


# ===========================================================================
# Peer Comparison screen — all 11 peer groups
# ===========================================================================

class TestPeerComparisonAllGroups:
    def test_all_11_peer_groups_load_without_exceptions(self, all_peer_groups):
        assert len(all_peer_groups) == 11
        for group in all_peer_groups:
            at = AppTest.from_file(str(PAGES_DIR / "04_peers.py"))
            at.run(timeout=30)
            at.sidebar.selectbox[0].select(group).run(timeout=30)
            assert not list(at.exception), f"{group}: {list(at.exception)}"


# ===========================================================================
# Sector Analysis screen — all sectors
# ===========================================================================

class TestSectorAnalysisAllSectors:
    def test_all_sectors_load_without_exceptions(self, all_sectors):
        for sector in all_sectors:
            at = AppTest.from_file(str(PAGES_DIR / "06_sectors.py"))
            at.run(timeout=30)
            at.sidebar.selectbox[0].select(sector).run(timeout=30)
            assert not list(at.exception), f"{sector}: {list(at.exception)}"


# ===========================================================================
# Screener screen — extreme slider values and all preset buttons
# ===========================================================================

class TestScreenerExtremesAndPresets:
    def test_all_sliders_at_minimum(self):
        at = AppTest.from_file(str(PAGES_DIR / "03_screener.py"))
        at.run(timeout=30)
        assert len(at.sidebar.slider) == 10  # Day 24: 10 metric sliders
        for s in at.sidebar.slider:
            s.set_value(s.min)
        at.run(timeout=30)
        assert not list(at.exception)

    def test_all_sliders_at_maximum(self):
        at = AppTest.from_file(str(PAGES_DIR / "03_screener.py"))
        at.run(timeout=30)
        for s in at.sidebar.slider:
            s.set_value(s.max)
        at.run(timeout=30)
        assert not list(at.exception)

    def test_all_preset_and_reset_buttons(self):
        """6 preset buttons (Day 24) + Reset filters."""
        at = AppTest.from_file(str(PAGES_DIR / "03_screener.py"))
        at.run(timeout=30)
        assert len(at.button) == 7
        for btn in at.button:
            btn.click().run(timeout=30)
            assert not list(at.exception), f"{btn.label}: {list(at.exception)}"


# ===========================================================================
# Company Profile screen — response-time exit criterion
# ===========================================================================

class TestProfileLoadTime:
    def test_profile_screen_loads_under_3_seconds(self, all_tickers):
        """Day 27 exit criterion: Company Profile screen loads in
        under 3 seconds, measured for 5 tickers."""
        import time
        for ticker in all_tickers[:5]:
            at = AppTest.from_file(str(PAGES_DIR / "02_profile.py"))
            at.run(timeout=30)
            start = time.time()
            at.sidebar.text_input[0].set_value(ticker).run(timeout=30)
            elapsed = time.time() - start
            assert not list(at.exception)
            assert elapsed < 3.0, f"{ticker} took {elapsed:.2f}s (limit 3.0s)"
