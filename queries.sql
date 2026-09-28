/* =====================================================================
   BCA Data Analytics Test Project - SQL Queries
   Database : data/sales.db  (SQLite, created by analysis.ipynb)
   Tables   : orders_raw  - original Orders sheet (1,200 rows, uncleaned)
              orders      - cleaned orders (1,198 rows)
              customers   - customer master (80 rows)
              products    - product master (25 rows)
   Run      : sqlite3 data/sales.db < queries.sql
              (or open sales.db in DB Browser for SQLite / DBeaver)
   ===================================================================== */


/* ---------------------------------------------------------------------
   SECTION A : DATA QUALITY CHECKS (on raw data)
   --------------------------------------------------------------------- */

-- A1. Row counts of raw vs cleaned data
SELECT 'orders_raw' AS table_name, COUNT(*) AS row_count FROM orders_raw
UNION ALL
SELECT 'orders', COUNT(*) FROM orders;

-- A2. Orders whose customer_id / product_id do not exist in the master tables
SELECT o.order_id, o.customer_id, o.product_id,
       CASE WHEN c.customer_id IS NULL THEN 'Missing customer' END AS customer_issue,
       CASE WHEN p.product_id  IS NULL THEN 'Missing product'  END AS product_issue
FROM orders_raw o
LEFT JOIN customers c ON o.customer_id = c.customer_id
LEFT JOIN products  p ON o.product_id  = p.product_id
WHERE c.customer_id IS NULL OR p.product_id IS NULL;

-- A3. Invalid values: missing sales, non-positive quantity, discount above 20%
SELECT order_id, quantity, discount_pct, net_sales,
       CASE
           WHEN net_sales IS NULL THEN 'Missing sales values'
           WHEN quantity <= 0     THEN 'Invalid quantity'
           WHEN discount_pct > 20 THEN 'Discount outlier'
       END AS issue
FROM orders_raw
WHERE net_sales IS NULL OR quantity <= 0 OR discount_pct > 20;

-- A4. Inconsistent payment_status spelling (case-sensitive distinct values)
SELECT payment_status, COUNT(*) AS orders
FROM orders_raw
GROUP BY payment_status
ORDER BY orders DESC;

-- A5. Duplicate order IDs (expected: no rows)
SELECT order_id, COUNT(*) AS cnt
FROM orders_raw
GROUP BY order_id
HAVING COUNT(*) > 1;


/* ---------------------------------------------------------------------
   SECTION B : BUSINESS KPIs (on cleaned data)
   --------------------------------------------------------------------- */

-- B1. Headline KPIs
SELECT COUNT(*)                                   AS total_orders,
       SUM(quantity)                              AS units_sold,
       ROUND(SUM(gross_sales), 2)                 AS gross_sales,
       ROUND(SUM(discount_amount), 2)             AS total_discount,
       ROUND(SUM(net_sales), 2)                   AS net_sales,
       ROUND(SUM(profit), 2)                      AS profit,
       ROUND(100.0 * SUM(profit) / SUM(net_sales), 2) AS profit_margin_pct,
       ROUND(AVG(net_sales), 2)                   AS avg_order_value
FROM orders;

-- B2. Monthly sales trend with month-over-month growth (window function LAG)
WITH monthly AS (
    SELECT strftime('%Y-%m', order_date) AS year_month,
           COUNT(*)                      AS orders,
           SUM(net_sales)                AS net_sales,
           SUM(profit)                   AS profit
    FROM orders
    GROUP BY year_month
)
SELECT year_month, orders,
       ROUND(net_sales, 2) AS net_sales,
       ROUND(profit, 2)    AS profit,
       ROUND(100.0 * (net_sales - LAG(net_sales) OVER (ORDER BY year_month))
             / LAG(net_sales) OVER (ORDER BY year_month), 2) AS mom_growth_pct
FROM monthly
ORDER BY year_month;

-- B3. Quarterly performance
SELECT 'Q' || ((CAST(strftime('%m', order_date) AS INTEGER) + 2) / 3) AS quarter,
       COUNT(*) AS orders,
       ROUND(SUM(net_sales), 2) AS net_sales,
       ROUND(SUM(profit), 2)    AS profit,
       ROUND(100.0 * SUM(profit) / SUM(net_sales), 2) AS margin_pct
FROM orders
GROUP BY quarter
ORDER BY quarter;


/* ---------------------------------------------------------------------
   SECTION C : PRODUCT & CATEGORY ANALYSIS
   --------------------------------------------------------------------- */

-- C1. Category performance with share of total sales
SELECT p.category,
       COUNT(*)                   AS orders,
       SUM(o.quantity)            AS units,
       ROUND(SUM(o.net_sales), 2) AS net_sales,
       ROUND(SUM(o.profit), 2)    AS profit,
       ROUND(100.0 * SUM(o.profit) / SUM(o.net_sales), 2) AS margin_pct,
       ROUND(100.0 * SUM(o.net_sales) / (SELECT SUM(net_sales) FROM orders), 2) AS sales_share_pct
FROM orders o
JOIN products p ON o.product_id = p.product_id
GROUP BY p.category
ORDER BY net_sales DESC;

-- C2. Top 5 products by net sales
SELECT p.product_id, p.product_name, p.category,
       SUM(o.quantity)            AS units,
       ROUND(SUM(o.net_sales), 2) AS net_sales,
       ROUND(SUM(o.profit), 2)    AS profit
FROM orders o
JOIN products p ON o.product_id = p.product_id
GROUP BY p.product_id, p.product_name, p.category
ORDER BY net_sales DESC
LIMIT 5;

