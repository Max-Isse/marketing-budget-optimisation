"""Customer value: discounted contribution per new customer over a fixed horizon, and payback.

Two revenue models:
* subscription - a monthly contribution while the customer stays; survival after the first month differs from
  later months (most churn happens after the first box or the first invoice).
* ecommerce    - one first order, then repeat orders at a monthly rate that decays geometrically.

The value excludes the advertising cost: CAC is set against it separately so the same customer value can be
compared with attributed, incremental and marginal acquisition costs.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def monthly_discount_factors(horizon_months: int, annual_rate: float) -> np.ndarray:
    """Discount factor for months 0..horizon-1, with month 0 (the acquisition month) undiscounted."""
    r = (1 + annual_rate) ** (1 / 12) - 1
    return (1 + r) ** -np.arange(horizon_months, dtype=float)


def subscription_stream(
    monthly_contribution: float, survival_first_month: float, survival_monthly: float, horizon_months: int
) -> np.ndarray:
    """Expected contribution in each month: contribution x probability the customer is still active."""
    alive = np.ones(horizon_months)
    for t in range(1, horizon_months):
        alive[t] = alive[t - 1] * (survival_first_month if t == 1 else survival_monthly)
    return monthly_contribution * alive


def ecommerce_stream(
    order_contribution: float, repeat_rate_first_month: float, repeat_decay_monthly: float, horizon_months: int
) -> np.ndarray:
    """Expected contribution in each month: the first order in month 0, then decaying repeat orders."""
    stream = np.zeros(horizon_months)
    stream[0] = order_contribution
    t = np.arange(1, horizon_months)
    stream[1:] = order_contribution * repeat_rate_first_month * repeat_decay_monthly ** (t - 1)
    return stream


@dataclass(frozen=True)
class CustomerValue:
    stream: np.ndarray  # undiscounted expected contribution per month
    discount: np.ndarray
    acquisition_cost: float

    @property
    def value(self) -> float:
        """Discounted contribution over the horizon, net of one-off acquisition costs (excluding ad spend)."""
        return float(np.sum(self.stream * self.discount) - self.acquisition_cost)

    def payback_months(self, cac: float) -> float:
        """Months until cumulative discounted contribution covers CAC plus acquisition costs; inf if never."""
        cum = np.cumsum(self.stream * self.discount) - self.acquisition_cost
        hit = np.nonzero(cum >= cac)[0]
        return float(hit[0]) if len(hit) else float("inf")


def customer_value(model: str, econ: dict[str, float], horizon_months: int, annual_rate: float) -> CustomerValue:
    if model == "subscription":
        stream = subscription_stream(
            econ["monthly_contribution"], econ["survival_first_month"], econ["survival_monthly"], horizon_months
        )
    elif model == "ecommerce":
        stream = ecommerce_stream(
            econ["order_contribution"], econ["repeat_rate_first_month"], econ["repeat_decay_monthly"], horizon_months
        )
    else:
        raise ValueError(f"unknown revenue model: {model}")
    return CustomerValue(stream, monthly_discount_factors(horizon_months, annual_rate), float(econ["acquisition_cost"]))
