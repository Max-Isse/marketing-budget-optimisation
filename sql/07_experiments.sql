-- Experiment data (SYNTHETIC), loaded unchanged. Written by `mbo experiments` after the designs are fixed.
CREATE OR REPLACE TABLE synthetic_exp_landing_page AS
SELECT * FROM read_parquet(getvariable('raw_dir') || '/synthetic_exp_landing_page.parquet');

CREATE OR REPLACE TABLE synthetic_exp_creative AS
SELECT * FROM read_parquet(getvariable('raw_dir') || '/synthetic_exp_creative.parquet');

CREATE OR REPLACE TABLE synthetic_exp_audience AS
SELECT * FROM read_parquet(getvariable('raw_dir') || '/synthetic_exp_audience.parquet');

CREATE OR REPLACE TABLE synthetic_exp_geo AS
SELECT * FROM read_parquet(getvariable('raw_dir') || '/synthetic_exp_geo.parquet');

-- Region x period totals for the region tests (what the ANCOVA reads).
CREATE OR REPLACE TABLE exp_geo_region_period AS
SELECT experiment, business, channel, region, period, any_value(treated) AS treated,
       sum(customers) AS customers, sum(line_spend) AS line_spend,
       sum(line_last_click_customers) AS line_last_click_customers,
       sum(line_platform_conversions) AS line_platform_conversions
FROM synthetic_exp_geo
GROUP BY ALL;
