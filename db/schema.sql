-- ============================================================================
-- schema.sql — Nifty 100 Financial Intelligence Platform
-- Sprint 1, Day 04 deliverable (Module 1, feature 1.4)
--
-- 12 tables, one per source file (7 core + 5 supplementary). `companies`
-- is the FK parent for every other table via company_id -> companies.id
-- (DQ-01/DQ-03). Composite UNIQUE constraints enforce DQ-02 (one row per
-- company per fiscal period) wherever the source data supports it.
--
-- Applied with `PRAGMA foreign_keys = ON;` by db_loader.py before this
-- script runs, and `PRAGMA foreign_key_check` is run after load (AC-03).
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ----------------------------------------------------------------------------
-- companies — FK parent for all other tables. PK = ticker (DQ-01).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS companies (
    id                  TEXT    PRIMARY KEY,
    company_logo        TEXT,
    company_name        TEXT    NOT NULL,
    chart_link          TEXT,
    about_company       TEXT,
    website             TEXT,
    nse_profile         TEXT,
    bse_profile         TEXT,
    face_value          REAL,
    book_value          REAL,
    roce_percentage     REAL,
    roe_percentage      REAL
);

-- ----------------------------------------------------------------------------
-- profitandloss — annual P&L per company. year is normalised 'YYYY-MM'.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS profitandloss (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id          TEXT    NOT NULL REFERENCES companies(id),
    year                TEXT    NOT NULL,
    sales               REAL,
    expenses            REAL,
    operating_profit    REAL,
    opm_percentage      REAL,
    other_income        REAL,
    interest            REAL,
    depreciation        REAL,
    profit_before_tax   REAL,
    tax_percentage      REAL,
    net_profit          REAL,
    eps                 REAL,
    dividend_payout     REAL,
    UNIQUE (company_id, year)
);
CREATE INDEX IF NOT EXISTS idx_pl_company ON profitandloss(company_id);
CREATE INDEX IF NOT EXISTS idx_pl_year ON profitandloss(year);

-- ----------------------------------------------------------------------------
-- balancesheet — annual balance sheet per company.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS balancesheet (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id          TEXT    NOT NULL REFERENCES companies(id),
    year                TEXT    NOT NULL,
    equity_capital      REAL,
    reserves            REAL,
    borrowings          REAL,
    other_liabilities   REAL,
    total_liabilities   REAL,
    fixed_assets        REAL,
    cwip                REAL,
    investments         REAL,
    other_asset         REAL,
    total_assets        REAL,
    UNIQUE (company_id, year)
);
CREATE INDEX IF NOT EXISTS idx_bs_company ON balancesheet(company_id);
CREATE INDEX IF NOT EXISTS idx_bs_year ON balancesheet(year);

-- ----------------------------------------------------------------------------
-- cashflow — annual cash flow statement per company.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cashflow (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id          TEXT    NOT NULL REFERENCES companies(id),
    year                TEXT    NOT NULL,
    operating_activity  REAL,
    investing_activity  REAL,
    financing_activity  REAL,
    net_cash_flow       REAL,
    UNIQUE (company_id, year)
);
CREATE INDEX IF NOT EXISTS idx_cf_company ON cashflow(company_id);
CREATE INDEX IF NOT EXISTS idx_cf_year ON cashflow(year);

-- ----------------------------------------------------------------------------
-- analysis — growth/CAGR metrics. Multiple rows per company (one per
-- reporting period: TTM / 3Y / 5Y / 10Y) captured as free-text labels
-- in the source, so no per-company UNIQUE constraint.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analysis (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id                  TEXT    NOT NULL REFERENCES companies(id),
    compounded_sales_growth     TEXT,
    compounded_profit_growth    TEXT,
    stock_price_cagr            TEXT,
    roe                         TEXT
);
CREATE INDEX IF NOT EXISTS idx_analysis_company ON analysis(company_id);

-- ----------------------------------------------------------------------------
-- documents — annual report links. report_year is the calendar year of
-- the filing (not a fiscal 'YYYY-MM' label), one row per company/year.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documents (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id          TEXT    NOT NULL REFERENCES companies(id),
    report_year         INTEGER,
    annual_report_url   TEXT,
    UNIQUE (company_id, report_year)
);
CREATE INDEX IF NOT EXISTS idx_documents_company ON documents(company_id);

-- ----------------------------------------------------------------------------
-- prosandcons — pros/cons bullet points. Multiple rows per company (each
-- row is a single bullet, not an aggregate), so no per-company UNIQUE.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS prosandcons (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id          TEXT    NOT NULL REFERENCES companies(id),
    pros                TEXT,
    cons                TEXT
);
CREATE INDEX IF NOT EXISTS idx_prosandcons_company ON prosandcons(company_id);

-- ----------------------------------------------------------------------------
-- sectors — one row per company (sector/sub-sector classification).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sectors (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id              TEXT    NOT NULL REFERENCES companies(id),
    broad_sector            TEXT,
    sub_sector              TEXT,
    index_weight_pct        REAL,
    market_cap_category     TEXT,
    UNIQUE (company_id)
);
CREATE INDEX IF NOT EXISTS idx_sectors_company ON sectors(company_id);

