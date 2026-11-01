"""Command-line entry point: `mbo <step>` (or `python -m marketing_budget.cli <step>`)."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable
from typing import TYPE_CHECKING

from marketing_budget.config import Config, load_config

if TYPE_CHECKING:
    import pandas as pd

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


def cmd_forecast(cfg: Config) -> None:
    import pandas as pd

    from marketing_budget.data.db import connect
    from marketing_budget.forecasting.backtest import (
        accuracy,
        backtest,
        empirical_intervals,
        load_series,
        select_models,
        total_errors,
    )
    from marketing_budget.forecasting.scenarios import forward
    from marketing_budget.forecasting.spend_effect import observational_elasticity
    from marketing_budget.reporting.forecasting import write_forecasting_report
    from marketing_budget.synthetic.truth import load_ground_truth
    from marketing_budget.validation.phase2 import true_elasticity

    con = connect(cfg, read_only=True)
    try:
        series = load_series(con)
    finally:
        con.close()
    log.info("rolling-origin backtest (about 2 minutes)")
    bt = backtest(series, cfg)
    art = cfg.path("artifacts_dir")
    art.mkdir(parents=True, exist_ok=True)
    bt.to_parquet(art / "forecast_backtest.parquet", index=False)
    acc = accuracy(bt, ["business", "target", "model"])
    acc_h = accuracy(bt, ["business", "target", "model", "horizon_bucket"])
    selected = select_models(acc, cfg)
    intervals = empirical_intervals(bt, cfg)
    totals = total_errors(bt)
    fwd = forward(series, selected, intervals, totals, cfg)
    elasticity = observational_elasticity(series, cfg)
    truth_weekly = pd.read_parquet(cfg.path("raw_dir") / "truth" / "synthetic_truth_weekly.parquet")
    te = true_elasticity(load_ground_truth(), truth_weekly, series)
    path = write_forecasting_report(
        series, bt, acc, acc_h, selected, intervals, totals, fwd, elasticity, cfg, true_elasticity=te
    )
    log.info("wrote %s", path)


def run_experiments(cfg: Config) -> dict[str, object]:
    """Design (from historical data), run in the simulation, load, analyse. Returns everything the report
    and validation need. Truth is used only by the synthetic.* calls."""
    import json
    from typing import Any

    import pandas as pd

    from marketing_budget.analysis.retention import ALL, estimate_retention
    from marketing_budget.data.db import connect, run_sql_file, set_variables
    from marketing_budget.experiments.design import (
        _z,
        assign_regions,
        choose_geo_design,
        design_user_tests,
        geo_mde,
        peeking_false_positive_rate,
    )
    from marketing_budget.experiments.results import analyse
    from marketing_budget.synthetic import experiments as sx
    from marketing_budget.synthetic.truth import load_ground_truth

    e = cfg.section("experiments")
    za, zb = _z(cfg)
    truth = load_ground_truth()
    tw = pd.read_parquet(cfg.path("raw_dir") / "truth" / "synthetic_truth_weekly.parquet")
    con = connect(cfg)
    try:
        plan = design_user_tests(con, cfg)
        values = {
            str(r["business"]): float(r["customer_value"])
            for r in estimate_retention(con, cfg).estimates.to_dict("records")
            if r["source"] == ALL
        }
        shares = sx.regions(truth, cfg.seed + 300)
        geo_frames, blocks, true_geo, geo_design = [], {}, {}, []
        geo_weeks: dict[str, int] = {}
        for i, (name, spec) in enumerate(e["geo_tests"].items()):
            seed = cfg.seed + 400 + i
            pre, _ = sx.simulate_geo(truth, tw, name, spec, shares, None, seed)
            claimed = float("nan")
            if spec["treatment"] == "spend":
                row = con.execute(
                    "SELECT sum(l.platform_conversions) / (SELECT sum(customers) FROM business_week b "
                    "WHERE b.business = ? "
                    "AND b.week_start > (SELECT max(week_start) FROM line_week) - INTERVAL 52 WEEK) "
                    "FROM line_week l WHERE l.business = ? AND l.channel = ? "
                    "AND l.week_start > (SELECT max(week_start) FROM line_week) - INTERVAL 52 WEEK",
                    [spec["business"], spec["business"], spec["channel"]],
                ).fetchone()
                claimed = float(row[0]) * abs(float(spec["spend_multiplier"]) - 1) if row else float("nan")
                target = claimed * float(e["geo"]["detect_share_of_platform_claim"])
            else:
                target = float(spec["target_effect"])
            candidates: list[dict[str, Any]] = []
            for share in e["geo"]["candidate_treated_shares"]:
                assignment = assign_regions(pre, float(share), seed + 50)
                for weeks in e["geo"]["candidate_test_weeks"]:
                    candidates.append(
                        {
                            "treated_share": float(share),
                            "test_weeks": int(weeks),
                            "mde": geo_mde(pre, assignment, int(weeks), za, zb),
                            "assignment": assignment,
                        }
                    )
            pick = choose_geo_design(candidates, target)
            assignment, weeks = pick["assignment"], int(pick["test_weeks"])
            geo_weeks[name] = weeks
            order = pre.groupby("region")["customers"].sum().sort_values().index
            k = round(1 / pick["treated_share"])
            blocks[name] = pd.Series({r: j // k for j, r in enumerate(order)})
            panel, true = sx.simulate_geo(truth, tw, name, spec, shares, assignment, seed, weeks)
            geo_frames.append(panel)
            true_geo[name] = true
            geo_design.append(
                {
                    "experiment": name,
                    "line": f"{spec['business']} {spec['channel']}",
                    "treatment": spec["treatment"]
                    if spec["treatment"] == "tcpa"
                    else f"spend x {float(spec['spend_multiplier']):g}",
                    "effect_if_platform_right": claimed,
                    "target_mde": target,
                    "treated_share": pick["treated_share"],
                    "regions_treated": int(assignment["treated"].sum()),
                    "weeks_pre": sx.PRE,
                    "weeks_test": weeks,
                    "mde_share_of_customers": pick["mde"],
                    "powered": pick["powered"],
                    "best_possible_mde": min(c["mde"] for c in candidates),
                }
            )
        lp = sx.simulate_landing_page(truth, int(plan["landing_page"]["weeks"]), cfg.seed + 501)
        cr = sx.simulate_creative(
            truth, int(plan["ad_creative"]["weeks"]), float(plan["ad_creative"]["weekly_users"]), cfg.seed + 502
        )
        au = sx.simulate_audience(truth, plan["audience_targeting"], cfg.seed + 503)
        raw = cfg.path("raw_dir")
        lp.to_parquet(raw / "synthetic_exp_landing_page.parquet", index=False)
        cr.to_parquet(raw / "synthetic_exp_creative.parquet", index=False)
        au.to_parquet(raw / "synthetic_exp_audience.parquet", index=False)
        pd.concat(geo_frames, ignore_index=True).to_parquet(raw / "synthetic_exp_geo.parquet", index=False)
        true_tab = pd.DataFrame(
            [
                {"experiment": k, "metric": "relative_effect", "true_value": v}
                for k, v in sx.true_user_effects(truth).items()
            ]
            + [{"experiment": k, "metric": m, "true_value": val} for k, d in true_geo.items() for m, val in d.items()]
        )
        true_tab.to_parquet(raw / "truth" / "synthetic_truth_experiments.parquet", index=False)
        set_variables(con, {"raw_dir": raw.as_posix()})
        run_sql_file(con, "07_experiments.sql")
        results = analyse(con, plan, blocks, geo_weeks, values, cfg)
    finally:
        con.close()
    art = cfg.path("artifacts_dir")
    art.mkdir(parents=True, exist_ok=True)
    (art / "experiment_plan.json").write_text(json.dumps(plan, indent=2, default=float), encoding="utf-8")
    # Calibration targets for phase 4: what each budget test measured, as a share of the business's customers
    # in the treated regions, with its standard error (from the t interval, df = regions - 3).
    from scipy import stats

    eff = results.effects.set_index("experiment")
    geo_all = pd.concat(geo_frames, ignore_index=True)
    calibration = []
    for name, spec in e["geo_tests"].items():
        if spec["treatment"] != "spend":
            continue
        g = geo_all[(geo_all["experiment"] == name) & (geo_all["period"] == "test")]
        t = float(stats.t.ppf(0.975, df=g["region"].nunique() - 3))
        r = eff.loc[name]
        calibration.append(
            {
                "experiment": name,
                "business": spec["business"],
                "channel": spec["channel"],
                "spend_multiplier": float(spec["spend_multiplier"]),
                "test_start": str(pd.Timestamp(g["week_start"].min()).date()),
                "test_weeks": int(geo_weeks[name]),
                "relative_effect": float(r["relative_effect"]),
                "se": float((r["ci_high"] - r["ci_low"]) / (2 * t)),
            }
        )
    (art / "experiment_calibration.json").write_text(json.dumps(calibration, indent=2), encoding="utf-8")
    lp_plan = plan["landing_page"]
    peek = peeking_false_positive_rate(
        int(float(e["landing_page"]["weekly_visitors"]) / 7 / 2),
        float(lp_plan["baseline"]),
        int(lp_plan["weeks"]) * 7,
        float(e["alpha"]),
        2000,
        cfg.seed + 600,
    )
    return {
        "plan": plan,
        "geo_design": pd.DataFrame(geo_design),
        "results": results,
        "values": values,
        "peeking_simulation": peek,
        "truth_table": true_tab,
    }


def cmd_experiments(cfg: Config) -> None:
    import pandas as pd

    from marketing_budget.reporting.experiments import write_experiments_report
    from marketing_budget.synthetic import experiments as sx
    from marketing_budget.synthetic.truth import load_ground_truth
    from marketing_budget.validation.phase3 import geo_monte_carlo, score_experiments

    out = run_experiments(cfg)
    score = score_experiments(out["results"], out["truth_table"])  # type: ignore[arg-type]
    truth = load_ground_truth()
    tw = pd.read_parquet(cfg.path("raw_dir") / "truth" / "synthetic_truth_weekly.parquet")
    log.info("method check: re-running each region test 40 times")
    mc = geo_monte_carlo(
        truth,
        tw,
        cfg.section("experiments")["geo_tests"],
        out["geo_design"],  # type: ignore[arg-type]
        sx.regions(truth, cfg.seed + 300),
        40,
        cfg.seed + 9000,
    )
    log.info("wrote %s", write_experiments_report(out, score, cfg, mc))


def cmd_optimise(cfg: Config) -> None:
    from marketing_budget.data.db import connect
    from marketing_budget.optimisation.plan import build_plan, save_fits
    from marketing_budget.reporting.optimisation import write_optimisation_report
    from marketing_budget.synthetic.truth import load_ground_truth
    from marketing_budget.validation.phase4 import score_plan

    con = connect(cfg, read_only=True)
    try:
        log.info("fitting calibrated response curves and optimising (several minutes)")
        plan = build_plan(con, cfg)
    finally:
        con.close()
    save_fits(plan, cfg)
    score = score_plan(plan, load_ground_truth(), cfg, int(plan.extras["n_weeks"]))  # type: ignore[call-overload]
    log.info("wrote %s", write_optimisation_report(plan, cfg, score))


def cmd_sensitivity(cfg: Config) -> None:
    from marketing_budget.data.db import connect
    from marketing_budget.optimisation.plan import load_fits
    from marketing_budget.reporting.sensitivity import write_sensitivity_report
    from marketing_budget.sensitivity.scenarios import (
        SCENARIOS,
        budget_curve,
        build_context,
        no_regret,
        run_scenario,
        summarise,
    )
    from marketing_budget.synthetic.truth import load_ground_truth
    from marketing_budget.validation.phase5 import score_sensitivity

    sc = cfg.section("sensitivity")
    con = connect(cfg, read_only=True)
    try:
        ctx = build_context(con, cfg, load_fits(cfg))
    finally:
        con.close()
    results = []
    for s in SCENARIOS:
        log.info("scenario %s%s", s.name, " (refit)" if s.refit else "")
        results.append(run_scenario(ctx, s))
    summary, changes = summarise(ctx, results, float(sc["move_threshold"]))
    verdicts = no_regret(
        changes,
        dict(zip(summary["scenario"], summary["solved"], strict=True)),
        float(sc["move_threshold"]),
        ctx.tested,
    )
    curve, plans = budget_curve(ctx, [float(b) for b in sc["budgets"]], log.info)
    n_weeks = len(next(iter(ctx.data.values())).y)
    score = score_sensitivity(results, curve, plans, verdicts, load_ground_truth(), cfg, n_weeks)
    log.info("wrote %s", write_sensitivity_report(summary, verdicts, curve, cfg, score))


def cmd_dashboard(cfg: Config) -> None:
    import json

    from marketing_budget.dashboard.extracts import build_extracts, write_extracts
    from marketing_budget.dashboard.tieout import tieout
    from marketing_budget.data.db import connect

    cal = json.loads((cfg.path("artifacts_dir") / "experiment_calibration.json").read_text(encoding="utf-8"))
    tested = {f"{c['business']}.{c['channel']}" for c in cal}
    con = connect(cfg, read_only=True)
    try:
        extracts = build_extracts(con, cfg, tested)
    finally:
        con.close()
    out = write_extracts(extracts, cfg)
    tieout(extracts).to_csv(out.parent / "tieout.csv", index=False, float_format="%.6g")
    log.info("wrote %d extracts to %s", len(extracts), out)


def cmd_commentary(cfg: Config, use_llm: bool) -> None:
    from marketing_budget.data.db import connect
    from marketing_budget.reporting_ai.draft import make_draft
    from marketing_budget.reporting_ai.facts import evidence_facts, period_facts
    from marketing_budget.reporting_ai.report import write_draft, write_phase_report

    con = connect(cfg, read_only=True)
    try:
        facts, periods = period_facts(con, cfg)
    finally:
        con.close()
    facts += evidence_facts(cfg)
    res = make_draft(facts, periods, cfg, use_llm=use_llm or bool(cfg.section("ai_reporting")["use_llm"]))
    log.info("draft source: %s; findings on final draft: %d", res.source, len(res.findings))
    log.info("wrote %s", write_draft(res, facts, periods, cfg))
    log.info("wrote %s", write_phase_report(res, facts, periods, cfg))


def cmd_stakeholders(cfg: Config) -> None:
    from marketing_budget.data.db import connect
    from marketing_budget.reporting.stakeholders import compute_numbers, write_stakeholder_report

    con = connect(cfg, read_only=True)
    try:
        numbers = compute_numbers(con, cfg)
    finally:
        con.close()
    log.info("wrote %s", write_stakeholder_report(numbers, cfg))


def cmd_final(cfg: Config) -> None:
    from marketing_budget.data.db import connect
    from marketing_budget.reporting.final import truth_check, write_final

    con = connect(cfg, read_only=True)
    try:
        paths = write_final(con, cfg, truth_check(cfg))
    finally:
        con.close()
    for p in paths:
        log.info("wrote %s", p)


def cmd_manifest(cfg: Config) -> None:
    from marketing_budget.manifest import write_manifest

    log.info("wrote %s", write_manifest(cfg))


def _report_diff(diff: pd.DataFrame) -> None:
    if diff.empty:
        log.info("all outputs match the manifest")
        return
    for r in diff.itertuples():
        log.error("%s: %s", r.status, r.path)
    sys.exit(1)


def cmd_verify(cfg: Config) -> None:
    from marketing_budget.manifest import verify

    _report_diff(verify(cfg))


def cmd_reproduce(cfg: Config, steps: dict[str, Callable[[], None]]) -> None:
    from marketing_budget.manifest import compare, hash_outputs, read_manifest

    expected = read_manifest(cfg)
    for name in STEPS:
        steps[name]()
    _report_diff(compare(expected, hash_outputs(cfg)))


def cmd_review(cfg: Config, reviewer: str, decision: str, notes: str) -> None:
    from marketing_budget.reporting_ai.review import record_review

    rec = record_review(cfg, reviewer, decision, notes)
    log.info("recorded review: %s by %s (draft %s)", rec["decision"], rec["reviewer"], rec["draft_sha256"][:12])
    log.info("re-run `mbo commentary` to show the status on the draft")


STEPS = [
    "design",
    "generate",
    "build",
    "quality",
    "retention",
    "forecast",
    "experiments",
    "optimise",
    "sensitivity",
    "dashboard",
    "commentary",
    "stakeholders",
    "final",
    "manifest",
]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="mbo", description=__doc__)
    parser.add_argument("step", choices=[*STEPS, "all", "review", "verify", "reproduce"])
    parser.add_argument(
        "--llm", action="store_true", help="commentary: draft with the Claude API (sends the fact sheet)"
    )
    parser.add_argument("--reviewer", default="", help="review: reviewer's name")
    parser.add_argument("--decision", default="approved", help="review: approved | approved with edits | rejected")
    parser.add_argument("--notes", default="", help="review: notes")
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
        "forecast": lambda: cmd_forecast(cfg),
        "experiments": lambda: cmd_experiments(cfg),
        "optimise": lambda: cmd_optimise(cfg),
        "sensitivity": lambda: cmd_sensitivity(cfg),
        "dashboard": lambda: cmd_dashboard(cfg),
        "commentary": lambda: cmd_commentary(cfg, args.llm),
        "stakeholders": lambda: cmd_stakeholders(cfg),
        "final": lambda: cmd_final(cfg),
        "manifest": lambda: cmd_manifest(cfg),
        "verify": lambda: cmd_verify(cfg),
        "review": lambda: cmd_review(cfg, args.reviewer, args.decision, args.notes),
    }
    if args.step == "reproduce":
        cmd_reproduce(cfg, steps)
        return
    for name in STEPS if args.step == "all" else [args.step]:
        steps[name]()


if __name__ == "__main__":
    main()
