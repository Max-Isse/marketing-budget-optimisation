-- Weekly P&L per business: revenue and contribution from every active customer (inherited and new), minus the
-- one-off acquisition costs of new customers and the advertising spend. Each customer-month is booked in the
-- week its month starts (acquisition date + month_index x 30.44 days).
CREATE OR REPLACE TABLE business_week_pnl AS
WITH meta AS (SELECT first_week::DATE AS first_week, data_end_date::DATE AS end_date FROM synthetic_data_meta),
booked AS (
    SELECT
        c.business,
        date_trunc(
            'week',
            c.acquisition_date::DATE + to_days(CAST(floor(a.month_index * getvariable('days_per_month')) AS INTEGER))
        )::DATE AS week_start,
        a.revenue,
        a.contribution,
        a.customer_id
    FROM synthetic_customer_activity a
    JOIN synthetic_customers c USING (customer_id)
),
weekly AS (
    SELECT business, week_start, round(sum(revenue), 2) AS revenue, round(sum(contribution), 2) AS contribution,
           count(DISTINCT customer_id) AS billed_customers
    FROM booked, meta
    WHERE week_start >= meta.first_week AND week_start < meta.end_date
    GROUP BY ALL
),
acq AS (
    SELECT business, date_trunc('week', acquisition_date)::DATE AS week_start,
           round(sum(acquisition_cost), 2) AS acquisition_costs
    FROM synthetic_customers, meta
    WHERE acquisition_date::DATE >= meta.first_week
    GROUP BY ALL
)
SELECT
    b.week_start,
    b.business,
    b.spend,
    b.clicks,
    b.leads,
    b.qualified_leads,
    b.customers,
    coalesce(w.revenue, 0) AS revenue,
    coalesce(w.contribution, 0) AS contribution,
    coalesce(w.billed_customers, 0) AS billed_customers,
    coalesce(q.acquisition_costs, 0) AS acquisition_costs,
    round(coalesce(w.contribution, 0) - coalesce(q.acquisition_costs, 0) - b.spend, 2) AS contribution_profit,
    b.blended_cac,
    b.any_dq_flag
FROM business_week b
LEFT JOIN weekly w USING (business, week_start)
LEFT JOIN acq q USING (business, week_start);
