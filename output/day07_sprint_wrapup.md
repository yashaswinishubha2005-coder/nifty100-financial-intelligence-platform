# Sprint 1 — Data Foundation: Wrap-Up &amp; Review (Day 07)

Epic 01 · Data Ingestion &amp; ETL · 34 SP · Day 01-07

## Exit criteria — status

| Criterion | Result |
|---|---|
| `SELECT COUNT(*) FROM companies` = 92 | ✅ 92 |
| `PRAGMA foreign_key_check` → 0 rows | ✅ 0 rows |
| `load_audit.csv` → CRITICAL rejections all attributable to DQ-03's own prescribed reject-and-log action | ✅ see below |
| 35+ ETL unit tests pass | ✅ 69 passed (`pytest tests/`) |
| Manual review: 5 companies correct | ✅ see `output/day06_manual_review.md` |
| Sprint review signed off | pending team sign-off |

## What shipped

- `db/schema.sql` — 12-table SQLite schema (PK/FK constraints, `UNIQUE`
  constraints enforcing DQ-02 where the source data supports it, indexes
  on `company_id`/`year`/`date`).
- `src/etl/db_loader.py` — builds `data/nifty100.db` from
  `loader.load_all()`'s 12 normalised tables, enforcing DQ-03 FK
  integrity by rejecting (not inserting) orphan `company_id` rows, and
  verifying `PRAGMA foreign_key_check` = 0 after load.
- Three real loader bugs found during Day 06 manual review and fixed
  (not just documented) — see `output/day06_manual_review.md` §2:
  1. `financial_ratios` year labels were never normalised/deduped (119
     duplicate rows fixed).
  2. `documents` had 1 undetected duplicate `(company_id, Year)` row.
  3. A ticker typo (`AGTL` → `ATGL`, Adani Total Gas Ltd) was silently
     causing DQ-03 rejections *and* a false DQ-16 coverage failure
     simultaneously; fixed via a ticker-alias correction map.
- `pytest.ini` `testpaths` typo fixed (`test` → `tests`) — bare `pytest`
  was silently falling back to a recursive search rather than using the
  configured path.
- `tests/etl/test_db_loader.py` — 11 new unit tests covering schema
  creation, DQ-03 FK enforcement at insert time, `PRAGMA
  foreign_key_check`, idempotent rebuilds, and `load_audit.csv` output.
  Total suite: **69 passed** (up from 58 at the start of this session).
- `notebooks/exploratory_queries.sql` — 10 queries (verified to run
  against the built DB) covering market cap rankings, sector ROE,
  leverage, sales growth, balance sheet integrity, dividend payouts,
  peer-group comparison, stock price momentum, cash flow, and a
  row-count health check.
- `Makefile` — added a `db` target (`make db` → `python
  src/etl/db_loader.py`), alongside the existing `load` target for the
  Day 02 loader.

## Final row counts (`data/nifty100.db`)

| Table | Rows |
|---|---|
| companies | 92 |
| profitandloss | 1,070 |
| balancesheet | 1,140 |
| cashflow | 1,063 |
| analysis | 16 |
| documents | 1,456 |
| prosandcons | 14 |
| sectors | 92 |
| stock_prices | 5,520 |
| market_cap | 552 |
| financial_ratios | 1,041 |
| peer_groups | 56 |

## Known, documented (not fixed) data gaps

These were investigated during Day 06 and confirmed to be genuine gaps
in the source spreadsheets, not loader bugs — see
`output/day06_manual_review.md` §3-4 for detail:

- `companies.xlsx` has 92 of the intended Nifty 100 constituents; 8
  tickers referenced elsewhere (`ULTRACEMCO`, `UNIONBANK`, `UNITDSPR`,
  `VBL`, `VEDL`, `WIPRO`, `ZOMATO`, `ZYDUSLIFE`) are legitimately absent
  from the master list and their child rows are correctly FK-rejected
  per DQ-03.
- `SBIN` has 0 years of balance sheet data (missing from
  `balancesheet.xlsx` entirely) — flagged for the data-source owner.
- `JIOFIN`'s short history (2-3 years) is expected given its 2023
  listing date, not a data quality issue.

## Retrospective notes

**Went well:** Day 02-03 (`loader.py`, `normaliser.py`, `validator.py`)
were already solid and well-tested going into this session — all 16 DQ
rules implemented, 58 tests passing, clear separation of concerns
between load-time normalisation and post-load validation.

**Found &amp; fixed:** the Day 06 manual-review step earned its place in the
plan — cross-referencing a DQ-03 orphan-row list against a DQ-16
coverage-gap list surfaced the `AGTL`/`ATGL` typo, which neither rule
would have caught in isolation.

**Carry forward to Sprint 2:** the `SBIN` balance-sheet gap and the
8 missing companies.xlsx tickers should go back to whoever supplies the
source spreadsheets; they're outside the ETL pipeline's ability to fix.
