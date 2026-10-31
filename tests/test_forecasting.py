import numpy as np
import pandas as pd
import pytest

from marketing_budget.config import Config
from marketing_budget.forecasting.backtest import accuracy, backtest, empirical_intervals, select_models, total_errors
from marketing_budget.forecasting.models import MODELS, fourier, naive, regression, seasonal_naive
from marketing_budget.forecasting.scenarios import forward, spend_plan

TARGETS = ["spend", "customers"]


def _series(n: int = 140, seed: int = 0, business: str = "B9") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    season = 1 + 0.2 * np.sin(2 * np.pi * t / 52.1775)
    spend = 10_000 * season**0.6 * np.exp(rng.normal(0, 0.1, n))
    customers = 50 * season * (spend / 10_000) ** 0.4 * np.exp(rng.normal(0, 0.05, n))
    return pd.DataFrame(
        {
            "business": business,
            "t": t,
            "week_start": pd.date_range("2023-10-30", periods=n, freq="7D"),
            "spend": spend,
            "customers": customers,
        }
    )


def _cfg(cfg: Config, **over) -> Config:
    f = {**cfg.raw["forecasting"], "targets": TARGETS, "origin_step_weeks": 13, **over}
    return Config({**cfg.raw, "forecasting": f}, cfg.root)


def test_naive_and_seasonal_naive(cfg):
    s = _series()
    hist, fut = s.iloc[:120], s.iloc[120:130]
    assert np.all(naive(hist, fut, "customers", cfg) == s["customers"].iloc[119])
    assert seasonal_naive(hist, fut, "customers", cfg) == pytest.approx(s["customers"].iloc[68:78].to_numpy())


def test_regression_recovers_a_noise_free_seasonal_series(cfg):
    t = np.arange(150)
    y = np.exp(3 + 0.1 * t / 52 + fourier(t, 52.1775, 3) @ np.array([0.2, 0.05, 0, 0.1, 0, 0]))
    s = pd.DataFrame({"t": t, "spend": 1000.0, "y": y})
    pred = regression(s.iloc[:130], s.iloc[130:], "y", cfg)
    assert pred == pytest.approx(y[130:], rel=1e-6)


@pytest.mark.parametrize("name", list(MODELS))
def test_models_ignore_future_actuals(name, cfg):
    s = _series()
    hist, fut = s.iloc[:120], s.iloc[120:133].copy()
    a = MODELS[name](hist, fut, "customers", cfg)
    fut["customers"] = fut["customers"] * 100  # future outcomes must not influence the forecast
    b = MODELS[name](hist, fut, "customers", cfg)
    assert np.all(np.isfinite(a)) and len(a) == 13
    np.testing.assert_allclose(a, b)


def test_backtest_uses_only_the_past(cfg):
    c = _cfg(cfg, models=["naive", "seasonal_naive", "regression"])
    s = _series()
    bt = backtest(s, c)
    origin = int(bt["origin"].min())
    s2 = s.copy()
    s2.loc[s2["t"] >= origin, "customers"] *= 3  # change every outcome from the first origin on
    bt2 = backtest(s2, c)
    first = bt[bt["origin"] == origin].sort_values(["target", "model", "horizon"])
    first2 = bt2[bt2["origin"] == origin].sort_values(["target", "model", "horizon"])
    np.testing.assert_allclose(first["forecast"].to_numpy(), first2["forecast"].to_numpy())


def test_accuracy_definitions():
    bt = pd.DataFrame({"g": "x", "actual": [10.0, 20.0], "forecast": [12.0, 14.0]})
    a = accuracy(bt, ["g"]).iloc[0]
    assert a["mae"] == pytest.approx(4.0)
    assert a["rmse"] == pytest.approx(np.sqrt((4 + 36) / 2))
    assert a["wape"] == pytest.approx(8 / 30)
    assert a["bias"] == pytest.approx(-4 / 30)


def test_selection_prefers_the_simpler_model_within_tolerance(cfg):
    acc = pd.DataFrame(
        {
            "business": "B9",
            "target": "customers",
            "model": ["naive", "seasonal_naive", "ets", "regression", "gbm"],
            "wape": [0.30, 0.104, 0.2, 0.101, 0.100],
            "bias": 0.0,
        }
    )
    pick = select_models(acc, cfg).iloc[0]
    assert pick["selected"] == "seasonal_naive"  # within 5% of gbm's 0.100 and simpler
    assert pick["lowest_wape_model"] == "gbm"


def test_spend_plan_is_last_year_rolled_forward():
    s = _series(n=110)
    plan = spend_plan(s, 13)
    assert plan["t"].iloc[0] == 110
    assert plan["spend"].to_numpy() == pytest.approx(s["spend"].iloc[58:71].to_numpy())


def test_scenarios_are_ordered_and_cac_moves_against_customers(cfg):
    c = _cfg(cfg, models=["naive", "seasonal_naive", "regression"])
    s = pd.concat([_series(seed=1), _series(seed=2, business="B8")], ignore_index=True)
    bt = backtest(s, c)
    acc = accuracy(bt, ["business", "target", "model"])
    fwd = forward(s, select_models(acc, c), empirical_intervals(bt, c), total_errors(bt), c)
    sc = fwd.scenarios.pivot_table(index=["business", "target", "period"], columns="scenario", values="value")
    cust = sc.xs("customers", level="target")
    assert (cust["pessimistic"] <= cust["baseline"]).all() and (cust["baseline"] <= cust["optimistic"]).all()
    cac = sc.xs("cac", level="target")
    assert (cac["pessimistic"] >= cac["optimistic"]).all()
    spend = sc.xs("spend", level="target")
    assert (spend["pessimistic"] == spend["optimistic"]).all()  # spend is the plan in every scenario
