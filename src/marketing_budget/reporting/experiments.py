"""Phase 3 report: reports/experiments.md and its tables."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from marketing_budget.config import Config
from marketing_budget.experiments.results import ExperimentResults


def _md(df: pd.DataFrame, floatfmt: str = ",.3f") -> str:
    return df.to_markdown(index=False, floatfmt=floatfmt)


def _pct(x: float) -> str:
    return f"{x:+.1%}"


def _money(x: float) -> str:
    return f"-${abs(x) / 1000:,.0f}k" if x < 0 else f"${x / 1000:,.0f}k"


def econ_verdict(econ: pd.DataFrame) -> pd.DataFrame:
    w = econ.pivot_table(index=["experiment", "decision"], columns="case", values="contribution_per_year").reset_index()
    lo = w[["ci_low", "ci_high"]].min(axis=1)
    hi = w[["ci_low", "ci_high"]].max(axis=1)
    w["low"], w["high"] = lo, hi
    w["verdict"] = np.select(
        [lo > 0, hi < 0],
        ["do it: gains even in the cautious case", "don't: loses money even in the best case"],
        "uncertain: the range includes a loss and a gain",
    )
    return w[["experiment", "decision", "estimate", "low", "high", "verdict"]]


def write_experiments_report(
    out: dict[str, Any], score: pd.DataFrame, cfg: Config, mc: pd.DataFrame | None = None
) -> Path:
    res: ExperimentResults = out["results"]
    plan, geo_design, values = out["plan"], out["geo_design"], out["values"]
    peek = out["peeking_simulation"]
    e = cfg.section("experiments")
    tables = cfg.path("tables_dir")
    tables.mkdir(parents=True, exist_ok=True)
    res.effects.to_csv(tables / "experiment_effects.csv", index=False, float_format="%.6g")
    res.segments.to_csv(tables / "experiment_segments.csv", index=False, float_format="%.6g")
    res.attribution.to_csv(tables / "experiment_attribution_vs_causal.csv", index=False, float_format="%.6g")
    res.economics.to_csv(tables / "experiment_economics.csv", index=False, float_format="%.6g")
    geo_design.to_csv(tables / "experiment_geo_design.csv", index=False, float_format="%.6g")
    pd.DataFrame(plan).T.reset_index(names="experiment").to_csv(
        tables / "experiment_user_design.csv", index=False, float_format="%.6g"
    )
    verdict = econ_verdict(res.economics)
    verdict.to_csv(tables / "experiment_decisions.csv", index=False, float_format="%.6g")

    eff: dict[Any, dict[Any, Any]] = res.effects.set_index(["experiment", "metric"]).to_dict("index")
    lp = eff[("landing_page", "conversion rate")]
    cr = eff[("ad_creative", "click-through rate")]
    au_l = eff[("audience_targeting", "leads per $")]
    au_q = eff[("audience_targeting", "qualified leads per $")]
    v: dict[Any, dict[Any, Any]] = verdict.set_index("experiment").to_dict("index")
    att_df = res.attribution.set_index("experiment")
    att: dict[Any, dict[Any, Any]] = att_df.to_dict("index")
    gd: dict[Any, dict[Any, Any]] = geo_design.set_index("experiment").to_dict("index")
    geo = {k: g.summary for k, g in res.geo.items()}
    rt, bs, so, tc = geo["retargeting_off"], geo["brand_search_off"], geo["social_plus_50"], geo["bidding_tcpa"]
    tm: dict[Any, dict[Any, Any]] = res.geo["bidding_tcpa"].by_metric.set_index("metric").to_dict("index")
    tcpa_plat = float(tm["line_platform_conversions"]["effect_per_treated_region"]) / float(
        tm["line_platform_conversions"]["control_mean_per_region"]
    )
    tcpa_lc = float(tm["line_last_click_customers"]["effect_per_treated_region"]) / float(
        tm["line_last_click_customers"]["control_mean_per_region"]
    )

    def vs_claim(name: str, summ: dict[str, float]) -> str:
        claim = float(gd[name]["effect_if_platform_right"])
        lo, hi = -summ["relative_ci_high"], -summ["relative_ci_low"]  # loss from switching off, as a positive share
        if lo <= claim <= hi:
            return f"consistent with the {claim:.0%} the platform implies; the test cannot tell them apart"
        if claim > hi:
            return f"the platform's implied {claim:.0%} is ruled out: the channel brings in fewer customers than it is credited with"
        return f"more than the {claim:.0%} the platform implies"

    actions = []
    for r in verdict.sort_values("estimate", ascending=False).to_dict("records"):
        if r["verdict"].startswith("do it"):
            actions.append(f"{r['decision'][0].upper()}{r['decision'][1:]}.")
        elif r["verdict"].startswith("don't"):
            actions.append(f"Do not {r['decision']}.")
        elif r["estimate"] < 0:
            actions.append(
                f"Do not {r['decision']}: the likely result is a loss of {_money(-r['estimate'])} a year "
                f"(range {_money(r['low'])} to {_money(r['high'])})."
            )
        else:
            actions.append(
                f"Do not {r['decision']} yet: the yearly result could be anywhere from {_money(r['low'])} to "
                f"{_money(r['high'])}; a longer or larger test would settle it."
            )
    n_unpowered = int((~geo_design["powered"].astype(bool)).sum())
    budget_tested = sum(
        float(att[k]["annual_line_spend"]) for k in ("retargeting_off", "brand_search_off", "social_plus_50")
    )

    lp_peek = res.peeking["landing_page"]
    first_sig = lp_peek[lp_peek["p_value"] < 0.05]
    peek_line = ""
    if len(first_sig):
        d0 = first_sig.to_dict("records")[0]
        peek_line = (
            f" Checked daily, the landing-page test first looked 'significant' on day {int(d0['day']) + 1}, showing a "
            f"{d0['relative_effect']:+.0%} uplift, against {lp['relative_effect']:+.1%} at the planned end."
        )
    cr_peek = res.peeking["ad_creative"]
    au = plan["audience_targeting"]
    seg = res.segments
    creative_naive = seg[seg["segment"].str.startswith("naive")].to_dict("records")[0]

    def ver(x: str) -> str:
        r = v[x]
        return (
            f"{r['verdict'].split(':')[0]}: {_money(r['estimate'])} a year ({_money(r['low'])} to {_money(r['high'])})"
        )

    att_show = res.attribution[
        [
            "experiment",
            "line",
            "spend_change",
            "correlation_per_1000",
            "platform_per_1000",
            "last_click_per_1000",
            "causal_per_1000",
            "causal_change",
            "causal_ci_low",
            "causal_ci_high",
        ]
    ]
    validation = ""
    if score is not None:
        mc_text = ""
        if mc is not None:
            mc_text = f"""
