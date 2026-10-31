-- Validated line-week metrics (docs/metric_definitions.md). Requires dq_attribution_shift, which the Python
-- data-quality step writes after 03. Ratios are NULL when the denominator is 0.
CREATE OR REPLACE TABLE line_week AS
SELECT
    b.*,
    coalesce(b.week_start >= s.shift_week_start AND s.detected, FALSE) AS attribution_changed,
    b.tracking_outage OR b.cost_restated OR b.crm_duplicate_leads > 0
        OR coalesce(b.week_start >= s.shift_week_start AND s.detected, FALSE) AS any_dq_flag,
    b.spend / nullif(b.clicks, 0) AS cpc,
    b.clicks / nullif(b.impressions, 0) AS ctr,
    b.spend / nullif(b.crm_leads, 0) AS cost_per_lead,
    b.spend / nullif(b.crm_qualified_leads, 0) AS cost_per_qualified_lead,
    b.crm_qualified_leads / nullif(b.crm_leads, 0) AS lead_to_qualified_rate,
    b.spend / nullif(b.crm_customers, 0) AS last_click_cac,
    b.spend / nullif(b.platform_conversions, 0) AS platform_cac
FROM line_week_base b
LEFT JOIN dq_attribution_shift s ON s.business = b.business AND s.channel = b.channel;

-- Business-week totals across all sources, paid and organic.
CREATE OR REPLACE TABLE business_week AS
WITH crm AS (
    SELECT week_start, business,
           sum(leads) AS leads,
           sum(qualified_leads) AS qualified_leads,
           sum(customers) AS customers,
           sum(customers) FILTER (WHERE source = 'organic') AS organic_source_customers
    FROM crm_clean GROUP BY ALL
),
media AS (
    SELECT week_start, business,
           round(sum(spend), 2) AS spend, sum(impressions) AS impressions, sum(clicks) AS clicks,
           sum(platform_conversions) AS platform_conversions,
           bool_or(any_dq_flag) AS any_dq_flag
    FROM line_week GROUP BY ALL
)
SELECT
    m.week_start, m.business, m.spend, m.impressions, m.clicks, m.platform_conversions,
    c.leads, c.qualified_leads, c.customers, c.organic_source_customers,
    c.customers - c.organic_source_customers AS paid_source_customers,
    m.spend / nullif(c.customers, 0) AS blended_cac,
    m.any_dq_flag
FROM media m JOIN crm c USING (week_start, business);
