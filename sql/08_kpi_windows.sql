-- Rolling 4-week totals per business and per business-channel line: the validated inputs for the AI-assisted
-- commentary (phase 7). One row per scope and week, holding the sums of the four weeks ending that week. Ratios
-- (CAC, qualification rate, platform / CRM) are computed from these sums, never averaged. Data-quality flags are
-- counted separately by type, so a note is attached only to the metrics that flag can affect.
CREATE OR REPLACE TABLE kpi_windows AS
WITH flags AS (
    SELECT business, week_start,
           max(cost_restated::INTEGER) AS restated,
           max(tracking_outage::INTEGER) AS outage,
           max(attribution_changed::INTEGER) AS attribution
    FROM line_week GROUP BY ALL
),
b AS (
    SELECT 'business' AS scope_type, p.business, NULL::VARCHAR AS channel, p.week_start,
           p.spend, p.leads, p.qualified_leads, p.customers, p.revenue, p.contribution_profit,
           NULL::DOUBLE AS platform_conversions, f.restated, f.outage, f.attribution
    FROM business_week_pnl p JOIN flags f USING (business, week_start)
),
l AS (
    SELECT 'line' AS scope_type, business, channel, week_start,
           spend, crm_leads AS leads, crm_qualified_leads AS qualified_leads, crm_customers AS customers,
           NULL::DOUBLE AS revenue, NULL::DOUBLE AS contribution_profit,
           platform_conversions::DOUBLE AS platform_conversions,
           cost_restated::INTEGER AS restated, tracking_outage::INTEGER AS outage,
           attribution_changed::INTEGER AS attribution
    FROM line_week
),
u AS (SELECT * FROM b UNION ALL SELECT * FROM l)
SELECT
    scope_type,
    business,
    channel,
    week_start,
    row_number() OVER s AS week_index,
    count(*) OVER w AS weeks_in_window,
    round(sum(spend) OVER w, 2) AS spend,
    sum(leads) OVER w AS leads,
    sum(qualified_leads) OVER w AS qualified_leads,
    sum(customers) OVER w AS customers,
    round(sum(revenue) OVER w, 2) AS revenue,
    round(sum(contribution_profit) OVER w, 2) AS contribution_profit,
    sum(platform_conversions) OVER w AS platform_conversions,
    sum(restated) OVER w AS restated_weeks,
    sum(outage) OVER w AS outage_weeks,
    sum(attribution) OVER w AS attribution_weeks
FROM u
WINDOW
    s AS (PARTITION BY scope_type, business, channel ORDER BY week_start),
    w AS (PARTITION BY scope_type, business, channel ORDER BY week_start ROWS BETWEEN 3 PRECEDING AND CURRENT ROW)
ORDER BY scope_type, business, channel, week_start;
