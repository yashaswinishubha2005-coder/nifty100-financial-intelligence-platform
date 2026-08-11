"""
tests/analytics/test_peer.py — Sprint 3, Days 18-20 unit tests for
src/analytics/peer.py.

Covers:
    - _percent_rank(): SQL-style PERCENT_RANK, D/E inversion
    - compute_peer_percentiles(): 10 metrics x 11 real peer groups
    - lookup_company_percentiles(): NO_PEER_GROUP_MESSAGE for unassigned companies
    - Day 21 exit criteria: exactly 11 peer groups, IT Services / FMCG spot-checks

Run with:
    pytest tests/analytics/test_peer.py -v
"""

import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src" / "analytics"))

from peer import (
    _percent_rank, build_peer_universe, compute_peer_percentiles,
    lookup_company_percentiles, NO_PEER_GROUP_MESSAGE,
)

DB_PATH = PROJECT_ROOT / "data" / "nifty100.db"


@pytest.fixture(scope="module")
def conn():
    if not DB_PATH.exists():
        pytest.skip("data/nifty100.db not built yet")
    c = sqlite3.connect(DB_PATH)
    yield c
    c.close()


@pytest.fixture(scope="module")
def universe(conn):
    return build_peer_universe(conn)


@pytest.fixture(scope="module")
def peer_groups(conn):
    return pd.read_sql("SELECT peer_group_name, company_id, is_benchmark FROM peer_groups", conn)


@pytest.fixture(scope="module")
def percentiles(universe, peer_groups):
    return compute_peer_percentiles(universe, peer_groups)


# ===========================================================================
# _percent_rank
# ===========================================================================

class TestPercentRank:
    def test_highest_value_gets_100(self):
        series = pd.Series([10.0, 20.0, 30.0])
        result = _percent_rank(series)
        assert result.iloc[2] == 100.0

    def test_lowest_value_gets_0(self):
        series = pd.Series([10.0, 20.0, 30.0])
        result = _percent_rank(series)
        assert result.iloc[0] == 0.0

    def test_de_inversion_makes_lowest_de_the_best(self):
        de = pd.Series([2.0, 1.0, 0.5])  # ascending raw D/E
        inverted_rank = _percent_rank(-de)
        assert inverted_rank.idxmax() == de.idxmin()

    def test_nan_stays_nan(self):
        series = pd.Series([10.0, np.nan, 30.0])
        result = _percent_rank(series)
        assert pd.isna(result.iloc[1])


# ===========================================================================
# compute_peer_percentiles — against the real dataset
# ===========================================================================

class TestComputePeerPercentilesRealData:
    def test_exactly_11_peer_groups(self, peer_groups):
        assert peer_groups["peer_group_name"].nunique() == 11

    def test_percentiles_cover_10_metrics(self, percentiles):
        assert percentiles["metric"].nunique() == 10

    def test_percentile_ranks_within_0_100(self, percentiles):
        valid = percentiles["percentile_rank"].dropna()
        assert not valid.empty
        assert valid.between(0, 100).all()

    def test_it_services_highest_roe_has_highest_percentile(self, percentiles):
        """Day 21 exit criterion: within IT Services, the company with the
        highest ROE should have the highest ROE percentile rank."""
        grp = percentiles[(percentiles["peer_group_name"] == "IT Services") & (percentiles["metric"] == "ROE")]
        top_by_value = grp.loc[grp["value"].idxmax(), "company_id"]
        top_by_rank = grp.loc[grp["percentile_rank"].idxmax(), "company_id"]
        assert top_by_value == top_by_rank

    def test_fmcg_lowest_de_has_highest_de_percentile(self, percentiles):
        """D/E is inverted -- lowest raw D/E should get the highest percentile."""
        grp = percentiles[(percentiles["peer_group_name"] == "FMCG") & (percentiles["metric"] == "D/E")]
        lowest_de_company = grp.loc[grp["value"].idxmin(), "company_id"]
        top_rank_company = grp.loc[grp["percentile_rank"].idxmax(), "company_id"]
        assert lowest_de_company == top_rank_company


# ===========================================================================
# lookup_company_percentiles — unassigned companies
# ===========================================================================

class TestLookupCompanyPercentiles:
    def test_unassigned_company_returns_message_not_error(self, percentiles):
        result = lookup_company_percentiles("__NOT_A_REAL_COMPANY__", percentiles)
        assert result == NO_PEER_GROUP_MESSAGE

    def test_assigned_company_returns_dataframe(self, percentiles):
        result = lookup_company_percentiles("TCS", percentiles)
        assert isinstance(result, pd.DataFrame)
        assert not result.empty
