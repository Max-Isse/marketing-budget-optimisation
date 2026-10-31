"""Generate the SYNTHETIC company from the sealed ground truth.

Two kinds of output:
* observable tables (`data/raw/synthetic_*.parquet`): what a real company would have. Ad-platform reports, a
  CRM with last-click sources, B2 lead records and customer activity. The data problems in
  `data_issues` are injected here.
* truth tables (`data/raw/truth/synthetic_truth_*.parquet`): what caused each lead and customer. Only the
  validation package may read them.

The key point: a CRM credits a line with every lead it touched last, including people who would have arrived
anyway (`attribution_capture`). Separating those from the leads the advertising caused is what later phases
must do from the observable tables alone.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from marketing_budget.config import Config
from marketing_budget.curves import adstock, hill
from marketing_budget.economics import DAYS_PER_MONTH, customer_value

log = logging.getLogger(__name__)

ORGANIC = "organic"


@dataclass
class Generated:
    observable: dict[str, pd.DataFrame]
    truth: dict[str, pd.DataFrame]


def _nb(rng: np.random.Generator, mean: np.ndarray, size: float) -> np.ndarray:
    """Negative-binomial counts with the given mean (variance mean + mean^2 / size)."""
    mean = np.maximum(np.asarray(mean, float), 0.0)
    return rng.negative_binomial(size, size / (size + mean + 1e-12))


def _lognormal_unit(rng: np.random.Generator, sd: float, n: int) -> np.ndarray:
    """Multiplicative noise with mean exactly 1."""
    return np.exp(rng.normal(-(sd**2) / 2, sd, n))


def _month_of(weeks: pd.DatetimeIndex) -> np.ndarray:
    return np.asarray((weeks + pd.Timedelta(days=3)).month) - 1  # month of the mid-week Thursday


def _solve_multiplier(model: str, econ: dict[str, float], target: float, horizon: int, rate: float) -> dict[str, float]:
    """Lower the retention parameter until customer value equals `target` x the base value (bisection).

    Subscriptions scale both survival rates (B2) or first-month survival (when the two differ, B1); e-commerce
    scales the repeat rate. Affiliate and low-quality customers churn faster, not pay less.
    """
    if target == 1.0:
        return dict(econ)
    base = customer_value(model, econ, horizon, rate).value
    if model == "ecommerce":
        keys = ["repeat_rate_first_month"]
    elif econ["survival_first_month"] == econ["survival_monthly"]:
        keys = ["survival_first_month", "survival_monthly"]
    else:
        keys = ["survival_first_month"]
    lo, hi = 0.0, 1.0
    for _ in range(80):
        mid = (lo + hi) / 2
        trial = {**econ, **{k: econ[k] * mid for k in keys}}
        if customer_value(model, trial, horizon, rate).value < target * base:
            lo = mid
        else:
            hi = mid
    return {**econ, **{k: econ[k] * (lo + hi) / 2 for k in keys}}


def _issue_weeks(issues: list[dict[str, Any]], biz: str, ch: str) -> list[tuple[int, int]]:
    return [(i["from_week"], i["to_week"]) for i in issues if i["business"] == biz and i["channel"] == ch]


def generate(truth: dict[str, Any], cfg: Config) -> Generated:
    rng = np.random.default_rng(cfg.seed)
    cal, noise, pol, issues = truth["calendar"], truth["noise"], truth["historical_spend_policy"], truth["data_issues"]
    v = cfg.section("valuation")
    horizon, rate = int(v["horizon_months"]), float(v["annual_discount_rate"])
    n = int(cal["n_weeks"])
    weeks = pd.date_range(pd.Timestamp(cal["first_week"]), periods=n, freq="7D")
    end_date = weeks[-1] + pd.Timedelta(days=7)
    t = np.arange(n)
    month = _month_of(weeks)
    size = float(noise["count_dispersion"])

    media, crm, truth_weekly, b2_leads_parts = [], [], [], []
    cust_parts: list[pd.DataFrame] = []
    line_params = []

    for biz, b in truth["businesses"].items():
        season = np.asarray(b["seasonality"], float)[month]
        demand = season * (1 + b["trend_per_year"]) ** (t / 52) * _lognormal_unit(rng, noise["demand_week_sd"], n)
        follow = season ** pol["seasonality_follow"]
        follow /= follow.mean()
        close = float(b["qualified_to_customer"])
        q_org = float(b["organic_lead_to_qualified"])

        # Organic leads arrive regardless of advertising; each paid line's CRM source captures a share of them.
        org_leads = _nb(rng, b["organic_customers_per_week"] * demand / (q_org * close), size)
        chans = list(b["channels"])
        capture = np.array([b["channels"][c]["attribution_capture"] for c in chans])
        shares = np.append(capture, 1 - capture.sum())
        captured = np.stack([rng.multinomial(k, shares) for k in org_leads])  # weeks x (lines + organic)
        cap_qual = rng.binomial(captured, q_org)
        cap_cust = rng.binomial(cap_qual, close)

        # Leads by CRM source, by true source: [week, source line or organic]
        groups: list[tuple[str, str, np.ndarray, np.ndarray, np.ndarray]] = []  # (crm_source, true_source, ...)
        for j, ch in enumerate(chans):
            p = b["channels"][ch]
            shift = np.ones(n)
            for s in pol["budget_shifts"]:
                if s["business"] == biz and s["channel"] == ch:
                    shift[s["from_week"] : s["to_week"] + 1] = s["multiplier"]
            spend = np.round(p["hist_spend"] * follow * _lognormal_unit(rng, pol["weekly_noise_sd"], n) * shift, 2)
            first_reported = spend.copy()
            for r in issues["late_cost_corrections"]:
                if r["business"] == biz and r["channel"] == ch:
                    first_reported[r["week"]] = np.round(spend[r["week"]] / r["multiplier"], 2)

            ad = adstock(spend, p["decay"])
            exp_leads = demand * hill(ad, p["vmax_leads"], p["half_sat"], p["shape"])
            leads = _nb(rng, exp_leads, size)
            qual = rng.binomial(leads, p["lead_to_qualified"])
            cust = rng.binomial(qual, close)

            cpc = (
                p["cpc"]
                * (spend / p["hist_spend"]) ** noise["cpc_spend_elasticity"]
                * _lognormal_unit(rng, noise["cpc_week_sd"], n)
            )
            clicks = rng.poisson(spend / cpc)
            impressions = rng.poisson(clicks / p["ctr"])

            # Platform-reported conversions: what the CRM credits by last click, plus view-through and multi-touch
            # over-claim, minus tracking failures.
            last_click = cust + cap_cust[:, j]
            platform = last_click + rng.poisson((p["platform_overclaim"] - 1) * last_click)
            for s in issues["attribution_signal_loss"]:
                if s["business"] == biz and s["channel"] == ch:
                    platform[s["from_week"] :] = rng.binomial(platform[s["from_week"] :], s["retained_share"])
            for lo, hi in _issue_weeks(issues["tracking_outages"], biz, ch):
                platform[lo : hi + 1] = 0

            media.append(
                pd.DataFrame(
                    {
                        "week_start": weeks,
                        "business": biz,
                        "channel": ch,
                        "spend": spend,
                        "spend_first_reported": first_reported,
                        "impressions": impressions,
                        "clicks": clicks,
                        "platform_conversions": platform,
                    }
                )
            )
            truth_weekly.append(
                pd.DataFrame(
                    {
                        "week_start": weeks,
                        "business": biz,
                        "channel": ch,
                        "demand_index": demand,
                        "spend": spend,
                        "adstock": ad,
                        "expected_incremental_leads": exp_leads,
                        "incremental_leads": leads,
                        "incremental_qualified": qual,
                        "incremental_customers": cust,
                        "captured_organic_leads": captured[:, j],
                        "captured_organic_customers": cap_cust[:, j],
                    }
                )
            )
            groups.append((ch, ch, leads, qual, cust))
            groups.append((ch, ORGANIC, captured[:, j], cap_qual[:, j], cap_cust[:, j]))
        groups.append((ORGANIC, ORGANIC, captured[:, -1], cap_qual[:, -1], cap_cust[:, -1]))

        # CRM weekly counts by (last-click) source; B2 leads are recorded one row per lead (with duplicates).
        by_source: dict[str, list[np.ndarray]] = {}
        for src, _, lv, qv, cv in groups:
            acc = by_source.setdefault(src, [np.zeros(n, int), np.zeros(n, int), np.zeros(n, int)])
            acc[0] += lv
            acc[1] += qv
            acc[2] += cv
        for src, (lv, qv, cv) in by_source.items():
            crm.append(
                pd.DataFrame(
                    {
                        "week_start": weeks,
                        "business": biz,
                        "source": src,
                        "leads": lv,
                        "qualified_leads": qv,
                        "customers": cv,
                    }
                )
            )
        if biz in issues["duplicate_lead_rate"]:
            b2_leads_parts.append(_lead_records(rng, biz, weeks, by_source, issues["duplicate_lead_rate"][biz]))

        # Customers: one row per new customer, with CRM source and (truth only) true source.
        econ = b["economics"]
        params = {ORGANIC: dict(econ)}
        for ch in chans:
            params[ch] = _solve_multiplier(
                b["model"], econ, float(b["channels"][ch]["value_multiplier"]), horizon, rate
            )
        for src_true, pr in params.items():
            line_params.append(
                {
                    "business": biz,
                    "true_source": src_true,
                    **{k: pr[k] for k in pr if k != "order_value_sd"},
                    "customer_value": customer_value(b["model"], pr, horizon, rate).value,
                }
            )
        for src, true_src, _, _, cv in groups:
            if cv.sum() == 0:
                continue
            wk = np.repeat(np.arange(n), cv)
            days = rng.integers(0, 7, len(wk))
            cust_parts.append(
                pd.DataFrame(
                    {
                        "business": biz,
                        "acquisition_date": weeks[wk] + pd.to_timedelta(days, unit="D"),
                        "source": src,
                        "true_source": true_src,
                    }
                )
            )

    customers = pd.concat(cust_parts, ignore_index=True)
    customers = customers.sort_values(["acquisition_date", "business", "source"], kind="stable", ignore_index=True)
    customers.insert(0, "customer_id", np.arange(1, len(customers) + 1))
    acq_cost = {biz: float(b["economics"]["acquisition_cost"]) for biz, b in truth["businesses"].items()}
    customers["acquisition_cost"] = customers["business"].map(acq_cost)
    params_df = pd.DataFrame(line_params)
    activity = _activity(rng, customers, truth, params_df, end_date)

    observable = {
        "synthetic_weekly_media": pd.concat(media, ignore_index=True),
        "synthetic_weekly_crm": pd.concat(crm, ignore_index=True),
        "synthetic_b2_leads": pd.concat(b2_leads_parts, ignore_index=True),
        "synthetic_customers": customers.drop(columns="true_source"),
        "synthetic_customer_activity": activity,
        "synthetic_data_meta": pd.DataFrame(
            {"first_week": [weeks[0]], "n_weeks": [n], "data_end_date": [end_date], "seed": [cfg.seed]}
        ),
    }
    truth_tables = {
        "synthetic_truth_weekly": pd.concat(truth_weekly, ignore_index=True),
        "synthetic_truth_customer_source": customers[["customer_id", "business", "source", "true_source"]],
        "synthetic_truth_line_params": params_df,
    }
    return Generated(observable, truth_tables)


def _lead_records(
    rng: np.random.Generator, biz: str, weeks: pd.DatetimeIndex, by_source: dict[str, list[np.ndarray]], dup_rate: float
) -> pd.DataFrame:
    """One row per CRM lead. Qualified and won flags match the weekly counts exactly; duplicates are re-submitted
    forms from the same company (same e-mail domain) 0-10 days later, never qualified."""
    parts = []
    for src, (lv, qv, cv) in by_source.items():
        for w in np.nonzero(lv)[0]:
            k = int(lv[w])
            flags = np.zeros(k, bool)
            won = np.zeros(k, bool)
            qi = rng.choice(k, int(qv[w]), replace=False)
            flags[qi] = True
            won[rng.choice(qi, int(cv[w]), replace=False)] = True
            parts.append(
                pd.DataFrame(
                    {
                        "created_date": weeks[int(w)] + pd.to_timedelta(rng.integers(0, 7, k), unit="D"),
                        "source": src,
                        "is_qualified": flags,
                        "is_won": won,
                    }
                )
            )
    leads = pd.concat(parts, ignore_index=True)
    leads["email_domain"] = [f"firm{i:06d}.example" for i in rng.permutation(len(leads))]
    dup = leads.sample(frac=dup_rate, random_state=int(rng.integers(1 << 31))).copy()
    dup["created_date"] = dup["created_date"] + pd.to_timedelta(rng.integers(0, 11, len(dup)), unit="D")
    dup[["is_qualified", "is_won"]] = False
    leads = pd.concat([leads, dup], ignore_index=True)
    leads = leads[leads["created_date"] < weeks[-1] + pd.Timedelta(days=7)]
    leads = leads.sort_values(["created_date", "email_domain"], ignore_index=True)
    leads.insert(0, "lead_id", np.arange(1, len(leads) + 1))
    leads.insert(1, "business", biz)
    return leads


def _activity(
    rng: np.random.Generator,
    customers: pd.DataFrame,
    truth: dict[str, Any],
    params: pd.DataFrame,
    end_date: pd.Timestamp,
) -> pd.DataFrame:
    """Monthly activity per customer up to the end of the data (later months are not yet observed)."""
    days_left = (end_date - customers["acquisition_date"]).dt.days.to_numpy()
    observable = np.floor((days_left - 1) / DAYS_PER_MONTH).astype(int) + 1  # months 0..observable-1 seen
    out = []
    pmap: dict[tuple[str, str], dict[str, Any]] = {}
    for r in params.to_dict("records"):
        pmap[(str(r["business"]), str(r["true_source"]))] = {str(k): val for k, val in r.items()}
    keys = (customers["business"].astype(str) + "|" + customers["true_source"].astype(str)).to_numpy()
    for key in sorted(set(keys)):
        biz, src = key.split("|")
        idx = np.nonzero(keys == key)[0]
        b = truth["businesses"][biz]
        pr = pmap[(biz, src)]
        ids = customers["customer_id"].to_numpy()[idx]
        m_obs = observable[idx]
        econ = b["economics"]
        if b["model"] == "subscription":
            stay1 = rng.random(len(ids)) < pr["survival_first_month"]
            later = rng.geometric(1 - pr["survival_monthly"], len(ids)) - 1  # months survived after month 1
            life = np.where(stay1, 2 + later, 1)
            seen = np.minimum(life, m_obs)
            cid = np.repeat(ids, seen)
            mi = np.concatenate([np.arange(k) for k in seen])
            orders = np.ones(len(cid), int)
            revenue = np.full(len(cid), econ["monthly_revenue"])
            contribution = np.full(len(cid), econ["monthly_contribution"])
        else:
            cid_all = np.repeat(ids, m_obs)
            mi_all = np.concatenate([np.arange(k) for k in m_obs])
            lam = np.where(
                mi_all == 0,
                1.0,
                pr["repeat_rate_first_month"] * pr["repeat_decay_monthly"] ** np.maximum(mi_all - 1, 0),
            )
            orders_all = np.where(mi_all == 0, 1, rng.poisson(lam))
            keep = orders_all > 0
            cid, mi, orders = cid_all[keep], mi_all[keep], orders_all[keep]
            value = econ["order_revenue"] * _lognormal_unit(rng, econ["order_value_sd"], len(cid))
            revenue = np.round(orders * value, 2)
            contribution = np.round(revenue * econ["order_contribution"] / econ["order_revenue"], 2)
        out.append(
            pd.DataFrame(
                {
                    "customer_id": cid,
                    "month_index": mi,
                    "orders": orders,
                    "revenue": revenue,
                    "contribution": contribution,
                }
            )
        )
    return pd.concat(out, ignore_index=True).sort_values(["customer_id", "month_index"], ignore_index=True)


def write_generated(gen: Generated, cfg: Config) -> dict[str, Path]:
    raw = cfg.path("raw_dir")
    (raw / "truth").mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, df in gen.observable.items():
        paths[name] = raw / f"{name}.parquet"
        df.to_parquet(paths[name], index=False)
    for name, df in gen.truth.items():
        paths[name] = raw / "truth" / f"{name}.parquet"
        df.to_parquet(paths[name], index=False)
    for name, df in {**gen.observable, **gen.truth}.items():
        log.info("%s: %s rows", name, f"{len(df):,}")
    return paths
