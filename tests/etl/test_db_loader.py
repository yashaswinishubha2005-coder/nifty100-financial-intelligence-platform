"""
tests/etl/test_db_loader.py — Unit tests for db_loader.py (src/etl/db_loader.py).

Covers Sprint 1, Day 04-05 acceptance criteria:
    - Schema creation (14 tables from db/schema.sql, incl. Sprint 3's peer_percentiles and Sprint 4's valuation)
    - DQ-03 FK enforcement: orphan company_id rows are rejected, not inserted
    - AC-03: PRAGMA foreign_key_check returns 0 rows after load
    - load_audit.csv reflects rows_in / rows_out / fk_rejected / final_db_count
    - Re-running build_database() is idempotent (fresh rebuild each time)

These tests build a tiny synthetic `tables` dict directly (bypassing
loader.load_all() and real Excel files) so they run fast and don't
depend on data/ being populated.

Run with:
    pytest tests/etl/test_db_loader.py -v
"""

import csv
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "etl"))

import db_loader as db_loader_module
from db_loader import build_schema, insert_table, build_database, TABLE_MAP, LOAD_ORDER


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def tmp_project(tmp_path, monkeypatch):
    """
    Point db_loader's PROJECT_ROOT-derived paths at a scratch directory,
    write a copy of the real db/schema.sql there, and monkeypatch
    db_loader.load_all to return a small synthetic 12-table dataset
    (2 valid companies + 1 orphan company_id per child table).
    """
    db_dir = tmp_path / "db"
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "output"
    db_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)

    real_schema = Path(__file__).resolve().parents[2] / "db" / "schema.sql"
    (db_dir / "schema.sql").write_text(real_schema.read_text())

    monkeypatch.setattr(db_loader_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(db_loader_module, "DB_PATH", data_dir / "nifty100_test.db")
    monkeypatch.setattr(db_loader_module, "SCHEMA_PATH", db_dir / "schema.sql")
    monkeypatch.setattr(db_loader_module, "OUTPUT_DIR", output_dir)

    companies = pd.DataFrame({
        "id": ["TCS", "INFY"],
        "company_logo": ["", ""],
        "company_name": ["Tata Consultancy Services", "Infosys"],
        "chart_link": ["", ""],
        "about_company": ["", ""],
        "website": ["", ""],
        "nse_profile": ["", ""],
        "bse_profile": ["", ""],
        "face_value": [1.0, 5.0],
        "book_value": [100.0, 200.0],
        "roce_percentage": [30.0, 28.0],
        "roe_percentage": [45.0, 30.0],
    })
    # one orphan row (BADCO) mixed in with valid rows, per child table
    profitandloss = pd.DataFrame({
        "company_id": ["TCS", "INFY", "BADCO"],
        "year": ["2023-03", "2023-03", "2023-03"],
        "sales": [100, 200, 50], "expenses": [50, 90, 20],
        "operating_profit": [50, 110, 30], "opm_percentage": [50.0, 55.0, 60.0],
        "other_income": [1, 1, 1], "interest": [1, 1, 1], "depreciation": [1, 1, 1],
        "profit_before_tax": [49, 109, 29], "tax_percentage": [25.0, 25.0, 25.0],
        "net_profit": [37, 82, 22], "eps": [10.0, 20.0, 5.0], "dividend_payout": [30.0, 30.0, 30.0],
    })

    def fake_load_all():
        tables = {name: pd.DataFrame() for name in LOAD_ORDER}
        tables["companies"] = companies
        tables["profitandloss"] = profitandloss
        return tables

    monkeypatch.setattr(db_loader_module, "load_all", fake_load_all)

    return tmp_path


# ===========================================================================
# Schema creation
# ===========================================================================

class TestSchemaCreation:

    def test_build_schema_creates_all_14_tables(self, tmp_project):
        # 12 tables from Sprint 1 (one per source file) + peer_percentiles
        # (Sprint 3, Day 18) + valuation (Sprint 4, Day 26).
        conn = sqlite3.connect(":memory:")
        conn.execute("PRAGMA foreign_keys = ON;")
        build_schema(conn)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'").fetchall()}
        for table_cfg in TABLE_MAP.values():
            assert table_cfg["sqlite_table"] in tables
        assert "peer_percentiles" in tables
        assert "valuation" in tables
        assert len(tables) == 14

    def test_companies_table_has_primary_key_on_id(self, tmp_project):
        conn = sqlite3.connect(":memory:")
        build_schema(conn)
        cols = conn.execute("PRAGMA table_info(companies)").fetchall()
        pk_cols = [c[1] for c in cols if c[5] > 0]  # col[5] = pk index, >0 means part of PK
        assert pk_cols == ["id"]


# ===========================================================================
# DQ-03 FK enforcement at insert time
# ===========================================================================

class TestFKEnforcement:

    def test_orphan_rows_rejected_not_inserted(self, tmp_project):
        conn = sqlite3.connect(":memory:")
        conn.execute("PRAGMA foreign_keys = ON;")
        build_schema(conn)
        conn.execute("INSERT INTO companies (id, company_name) VALUES ('TCS', 'Tata Consultancy Services')")

        df = pd.DataFrame({
            "company_id": ["TCS", "BADCO"],
            "year": ["2023-03", "2023-03"],
            "sales": [100, 999],
        })
        stats = insert_table(conn, "profitandloss", df, valid_company_ids={"TCS"})

        assert stats["rows_in"] == 2
        assert stats["rows_out"] == 1
        assert stats["fk_rejected"] == 1
        assert "BADCO" in stats["fk_rejected_sample"]

        row_count = conn.execute("SELECT COUNT(*) FROM profitandloss").fetchone()[0]
        assert row_count == 1

    def test_valid_rows_all_inserted_when_no_orphans(self, tmp_project):
        conn = sqlite3.connect(":memory:")
        conn.execute("PRAGMA foreign_keys = ON;")
        build_schema(conn)
        conn.execute("INSERT INTO companies (id, company_name) VALUES ('TCS', 'Tata Consultancy Services')")

        df = pd.DataFrame({"company_id": ["TCS", "TCS"], "year": ["2022-03", "2023-03"], "sales": [90, 100]})
        stats = insert_table(conn, "profitandloss", df, valid_company_ids={"TCS"})

        assert stats["fk_rejected"] == 0
        assert stats["rows_out"] == 2

    def test_empty_dataframe_returns_zeroed_stats(self, tmp_project):
        conn = sqlite3.connect(":memory:")
        build_schema(conn)
        stats = insert_table(conn, "profitandloss", pd.DataFrame(), valid_company_ids={"TCS"})
        assert stats == {"table": "profitandloss", "rows_in": 0, "rows_out": 0, "fk_rejected": 0}

    def test_companies_table_itself_is_never_fk_filtered(self, tmp_project):
        conn = sqlite3.connect(":memory:")
        build_schema(conn)
        df = pd.DataFrame({"id": ["TCS", "INFY"], "company_name": ["TCS Ltd", "Infosys"]})
        # valid_company_ids intentionally empty/irrelevant -- companies is the FK parent
        stats = insert_table(conn, "companies", df, valid_company_ids=set())
        assert stats["rows_out"] == 2
        assert stats["fk_rejected"] == 0


# ===========================================================================
# Full build_database() pipeline
# ===========================================================================

class TestBuildDatabase:

    def test_build_database_end_to_end(self, tmp_project):
        result = build_database()

        assert result["fk_check_violations"] == 0
        assert result["row_counts"]["companies"] == 2
        # 1 of 3 profitandloss rows (BADCO) must be FK-rejected
        assert result["row_counts"]["profitandloss"] == 2

    def test_pragma_foreign_key_check_clean_after_build(self, tmp_project):
        result = build_database()
        conn = sqlite3.connect(result["db_path"])
        violations = conn.execute("PRAGMA foreign_key_check;").fetchall()
        conn.close()
        assert violations == []

    def test_rebuild_is_idempotent(self, tmp_project):
        result1 = build_database()
        result2 = build_database()
        assert result1["row_counts"] == result2["row_counts"]

    def test_load_audit_csv_written_with_expected_columns(self, tmp_project):
        result = build_database()
        audit_path = Path(result["db_path"]).parent.parent / "output" / "load_audit.csv"
        assert audit_path.exists()
        with open(audit_path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert reader.fieldnames == ["table", "rows_in", "rows_out", "fk_rejected", "final_db_count"]
        assert len(rows) == len(LOAD_ORDER)

    def test_load_audit_reflects_fk_rejection_for_profitandloss(self, tmp_project):
        result = build_database()
        pl_stats = next(s for s in result["insert_stats"] if s["table"] == "profitandloss")
        assert pl_stats["rows_in"] == 3
        assert pl_stats["rows_out"] == 2
        assert pl_stats["fk_rejected"] == 1
