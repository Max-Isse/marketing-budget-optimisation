"""Load the sealed ground truth and summarise the simulated world at its planned (historical) spend.

This is a design check on the simulation, not an analysis result: it shows what the models in later phases
should recover, and lets tests assert that the world contains the features the brief needs (saturated
channels, over-attributed channels, under-invested channels, cheap low-quality leads).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from marketing_budget.config import PROJECT_ROOT, Config
from marketing_budget.curves import hill, hill_marginal
from marketing_budget.economics import customer_value

GROUND_TRUTH = PROJECT_ROOT / "configs" / "ground_truth_SYNTHETIC.yaml"
WEEKS_PER_YEAR = 52


def load_ground_truth(path: Path | str | None = None) -> dict[str, Any]:
    with Path(path or GROUND_TRUTH).open(encoding="utf-8") as f:
        truth: dict[str, Any] = yaml.safe_load(f)
    for b in truth["businesses"].values():
        s = np.asarray(b["seasonality"], float)
        b["seasonality"] = (s / s.mean()).tolist()  # demand index averages 1 over a year
    return truth


def planned_annual_spend(truth: dict[str, Any]) -> dict[str, float]:
    return {
        f"{biz}.{ch}": float(p["hist_spend"]) * WEEKS_PER_YEAR
        for biz, b in truth["businesses"].items()
        for ch, p in b["channels"].items()
    }


def world_summary(truth: dict[str, Any], cfg: Config) -> pd.DataFrame:
    """One row per line at planned weekly spend, average demand (seasonality 1), no trend or noise.

    Returns are contribution per ad dollar over the valuation horizon: above 1 the spend pays back, below 1
    it destroys value.
    """
    v = cfg.section("valuation")
    rows = []
    for biz, b in truth["businesses"].items():
        cv = customer_value(b["model"], b["economics"], int(v["horizon_months"]), float(v["annual_discount_rate"]))
        close = float(b["qualified_to_customer"])
        organic = float(b["organic_customers_per_week"])
        for ch, p in b["channels"].items():
            x = float(p["hist_spend"])
            per_lead = float(p["lead_to_qualified"]) * close
            leads = float(hill(x, p["vmax_leads"], p["half_sat"], p["shape"]))
            marg_leads = float(hill_marginal(x, p["vmax_leads"], p["half_sat"], p["shape"]))
            customers = leads * per_lead
            value = cv.value * float(p["value_multiplier"])
            attributed = customers + float(p["attribution_capture"]) * organic
            rows.append(
                {
                    "business": biz,
                    "channel": ch,
                    "weekly_spend": x,
                    "incremental_leads": leads,
                    "cost_per_lead": x / leads,
                    "lead_to_customer": per_lead,
                    "incremental_customers": customers,
                    "attributed_customers": attributed,
                    "customer_value": value,
                    "attributed_cac": x / attributed,
                    "incremental_cac": x / customers,
                    "marginal_cac": 1 / (marg_leads * per_lead),
                    "attributed_return": attributed * value / x,
                    "incremental_return": customers * value / x,
                    "marginal_return": marg_leads * per_lead * value,
                    "annual_net_contribution": (customers * value - x) * WEEKS_PER_YEAR,
                }
            )
    return pd.DataFrame(rows)


def business_summary(truth: dict[str, Any], lines: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    v = cfg.section("valuation")
    rows = []
    for biz, b in truth["businesses"].items():
        sub = lines[lines["business"] == biz]
        cv = customer_value(b["model"], b["economics"], int(v["horizon_months"]), float(v["annual_discount_rate"]))
        close = float(b["qualified_to_customer"])
        qualified_paid = float((sub["incremental_customers"] / close).sum())
        qualified_organic = float(b["organic_customers_per_week"]) / close
        cac = float(sub["weekly_spend"].sum() / sub["incremental_customers"].sum())
        rows.append(
            {
                "business": biz,
                "name": b["name"],
                "model": b["model"],
                "customer_value_24m": cv.value,
                "annual_spend": float(sub["weekly_spend"].sum()) * WEEKS_PER_YEAR,
                "incremental_customers_per_week": float(sub["incremental_customers"].sum()),
                "organic_customers_per_week": float(b["organic_customers_per_week"]),
                "qualified_leads_per_week": qualified_paid + qualified_organic,
                "incremental_cac": cac,
                "payback_months": cv.payback_months(cac),
                "annual_net_contribution": float(sub["annual_net_contribution"].sum()),
            }
        )
    return pd.DataFrame(rows)
