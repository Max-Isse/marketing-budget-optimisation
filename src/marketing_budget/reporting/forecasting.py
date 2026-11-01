"""Phase 2 report: reports/forecasting.md, its tables and one figure."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from marketing_budget.config import Config
from marketing_budget.forecasting.backtest import Intervals
from marketing_budget.forecasting.scenarios import ForwardForecast

# Reference palette (dataviz skill), light mode; validated: blue/orange pass all checks.
SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
ACTUAL, FORECAST = "#2a78d6", "#eb6834"
NAMES = {"B1": "Hearth Box (B1)", "B2": "Ledgerline (B2)", "B3": "Atlas Outdoor (B3)"}
COUNT_TARGETS = ["leads", "qualified_leads", "customers"]


def _md(df: pd.DataFrame, floatfmt: str = ",.3f") -> str:
    return df.to_markdown(index=False, floatfmt=floatfmt)


def quarter_accuracy(totals: pd.DataFrame) -> pd.DataFrame:
    """WAPE of 13-week totals: mean |total error| / mean actual total, across origins."""
    t = totals.assign(abs_err=(totals["forecast"] - totals["actual"]).abs())
    g = t.groupby(["business", "target", "model"])
    return (g["abs_err"].sum() / g["actual"].sum()).rename("quarter_wape").reset_index()


def noise_floor(bt: pd.DataFrame) -> pd.DataFrame:
    """Lowest weekly WAPE any forecast could reach if counts were Poisson around a perfectly known mean:
    E|Y - mu| ~ sqrt(2 mu / pi). Real counts vary more than Poisson, so the true floor is higher."""
    w = bt[bt["target"].isin(COUNT_TARGETS)].drop_duplicates(["business", "target", "week_start"])
    w = w.assign(e=np.sqrt(2 * w["actual"].clip(lower=0) / np.pi))
    g = w.groupby(["business", "target"])
    return (g["e"].sum() / g["actual"].sum()).rename("poisson_floor_wape").reset_index()


def _figure(series: pd.DataFrame, fwd: ForwardForecast, cfg: Config) -> Path:
    h = int(cfg.section("forecasting")["horizon_weeks"])
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.8), facecolor=SURFACE)
    for ax, biz in zip(axes, ["B1", "B2", "B3"], strict=True):
        hist = series[series["business"] == biz].tail(52)
        fc = fwd.weekly[(fwd.weekly["business"] == biz) & (fwd.weekly["target"] == "customers")].head(h)
        ax.set_facecolor(SURFACE)
        ax.fill_between(fc["week_start"], fc["low"], fc["high"], color=FORECAST, alpha=0.18, linewidth=0)
        ax.plot(hist["week_start"], hist["customers"], color=ACTUAL, linewidth=2)
        ax.plot(fc["week_start"], fc["forecast"], color=FORECAST, linewidth=2)
        ax.annotate(
            "Forecast",
            (fc["week_start"].iloc[-1], fc["forecast"].iloc[-1]),
            xytext=(4, 0),
            textcoords="offset points",
            color=INK_2,
            fontsize=9,
            va="center",
        )
        ax.set_title(NAMES[biz], loc="left", color=INK, fontsize=11)
        ax.set_ylim(bottom=0)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(GRID)
        ax.tick_params(colors=INK_2, labelsize=8, length=0)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
    handles = [
        plt.Line2D([], [], color=ACTUAL, linewidth=2, label="Actual new customers per week"),
        plt.Line2D([], [], color=FORECAST, linewidth=2, label="Forecast, last year's spend plan"),
        plt.Rectangle((0, 0), 1, 1, color=FORECAST, alpha=0.18, label="80% range"),
    ]
    fig.legend(handles=handles, loc="upper center", ncol=3, frameon=False, fontsize=9, labelcolor=INK_2)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    path = cfg.path("figures_dir") / "forecast_customers.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return path


def write_forecasting_report(
    series: pd.DataFrame,
    bt: pd.DataFrame,
    acc: pd.DataFrame,
    acc_h: pd.DataFrame,
    selected: pd.DataFrame,
    intervals: Intervals,
    totals: pd.DataFrame,
    fwd: ForwardForecast,
    elasticity: pd.DataFrame,
    cfg: Config,
    true_elasticity: pd.DataFrame | None = None,
) -> Path:
    f = cfg.section("forecasting")
    tables = cfg.path("tables_dir")
    tables.mkdir(parents=True, exist_ok=True)
    acc.to_csv(tables / "forecast_accuracy.csv", index=False, float_format="%.6g")
    acc_h.to_csv(tables / "forecast_accuracy_by_horizon.csv", index=False, float_format="%.6g")
    selected.to_csv(tables / "forecast_selected_models.csv", index=False, float_format="%.6g")
    intervals.coverage.to_csv(tables / "forecast_interval_coverage.csv", index=False, float_format="%.6g")
    fwd.weekly.to_csv(tables / "forecast_weekly.csv", index=False, float_format="%.6g")
    fwd.scenarios.to_csv(tables / "forecast_scenarios.csv", index=False, float_format="%.6g")
    elasticity.to_csv(tables / "spend_elasticity_observational.csv", index=False, float_format="%.6g")
    fig = _figure(series, fwd, cfg)

    models = [*f["models"], "regression_spend_forecast"]
    wape = acc.pivot_table(index=["business", "target"], columns="model", values="wape")[models].reset_index()
    qa = quarter_accuracy(totals)
    sel = selected.merge(qa, left_on=["business", "target", "selected"], right_on=["business", "target", "model"])
    sel = sel.drop(columns="model")
    sel[["business", "target", "selected", "quarter_wape"]].to_csv(
        tables / "forecast_quarter_accuracy.csv", index=False, float_format="%.6g"
    )
    floor = noise_floor(bt)
    sel_floor = sel[sel["target"].isin(COUNT_TARGETS)].merge(floor, on=["business", "target"])
    cov = intervals.coverage.merge(
        selected[["business", "target", "selected"]],
        left_on=["business", "target", "model"],
        right_on=["business", "target", "selected"],
    )[["business", "target", "model", "coverage", "target_level"]]
    by_h = (
        acc_h.merge(
            selected[["business", "target", "selected"]],
            left_on=["business", "target", "model"],
            right_on=["business", "target", "selected"],
        )
        .pivot_table(index=["business", "target"], columns="horizon_bucket", values="wape")
        .reset_index()
    )

    # Headline numbers (computed, never typed)
    funnel = wape[wape["target"].isin(["clicks", "leads", "qualified_leads", "customers"])]
    reg_wins = int((funnel[["naive", "seasonal_naive", "ets", "gbm"]].min(axis=1) > funnel["regression"]).sum())
    gbm_beats_reg = int((wape["gbm"] < wape["regression"]).sum())
    clicks = wape[wape["target"] == "clicks"]
    cust = wape[wape["target"] == "customers"]
    qcust = sel[sel["target"] == "customers"].set_index("business")["quarter_wape"]
    q_cp = sel[sel["target"] == "contribution_profit"].set_index("business")["quarter_wape"]
    avg_cov = float(cov["coverage"].mean())

    sc = fwd.scenarios
    nq = sc[sc["period"] == "next quarter"]
    show_targets = ["spend", "customers", "cac", "revenue", "contribution_profit"]
    nq_tab = (
        nq[nq["target"].isin(show_targets)]
        .pivot_table(index=["business", "target"], columns="scenario", values="value")
        .reset_index()[["business", "target", "pessimistic", "baseline", "optimistic"]]
    )
    nq_tab["target"] = pd.Categorical(nq_tab["target"], show_targets)
    nq_tab = nq_tab.sort_values(["business", "target"])
    yr = sc[sc["period"] == "next 52 weeks"]
    yr_tab = (
        yr[yr["target"].isin(show_targets)]
        .pivot_table(index=["business", "target"], columns="scenario", values="value")
        .reset_index()[["business", "target", "pessimistic", "baseline", "optimistic"]]
    )
    yr_tab["target"] = pd.Categorical(yr_tab["target"], show_targets)
    yr_tab = yr_tab.sort_values(["business", "target"])
    group = yr_tab.groupby("target", observed=True)[["pessimistic", "baseline", "optimistic"]].sum()
    cp_group = group.loc["contribution_profit"]
    start = fwd.weekly["week_start"].min()
    q_end = start + pd.Timedelta(weeks=int(f["horizon_weeks"]) - 1, days=6)

    def lines_for(biz: str) -> str:
        r = nq_tab[nq_tab["business"] == biz].set_index("target")
        c, k, p = r.loc["customers"], r.loc["cac"], r.loc["contribution_profit"]
        return (
            f"   - **{biz}:** {c['baseline']:,.0f} new customers (range {c['pessimistic']:,.0f}–{c['optimistic']:,.0f}), "
            f"blended CAC ${k['baseline']:,.0f} (${k['optimistic']:,.0f}–${k['pessimistic']:,.0f}), "
            f"contribution profit ${p['baseline'] / 1e6:,.2f}M (${p['pessimistic'] / 1e6:,.2f}M–${p['optimistic'] / 1e6:,.2f}M)"
        )

    el = elasticity.pivot_table(index="business", columns="specification", values="elasticity")
    el_text = (
        f"between {el['spend only'].min():.2f} and {el['spend only'].max():.2f} without controls and "
        f"{el['spend + trend + seasonality'].min():.2f}–{el['spend + trend + seasonality'].max():.2f} with them"
    )
    validation = ""
    if true_elasticity is not None:
        v = elasticity.merge(true_elasticity, on="business")
        v["overstatement"] = v["elasticity"] / v["true_elasticity"]
        v["true_in_ci"] = (v["true_elasticity"] >= v["ci_low"]) & (v["true_elasticity"] <= v["ci_high"])
        v.to_csv(tables / "spend_elasticity_validation.csv", index=False, float_format="%.6g")
        ctrl = v[v["specification"] == "spend + trend + seasonality"]
        wide = ctrl.iloc[int(np.argmax((ctrl["ci_high"] - ctrl["ci_low"]).to_numpy()))]
        lo = v.groupby("specification")["overstatement"].min()
        hi = v.groupby("specification")["overstatement"].max()
        validation = f"""
