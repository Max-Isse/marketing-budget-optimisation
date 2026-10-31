-- Raw layer: the generated (SYNTHETIC) observable tables, unchanged. The truth/ folder is never read here.
CREATE OR REPLACE TABLE synthetic_weekly_media AS
SELECT * FROM read_parquet(getvariable('raw_dir') || '/synthetic_weekly_media.parquet');

CREATE OR REPLACE TABLE synthetic_weekly_crm AS
SELECT * FROM read_parquet(getvariable('raw_dir') || '/synthetic_weekly_crm.parquet');

CREATE OR REPLACE TABLE synthetic_b2_leads AS
SELECT * FROM read_parquet(getvariable('raw_dir') || '/synthetic_b2_leads.parquet');

CREATE OR REPLACE TABLE synthetic_customers AS
SELECT * FROM read_parquet(getvariable('raw_dir') || '/synthetic_customers.parquet');

CREATE OR REPLACE TABLE synthetic_customer_activity AS
SELECT * FROM read_parquet(getvariable('raw_dir') || '/synthetic_customer_activity.parquet');

CREATE OR REPLACE TABLE synthetic_data_meta AS
SELECT * FROM read_parquet(getvariable('raw_dir') || '/synthetic_data_meta.parquet');
