"""Score phase 1 against the SYNTHETIC ground truth: did the data-quality checks find every injected issue,
and do the estimated customer values match the true values?

The CRM credits each line with some organic customers (last-click capture), so the right benchmark for an
estimate by CRM source is the true value of the customers actually in that source, a mix of incremental and
captured organic customers. That mix is computed here from the truth tables.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from marketing_budget.analysis.retention import ALL
from marketing_budget.config import Config


def load_truth_tables(cfg: Config) -> dict[str, pd.DataFrame]:
    d = cfg.path("raw_dir") / "truth"
    return {p.stem: pd.read_parquet(p) for p in sorted(d.glob("synthetic_truth_*.parquet"))}


def _week(truth: dict[str, Any], i: int) -> pd.Timestamp:
    return pd.Timestamp(truth["calendar"]["first_week"]) + pd.Timedelta(weeks=i)


def injected_issues(truth: dict[str, Any]) -> pd.DataFrame:
    di = truth["data_issues"]
    last = int(truth["calendar"]["n_weeks"]) - 1
    rows = [
        {
            "issue": "tracking_outage",
            "business": o["business"],
            "channel": o["channel"],
            "from": o["from_week"],
            "to": o["to_week"],
        }
        for o in di["tracking_outages"]
    ]
    rows += [
        {
            "issue": "attribution_change",
            "business": s["business"],
            "channel": s["channel"],
            "from": s["from_week"],
            "to": last,
        }
        for s in di["attribution_signal_loss"]
    ]
    rows += [
        {"issue": "duplicate_leads", "business": b, "channel": "all", "from": 0, "to": last}
        for b in di["duplicate_lead_rate"]
    ]
    rows += [
        {
            "issue": "cost_restated",
            "business": c["business"],
            "channel": c["channel"],
            "from": c["week"],
            "to": c["week"],
        }
        for c in di["late_cost_corrections"]
    ]
    out = pd.DataFrame(rows)
    out["first_week"] = [_week(truth, i) for i in out["from"]]
    out["last_week"] = [_week(truth, i) for i in out["to"]]
    return out.drop(columns=["from", "to"])


def score_quality(detected: pd.DataFrame, truth: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (one row per injected issue with what was detected, detected issues matching nothing)."""
    inj = injected_issues(truth)
    det = detected.copy()
    det["first_week"] = pd.to_datetime(det["first_week"])
    det["last_week"] = pd.to_datetime(det["last_week"])
    matched = set()
    rows = []
    for r in inj.to_dict("records"):
        first, last = pd.Timestamp(r["first_week"]), pd.Timestamp(r["last_week"])
        m = det[(det["issue"] == r["issue"]) & (det["business"] == r["business"]) & (det["channel"] == r["channel"])]
        hit = m[(m["first_week"] <= last) & (m["last_week"] >= first)]
        matched |= set(hit.index)
        rows.append(
            {
                "issue": r["issue"],
                "business": r["business"],
                "channel": r["channel"],
                "injected_from": first.date(),
                "injected_to": last.date(),
                "detected": len(hit) > 0,
                "detected_from": hit["first_week"].min().date() if len(hit) else None,
                "detected_to": hit["last_week"].max().date() if len(hit) else None,
                "start_error_weeks": int((hit["first_week"].min() - first).days // 7) if len(hit) else None,
            }
        )
    return pd.DataFrame(rows), det.drop(index=list(matched)).reset_index(drop=True)


def score_retention(
    estimates: pd.DataFrame, line_params: pd.DataFrame, customer_source: pd.DataFrame, cfg: Config
) -> pd.DataFrame:
    """True value of the customers in each CRM source (and in total) vs the estimate and its 95% interval."""
    true_value = line_params.set_index(["business", "true_source"])["customer_value"]
    cs = customer_source.assign(
        true_value=[
            true_value[(b, s)] for b, s in zip(customer_source["business"], customer_source["true_source"], strict=True)
        ]
    )
    by_src = cs.groupby(["business", "source"])["true_value"].mean()
    by_biz = cs.groupby("business")["true_value"].mean()
    out = estimates[["business", "source", "n_customers", "customer_value", "value_ci_low", "value_ci_high"]].copy()
    out["true_value"] = [
        by_biz[b] if s == ALL else by_src[(b, s)] for b, s in zip(out["business"], out["source"], strict=True)
    ]
    out["error_pct"] = out["customer_value"] / out["true_value"] - 1
    out["true_in_ci"] = (out["true_value"] >= out["value_ci_low"]) & (out["true_value"] <= out["value_ci_high"])
    incr = line_params.rename(columns={"true_source": "source", "customer_value": "true_incremental_value"})
    out = out.merge(incr[["business", "source", "true_incremental_value"]], on=["business", "source"], how="left")
    return out