## Validation against the SYNTHETIC ground truth: is the spend coefficient causal?

The true elasticity comes from the simulation's response curves at each week's actual spend. The
regression without controls overstates it **{lo["spend only"]:.1f}–{hi["spend only"]:.1f}x**. With trend and
seasonality controls it still overstates it **{lo["spend + trend + seasonality"]:.1f}–{hi["spend + trend + seasonality"]:.1f}x**:
the controls are smooth annual curves, and budgets followed the month-by-month demand pattern more closely
than those curves capture. With controls, the true value lies inside the regression's 95% interval for
{int(ctrl["true_in_ci"].sum())} of {len(ctrl)} businesses. That is not reassurance: the intervals are too
wide to guide a budget (widest: {wide["business"]}, {wide["ci_low"]:.2f} to {wide["ci_high"]:.2f}), and the
point estimates lean high. An analyst could not detect the residual bias
from the data alone. That is why the optimiser in phase 4 does not use these coefficients without
experimental calibration.

{_md(v[["business", "specification", "elasticity", "ci_low", "ci_high", "true_elasticity", "overstatement", "true_in_ci"]])}
"""

    text = f"""# Forecasting (SYNTHETIC data)

## Summary for management

1. **Business question.** If each business keeps last year's spending pattern, what will the next quarter
   ({start:%d %b %Y}–{q_end:%d %b %Y}) and the next 12 months bring in spend, leads, customers, acquisition
   cost, revenue and contribution profit? And how far off could that be?
