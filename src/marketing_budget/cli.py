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


STEPS = ["design"]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="mbo", description=__doc__)
    parser.add_argument("step", choices=[*STEPS, "all"])
    parser.add_argument("--config", default=None, help="path to config.yaml")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    cfg = load_config(args.config)
    steps: dict[str, Callable[[], None]] = {
        "design": lambda: cmd_design(cfg),
    }
    for name in STEPS if args.step == "all" else [args.step]:
        steps[name]()


if __name__ == "__main__":
    main()