-- C3. Bottom 5 products by profit margin
SELECT p.product_id, p.product_name, p.category,
       ROUND(SUM(o.net_sales), 2) AS net_sales,
       ROUND(100.0 * SUM(o.profit) / SUM(o.net_sales), 2) AS margin_pct
FROM orders o
JOIN products p ON o.product_id = p.product_id
GROUP BY p.product_id, p.product_name, p.category
ORDER BY margin_pct ASC
LIMIT 5;

-- C4. Best-selling product within each category (window function RANK)
SELECT category, product_name, net_sales
FROM (
    SELECT p.category, p.product_name,
           ROUND(SUM(o.net_sales), 2) AS net_sales,
           RANK() OVER (PARTITION BY p.category ORDER BY SUM(o.net_sales) DESC) AS rnk
    FROM orders o
    JOIN products p ON o.product_id = p.product_id
    GROUP BY p.category, p.product_name
)
WHERE rnk = 1
ORDER BY net_sales DESC;


/* ---------------------------------------------------------------------
   SECTION D : CUSTOMER & REGION ANALYSIS
   --------------------------------------------------------------------- */

-- D1. City-wise sales (orders with unknown customer shown as 'Unknown')
SELECT COALESCE(c.city, 'Unknown') AS city,
       COUNT(DISTINCT o.customer_id) AS customers,
       COUNT(*)                      AS orders,
       ROUND(SUM(o.net_sales), 2)    AS net_sales,
       ROUND(SUM(o.profit), 2)       AS profit
FROM orders o
LEFT JOIN customers c ON o.customer_id = c.customer_id
GROUP BY COALESCE(c.city, 'Unknown')
ORDER BY net_sales DESC;

-- D2. Customer type: sales and average order value
SELECT COALESCE(c.customer_type, 'Unknown') AS customer_type,
       COUNT(DISTINCT o.customer_id) AS customers,
       COUNT(*)                      AS orders,
       ROUND(SUM(o.net_sales), 2)    AS net_sales,
       ROUND(AVG(o.net_sales), 2)    AS avg_order_value,
       ROUND(100.0 * SUM(o.profit) / SUM(o.net_sales), 2) AS margin_pct
FROM orders o
LEFT JOIN customers c ON o.customer_id = c.customer_id
GROUP BY COALESCE(c.customer_type, 'Unknown')
ORDER BY net_sales DESC;

-- D3. Top 10 customers by net sales
SELECT c.customer_id, c.customer_name, c.city, c.customer_type,
       COUNT(*)                   AS orders,
       ROUND(SUM(o.net_sales), 2) AS net_sales,
       ROUND(SUM(o.profit), 2)    AS profit
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name, c.city, c.customer_type
ORDER BY net_sales DESC
LIMIT 10;


/* ---------------------------------------------------------------------
   SECTION E : SALESPERSON, PAYMENTS & DISCOUNTS
   --------------------------------------------------------------------- */

-- E1. Salesperson ranking
SELECT salesperson,
       COUNT(*)                   AS orders,
       ROUND(SUM(net_sales), 2)   AS net_sales,
       ROUND(SUM(profit), 2)      AS profit,
       ROUND(100.0 * SUM(profit) / SUM(net_sales), 2) AS margin_pct,
       ROUND(AVG(discount_pct), 2) AS avg_discount_pct,
       SUM(CASE WHEN payment_status = 'Overdue' THEN 1 ELSE 0 END) AS overdue_orders,
       RANK() OVER (ORDER BY SUM(net_sales) DESC) AS sales_rank
FROM orders
GROUP BY salesperson
ORDER BY sales_rank;

-- E2. Payment status summary (receivables)
SELECT payment_status,
       COUNT(*) AS orders,
       ROUND(SUM(net_sales), 2) AS net_sales,
       ROUND(100.0 * SUM(net_sales) / (SELECT SUM(net_sales) FROM orders), 2) AS share_pct
FROM orders
GROUP BY payment_status
ORDER BY net_sales DESC;

-- E3. Top 10 customers by overdue amount (collection priority list)
SELECT o.customer_id,
       COALESCE(c.customer_name, 'Unknown') AS customer_name,
       COALESCE(c.city, 'Unknown')          AS city,
       COUNT(*)                   AS overdue_orders,
       ROUND(SUM(o.net_sales), 2) AS overdue_amount
FROM orders o
LEFT JOIN customers c ON o.customer_id = c.customer_id
WHERE o.payment_status = 'Overdue'
GROUP BY o.customer_id, c.customer_name, c.city
ORDER BY overdue_amount DESC
LIMIT 10;

-- E4. Discount band vs profit margin
SELECT CASE
           WHEN discount_pct = 0   THEN '1) 0%'
           WHEN discount_pct <= 5  THEN '2) 1-5%'
           WHEN discount_pct <= 10 THEN '3) 6-10%'
           ELSE '4) >10%'
       END AS discount_band,
       COUNT(*) AS orders,
       ROUND(SUM(net_sales), 2) AS net_sales,
       ROUND(100.0 * SUM(profit) / SUM(net_sales), 2) AS margin_pct,
       SUM(CASE WHEN profit < 0 THEN 1 ELSE 0 END) AS loss_orders
FROM orders
GROUP BY discount_band
ORDER BY discount_band;

-- E5. Loss-making orders
SELECT o.order_id, o.order_date, p.product_name, p.category, o.salesperson,
       o.discount_pct, ROUND(o.net_sales, 2) AS net_sales, ROUND(o.profit, 2) AS profit
FROM orders o
JOIN products p ON o.product_id = p.product_id
WHERE o.profit < 0
ORDER BY o.profit ASC;