2. **Why it matters.** The quarter ahead includes B3's Black Friday and Christmas peak and B1's January peak.
   Finance needs a range, not a point, to plan cash. This forecast is also the "do nothing different"
   baseline that the optimised budget in phase 4 has to beat.
3. **What this establishes.** Five methods were tested the way they would have been used: at 10 points in the
   last year, each forecast the following 13 weeks using only the data available at the time. A seasonal
   regression that knows the spend plan was the most accurate for {reg_wins} of {len(funnel)} funnel
   forecasts. The machine-learning model beat it in {gbm_beats_reg} of {len(wape)} cases. Quarterly totals of new
   customers were accurate to within {qcust.min():.0%}–{qcust.max():.0%} on average, and contribution profit to
   within {q_cp.min():.0%}–{q_cp.max():.0%}.
4. **In business terms.** Baseline next quarter, with the realistic downside–upside range:
{lines_for("B1")}
{lines_for("B2")}
{lines_for("B3")}

   Across the group, next-12-month contribution profit is about ${cp_group["baseline"] / 1e6:,.1f}M
   (${cp_group["pessimistic"] / 1e6:,.1f}M–${cp_group["optimistic"] / 1e6:,.1f}M).
5. **Action to consider.** Plan on quarterly totals, not weekly figures: B2's weekly sign-ups are too few to
   forecast closely, and no method can do much better. Use the pessimistic case for cash planning. Do **not**
   use the forecasting model to decide how much to spend. Its spend coefficients say a 1% rise in spend lifts
   customers by {el_text}, and that is a correlation with budgets that followed demand, not the effect of the
   spend.
6. **Assumptions and limits.** Forecasts assume the next year behaves like the last two to three. The spend plan
   is last year's, week by week. Ranges come from only 10 historical test points, so the 10% and 90% cases
   are rough. The 80% weekly ranges contained the actual value {avg_cov:.0%} of the time when tested on
   held-out periods, so they are slightly too narrow. The 12-month range applies the quarterly error to the
   whole year (an assumption).

