"""Calibrated marketing-mix model: one per business, fitted on weekly data and anchored to the phase 3 tests.

    expected customers_t = base_t x (1 + sum_l beta_l x a_lt / (a_lt + K_l))
    base_t = exp(alpha0 + alpha1 t/52 + annual Fourier terms)          (organic demand: season and trend)
    a_lt   = adstock(spend_l, decay_l)                                  (carry-over, steady state = spend)

beta_l is the most a line can add, as a share of organic demand; K_l the weekly spend at which it adds half
of that. Fitted by Poisson deviance with three kinds of extra term:
* weak priors keep each half-saturation point within about 3x of the line's average spend and each decay near
  0.3 (assumptions, in config `response_model`);
* a one-sided prior: organic demand is at least the customers whose last click was not paid media (CRM
  "organic" source). Without it, history cannot split "would have come anyway" from "came because of ads",
  and the fit hands almost every customer to paid media;
* calibration terms make the model reproduce each budget test's measured effect, weighted by its precision;
* nothing else: the remaining lines are identified by history alone, and are labelled model-based.

Uncertainty: a weighted-likelihood bootstrap. Each draw refits with random exponential weights on the weeks and
redraws each test result from its sampling distribution. The spread of the draws is the curve uncertainty the
optimiser sees.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import duckdb
import numpy as np
import pandas as pd
from scipy.optimize import least_squares

from marketing_budget.config import Config
from marketing_budget.curves import adstock
from marketing_budget.data.db import query_df
from marketing_budget.forecasting.models import fourier


@dataclass
class BusinessData:
    business: str
    channels: list[str]
    weeks: pd.Series
    y: np.ndarray  # weekly new customers (all sources)
    spend: np.ndarray  # weeks x lines
    mean_spend: np.ndarray  # lines
    calibration: list[dict[str, Any]]
    organic_floor: float  # weekly customers whose last click was not paid media (CRM "organic" source)


def load_business_data(con: duckdb.DuckDBPyConnection, cfg: Config) -> dict[str, BusinessData]:
    lw = query_df(
        con, "SELECT week_start, business, channel, spend FROM line_week ORDER BY business, channel, week_start"
    )
    bw = query_df(
        con,
        "SELECT week_start, business, customers, organic_source_customers FROM business_week "
        "ORDER BY business, week_start",
    )
    cal_path = cfg.path("artifacts_dir") / "experiment_calibration.json"
    cal = json.loads(cal_path.read_text(encoding="utf-8")) if cal_path.exists() else []
    out = {}
    for biz in cfg.businesses:
        s = lw[lw["business"] == biz].pivot(index="week_start", columns="channel", values="spend").sort_index()
        y = bw[bw["business"] == biz].set_index("week_start").loc[s.index, "customers"].to_numpy(float)
        out[biz] = BusinessData(
            biz,
            list(s.columns),
            pd.Series(s.index),
            y,
            s.to_numpy(float),
            s.to_numpy(float).mean(axis=0),
            [c for c in cal if c["business"] == biz],
            float(bw.loc[bw["business"] == biz, "organic_source_customers"].mean()),
        )
    return out


@dataclass
class Params:
    alpha: np.ndarray  # intercept, trend, Fourier
    beta: np.ndarray  # lines
    half_sat: np.ndarray  # lines (dollars per week)
    decay: np.ndarray  # lines


class MMM:
    def __init__(self, data: BusinessData, cfg: Config):
        self.d = data
        rc = cfg.section("response_model")
        f = cfg.section("forecasting")
        self.period, self.k = float(f["season_weeks"]), int(f["fourier_terms"])
        self.shape = float(rc["shape"])
        self.decay_lo, self.decay_hi = (float(x) for x in rc["decay_bounds"])
        self.k_lo, self.k_hi = (np.log(float(x)) for x in rc["half_sat_bounds"])
        self.decay_prior = rc["decay_prior"]
        self.k_prior_sd = float(rc["half_sat_prior_sd_log"])
        self.organic_sd = float(rc["organic_floor_sd_log"])
        n = len(data.y)
        self.t = np.arange(n, dtype=float)
        self.X = np.column_stack([np.ones(n), self.t / 52, fourier(self.t, self.period, self.k)])
        self.n_alpha = self.X.shape[1]
        self.L = len(data.channels)
        self.dispersion = 1.0  # quasi-Poisson scale, set by fit_business from a first fit

    # theta = [alpha (n_alpha), log beta (L), log K multiple (L), decay (L)]
    def unpack(self, th: np.ndarray) -> Params:
        a = th[: self.n_alpha]
        b = np.exp(th[self.n_alpha : self.n_alpha + self.L])
        k = self.d.mean_spend * np.exp(th[self.n_alpha + self.L : self.n_alpha + 2 * self.L])
        lam = th[self.n_alpha + 2 * self.L :]
        return Params(a, b, k, lam)

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        L = self.L
        lo = np.r_[np.full(self.n_alpha, -np.inf), np.full(L, -12.0), np.full(L, self.k_lo), np.full(L, self.decay_lo)]
        hi = np.r_[np.full(self.n_alpha, np.inf), np.full(L, 3.0), np.full(L, self.k_hi), np.full(L, self.decay_hi)]
        return lo, hi

    def x0(self) -> np.ndarray:
        a = np.zeros(self.n_alpha)
        a[0] = np.log(max(self.d.y.mean(), 1.0) / 1.3)
        L = self.L
        return np.r_[a, np.full(L, np.log(0.1)), np.zeros(L), np.full(L, 0.3)]

    def saturation(self, spend: np.ndarray, p: Params) -> np.ndarray:
        """weeks x lines: share of each line's maximum lift reached, given the spend history."""
        a = np.column_stack([adstock(spend[:, j], float(p.decay[j])) for j in range(self.L)])
        s = self.shape
        return a**s / (a**s + p.half_sat**s)

    def mean(self, p: Params, spend: np.ndarray | None = None) -> np.ndarray:
        h = self.saturation(self.d.spend if spend is None else spend, p)
        return np.exp(self.X @ p.alpha) * (1 + h @ p.beta)

    def predicted_test_effect(self, p: Params, c: dict[str, Any]) -> float:
        """Relative change in customers over the test weeks if the line's spend had been multiplied."""
        j = self.d.channels.index(c["channel"])
        start = int(np.nonzero(self.d.weeks.dt.date.astype(str).to_numpy() == c["test_start"])[0][0])
        test = slice(start, start + int(c["test_weeks"]))
        mod = self.d.spend.copy()
        mod[test, j] *= float(c["spend_multiplier"])
        m0, m1 = self.mean(p), self.mean(p, mod)
        return float((m1[test] - m0[test]).sum() / m0[test].sum())

    def residuals(self, th: np.ndarray, w: np.ndarray, targets: list[tuple[dict[str, Any], float]]) -> np.ndarray:
        p = self.unpack(th)
        mu = self.mean(p)
        y = self.d.y
        with np.errstate(divide="ignore", invalid="ignore"):
            dev = 2 * (np.where(y > 0, y * np.log(y / mu), 0.0) - (y - mu))
        r_dev = np.sign(y - mu) * np.sqrt(np.maximum(dev, 0) * w / self.dispersion)
        logk = th[self.n_alpha + self.L : self.n_alpha + 2 * self.L]
        lam = th[self.n_alpha + 2 * self.L :]
        base = float(np.exp(self.X @ p.alpha).mean())
        r_prior = np.r_[
            logk / self.k_prior_sd,
            (lam - float(self.decay_prior["mean"])) / float(self.decay_prior["sd"]),
            # one-sided: organic demand is at least the customers who arrived with no paid last click
            max(0.0, np.log(self.d.organic_floor) - np.log(base)) / self.organic_sd,
        ]
        r_cal = np.array([(self.predicted_test_effect(p, c) - target) / float(c["se"]) for c, target in targets])
        return np.r_[r_dev, r_prior, r_cal]

    def fit(
        self,
        w: np.ndarray | None = None,
        targets: list[tuple[dict[str, Any], float]] | None = None,
        x0: np.ndarray | None = None,
    ) -> np.ndarray:
        w = np.ones(len(self.d.y)) if w is None else w
        targets = [] if targets is None else targets
        lo, hi = self.bounds()
        start = np.clip(self.x0() if x0 is None else x0, lo + 1e-9, hi - 1e-9)
        sol = least_squares(self.residuals, start, bounds=(lo, hi), args=(w, targets), method="trf", max_nfev=400)
        return np.asarray(sol.x)


