-- Customer lifetimes and cohort tables. A month is observable only if it started before the end of the data,
-- so recent customers are right-censored: still active, with their future unknown.
CREATE OR REPLACE TABLE customer_lifetimes AS
WITH meta AS (SELECT data_end_date::DATE AS end_date FROM synthetic_data_meta),
act AS (
    SELECT customer_id,
           count(*) AS active_months,
           max(month_index) AS last_active_month,
           sum(orders) AS orders,
           sum(revenue) AS revenue,
           sum(contribution) AS contribution
    FROM synthetic_customer_activity GROUP BY customer_id
)
SELECT
    c.customer_id,
    c.business,
    c.source,
    c.acquisition_date::DATE AS acquisition_date,
    date_trunc('month', c.acquisition_date)::DATE AS acquisition_month,
    c.acquisition_cost,
    floor((meta.end_date - c.acquisition_date::DATE - 1) / getvariable('days_per_month'))::INTEGER + 1
        AS observable_months,
    a.active_months,
    a.last_active_month,
    a.orders,
    a.revenue,
    a.contribution
FROM synthetic_customers c
CROSS JOIN meta
JOIN act a USING (customer_id);

-- Orders per month since acquisition, with the number of customers observable in that month (e-commerce).
CREATE OR REPLACE TABLE repeat_orders_by_month AS
WITH months AS (
    SELECT l.business, l.source, m.month_index, count(*) AS customers_observable
    FROM customer_lifetimes l, range(0, 40) m(month_index)
    WHERE m.month_index < l.observable_months
    GROUP BY ALL
),
orders AS (
    SELECT l.business, l.source, a.month_index, sum(a.orders) AS orders, sum(a.revenue) AS revenue,
           sum(a.contribution) AS contribution
    FROM synthetic_customer_activity a JOIN customer_lifetimes l USING (customer_id)
    GROUP BY ALL
)
SELECT m.*, coalesce(o.orders, 0) AS orders, coalesce(o.revenue, 0) AS revenue,
       coalesce(o.contribution, 0) AS contribution
FROM months m LEFT JOIN orders o USING (business, source, month_index);
