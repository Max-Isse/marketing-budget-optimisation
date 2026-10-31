import numpy as np
import pytest

from marketing_budget.curves import adstock, hill, hill_marginal


def test_adstock_constant_spend_converges_to_spend():
    a = adstock(np.full(200, 1000.0), decay=0.6)
    assert a[-1] == pytest.approx(1000.0, rel=1e-9)


def test_adstock_carries_a_pulse_forward():
    a = adstock(np.array([100.0, 0, 0]), decay=0.5)
    assert a == pytest.approx([50.0, 25.0, 12.5])


def test_adstock_rejects_bad_decay():
    with pytest.raises(ValueError):
        adstock(np.ones(3), decay=1.0)


def test_hill_is_half_of_vmax_at_half_saturation():
    assert float(hill(500.0, vmax=80, half_sat=500, shape=1.3)) == pytest.approx(40.0)


@pytest.mark.parametrize("shape", [0.8, 1.0, 1.7])
def test_hill_marginal_matches_finite_difference(shape):
    x, h = 3000.0, 1e-3
    fd = (hill(x + h, 100, 2000, shape) - hill(x - h, 100, 2000, shape)) / (2 * h)
    assert float(hill_marginal(x, 100, 2000, shape)) == pytest.approx(float(fd), rel=1e-6)


def test_diminishing_returns_beyond_half_saturation():
    m = hill_marginal(np.array([2000.0, 4000.0, 8000.0]), 100, 2000, 1.0)
    assert np.all(np.diff(m) < 0)