-- ----------------------------------------------------------------------------
-- stock_prices — monthly OHLCV per company.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stock_prices (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id          TEXT    NOT NULL REFERENCES companies(id),
    date                TEXT    NOT NULL,
    open_price          REAL,
    high_price          REAL,
    low_price           REAL,
    close_price         REAL,
    volume              INTEGER,
    adjusted_close      REAL,
    UNIQUE (company_id, date)
);
CREATE INDEX IF NOT EXISTS idx_stock_prices_company ON stock_prices(company_id);
CREATE INDEX IF NOT EXISTS idx_stock_prices_date ON stock_prices(date);

-- ----------------------------------------------------------------------------
-- market_cap — annual market cap / valuation multiples. year is a plain
-- calendar year (int), not a fiscal label.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS market_cap (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id                  TEXT    NOT NULL REFERENCES companies(id),
    year                         INTEGER NOT NULL,
    market_cap_crore            REAL,
    enterprise_value_crore      REAL,
    pe_ratio                    REAL,
    pb_ratio                    REAL,
    ev_ebitda                   REAL,
    dividend_yield_pct          REAL,
    UNIQUE (company_id, year)
);
CREATE INDEX IF NOT EXISTS idx_market_cap_company ON market_cap(company_id);

-- ----------------------------------------------------------------------------
-- financial_ratios — annual ratio pack. year normalised to 'YYYY-MM'
-- (Day 06 fix: previously left unnormalised, causing duplicate rows).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS financial_ratios (
    id                              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id                      TEXT    NOT NULL REFERENCES companies(id),
    year                             TEXT    NOT NULL,
    net_profit_margin_pct           REAL,
    operating_profit_margin_pct     REAL,
    return_on_equity_pct            REAL,
    debt_to_equity                  REAL,
    interest_coverage               REAL,
    asset_turnover                  REAL,
    free_cash_flow_cr               REAL,
    capex_cr                        REAL,
    earnings_per_share              REAL,
    book_value_per_share            REAL,
    dividend_payout_ratio_pct       REAL,
    total_debt_cr                   REAL,
    cash_from_operations_cr         REAL,
    -- Sprint 2 (Day 12) additions: CAGR engine outputs + composite score
    revenue_cagr_5yr                REAL,
    revenue_cagr_5yr_flag           TEXT,
    pat_cagr_5yr                    REAL,
    pat_cagr_5yr_flag               TEXT,
    eps_cagr_5yr                    REAL,
    eps_cagr_5yr_flag               TEXT,
    composite_quality_score         REAL,
    -- Sprint 2 (Day 09) additions: flags/labels the spec asks to persist
    icr_label                        TEXT,
    high_leverage_flag              INTEGER,
    icr_risk_flag                   INTEGER,
    UNIQUE (company_id, year)
);
CREATE INDEX IF NOT EXISTS idx_financial_ratios_company ON financial_ratios(company_id);
CREATE INDEX IF NOT EXISTS idx_financial_ratios_year ON financial_ratios(year);

-- ----------------------------------------------------------------------------
-- peer_groups — company membership in named peer groups, with an
-- is_benchmark flag marking the group's reference constituent.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS peer_groups (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    peer_group_name     TEXT    NOT NULL,
    company_id          TEXT    NOT NULL REFERENCES companies(id),
    is_benchmark         INTEGER NOT NULL DEFAULT 0 CHECK (is_benchmark IN (0, 1)),
    UNIQUE (peer_group_name, company_id)
);
CREATE INDEX IF NOT EXISTS idx_peer_groups_company ON peer_groups(company_id);

-- ----------------------------------------------------------------------------
-- peer_percentiles — Sprint 3, Day 18 deliverable (Epic 04, Module 2).
-- One row per (company, peer_group, metric, year): the company's raw
-- metric value plus its percentile rank (0-100) within that peer group
-- for that year. D/E is stored already inverted (see src/analytics/peer.py)
-- so that percentile_rank is always "higher = better" for every metric.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS peer_percentiles (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id          TEXT    NOT NULL REFERENCES companies(id),
    peer_group_name     TEXT    NOT NULL,
    metric               TEXT    NOT NULL,
    value                REAL,
    percentile_rank      REAL,
    year                 TEXT    NOT NULL,
    UNIQUE (company_id, peer_group_name, metric, year)
);
CREATE INDEX IF NOT EXISTS idx_peer_percentiles_company ON peer_percentiles(company_id);
CREATE INDEX IF NOT EXISTS idx_peer_percentiles_group ON peer_percentiles(peer_group_name);

-- ----------------------------------------------------------------------------
-- valuation — Sprint 4, Day 26 deliverable (Epic 06, Module 1). One row
-- per company (latest year): valuation multiples, FCF yield, the
-- sector's median P/E for that year, and the resulting Caution /
-- Discount / Fair flag. Mirrors output/valuation_summary.xlsx.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS valuation (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id                  TEXT    NOT NULL REFERENCES companies(id),
    year                         INTEGER NOT NULL,
    pe_ratio                    REAL,
    pb_ratio                    REAL,
    ev_ebitda                   REAL,
    fcf_yield_pct                REAL,
    sector_median_pe             REAL,
    pe_vs_sector_median_pct      REAL,
    flag                         TEXT,
    UNIQUE (company_id, year)
);
CREATE INDEX IF NOT EXISTS idx_valuation_company ON valuation(company_id);
