import numpy as np
import pytest

from marketing_budget.economics import customer_value, ecommerce_stream, monthly_discount_factors, subscription_stream


def test_no_churn_no_discount_is_contribution_times_months():
    econ = {"monthly_contribution": 10.0, "survival_first_month": 1.0, "survival_monthly": 1.0, "acquisition_cost": 5}
    assert customer_value("subscription", econ, 12, 0.0).value == pytest.approx(115.0)


def test_first_month_churn_applies_once():
    s = subscription_stream(10.0, 0.5, 0.9, 4)
    assert s == pytest.approx([10.0, 5.0, 4.5, 4.05])


def test_ecommerce_stream_first_order_then_decaying_repeats():
    s = ecommerce_stream(40.0, 0.1, 0.5, 4)
    assert s == pytest.approx([40.0, 4.0, 2.0, 1.0])


def test_discount_month_zero_undiscounted_and_one_year_matches_rate():
    d = monthly_discount_factors(13, 0.10)
    assert d[0] == 1.0
    assert d[12] == pytest.approx(1 / 1.10)


def test_payback_month_and_never():
    econ = {"monthly_contribution": 10.0, "survival_first_month": 1.0, "survival_monthly": 1.0, "acquisition_cost": 0}
    cv = customer_value("subscription", econ, 12, 0.0)
    assert cv.payback_months(30.0) == 2.0  # cumulative 10, 20, 30 -> reached in month index 2
    assert np.isinf(cv.payback_months(1e6))


def test_unknown_model_rejected():
    with pytest.raises(ValueError):
        customer_value("marketplace", {}, 12, 0.1)
