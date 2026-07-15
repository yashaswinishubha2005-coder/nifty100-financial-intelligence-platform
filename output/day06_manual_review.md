# Day 06 — Data Quality Manual Review

Sprint 1, Day 06. Manual spot-check of the loaded database plus a
targeted hunt for loader bugs before the sprint's final rebuild.

## 1. Five-company random sample (seed=42)

| Ticker | Company | P&L | BS | CF | Fin. Ratios | Docs | Sector |
|---|---|---|---|---|---|---|---|
| SUNPHARMA | Sun Pharmaceuticals Industries Ltd | 12yr | 13yr | 12yr | 12yr | 16 | Healthcare / Pharmaceuticals |
| BAJFINANCE | Bajaj Finance Ltd | 10yr | 11yr | 10yr | 10yr | 16 | Financials / Consumer Finance |
| ADANIGREEN | Adani Green Energy Ltd | 8yr | 9yr | 8yr | 8yr | 16 | Energy / Renewable Energy |
| HAL | Hindustan Aeronautics Ltd | 12yr | 10yr | 8yr | 8yr | 16 | Industrials / Defence & Aerospace |
| EICHERMOT | Eicher Motors Ltd | 12yr | 13yr | 12yr | 12yr | 16 | Consumer Discretionary / Two Wheelers |

All 5 sampled companies clear the DQ-16 5-year coverage bar comfortably,
have a sector classification, and have annual-report links for all
available years. No issues found in this sample.

## 2. Loader bugs found and fixed

Three real bugs were found and fixed in `src/etl/loader.py` /
`src/etl/normaliser.py` (not just documented — the fixes are live and the
pipeline was re-run after each one):

1. **`financial_ratios` year field never normalised/deduplicated.**
   `loader.py`'s `SUPPORTING_FILES` config had `year_col=None` for
   `financial_ratios`, but its raw `year` values use the same fiscal-year
   label format as `profitandloss`/`balancesheet`/`cashflow` (e.g.
   `"Mar 2014"`). Because normalisation was skipped, the labels were never
   converted to `YYYY-MM` (breaking joins to the other time-series tables)
   and the row-level dedup step — which only runs when `year_col` is set —
   never ran, leaving **119 duplicate `(company_id, year)` rows**.
   Fix: set `year_col="year"` for `financial_ratios`. After the fix,
   duplicates dropped to 0 and years are `YYYY-MM`-formatted like the
   other fiscal tables.

2. **`documents` had 1 undetected duplicate row.** `(company_id, Year)` is
   documents' natural key, but since `Year` is a calendar int (not a
   fiscal label), it never went through the fiscal-year dedup path either.
   One row was found: `HAL`, `2011` appeared twice — once with a null
   `Annual_Report` URL and once with the real URL. Fix: added a generic
   `dedup_subset` / `prefer_notna` option to `load_excel_file()` so
   `documents` now dedupes on `(company_id, Year)`, preferring the row
   with a non-null URL when duplicates differ only in that field.

3. **`AGTL` → `ATGL` ticker typo in `cashflow.xlsx`.** DQ-16 coverage
   flagged `ATGL` (Adani Total Gas Ltd, a valid company in
   `companies.xlsx`) with **0 years of cashflow history**, while DQ-03 was
   separately rejecting 7 orphan rows under the ticker `AGTL`, which does
   not exist in `companies.xlsx`. The two findings pointed at the same
   root cause: a letter-transposition typo. Fix: added a
   `_TICKER_ALIASES` correction map to `normaliser.py`
   (`{"AGTL": "ATGL"}`), applied inside `normalize_ticker()`. After the
   fix, ATGL's cashflow coverage is restored and it drops off the DQ-16
   violation list; cashflow's FK-rejected count fell from 96 to 89 rows
   (the 7 corrected rows are no longer orphans).

All three fixes are covered by re-running the full test suite
(`pytest tests/` — 69 passed) and by re-running `db_loader.py` /
`validator.py` end to end after each change.

## 3. Genuine data gaps (not loader bugs — left as-is)

Two remaining DQ-16 coverage violations were investigated and confirmed
to be real gaps in the source spreadsheets, not normalisation bugs:

- **`SBIN` (State Bank of India) has 0 years of balance sheet data.**
  Confirmed: `SBIN` does not appear anywhere in `balancesheet.xlsx`
  (98 unique tickers are present, `SBIN` isn't one of them). This is a
  source-data completeness gap that the ETL pipeline cannot fabricate a
  fix for — flagged for follow-up with whoever supplies `balancesheet.xlsx`.
- **`JIOFIN` (Jio Financial Services) has only 2-3 years of history.**
  This is expected: Jio Financial Services was only listed in 2023, so
  a short track record is correct, not a data quality issue.

## 4. Company master-list gap (context, not a bug)

`companies.xlsx` contains 92 companies (matching the sprint's stated
`companies=92` target), not the full Nifty 100. Nine tickers referenced
in child tables — `ULTRACEMCO`, `UNIONBANK`, `UNITDSPR`, `VBL`, `VEDL`,
`WIPRO`, `ZOMATO`, `ZYDUSLIFE` (and originally `AGTL`, now understood to
be `ATGL`) — are real companies simply absent from the companies master
file. Per DQ-03's own prescribed remediation, rows referencing them are
rejected and logged (not inserted) at DB-build time; `PRAGMA
foreign_key_check` returns 0 rows on the built database. This is a
content gap in `companies.xlsx`, not something the loader should paper
over by inventing company records.

## 5. Re-run confirmation

After all fixes: `pytest tests/` → 69 passed · `python
src/etl/db_loader.py` → `companies`=92, `PRAGMA foreign_key_check`=0
rows · `output/validation_failures.csv` → CRITICAL violations now solely
attributable to the 8 genuinely-missing tickers above (down from 9 after
the AGTL/ATGL fix).
