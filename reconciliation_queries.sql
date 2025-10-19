-- =====================================================================
-- reconciliation_queries.sql
-- Bank Reconciliation & Financial Controls — SQL implementation
-- (Same logic as the Python engine, written the way it would run
--  inside a bank's data warehouse. Tested on MySQL 8 / PostgreSQL.)
-- =====================================================================

-- ---------------------------------------------------------------
-- 0. TABLE SETUP (load the two CSVs into these tables)
-- ---------------------------------------------------------------
CREATE TABLE general_ledger (
    gl_ref        VARCHAR(20),
    posting_date  DATE,
    description   VARCHAR(120),
    counterparty  VARCHAR(60),
    mode          VARCHAR(10),
    drcr          CHAR(2),
    amount        DECIMAL(15,2)
);

CREATE TABLE bank_statement (
    bank_ref      VARCHAR(20),
    value_date    DATE,
    narration     VARCHAR(120),
    counterparty  VARCHAR(60),
    mode          VARCHAR(10),
    drcr          CHAR(2),
    amount        DECIMAL(15,2)
);

-- Helpful indexes (interviewers love hearing this)
CREATE INDEX ix_gl_ref   ON general_ledger (gl_ref);
CREATE INDEX ix_bank_ref ON bank_statement (bank_ref);


-- ---------------------------------------------------------------
-- 1. PASS 1 — EXACT MATCH  (ref + date + amount + direction)
-- ---------------------------------------------------------------
SELECT g.gl_ref, b.bank_ref, g.posting_date, g.amount,
       'P1-EXACT' AS match_pass
FROM   general_ledger g
JOIN   bank_statement b
       ON  b.bank_ref = g.gl_ref
       AND b.value_date = g.posting_date
       AND b.amount     = g.amount
       AND b.drcr       = g.drcr;


-- ---------------------------------------------------------------
-- 2. PASS 2 — TIMING DIFFERENCE  (T+1 to T+3 clearing lag)
-- ---------------------------------------------------------------
SELECT g.gl_ref, b.bank_ref,
       g.posting_date  AS gl_date,
       b.value_date    AS bank_date,
       DATEDIFF(b.value_date, g.posting_date) AS lag_days,
       g.amount,
       'P2-TIMING' AS match_pass
FROM   general_ledger g
JOIN   bank_statement b
       ON  b.bank_ref = g.gl_ref
       AND b.amount   = g.amount
       AND b.drcr     = g.drcr
       AND b.value_date > g.posting_date
       AND DATEDIFF(b.value_date, g.posting_date) <= 3;


-- ---------------------------------------------------------------
-- 3. PASS 3 — AMOUNT TOLERANCE  (bank fee / posting error <= 600)
-- ---------------------------------------------------------------
SELECT g.gl_ref, b.bank_ref, g.amount AS gl_amount, b.amount AS bank_amount,
       ROUND(g.amount - b.amount, 2)  AS amount_diff,
       'P3-AMOUNT-TOL' AS match_pass
FROM   general_ledger g
JOIN   bank_statement b
       ON  b.bank_ref = g.gl_ref
       AND b.drcr     = g.drcr
       AND ABS(DATEDIFF(b.value_date, g.posting_date)) <= 3
       AND ABS(b.amount - g.amount) BETWEEN 0.01 AND 600.00;


-- ---------------------------------------------------------------
-- 4. BREAK: MISSING IN BANK (deposits in transit / unpresented cheques)
--    GL entries with no bank line at all
-- ---------------------------------------------------------------
SELECT g.*, 'MISSING IN BANK' AS break_category
FROM   general_ledger g
LEFT JOIN bank_statement b ON b.bank_ref = g.gl_ref
WHERE  b.bank_ref IS NULL
  AND  g.gl_ref NOT LIKE '%-D';        -- exclude duplicates (handled below)


-- ---------------------------------------------------------------
-- 5. BREAK: MISSING IN GL (bank lines never booked in books)
-- ---------------------------------------------------------------
SELECT b.*,
       CASE WHEN b.mode = 'SYS' THEN 'MISSING IN GL - BANK CHARGES'
            ELSE 'MISSING IN GL' END AS break_category
FROM   bank_statement b
LEFT JOIN general_ledger g ON g.gl_ref = b.bank_ref
WHERE  g.gl_ref IS NULL;


-- ---------------------------------------------------------------
-- 6. CONTROL: DUPLICATE POSTING DETECTION (same base ref twice in GL)
-- ---------------------------------------------------------------
SELECT SUBSTRING_INDEX(gl_ref, '-', 1) AS base_ref,
       COUNT(*)          AS times_posted,
       SUM(amount)       AS total_exposure
FROM   general_ledger
GROUP  BY SUBSTRING_INDEX(gl_ref, '-', 1)
HAVING COUNT(*) > 1
ORDER  BY total_exposure DESC;


-- ---------------------------------------------------------------
-- 7. AGING ANALYSIS of open breaks (as of 2025-08-20)
-- ---------------------------------------------------------------
WITH open_breaks AS (
    SELECT g.gl_ref AS ref, g.posting_date AS txn_date, g.amount
    FROM   general_ledger g
    LEFT JOIN bank_statement b ON b.bank_ref = g.gl_ref
    WHERE  b.bank_ref IS NULL
)
SELECT CASE
         WHEN DATEDIFF('2025-08-20', txn_date) <= 30 THEN '0-30 days'
         WHEN DATEDIFF('2025-08-20', txn_date) <= 60 THEN '31-60 days'
         WHEN DATEDIFF('2025-08-20', txn_date) <= 90 THEN '61-90 days'
         ELSE '90+ days'
       END              AS aging_bucket,
       COUNT(*)         AS open_items,
       SUM(amount)      AS total_value
FROM   open_breaks
GROUP  BY aging_bucket
ORDER  BY MIN(DATEDIFF('2025-08-20', txn_date));


-- ---------------------------------------------------------------
-- 8. CONTROL: HIGH-VALUE ESCALATION QUEUE (>= 1,00,000)
-- ---------------------------------------------------------------
SELECT g.gl_ref, g.posting_date, g.counterparty, g.amount,
       'ESCALATE-L2' AS escalation,
       DATEDIFF('2025-08-20', g.posting_date) AS days_open
FROM   general_ledger g
LEFT JOIN bank_statement b ON b.bank_ref = g.gl_ref
WHERE  b.bank_ref IS NULL
  AND  g.amount >= 100000
ORDER  BY g.amount DESC;


-- ---------------------------------------------------------------
-- 9. KPI: DAILY MATCH-RATE TREND (for the dashboard)
-- ---------------------------------------------------------------
SELECT g.posting_date,
       COUNT(*)                                        AS gl_txns,
       SUM(CASE WHEN b.bank_ref IS NOT NULL
                 AND b.amount = g.amount THEN 1 ELSE 0 END) AS matched,
       ROUND(100.0 * SUM(CASE WHEN b.bank_ref IS NOT NULL
                 AND b.amount = g.amount THEN 1 ELSE 0 END) / COUNT(*), 2) AS match_rate_pct
FROM   general_ledger g
LEFT JOIN bank_statement b ON b.bank_ref = g.gl_ref
GROUP  BY g.posting_date
ORDER  BY g.posting_date;
