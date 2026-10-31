"""Media response maths shared by the generator and the models: geometric adstock and Hill saturation.

Adstock carries part of each week's advertising effect into later weeks. It is rescaled by (1 - decay) so a
constant weekly spend x has steady-state adstock x, which keeps the half-saturation point in dollars per week.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import lfilter


def adstock(spend: np.ndarray, decay: float) -> np.ndarray:
    """Geometric adstock, normalised so a constant spend x converges to x."""
    if not 0 <= decay < 1:
        raise ValueError("decay must be in [0, 1)")
    x = np.asarray(spend, float)
    return np.asarray(lfilter([1.0], [1.0, -decay], x)) * (1 - decay)  # a_t = x_t + decay * a_(t-1)


def hill(x: np.ndarray | float, vmax: float, half_sat: float, shape: float) -> np.ndarray:
    """Hill saturation: vmax * x^s / (x^s + K^s). Equals vmax / 2 at x = K."""
    x = np.maximum(np.asarray(x, float), 0.0)
    xs = np.power(x, shape)
    return vmax * xs / (xs + half_sat**shape)


def hill_marginal(x: np.ndarray | float, vmax: float, half_sat: float, shape: float) -> np.ndarray:
    """Derivative of `hill` with respect to x: extra response per extra dollar at spend level x."""
    x = np.maximum(np.asarray(x, float), 1e-12)
    ks = half_sat**shape
    xs = np.power(x, shape)
    return vmax * shape * ks * np.power(x, shape - 1) / (xs + ks) ** 2
