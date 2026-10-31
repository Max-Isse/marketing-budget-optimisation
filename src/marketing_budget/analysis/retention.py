"""Customer retention and 24-month customer value, estimated from the cohort tables.

Recent customers are right-censored: they are still active, and how long they will stay is unknown. Dropping
them would bias retention down (only the early, finished lifetimes would count); treating them as churned
would be worse. Both estimators below use every customer for exactly the months they were observed.

* Subscriptions (B1, B2): first-month survival s1 = share still active in month 1 among customers observable in
  month 1. Later churn is a constant monthly hazard h estimated as churn events / observed month-to-month
  transitions from month 2 onward, the censored-geometric maximum-likelihood estimate; s = 1 - h.
* E-commerce (B3): repeat orders in month t >= 1 follow log E[orders_t] = log(customers observable_t) + a + b(t-1),
  a Poisson GLM with quasi-likelihood standard errors. Repeat rate = exp(a), monthly decay = exp(b).

Customer value combines these with finance's contribution per month/order (config `unit_economics`). Its
confidence interval comes from Monte Carlo draws of the estimated parameters.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import duckdb
import numpy as np
import pandas as pd
import statsmodels.api as sm

from marketing_budget.config import Config
from marketing_budget.data.db import query_df
from marketing_budget.economics import customer_value

ALL = "all sources"


def subscription_retention(lt: pd.DataFrame) -> dict[str, float]:
    """`lt` has active_months and observable_months per customer."""
    a, m = lt["active_months"].to_numpy(), lt["observable_months"].to_numpy()
    at_risk1 = m >= 2
    n1 = int(at_risk1.sum())
    s1 = float((a[at_risk1] >= 2).mean()) if n1 else np.nan
    transitions = np.maximum(np.minimum(a, m - 1) - 1, 0)
    events = (a < m) & (a >= 2)
    r, e = int(transitions.sum()), int(events.sum())
    h = e / r if r else np.nan
    return {
        "n_customers": len(lt),
        "survival_first_month": s1,
        "survival_first_month_se": float(np.sqrt(s1 * (1 - s1) / n1)) if n1 else np.nan,
        "survival_monthly": 1 - h,
        "survival_monthly_se": float(np.sqrt(h * (1 - h) / r)) if r else np.nan,
        "transitions_observed": r,
        "churn_events": e,
    }


def ecommerce_repeat(orders: pd.DataFrame) -> dict[str, float]:
    """`orders` has month_index, orders, customers_observable (aggregated)."""
    d = orders[(orders["month_index"] >= 1) & (orders["customers_observable"] > 0)]
    X = sm.add_constant((d["month_index"] - 1).to_numpy(float))
    fit = sm.GLM(
        d["orders"].to_numpy(float),
        X,
        family=sm.families.Poisson(),
        offset=np.log(d["customers_observable"].to_numpy(float)),
    ).fit(scale="X2")
    cov = np.asarray(fit.cov_params())
    return {
        "n_customers": int(d.loc[d["month_index"] == 1, "customers_observable"].sum()),
        "repeat_rate_first_month": float(np.exp(fit.params[0])),
        "repeat_decay_monthly": float(np.exp(fit.params[1])),
        "log_rate": float(fit.params[0]),
        "log_decay": float(fit.params[1]),
        "cov_00": float(cov[0, 0]),
        "cov_01": float(cov[0, 1]),
        "cov_11": float(cov[1, 1]),
        "dispersion": float(fit.scale),
    }


def _value_draws(
    model: str, est: dict[str, float], econ: dict[str, float], horizon: int, rate: float, n: int, seed: int
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    out = np.empty(n)
    if model == "subscription":
        s1 = np.clip(rng.normal(est["survival_first_month"], est["survival_first_month_se"], n), 0, 1)
        sm_ = np.clip(rng.normal(est["survival_monthly"], est["survival_monthly_se"], n), 0, 1)
        for i in range(n):
            out[i] = customer_value(
                model, {**econ, "survival_first_month": s1[i], "survival_monthly": sm_[i]}, horizon, rate
            ).value
    else:
        cov = np.array([[est["cov_00"], est["cov_01"]], [est["cov_01"], est["cov_11"]]])
        draws = rng.multivariate_normal([est["log_rate"], est["log_decay"]], cov, n)
        for i in range(n):
            out[i] = customer_value(
                model,
                {
                    **econ,
                    "repeat_rate_first_month": float(np.exp(draws[i, 0])),
                    "repeat_decay_monthly": float(min(np.exp(draws[i, 1]), 1.0)),
                },
                horizon,
                rate,
            ).value
    return out


@dataclass
class RetentionResults:
    estimates: pd.DataFrame  # business, source, model, parameters, customer value with CI
    empirical: pd.DataFrame  # observed 24-month contribution of fully observed cohorts vs the model


def estimate_retention(con: duckdb.DuckDBPyConnection, cfg: Config) -> RetentionResults:
    v, ue = cfg.section("valuation"), cfg.section("unit_economics")
    horizon, rate = int(v["horizon_months"]), float(v["annual_discount_rate"])
    n_draws = int(cfg.section("retention")["value_draws"])
    lt = query_df(con, "SELECT * FROM customer_lifetimes")
    ro = query_df(con, "SELECT * FROM repeat_orders_by_month")

    rows: list[dict[str, Any]] = []
    for biz in cfg.businesses:
        econ = {k: val for k, val in ue[biz].items() if k != "model"}
        model = str(ue[biz]["model"])
        sub_lt, sub_ro = lt[lt["business"] == biz], ro[ro["business"] == biz]
        for src in [ALL, *sorted(sub_lt["source"].unique())]:
            if model == "subscription":
                est = subscription_retention(sub_lt if src == ALL else sub_lt[sub_lt["source"] == src])
                params = {k: est[k] for k in ("survival_first_month", "survival_monthly")}
            else:
                agg = sub_ro if src == ALL else sub_ro[sub_ro["source"] == src]
                agg = agg.groupby("month_index", as_index=False)[["orders", "customers_observable"]].sum()
                est = ecommerce_repeat(agg)
                params = {k: est[k] for k in ("repeat_rate_first_month", "repeat_decay_monthly")}
            value = customer_value(model, {**econ, **params}, horizon, rate).value
            draws = _value_draws(model, est, econ, horizon, rate, n_draws, cfg.seed + len(rows))
            rows.append(
                {
                    "business": biz,
                    "source": src,
                    "model": model,
                    **est,
                    "customer_value": value,
                    "value_ci_low": float(np.quantile(draws, 0.025)),
                    "value_ci_high": float(np.quantile(draws, 0.975)),
                }
            )
    estimates = pd.DataFrame(rows)

    # Model check without the truth: cohorts observed for the full horizon, observed contribution vs model.
    full = lt[lt["observable_months"] >= horizon]
    act = query_df(
        con,
        "SELECT a.customer_id, a.month_index, a.contribution FROM synthetic_customer_activity a "
        "JOIN customer_lifetimes l USING (customer_id) WHERE l.observable_months >= ?",
        [horizon],
    )
    act = act[act["month_index"] < horizon]
    r = (1 + rate) ** (1 / 12) - 1
    act["disc"] = act["contribution"] * (1 + r) ** -act["month_index"].to_numpy(float)
    per = act.groupby("customer_id")["disc"].sum()
    full = full.assign(disc=full["customer_id"].map(per).fillna(0.0) - full["acquisition_cost"])
    emp = (
        full.groupby("business")
        .agg(n_customers=("customer_id", "size"), observed_value=("disc", "mean"), sd=("disc", "std"))
        .reset_index()
    )
    emp["observed_ci_half"] = 1.96 * emp["sd"] / np.sqrt(emp["n_customers"])
    first_months = full.groupby("business")["acquisition_date"].agg(["min", "max"]).reset_index()
    emp = emp.merge(first_months, on="business").rename(columns={"min": "cohorts_from", "max": "cohorts_to"})
    model_all = estimates[estimates["source"] == ALL].set_index("business")["customer_value"]
    emp["model_value_all_cohorts"] = emp["business"].map(model_all)
    return RetentionResults(estimates, emp.drop(columns="sd"))
