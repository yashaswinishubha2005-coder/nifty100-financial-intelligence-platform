# Nifty 100 Financial Intelligence Platform

Financial Intelligence Platform for Nifty 100 companies with ETL, Data
Quality Validation, SQLite, Financial Screener, Peer Comparison Engine,
Valuation Module, and an interactive Streamlit Dashboard.

Built as a Bluestock Fintech Data Analyst internship capstone, delivered
over 4 Agile Scrum sprints (Sprint 1: Data Foundation, Sprint 2:
Financial Ratio Engine, Sprint 3: Screener & Peer Comparison Engine,
Sprint 4: Dashboard & Valuation Module).

## Project layout

```
config/                 Analyst-editable YAML configuration (screener thresholds, presets)
data/
  supporting/            Source Excel files (financial_ratios, market_cap, peer_groups, sectors)
  nifty100.db            SQLite database (built by src/etl/db_loader.py)
db/schema.sql             SQLite schema (13 tables)
src/
  etl/                    Loader, normaliser, DQ validator, DB loader
  analytics/               CAGR engine, cash-flow KPIs, ratio engine, peer percentile engine, valuation module
  screener/                 Financial screener engine (6 presets, composite score)
  dashboard/
    app.py                  Streamlit entry point
    utils/                   Cached SQLite data loader (db.py) + shared UI helpers (ui.py)
    pages/                   8 dashboard screens
output/                  Generated reports (Excel/CSV) from each pipeline stage
reports/radar_charts/     Per-company peer radar charts (PNG)
tests/                   pytest suite (etl, analytics, screener, dashboard)
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Rebuilding the data pipeline (optional — a pre-built `data/nifty100.db` is included)

Run in order:

```bash
python src/etl/db_loader.py          # Sprint 1: ETL + SQLite schema + FK-enforced load
python src/analytics/ratios.py       # Sprint 2: profitability/leverage/CAGR/cash-flow ratio engine
python src/screener/engine.py        # Sprint 3: screener presets + composite score + screener_output.xlsx
python src/analytics/peer.py         # Sprint 3: peer percentiles + radar charts + peer_comparison.xlsx
python src/analytics/valuation.py    # Sprint 4: FCF yield + valuation flags + valuation_summary.xlsx
pytest tests/ -q                     # full regression suite
```

## Running the dashboard

```bash
streamlit run src/dashboard/app.py
```

This opens the app at `http://localhost:8501`. The sidebar lists all 8
screens (Streamlit auto-discovers everything under
`src/dashboard/pages/`, which is why that directory sits next to
`app.py` rather than at the repository root — see the docstring at the
top of `app.py` for why).

### Dashboard screens

**1. Home** — Six headline KPI tiles (Average ROE, Median P/E, Median
D/E, Total Companies, Median Revenue CAGR 5yr, Debt-Free Companies), a
sector-breakdown donut chart, a Top-5-by-composite-score table, and a
fiscal-year selector (2019–2024) that all of the above respond to.

**2. Company Profile** — Search any of the 92 companies by name or
ticker. Shows a company card (sector, sub-sector, ticker, description,
website/NSE links), 6 KPI tiles (ROE, ROCE, Net Profit Margin, D/E,
Revenue CAGR 5yr, FCF), a 10-year Revenue vs. Net Profit bar chart, a
10-year ROE/ROCE dual-axis line chart, and pros/cons badges (where
available — most companies in this dataset have none, and the screen
says so rather than showing empty boxes).

**3. Screener** — 10 metric sliders (ROE min, D/E max, FCF min, Revenue
CAGR min, PAT CAGR min, OPM min, P/E max, P/B max, Dividend Yield min,
ICR min) with 6 one-click presets (Quality, Value, Growth, Dividend,
Debt-Free, Turnaround) that auto-fill them. Results update live, with a
company count, a sortable table, and a CSV download button. Reuses the
Sprint 3 screener engine's composite score so the numbers match
`output/screener_output.xlsx`.

**4. Peer Comparison** — Pick one of the 11 Sprint 3 peer groups, then a
company within it. Shows an 8-axis radar chart (company vs. peer-group
average) and a side-by-side KPI table with the benchmark company's row
highlighted gold.

**5. Trend Analysis** — Search a company, overlay up to 3 metrics
(ROE, ROCE, margins, D/E, FCF, Revenue, Net Profit, EPS) on one 10-year
line chart, with year-over-year % change annotated at every point.

**6. Sector Analysis** — Pick a broad sector; shows a bubble chart
(Revenue × ROE, bubble size = market cap, colour = sub-sector) and a
bar chart of that sector's median KPIs.

**7. Capital Allocation Map** — A treemap of all 92 companies grouped
by their Sprint 2 capital-allocation pattern (Cash Accumulator,
Reinvestor, Distress Signal, etc. — 8 CFO/CFI/CFF sign-based patterns).
Click a pattern in the treemap to filter the company list below it.

**8. Annual Reports** — Search a company to see its available annual
report years with BSE PDF links. An optional "check link availability"
toggle does a live HEAD request per link and shows a red "Report
unavailable" badge for anything that doesn't resolve.

### Notes on data edge cases (Sprint 4, Day 27 findings)

- A handful of companies carry a trailing interim data row (e.g.
  `2024-09`) with most ratio columns null. Every screen that needs
  "the latest year" selects the latest row with a *non-null* core
  metric instead of the literal maximum year, so KPI tiles don't go
  blank for the most recent period.
- `financial_ratios` does not persist a per-year ROCE column (Sprint 2
  only computed it transiently for a one-off cross-check). The
  dashboard recomputes a full ROCE time series on the fly using the
  same formula from `src/analytics/ratios.py`.
- 36 of the 92 companies have no Sprint 3 peer-group assignment, and
  88 of 92 have no pros/cons data — every relevant screen handles the
  empty case explicitly rather than crashing or rendering blank
  widgets.
- All numeric displays go through a None/NaN-safe formatter
  (`utils/ui.py:fmt`) that renders `N/A` instead of raising.

## Testing

```bash
pytest tests/ -q                       # full suite
pytest tests/dashboard/ -v             # Streamlit screen smoke tests (headless, via AppTest)
```

The dashboard test suite uses `streamlit.testing.v1.AppTest` to run
every screen's actual Python for all 92 tickers, all 11 peer groups,
all sectors, both slider extremes, and all 6 screener presets —
without needing a browser or a running server.
