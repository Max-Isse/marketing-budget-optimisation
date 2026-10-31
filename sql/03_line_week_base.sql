-- One row per business-channel line and week: platform report joined to the CRM's last-click counts.
-- tracking_outage: the platform reports no conversions while the CRM credits the line with several customers.
CREATE OR REPLACE TABLE line_week_base AS
SELECT
    m.week_start,
    m.business,
    m.channel,
    m.spend,
    m.cost_restated,
    m.impressions,
    m.clicks,
    m.platform_conversions,
    c.leads_recorded AS crm_leads_recorded,
    c.leads AS crm_leads,
    c.duplicate_leads AS crm_duplicate_leads,
    c.qualified_leads AS crm_qualified_leads,
    c.customers AS crm_customers,
    m.platform_conversions = 0 AND c.customers >= getvariable('outage_min_crm_customers') AND m.clicks > 0
        AS tracking_outage
FROM media_clean m
JOIN crm_clean c
    ON c.week_start = m.week_start AND c.business = m.business AND c.source = m.channel;
