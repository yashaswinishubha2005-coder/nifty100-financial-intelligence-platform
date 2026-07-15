-- ----------------------------------------------------------------------------
-- Q1. Top 10 companies by latest-year market capitalisation
-- ----------------------------------------------------------------------------
SELECT c.id, c.company_name, m.market_cap_crore
FROM market_cap m
JOIN companies c ON c.id = m.company_id
WHERE m.year = (SELECT MAX(year) FROM market_cap)
ORDER BY m.market_cap_crore DESC
LIMIT 10;


-- ----------------------------------------------------------------------------
-- Q2. Average ROE by broad sector, ranked highest to lowest
-- ----------------------------------------------------------------------------
SELECT s.broad_sector, ROUND(AVG(c.roe_percentage), 2) AS avg_roe, COUNT(*) AS n_companies
FROM companies c
JOIN sectors s ON s.company_id = c.id
GROUP BY s.broad_sector
ORDER BY avg_roe DESC;


-- ----------------------------------------------------------------------------
-- Q3. Top 10 most leveraged companies (debt-to-equity), most recent
-- fiscal year available per company (fiscal year-ends vary by company,
-- so MAX(year) must be computed per company, not globally).
-- ----------------------------------------------------------------------------
SELECT fr.company_id, fr.year, fr.debt_to_equity
FROM financial_ratios fr
JOIN (
    SELECT company_id, MAX(year) AS latest_year
    FROM financial_ratios
    GROUP BY company_id
) latest ON latest.company_id = fr.company_id AND latest.latest_year = fr.year
WHERE fr.debt_to_equity IS NOT NULL
ORDER BY fr.debt_to_equity DESC
LIMIT 10;


-- ----------------------------------------------------------------------------
-- Q4. Top 10 companies by sales growth from first to latest reported
-- year, restricted to companies with >= 5 years of P&L history (DQ-16
-- coverage threshold).
-- ----------------------------------------------------------------------------
WITH bounds AS (
    SELECT company_id, MIN(year) AS first_year, MAX(year) AS last_year, COUNT(*) AS n_years
    FROM profitandloss
    GROUP BY company_id
    HAVING n_years >= 5
)
SELECT b.company_id,
       first.sales AS first_year_sales,
       last.sales AS latest_year_sales,
       ROUND((last.sales - first.sales) * 100.0 / NULLIF(first.sales, 0), 1) AS pct_growth
FROM bounds b
JOIN profitandloss first ON first.company_id = b.company_id AND first.year = b.first_year
JOIN profitandloss last ON last.company_id = b.company_id AND last.year = b.last_year
WHERE first.sales > 0
ORDER BY pct_growth DESC
LIMIT 10;


-- ----------------------------------------------------------------------------
-- Q5. Balance sheet integrity summary (same tolerance check as DQ-04).
-- Note: in this dataset total_assets == total_liabilities exactly on every
-- row (0 imbalances), which is why this is a summary rather than a top-10 --
-- there is nothing to rank.
-- ----------------------------------------------------------------------------
SELECT
    COUNT(*) AS rows_checked,
    SUM(CASE WHEN ABS(total_assets - total_liabilities) * 1.0 / NULLIF(total_assets, 0) >= 0.01
              THEN 1 ELSE 0 END) AS rows_imbalanced_1pct,
    ROUND(MAX(ABS(total_assets - total_liabilities) * 100.0 / NULLIF(total_assets, 0)), 4) AS max_diff_pct
FROM balancesheet
WHERE total_assets IS NOT NULL AND total_liabilities IS NOT NULL AND total_assets != 0;


-- ----------------------------------------------------------------------------
-- Q6. Top 10 highest single-year dividend payout ratios reported
-- ----------------------------------------------------------------------------
SELECT company_id, year, dividend_payout
FROM profitandloss
WHERE dividend_payout IS NOT NULL
ORDER BY dividend_payout DESC
LIMIT 10;


-- ----------------------------------------------------------------------------
-- Q7. Peer group comparison: Private Banks peer group vs its benchmark
-- constituent, ranked by ROE.
-- ----------------------------------------------------------------------------
SELECT pg.peer_group_name, c.id, c.company_name, c.roe_percentage, pg.is_benchmark
FROM peer_groups pg
JOIN companies c ON c.id = pg.company_id
WHERE pg.peer_group_name = 'Private Banks'
ORDER BY c.roe_percentage DESC;


-- ----------------------------------------------------------------------------
-- Q8. Top 10 companies by 12-month stock price momentum (latest monthly
-- close vs. the close 12 months earlier).
-- ----------------------------------------------------------------------------
WITH ranked AS (
    SELECT company_id, date, close_price,
           ROW_NUMBER() OVER (PARTITION BY company_id ORDER BY date DESC) AS rn
    FROM stock_prices
)
SELECT a.company_id,
       a.close_price AS latest_close,
       b.close_price AS close_12mo_ago,
       ROUND((a.close_price - b.close_price) * 100.0 / b.close_price, 1) AS pct_change
FROM ranked a
JOIN ranked b ON a.company_id = b.company_id AND b.rn = 13
WHERE a.rn = 1
ORDER BY pct_change DESC
LIMIT 10;


-- ----------------------------------------------------------------------------
-- Q9. Top 10 companies by average operating cash flow (CFO), companies
-- with at least 5 years of cashflow history only.
-- ----------------------------------------------------------------------------
SELECT company_id, ROUND(AVG(operating_activity), 1) AS avg_cfo, COUNT(*) AS n_years
FROM cashflow
WHERE operating_activity IS NOT NULL
GROUP BY company_id
HAVING n_years >= 5
ORDER BY avg_cfo DESC
LIMIT 10;


-- ----------------------------------------------------------------------------
-- Q10. Data-foundation health check: row count per table (matches
-- output/load_audit.csv final_db_count column) -- the Day 07 sprint-demo
-- summary query.
-- ----------------------------------------------------------------------------
SELECT 'companies' AS tbl, COUNT(*) AS row_count FROM companies
UNION ALL SELECT 'profitandloss', COUNT(*) FROM profitandloss
UNION ALL SELECT 'balancesheet', COUNT(*) FROM balancesheet
UNION ALL SELECT 'cashflow', COUNT(*) FROM cashflow
UNION ALL SELECT 'analysis', COUNT(*) FROM analysis
UNION ALL SELECT 'documents', COUNT(*) FROM documents
UNION ALL SELECT 'prosandcons', COUNT(*) FROM prosandcons
UNION ALL SELECT 'sectors', COUNT(*) FROM sectors
UNION ALL SELECT 'stock_prices', COUNT(*) FROM stock_prices
UNION ALL SELECT 'market_cap', COUNT(*) FROM market_cap
UNION ALL SELECT 'financial_ratios', COUNT(*) FROM financial_ratios
UNION ALL SELECT 'peer_groups', COUNT(*) FROM peer_groups;
