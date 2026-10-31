import numpy as np
import pandas as pd
import pytest

from marketing_budget.analysis.retention import ecommerce_repeat, subscription_retention


def test_subscription_retention_counts_censored_customers_correctly():
    # (active months, observable months): churn after month 0; churn at month 3; still active (censored);
    # active in months 0-1 with only those two observable.
    lt = pd.DataFrame({"active_months": [1, 3, 5, 2], "observable_months": [5, 5, 5, 2]})
    est = subscription_retention(lt)
    assert est["survival_first_month"] == pytest.approx(3 / 4)
    # transitions from month 2 on: 0 + 2 + 3 + 0 = 5, churn events: 1
    assert est["transitions_observed"] == 5
    assert est["churn_events"] == 1
    assert est["survival_monthly"] == pytest.approx(0.8)


def test_subscription_retention_recovers_simulated_rates():
    rng = np.random.default_rng(0)
    n = 40_000
    stay1 = rng.random(n) < 0.6
    life = np.where(stay1, 2 + rng.geometric(1 - 0.9, n) - 1, 1)
    m = rng.integers(1, 30, n)
    est = subscription_retention(pd.DataFrame({"active_months": np.minimum(life, m), "observable_months": m}))
    assert est["survival_first_month"] == pytest.approx(0.6, abs=4 * est["survival_first_month_se"])
    assert est["survival_monthly"] == pytest.approx(0.9, abs=4 * est["survival_monthly_se"])


def test_ecommerce_repeat_recovers_rate_and_decay():
    rng = np.random.default_rng(1)
    t = np.arange(0, 30)
    n = np.linspace(50_000, 5_000, len(t)).round()
    lam = np.where(t == 0, 1.0, 0.07 * 0.93 ** np.maximum(t - 1, 0))
    orders = rng.poisson(n * lam)
    est = ecommerce_repeat(pd.DataFrame({"month_index": t, "orders": orders, "customers_observable": n}))
    assert est["repeat_rate_first_month"] == pytest.approx(0.07, rel=0.05)
    assert est["repeat_decay_monthly"] == pytest.approx(0.93, abs=0.005)