### Is the region-test method sound? (each test re-run {int(mc["repetitions"].iloc[0])} times with fresh random draws)

The average estimate should match the average true effect (bias near 0 standard errors), and 95% intervals
should contain the truth about 95% of the time.

{_md(mc)}
"""
        validation = f"""
## Validation against the SYNTHETIC ground truth

{int(score["true_in_ci"].sum())} of {len(score)} confidence intervals contain the true effect.

{_md(score)}
{mc_text}"""

    text = f"""# Experimentation (SYNTHETIC data)

## Summary for management

1. **Business question.** Which changes actually win profitable customers, and what does each advertising
   channel *cause*, as opposed to what dashboards credit it with?
2. **Why it matters.** Phase 2 showed that history alone overstates what spend achieves by 1.2–3.6x, because
   budgets were raised when demand was already high. Only randomised tests separate cause from coincidence.
   The three channels tested by changing their budgets in some regions cost
   ${budget_tested / 1e6:,.2f}M a year.
3. **What this establishes (causal evidence: every result below comes from a randomised test).**
   - **New landing page (B1):** conversion {_pct(lp["relative_effect"])} (95% range {_pct(lp["ci_low"])} to {_pct(lp["ci_high"])}).
     Break-even is {lp["threshold"]:.1%}. {lp["decision"].capitalize()}.
   - **New ad creative (B3 social):** click-through {_pct(cr["relative_effect"])} ({_pct(cr["ci_low"])} to {_pct(cr["ci_high"])}).
     There is no evidence it is better or worse.
   - **Lookalike audience (B2 LinkedIn):** leads per dollar {_pct(au_l["relative_effect"])}, but *qualified* leads per
     dollar {_pct(au_q["relative_effect"])} ({_pct(au_q["ci_low"])} to {_pct(au_q["ci_high"])}). More leads, worse leads.
   - **Retargeting switched off (B3):** customers {_pct(rt["relative_effect"])} ({_pct(rt["relative_ci_low"])} to
     {_pct(rt["relative_ci_high"])}): {vs_claim("retargeting_off", rt)}.
   - **Brand search switched off (B1):** customers {_pct(bs["relative_effect"])} ({_pct(bs["relative_ci_low"])} to
     {_pct(bs["relative_ci_high"])}): {vs_claim("brand_search_off", bs)}.
   - **Social spend +50% (B3):** {_pct(so["relative_effect"])} customers ({_pct(so["relative_ci_low"])} to {_pct(so["relative_ci_high"])}).
   - **Target-CPA bidding (B1 generic search):** in the test regions the platform reported {_pct(tcpa_plat)}
     conversions for the same spend, while the CRM's last-click count moved {_pct(tcpa_lc)}.
     Measured effect on all B1 customers: {_pct(tc["relative_effect"])} ({_pct(tc["relative_ci_low"])} to
     {_pct(tc["relative_ci_high"])}), too imprecise to confirm any gain.
