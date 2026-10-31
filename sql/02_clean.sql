-- Clean layer: cost restatements flagged, B2 duplicate leads removed, CRM counts rebuilt on clean leads.

-- Media: spend is the final (restated) figure; flag weeks where it moved after first report.
CREATE OR REPLACE TABLE media_clean AS
SELECT
    week_start::DATE AS week_start,
    business,
    channel,
    spend,
    spend_first_reported,
    abs(spend / nullif(spend_first_reported, 0) - 1) > getvariable('restatement_tolerance') AS cost_restated,
    impressions,
    clicks,
    platform_conversions
FROM synthetic_weekly_media;

-- B2 leads: a form from the same e-mail domain within the window of an earlier one is a duplicate.
CREATE OR REPLACE TABLE b2_leads_clean AS
SELECT
    *,
    created_date::DATE - lag(created_date::DATE) OVER (PARTITION BY email_domain ORDER BY created_date, lead_id)
        <= getvariable('duplicate_window_days') IS TRUE AS is_duplicate,
    date_trunc('week', created_date)::DATE AS week_start
FROM synthetic_b2_leads;

-- CRM weekly counts by last-click source. B2 lead counts are replaced by de-duplicated counts.
CREATE OR REPLACE TABLE crm_clean AS
WITH b2 AS (
    SELECT week_start, business, source,
           count(*) AS leads_recorded,
           count(*) FILTER (WHERE NOT is_duplicate) AS leads_unique,
           count(*) FILTER (WHERE is_duplicate) AS duplicate_leads
    FROM b2_leads_clean
    GROUP BY ALL
)
SELECT
    c.week_start::DATE AS week_start,
    c.business,
    c.source,
    coalesce(b2.leads_recorded, c.leads) AS leads_recorded,
    coalesce(b2.leads_unique, c.leads) AS leads,
    coalesce(b2.duplicate_leads, 0) AS duplicate_leads,
    c.qualified_leads,
    c.customers
FROM synthetic_weekly_crm c
LEFT JOIN b2
    ON b2.week_start = c.week_start::DATE AND b2.business = c.business AND b2.source = c.source;
