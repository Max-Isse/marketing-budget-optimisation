"""Build the DuckDB metric layer from the generated Parquet files: raw -> clean -> line-week -> cohorts.

The attribution-change detector runs between the SQL steps, because the validated line-week table needs its
result to flag the affected weeks.
"""

from __future__ import annotations

import duckdb

from marketing_budget.config import Config
from marketing_budget.data.db import connect, run_sql_file, set_variables
from marketing_budget.data.quality import detect_attribution_shifts
from marketing_budget.economics import DAYS_PER_MONTH


def build_database(cfg: Config, con: duckdb.DuckDBPyConnection | None = None) -> duckdb.DuckDBPyConnection:
    con = con or connect(cfg)
    dq = cfg.section("data_quality")
    set_variables(
        con,
        {
            "raw_dir": cfg.path("raw_dir").as_posix(),
            "restatement_tolerance": float(dq["restatement_tolerance"]),
            "duplicate_window_days": int(dq["duplicate_window_days"]),
            "outage_min_crm_customers": int(dq["outage_min_crm_customers"]),
            "days_per_month": DAYS_PER_MONTH,
        },
    )
    for name in ("01_load_raw.sql", "02_clean.sql", "03_line_week_base.sql"):
        run_sql_file(con, name)

    shifts = detect_attribution_shifts(con, cfg)
    con.register("shifts_df", shifts)
    con.execute("CREATE OR REPLACE TABLE dq_attribution_shift AS SELECT * FROM shifts_df")
    con.unregister("shifts_df")

    for name in ("04_line_week.sql", "05_cohorts.sql", "06_pnl.sql"):
        run_sql_file(con, name)
    return con