4. **In business terms (annual contribution, with the cautious-to-optimistic range).**
   - Launch the new landing page: {ver("landing_page")}.
   - Switch off B3 retargeting: {ver("retargeting_off")}.
   - Switch off B1 brand search: {ver("brand_search_off")}.
   - Raise B3 social by 50%: {ver("social_plus_50")}.
   - Switch B2 LinkedIn to lookalikes: {ver("audience_targeting")}.
   - Switch to target-CPA bidding: {ver("bidding_tcpa")}.
5. **Action to consider.**
{chr(10).join("   - " + a for a in actions)}
   - Judge bidding and audience changes by customers and qualified leads, never by the platform's own conversion
     count or by lead volume.
   - Phase 4 uses these measured effects to calibrate the budget model.
6. **Assumptions and limits.**
   - The tests ran for 8–16 weeks in summer and autumn; effects may differ in peak season.
   - Region tests assume people do not cross regions to buy.
   - LinkedIn's two audiences may overlap.
   - Yearly figures scale a test-period effect to 52 weeks and all regions (assumption), and value
     customers at phase 1's 24-month estimates: B1 ${values["B1"]:,.0f}, B2 ${values["B2"]:,.0f}, B3 ${values["B3"]:,.0f}.
   - {n_unpowered} of the {len(geo_design)} region tests could not reach their target sensitivity even at the
     strongest practical design. Their ranges are honest but wide.

## Correlation, attribution and causal impact

| | Question it answers | Here | Evidence |
|---|---|---|---|
| **Correlation** | Do sales rise in weeks when this channel spends more? | Weekly business customers regressed on the channel's spend | Neither: spend followed demand |
| **Attribution** | Which channel touched the customer last, or at all? | Platform-reported and CRM last-click conversions | An accounting rule; counts customers who would have bought anyway |
| **Causal impact** | What changes if we change the spend? | Randomised tests: regions or users assigned by chance | Causal, within the test's conditions |

Customers per $1,000 of spend, four ways, for the lines whose budgets were tested:

{_md(att_show, ",.1f")}