@dataclass
class FittedBusiness:
    model: MMM
    point: np.ndarray
    draws: list[np.ndarray]


def fit_business(data: BusinessData, cfg: Config, calibrate: bool, n_draws: int, seed: int) -> FittedBusiness:
    """Weekly counts vary far more than a Poisson model assumes, which would let 156 weeks of history drown out
    the experiments. A first fit estimates the over-dispersion (Pearson chi-square / df); the history's weight is
    then divided by it (quasi-Poisson), so each source counts for what it is worth."""
    m = MMM(data, cfg)
    first = m.fit()
    mu = m.mean(m.unpack(first))
    m.dispersion = max(float(((data.y - mu) ** 2 / mu).sum() / (len(data.y) - len(first))), 1.0)
    cal = data.calibration if calibrate else []
    point = m.fit(targets=[(c, float(c["relative_effect"])) for c in cal], x0=first)
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(n_draws):
        w = rng.exponential(1.0, len(data.y))
        targets = [(c, float(c["relative_effect"]) + float(c["se"]) * rng.standard_normal()) for c in cal]
        draws.append(m.fit(w, targets, x0=point))
    return FittedBusiness(m, point, draws)


def calibration_check(fb: FittedBusiness) -> pd.DataFrame:
    """Does the fitted model reproduce each test it was calibrated to?"""
    rows = []
    for c in fb.model.d.calibration:
        pred = fb.model.predicted_test_effect(fb.model.unpack(fb.point), c)
        draws = [fb.model.predicted_test_effect(fb.model.unpack(d), c) for d in fb.draws]
        rows.append(
            {
                "experiment": c["experiment"],
                "measured": c["relative_effect"],
                "measured_se": c["se"],
                "model": pred,
                "model_p10": float(np.quantile(draws, 0.1)),
                "model_p90": float(np.quantile(draws, 0.9)),
            }
        )
    return pd.DataFrame(rows)
