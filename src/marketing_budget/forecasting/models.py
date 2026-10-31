"""Forecast models for one weekly series, from simplest to most complex.

Every model has the same signature: `fit_predict(history, future, target, cfg) -> forecasts`, where `history`
holds past weeks (column `t` = week number, the target, and `spend`) and `future` the weeks to forecast (`t`,
and for the spend-aware models the *planned* `spend`). Positive series are modelled on the log scale and
transformed back with a smearing correction, so forecasts are means rather than medians.

* naive           last observed week, repeated
* seasonal_naive  the same week one year earlier
* ets             Holt-Winters exponential smoothing: damped trend + 52-week additive seasonality (log scale)
* regression      OLS on trend, annual Fourier terms and log planned spend (this week and last)
* gbm             gradient boosting on what the regression's trend does not explain, with seasonality,
                  last year's value and planned spend as features. Trees cannot extrapolate a trend, so
                  the linear trend is removed first.

Spend is a management decision. Models that use it forecast *conditional on the spend plan*; for the spend
target itself no model is given spend.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from marketing_budget.config import Config

SEASON = 52


def _uses_spend(target: str) -> bool:
    return target != "spend"


def _transform(y: np.ndarray) -> tuple[np.ndarray, bool]:
    if np.all(y > 0):
        return np.log(y), True
    return y.astype(float), False


def _back(z: np.ndarray, resid: np.ndarray, logged: bool) -> np.ndarray:
    if not logged:
        return z
    return np.exp(z) * float(np.mean(np.exp(resid)))  # Duan smearing: mean, not median, of the forecast


def fourier(t: np.ndarray, period: float, k: int) -> np.ndarray:
    w = 2 * np.pi * np.asarray(t, float)[:, None] * np.arange(1, k + 1)[None, :] / period
    return np.hstack([np.sin(w), np.cos(w)])


def _design(df: pd.DataFrame, prev_spend: float, target: str, cfg: Config) -> np.ndarray:
    f = cfg.section("forecasting")
    t = df["t"].to_numpy(float)
    cols = [np.ones(len(df)), t / 52.0, fourier(t, float(f["season_weeks"]), int(f["fourier_terms"]))]
    if _uses_spend(target):
        s = df["spend"].to_numpy(float)
        lag = np.concatenate([[prev_spend], s[:-1]])
        cols += [np.log1p(s), np.log1p(lag)]
    return np.column_stack(cols)


def naive(history: pd.DataFrame, future: pd.DataFrame, target: str, cfg: Config) -> np.ndarray:
    return np.full(len(future), float(history[target].iloc[-1]))


def seasonal_naive(history: pd.DataFrame, future: pd.DataFrame, target: str, cfg: Config) -> np.ndarray:
    y = history.set_index("t")[target]
    return np.array([float(y.get(t - SEASON, y.iloc[-1])) for t in future["t"]])


def ets(history: pd.DataFrame, future: pd.DataFrame, target: str, cfg: Config) -> np.ndarray:
    z, logged = _transform(history[target].to_numpy(float))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = ExponentialSmoothing(
            z,
            trend="add",
            damped_trend=True,
            seasonal="add",
            seasonal_periods=SEASON,
            initialization_method="estimated",
        ).fit()
    return _back(np.asarray(fit.forecast(len(future))), np.asarray(fit.resid), logged)


def regression(history: pd.DataFrame, future: pd.DataFrame, target: str, cfg: Config) -> np.ndarray:
    z, logged = _transform(history[target].to_numpy(float))
    X = _design(history, float(history["spend"].iloc[0]), target, cfg)
    beta, *_ = np.linalg.lstsq(X, z, rcond=None)
    Xf = _design(future, float(history["spend"].iloc[-1]), target, cfg)
    return _back(Xf @ beta, z - X @ beta, logged)


def gbm(history: pd.DataFrame, future: pd.DataFrame, target: str, cfg: Config) -> np.ndarray:
    g = cfg.section("forecasting")["gbm"]
    full = pd.concat([history, future], ignore_index=True)
    z_hist, logged = _transform(history[target].to_numpy(float))
    t_all = full["t"].to_numpy(float)
    trend = np.polyfit(history["t"].to_numpy(float), z_hist, 1)
    detr = z_hist - np.polyval(trend, history["t"].to_numpy(float))
    # last year's detrended value is known for every horizon up to 52 weeks
    z_by_t = dict(zip(history["t"], detr, strict=True))
    lag52 = np.array([z_by_t.get(t - SEASON, np.nan) for t in full["t"]])
    f = cfg.section("forecasting")
    feats = [fourier(t_all, float(f["season_weeks"]), int(f["fourier_terms"])), lag52[:, None]]
    if _uses_spend(target):
        s = full["spend"].to_numpy(float)
        feats += [np.log1p(s)[:, None], np.log1p(np.concatenate([[s[0]], s[:-1]]))[:, None]]
    X = np.hstack(feats)
    n = len(history)
    ok = ~np.isnan(lag52[:n])
    model = HistGradientBoostingRegressor(
        max_iter=int(g["max_iter"]),
        learning_rate=float(g["learning_rate"]),
        max_leaf_nodes=int(g["max_leaf_nodes"]),
        min_samples_leaf=int(g["min_samples_leaf"]),
        random_state=cfg.seed,
    ).fit(X[:n][ok], detr[ok])
    resid = detr[ok] - model.predict(X[:n][ok])
    zf = model.predict(X[n:]) + np.polyval(trend, t_all[n:])
    return _back(zf, resid, logged)


MODELS: dict[str, Callable[[pd.DataFrame, pd.DataFrame, str, Config], np.ndarray]] = {
    "naive": naive,
    "seasonal_naive": seasonal_naive,
    "ets": ets,
    "regression": regression,
    "gbm": gbm,
}
