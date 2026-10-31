"""Rolling-origin backtest, accuracy metrics, model selection and empirical prediction intervals.

At each origin T (every `origin_step_weeks` from `min_train_weeks`), each model is fitted on weeks 0..T-1
and forecasts T..T+h-1. Nothing after T is used, except the *spend plan* for spend-aware models, which is
known when a forecast is made (actual spend stands in for the plan). `regression_spend_forecast` repeats the
regression with planned spend replaced by a seasonal-naive spend forecast, to show how much accuracy comes
from knowing the plan.

CAC is not forecast directly: it is planned spend / forecast customers, because CAC is a ratio and averaging
ratio forecasts misbehaves.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb
import numpy as np
import pandas as pd

from marketing_budget.config import Config
from marketing_budget.data.db import query_df
from marketing_budget.forecasting.models import MODELS, regression, seasonal_naive

HORIZON_BUCKETS = [(1, 4), (5, 8), (9, 13)]


def load_series(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    df = query_df(con, "SELECT * FROM business_week_pnl ORDER BY business, week_start")
    df["t"] = df.groupby("business").cumcount()
    return df


def _bucket(h: np.ndarray) -> np.ndarray:
    out = np.empty(len(h), dtype=object)
    for lo, hi in HORIZON_BUCKETS:
        out[(h >= lo) & (h <= hi)] = f"{lo}-{hi}"
    return out


def backtest(series: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Long table: business, target, model, origin, horizon, week, actual, forecast (and cac rows)."""
    f = cfg.section("forecasting")
    h, start, step = int(f["horizon_weeks"]), int(f["min_train_weeks"]), int(f["origin_step_weeks"])
    rows = []
    for biz, df in series.groupby("business"):
        df = df.reset_index(drop=True)
        n = len(df)
        for origin in range(start, n - h + 1, step):
            hist, fut = df.iloc[:origin], df.iloc[origin : origin + h]
            spend_fc = seasonal_naive(hist, fut, "spend", cfg)
            fut_unplanned = fut.assign(spend=spend_fc)
            preds_customers = {}
            for target in f["targets"]:
                actual = fut[target].to_numpy(float)
                runs = {m: (fn, fut) for m, fn in MODELS.items() if m in f["models"]}
                if target != "spend":
                    runs["regression_spend_forecast"] = (regression, fut_unplanned)
                for m, (fn, future) in runs.items():
                    pred = fn(hist, future, target, cfg)
                    if target == "customers":
                        preds_customers[m] = pred
                    rows.append(
                        pd.DataFrame(
                            {
                                "business": biz,
                                "target": target,
                                "model": m,
                                "origin": origin,
                                "horizon": np.arange(1, h + 1),
                                "week_start": fut["week_start"].to_numpy(),
                                "actual": actual,
                                "forecast": pred,
                            }
                        )
                    )
            plan = fut["spend"].to_numpy(float)
            for m, pc in preds_customers.items():
                rows.append(
                    pd.DataFrame(
                        {
                            "business": biz,
                            "target": "cac",
                            "model": m,
                            "origin": origin,
                            "horizon": np.arange(1, h + 1),
                            "week_start": fut["week_start"].to_numpy(),
                            "actual": plan / fut["customers"].to_numpy(float),
                            "forecast": plan / pc,
                        }
                    )
                )
    out = pd.concat(rows, ignore_index=True)
    out["horizon_bucket"] = _bucket(out["horizon"].to_numpy())
    return out


def accuracy(bt: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """MAE, RMSE, WAPE (sum |error| / sum |actual|) and bias (sum error / sum actual; > 0 = forecasts high)."""
    e = bt["forecast"] - bt["actual"]
    g = bt.assign(err=e, abs_err=e.abs(), sq=e**2, abs_act=bt["actual"].abs()).groupby(by)
    out = pd.DataFrame(
        {
            "mae": g["abs_err"].mean(),
            "rmse": np.sqrt(g["sq"].mean()),
            "wape": g["abs_err"].sum() / g["abs_act"].sum(),
            "bias": g["err"].sum() / g["actual"].sum(),
            "n": g["err"].size(),
        }
    )
    return out.reset_index()


def select_models(acc: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Per business and target, the simplest model whose WAPE is within the tolerance of the best."""
    f = cfg.section("forecasting")
    order = {m: i for i, m in enumerate(f["models"])}
    tol = float(f["selection_tolerance"])
    cand = acc[acc["model"].isin(order)]
    rows = []
    for (biz, target), g in cand.groupby(["business", "target"]):
        best = g["wape"].min()
        ok = g[g["wape"] <= best * (1 + tol)].assign(rank=lambda d: d["model"].map(order))
        pick = ok.sort_values("rank").iloc[0]
        lowest = g.sort_values("wape").iloc[0]
        rows.append(
            {
                "business": biz,
                "target": target,
                "selected": pick["model"],
                "selected_wape": pick["wape"],
                "selected_bias": pick["bias"],
                "lowest_wape_model": lowest["model"],
                "lowest_wape": lowest["wape"],
                "seasonal_naive_wape": float(g.loc[g["model"] == "seasonal_naive", "wape"].iloc[0]),
            }
        )
    return pd.DataFrame(rows)


@dataclass
class Intervals:
    quantiles: pd.DataFrame  # business, target, model, horizon_bucket, q_low, q_high (log-ratio errors)
    coverage: pd.DataFrame  # leave-one-origin-out coverage per business, target, model


def empirical_intervals(bt: pd.DataFrame, cfg: Config) -> Intervals:
    """Intervals from the backtest's own errors: log(actual / forecast) quantiles by horizon bucket.

    Coverage is checked honestly: each origin's actuals are tested against quantiles computed from the
    *other* origins only.
    """
    level = float(cfg.section("forecasting")["interval_level"])
    lo_q, hi_q = (1 - level) / 2, (1 + level) / 2
    d = bt[(bt["actual"] > 0) & (bt["forecast"] > 0)].copy()
    d["log_err"] = np.log(d["actual"] / d["forecast"])
    keys = ["business", "target", "model", "horizon_bucket"]
    q = d.groupby(keys)["log_err"].quantile(np.array([lo_q, hi_q])).unstack()
    q.columns = ["q_low", "q_high"]
    q = q.reset_index()

    cov_rows = []
    for k, g in d.groupby(keys[:3]):
        hits, total = 0, 0
        for o in g["origin"].unique():
            train, test = g[g["origin"] != o], g[g["origin"] == o]
            for b, tb in test.groupby("horizon_bucket"):
                e = train.loc[train["horizon_bucket"] == b, "log_err"]
                lo, hi = e.quantile(lo_q), e.quantile(hi_q)
                hits += int(((tb["log_err"] >= lo) & (tb["log_err"] <= hi)).sum())
                total += len(tb)
        cov_rows.append(dict(zip(keys[:3], k, strict=True)) | {"coverage": hits / total, "target_level": level})
    return Intervals(q, pd.DataFrame(cov_rows))


def total_errors(bt: pd.DataFrame) -> pd.DataFrame:
    """log(actual / forecast) of each origin's 13-week *total*: the error that matters for a quarter's plan."""
    g = bt.groupby(["business", "target", "model", "origin"])[["actual", "forecast"]].sum().reset_index()
    g = g[(g["actual"] > 0) & (g["forecast"] > 0)]
    g["log_err"] = np.log(g["actual"] / g["forecast"])
    return g