![New customers per week: last 52 weeks and next quarter's forecast with 80% range]({fig.relative_to(cfg.path("reports_dir")).as_posix()})

## What is forecast, and from what

Weekly per business, from `business_week_pnl` (SQL layer): spend, clicks, leads (B2 de-duplicated), qualified
leads, new customers, revenue and contribution from all active customers, and contribution profit
(contribution − one-off acquisition costs − ad spend). **CAC** is planned spend ÷ forecast customers, a
*blended* CAC that includes organic customers. It is not the incremental CAC that budget decisions need.

| Model | How it works | Uses the spend plan |
|---|---|---|
| naive | next weeks = last week | no |
| seasonal_naive | next weeks = same weeks last year | no |
| ets | Holt-Winters: damped trend + 52-week seasonality, log scale | no |
| regression | trend + 3 annual sine/cosine pairs + log spend this week and last, log scale | yes |
| gbm | gradient-boosted trees on the de-trended series: seasonality, last year's value, spend | yes |
| regression_spend_forecast | the regression, with spend replaced by a seasonal-naive *forecast* of spend | no |

Spend is a management decision, so the spend-aware models forecast *given the plan*; in testing, the actual
spend stands in for the plan. The last row shows what that knowledge is worth.

## How the methods were tested (rolling origin)

Origins every {f["origin_step_weeks"]} weeks from week {f["min_train_weeks"]}. At each origin, models are fitted on all earlier weeks and
forecast the next {f["horizon_weeks"]}: {bt["origin"].nunique()} origins × {f["horizon_weeks"]} horizons per series. **WAPE** = total absolute error ÷ total actual
(comparable across series of different size). **Bias** = total error ÷ total actual (positive = forecasts too
high). MAE and RMSE are in `reports/tables/forecast_accuracy.csv`.

### Weekly WAPE by method

Lower is better. The selected model is the simplest within {f["selection_tolerance"]:.0%} (relative) of the best.

{_md(wape)}

Knowing the spend plan matters most for clicks: clicks WAPE {clicks["regression"].min():.1%}–{clicks["regression"].max():.1%} with the plan vs
{clicks["regression_spend_forecast"].min():.1%}–{clicks["regression_spend_forecast"].max():.1%} without. Clicks are bought almost one-for-one with spend. For customers the gain is
smaller (regression {cust["regression"].min():.1%}–{cust["regression"].max():.1%} vs {cust["regression_spend_forecast"].min():.1%}–{cust["regression_spend_forecast"].max():.1%}), because most customers do not depend on that week's
spend.

### Selected models: weekly and quarterly accuracy, bias

{_md(sel[["business", "target", "selected", "selected_wape", "quarter_wape", "selected_bias", "lowest_wape_model", "seasonal_naive_wape"]])}

B2 sign-ups ran ahead of every model's forecast in the last year (negative bias): sign-ups rose to a new level
that no model trained on earlier data anticipated. Bias at this size is a reason to re-forecast monthly, not to
trust any one model more.

### Selected models: weekly WAPE by horizon (weeks ahead)

{_md(by_h)}

### How close could any forecast get? (count targets)

If weekly counts were Poisson around a perfectly known mean, the smallest achievable weekly WAPE would be about
√(2μ/π)/μ. B2's weekly customer counts (a handful a week) are close to that floor, so better models cannot
help much.

{_md(sel_floor[["business", "target", "selected", "selected_wape", "poisson_floor_wape"]])}

### Prediction-interval coverage (selected models, leave-one-origin-out)

{_md(cov)}

## Scenarios

Spend is the plan (last year's weekly spend rolled forward) in every scenario; what varies is the market's
response. Pessimistic / baseline / optimistic = 10th / 50th / 90th percentile of the backtest's 13-week-total
errors. For CAC, pessimistic means *high*.

### Next quarter ({start:%d %b %Y}–{q_end:%d %b %Y})

{_md(nq_tab, ",.0f")}

### Next 52 weeks (quarter-level error band applied to the year: an assumption)

{_md(yr_tab, ",.0f")}

## What the forecasting model can and cannot say about spend

The regression forecasts well, but its spend coefficients are **predictive, not causal**. The implied
elasticity is the % change in weekly customers for a sustained 1% change in spend:

{_md(elasticity)}

Without controls the regression credits spend with the seasonal demand it followed. Adding trend and
seasonality roughly halves the estimate, but nothing in the historical data shows whether the remainder is
the effect of spend or something else that moved with it. Phase 3's experiments answer that.
{validation}"""
    path = cfg.path("reports_dir") / "forecasting.md"
    path.write_text(text, encoding="utf-8")
    return path