For retargeting, history suggests {att["retargeting_off"]["correlation_per_1000"]:.0f} customers per $1,000, the platform
{att["retargeting_off"]["platform_per_1000"]:.0f}, the CRM {att["retargeting_off"]["last_click_per_1000"]:.0f}, and the randomised test
{att["retargeting_off"]["causal_per_1000"]:.1f}. Each step removes customers who would have come anyway. The bidding test changes no
spend, so per-$1,000 figures do not apply (blank).

## Design: sizing the tests before running them

Each test is sized so that, if the effect worth detecting is real, it is found with {e["power"]:.0%} probability at a
{e["alpha"]:.0%} false-alarm rate.

### Customer-level tests

{_md(pd.DataFrame(plan).T.reset_index(names="experiment")[["experiment", "unit", "metric", "baseline", "baseline_source", "min_worthwhile_effect", "n_per_arm_required", "weeks", "n_per_arm_planned", "mde_at_planned_n"]], ",.4g")}

The audience test would need **{au["weeks_required"]} weeks** to detect a {au["min_worthwhile_effect"]:.0%} change in qualified leads, because B2's
LinkedIn produces about {au["qualified_leads_per_arm_week"] * 2:.0f} qualified leads a week. It ran for the {au["weeks"]}-week maximum, knowing it could only
detect changes of about {au["mde_at_planned_n"]:.0%}. A test this small can catch a large problem; it cannot certify a small gain.

### Region tests (budget and bidding)

Each test was sized to detect half of what the ad platform claims the channel does (for bidding, a 2% change in
the business's customers). The design picks the cheapest combination of holdout share and duration that gets
there; when none does, it uses the most sensitive one and says so. Sensitivity comes from an A/A rehearsal on the
8 weeks before the test.

{_md(geo_design, ",.3f")}

Holding out half the regions for 16 weeks is a real business cost: some customers are lost in the holdout. That
is the price of measuring the effect at all.

## Why peeking at results is dangerous

If a test with no real difference is checked every day and stopped at the first "significant" result, it
produces a false winner **{peek["false_positive_rate_any_daily_look"]:.0%}** of the time, against
{peek["false_positive_rate_final_look_only"]:.0%} when read once at the planned end ({peek["days"]} days, simulated).{peek_line}
The creative test's daily p-value never fell below 0.05 (lowest {cr_peek["p_value"].min():.2f}). Each test is read once, at its
planned end.

## Results: statistical and practical significance

A result can be *statistically* significant (unlikely to be chance) yet too small to be worth acting on, or
*practically* important but too uncertain to bet on. The decision column compares the 95% range with the
smallest effect worth having (`threshold`: break-even for the landing page; any gain for the free creative
switch; 15% for the audience switch).

{_md(res.effects[["experiment", "metric", "n_a", "n_b", "relative_effect", "ci_low", "ci_high", "p_value", "threshold", "decision"]].astype({"n_a": int, "n_b": int}), ",.4f")}

Region-test p-values come from randomisation inference: treatment re-assigned within the same blocks
{e["geo"]["permutations"]:,} times.

### Segments and analysis choices

The landing-page device results are corrected for testing two segments (Holm). The creative test's naive
analysis treats every impression as independent. Because impressions from the same user are correlated, its
range ({_pct(creative_naive["ci_low"])} to {_pct(creative_naive["ci_high"])}) is narrower than the correct one ({_pct(cr["ci_low"])} to {_pct(cr["ci_high"])}).

{_md(seg, ",.4f")}

### Region tests in detail

{_md(pd.concat([g.by_metric.assign(experiment=k) for k, g in res.geo.items()])[["experiment", "metric", "total_effect", "total_ci_low", "total_ci_high", "control_mean_per_region"]], ",.1f")}

## Incremental customers and contribution profit (annual, if rolled out)

The measured effect is causal. Scaling to a year and valuing customers are assumptions (see `basis`).

{_md(verdict, ",.0f")}

{_md(res.economics[["experiment", "case", "extra_customers_per_year", "contribution_per_year", "basis"]], ",.0f")}
{validation}"""
    path = cfg.path("reports_dir") / "experiments.md"
    path.write_text(text, encoding="utf-8")
    return path
