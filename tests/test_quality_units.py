import numpy as np
import pandas as pd
import pytest

from marketing_budget.data.quality import _best_split
from marketing_budget.validation.phase1 import score_retention


def test_best_split_finds_a_level_shift():
    rng = np.random.default_rng(2)
    y = np.concatenate([rng.normal(0, 0.05, 25), rng.normal(-0.35, 0.05, 15)])
    k, p = _best_split(y, 3)
    assert k == 25
    assert p < 1e-6


def test_best_split_on_a_constant_series_is_not_significant():
    _, p = _best_split(np.zeros(20), 3)
    assert p == 1.0


def test_true_value_of_a_crm_source_is_the_mix_of_caused_and_captured_customers():
    params = pd.DataFrame(
        {"business": ["B9", "B9"], "true_source": ["organic", "aff"], "customer_value": [100.0, 60.0]}
    )
    cs = pd.DataFrame(
        {
            "customer_id": [1, 2, 3, 4],
            "business": "B9",
            "source": ["aff", "aff", "aff", "organic"],
            "true_source": ["aff", "aff", "organic", "organic"],
        }
    )
    est = pd.DataFrame(
        {
            "business": "B9",
            "source": ["aff"],
            "n_customers": [3],
            "customer_value": [75.0],
            "value_ci_low": [70.0],
            "value_ci_high": [80.0],
        }
    )
    out = score_retention(est, params, cs, cfg=None)  # type: ignore[arg-type]
    assert out["true_value"].iloc[0] == pytest.approx((60 + 60 + 100) / 3)
    assert out["true_incremental_value"].iloc[0] == 60.0
    assert bool(out["true_in_ci"].iloc[0]) is True
