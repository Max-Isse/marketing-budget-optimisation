"""Command-line entry point: `mbo <step>` (or `python -m marketing_budget.cli <step>`)."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable

from marketing_budget.config import Config, load_config

log = logging.getLogger("mbo")


def cmd_design(cfg: Config) -> None:
    from marketing_budget.constraints import line_bounds
    from marketing_budget.reporting.design import write_design_report
    from marketing_budget.synthetic.truth import (
        business_summary,
        load_ground_truth,
        planned_annual_spend,
        world_summary,
    )

    truth = load_ground_truth()
    lines = world_summary(truth, cfg)
    bounds = line_bounds(cfg, planned_annual_spend(truth))
    for p in bounds.problems:
        log.warning("budget policy conflict: %s", p)
    log.info("wrote %s", write_design_report(lines, business_summary(truth, lines, cfg), bounds, cfg))


def cmd_generate(cfg: Config) -> None:
    from marketing_budget.synthetic.generate import generate, write_generated
    from marketing_budget.synthetic.truth import load_ground_truth

    write_generated(generate(load_ground_truth(), cfg), cfg)


def cmd_build(cfg: Config) -> None:
    from marketing_budget.data.build import build_database

    build_database(cfg).close()
    log.info("database built: %s", cfg.path("duckdb"))


def cmd_quality(cfg: Config) -> None:
    from marketing_budget.data.db import connect
    from marketing_budget.data.quality import build_quality_report
    from marketing_budget.reporting.phase1 import write_quality_report
    from marketing_budget.synthetic.truth import load_ground_truth
    from marketing_budget.validation.phase1 import score_quality

    con = connect(cfg, read_only=True)
    try:
        q = build_quality_report(con, cfg)
        score, false_flags = score_quality(q.issues, load_ground_truth())
        log.info("wrote %s", write_quality_report(q, con, cfg, score, false_flags))
    finally:
        con.close()


def cmd_retention(cfg: Config) -> None:
    from marketing_budget.analysis.retention import estimate_retention
    from marketing_budget.data.db import connect
    from marketing_budget.reporting.phase1 import write_customer_value_report
    from marketing_budget.validation.phase1 import load_truth_tables, score_retention

    con = connect(cfg, read_only=True)
    try:
        res = estimate_retention(con, cfg)
    finally:
        con.close()
    t = load_truth_tables(cfg)
    score = score_retention(res.estimates, t["synthetic_truth_line_params"], t["synthetic_truth_customer_source"], cfg)
    log.info("wrote %s", write_customer_value_report(res, cfg, score))


STEPS = ["design", "generate", "build", "quality", "retention"]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="mbo", description=__doc__)
    parser.add_argument("step", choices=[*STEPS, "all"])
    parser.add_argument("--config", default=None, help="path to config.yaml")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    cfg = load_config(args.config)
    steps: dict[str, Callable[[], None]] = {
        "design": lambda: cmd_design(cfg),
        "generate": lambda: cmd_generate(cfg),
        "build": lambda: cmd_build(cfg),
        "quality": lambda: cmd_quality(cfg),
        "retention": lambda: cmd_retention(cfg),
    }
    for name in STEPS if args.step == "all" else [args.step]:
        steps[name]()


if __name__ == "__main__":
    main()
