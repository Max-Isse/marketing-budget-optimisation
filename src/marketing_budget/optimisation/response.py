"""Steady-state response of each business-channel line to a sustained weekly spend, as draws.

At a constant weekly spend x the adstock equals x, so the weekly incremental customers of line l in draw d are
vmax[d, l] x^s / (x^s + K[d, l]^s), at the planning year's average demand. Built from the fitted MMMs here, and
from the ground truth in validation/ (same class, one draw), so allocations can be scored both ways.

Sales capacity: a business whose sales team can close at most `capacity[b]` customers a week gains nothing from
leads beyond that. Paid customers above the cap are scaled away (pro rata across its lines), so an allocation
that buys unworkable leads is not credited with them. This applies to every allocation, including last year's.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from marketing_budget.forecasting.models import fourier
from marketing_budget.optimisation.mmm import FittedBusiness


@dataclass
class ResponseModel:
    lines: list[tuple[str, str]]  # (business, channel)
    vmax: np.ndarray  # draws x L, weekly customers at saturation
    half_sat: np.ndarray  # draws x L, dollars per week
    shape: np.ndarray  # L
    organic: dict[str, np.ndarray]  # business -> draws, weekly customers without paid media
    value: np.ndarray  # L, 24-month value per incremental customer
    capacity: dict[str, float] = field(default_factory=dict)  # business -> max weekly customers sales can close

    @property
    def businesses(self) -> list[str]:
        return sorted({b for b, _ in self.lines})

    def idx(self, business: str) -> np.ndarray:
        return np.array([i for i, (b, _) in enumerate(self.lines) if b == business])

    def without_capacity(self) -> ResponseModel:
        return replace(self, capacity={})

    def customers(self, x: np.ndarray) -> np.ndarray:
        """draws x L weekly incremental customers the advertising generates (before any capacity limit)."""
        xs = np.power(np.maximum(x, 0.0), self.shape)
        return self.vmax * xs / (xs + self.half_sat**self.shape)

    def marginal(self, x: np.ndarray) -> np.ndarray:
        """draws x L extra weekly customers per extra weekly dollar (before any capacity limit)."""
        x = np.maximum(x, 1e-9)
        s, k = self.shape, self.half_sat
        return self.vmax * s * k**s * x ** (s - 1) / (x**s + k**s) ** 2

    def _capacity_scale(self, inc: np.ndarray) -> np.ndarray:
        scale = np.ones_like(inc)
        for b, cap in self.capacity.items():
            i = self.idx(b)
            room = np.maximum(cap - self.organic[b], 0.0)
            paid = inc[:, i].sum(axis=1)
            scale[:, i] = np.where(paid > room, room / np.maximum(paid, 1e-12), 1.0)[:, None]
        return scale

    def effective_customers(self, x: np.ndarray) -> np.ndarray:
        """draws x L incremental customers the business can actually serve."""
        inc = self.customers(x)
        return inc * self._capacity_scale(inc)

    def effective_marginal(self, x: np.ndarray) -> np.ndarray:
        """draws x L: d(effective customers of the line's business) / d(spend on the line). Zero for a business
        already at capacity."""
        inc, m = self.customers(x), self.marginal(x)
        return m * (self._capacity_scale(inc) >= 1.0)

    def annual_profit(self, x: np.ndarray) -> np.ndarray:
        """draws: 52 weeks of incremental contribution minus spend."""
        return 52 * (self.effective_customers(x) @ self.value - x.sum())

    def profit_gradient(self, x: np.ndarray) -> np.ndarray:
        """draws x L: d annual profit / d weekly spend."""
        inc, m = self.customers(x), self.marginal(x)
        g = m * self.value
        for b, cap in self.capacity.items():
            i = self.idx(b)
            room = np.maximum(cap - self.organic[b], 0.0)
            paid = inc[:, i].sum(axis=1)
            over = paid > room
            if not over.any():
                continue
            # at capacity the business's paid customers are fixed at `room`; spending only reshuffles them
            vsum = (inc[:, i] * self.value[i]).sum(axis=1)
            capped = room[:, None] * m[:, i] * (self.value[i] * paid[:, None] - vsum[:, None]) / paid[:, None] ** 2
            g[:, i] = np.where(over[:, None], capped, g[:, i])
        return 52 * (g - 1)


def from_fits(
    fits: dict[str, FittedBusiness],
    values: dict[str, float],
    capacity: dict[str, float] | None = None,
    use_point: bool = False,
) -> ResponseModel:
    """Planning-year response: organic base averaged over the next 52 weeks (trend and season extrapolated)."""
    lines, vmax_cols, k_cols, organic, value = [], [], [], {}, []
    for biz, fb in fits.items():
        m = fb.model
        n = len(m.d.y)
        t = np.arange(n, n + 52, dtype=float)
        Xf = np.column_stack([np.ones(52), t / 52, fourier(t, m.period, m.k)])
        thetas = [fb.point] if use_point else fb.draws
        params = [m.unpack(th) for th in thetas]
        base = np.array([np.exp(Xf @ p.alpha).mean() for p in params])
        organic[biz] = base
        for j, ch in enumerate(m.d.channels):
            lines.append((biz, ch))
            vmax_cols.append(base * np.array([p.beta[j] for p in params]))
            k_cols.append(np.array([p.half_sat[j] for p in params]))
            value.append(values[biz])
    shape = np.full(len(lines), next(iter(fits.values())).model.shape)
    return ResponseModel(
        lines, np.column_stack(vmax_cols), np.column_stack(k_cols), shape, organic, np.array(value), capacity or {}
    )
