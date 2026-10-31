"""The fact sheet: every number the commentary may use, with an ID, its evidence type and its source.

Period facts come from `kpi_windows` (sql/08): the latest four weeks against the previous four and the same four
weeks a year earlier. Each carries:
* `quantities`: the exact numbers a sentence citing it may quote, by kind (money, percent, count, ratio);
* `evidence`: actual (recorded), attribution (an accounting rule: CRM last click, platform report), causal (a
  randomised test) or model (fitted on history). Only causal facts may support causal wording;
* `unusual`: the 4-week change is at least `unusual_z` robust standard deviations from that series' typical
  4-week change (median and MAD of its own history), a statistical flag, not the model's opinion;
* `dq_note`: any data-quality flag inside the period.

Evidence facts come from the validated phase 3 and 4 outputs (experiment effects and the recommended plan).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from marketing_budget.config import Config
from marketing_budget.dashboard.extracts import BUSINESS_NAMES
from marketing_budget.data.db import query_df
from marketing_budget.experiments.results import CHANNEL_NAMES

# metric -> (label, kind of quantity, evidence type)
METRICS: dict[str, tuple[str, str, str]] = {
    "spend": ("ad spend", "money", "actual"),
    "customers": ("new customers", "count", "actual"),
    "blended_cac": ("blended CAC (spend per new customer, all sources)", "money", "actual"),
    "qualified_rate": ("share of leads that qualify", "percent", "actual"),
    "revenue": ("revenue from all active customers", "money", "actual"),
    "contribution_profit": ("contribution profit after ad spend", "money", "actual"),
    "last_click_customers": ("customers credited by CRM last click", "count", "attribution"),
    "last_click_cac": ("last-click CAC", "money", "attribution"),
    "platform_crm_ratio": ("platform-reported conversions per CRM last-click customer", "ratio", "attribution"),
}
# which data-quality flags can distort which metric
DQ_FLAGS: dict[str, list[tuple[str, str]]] = {
    "spend": [("restated_weeks", "spend restated after first report")],
    "blended_cac": [("restated_weeks", "spend restated after first report")],
    "contribution_profit": [("restated_weeks", "spend restated after first report")],
    "last_click_cac": [("restated_weeks", "spend restated after first report")],
    "platform_crm_ratio": [
        ("outage_weeks", "platform tracking outage"),
        ("attribution_weeks", "platform tracking change in effect"),
    ],
}
BUSINESS_METRICS = ["spend", "customers", "blended_cac", "qualified_rate", "revenue", "contribution_profit"]
LINE_METRICS = ["spend", "last_click_customers", "last_click_cac", "platform_crm_ratio"]


@dataclass
class Fact:
    fact_id: str
    scope: str
    metric: str
    metric_label: str
    evidence: str
    period: str
    current: float | None = None
    previous: float | None = None
    last_year: float | None = None
    change_vs_previous: float | None = None  # relative, e.g. 0.123 = +12.3%
    change_vs_last_year: float | None = None
    robust_z: float | None = None
    unusual: bool = False
    dq_note: str | None = None
    statement: str | None = None  # evidence facts: the validated finding, in words
    source: str = ""
    quantities: dict[str, list[float]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


def _ratio(num: float, den: float) -> float | None:
    return float(num / den) if den else None


def _metric_series(df: pd.DataFrame, metric: str) -> pd.Series:
    d = df
    if metric in ("spend", "customers", "revenue", "contribution_profit"):
        return d[metric].astype(float)
    if metric == "last_click_customers":
        return d["customers"].astype(float)
    if metric in ("blended_cac", "last_click_cac"):
        return d["spend"] / d["customers"].replace(0, np.nan)
    if metric == "qualified_rate":
        return d["qualified_leads"] / d["leads"].replace(0, np.nan)
    if metric == "platform_crm_ratio":
        return d["platform_conversions"] / d["customers"].replace(0, np.nan)
    raise KeyError(metric)


def _quantities(kind: str, values: list[float | None], changes: list[float | None]) -> dict[str, list[float]]:
    q: dict[str, list[float]] = {kind: [float(v) for v in values if v is not None and np.isfinite(v)]}
    q.setdefault("percent", [])
    q["percent"] += [abs(100 * c) for c in changes if c is not None and np.isfinite(c)]
    if kind == "percent":
        q["percent"] += [100 * float(v) for v in values if v is not None and np.isfinite(v)]
    return q


def _with_z(q: dict[str, list[float]], z: float | None) -> dict[str, list[float]]:
    """The robust z-score may be quoted too ("about 3.5 times its typical swing"): add it to the counts."""
    if z is not None:
        q.setdefault("count", []).append(round(abs(z), 1))
    return q


def period_facts(con: duckdb.DuckDBPyConnection, cfg: Config) -> tuple[list[Fact], dict[str, str]]:
    ai = cfg.section("ai_reporting")
    zcut = float(ai["unusual_z"])
    kw = query_df(con, "SELECT * FROM kpi_windows ORDER BY scope_type, business, channel, week_start")
    kw["week_start"] = pd.to_datetime(kw["week_start"])
    end = kw["week_start"].max()
    periods = {
        "current": f"the 4 weeks from {end - pd.Timedelta(weeks=3):%d %b %Y} to {end + pd.Timedelta(days=6):%d %b %Y}",
        "previous": "the previous 4 weeks",
        "last_year": "the same 4 weeks a year earlier",
    }
    facts: list[Fact] = []
    for (stype, biz, ch), g in kw.groupby(["scope_type", "business", "channel"], dropna=False):
        g = g.reset_index(drop=True)
        g = g[g["weeks_in_window"] == 4].reset_index(drop=True)
        if len(g) < 60:
            continue
        line = stype == "line"
        scope = f"{biz} {CHANNEL_NAMES.get(str(ch), str(ch))}" if line else f"{biz} {BUSINESS_NAMES[str(biz)]}"
        code = f"{biz}.{ch}" if line else str(biz)
        cur, prev, ly = len(g) - 1, len(g) - 5, len(g) - 53
        for metric in LINE_METRICS if line else BUSINESS_METRICS:
            label, kind, evidence = METRICS[metric]
            s = _metric_series(g, metric)
            v, p, y = (float(s.iloc[i]) if pd.notna(s.iloc[i]) else None for i in (cur, prev, ly))
            chg_p = (v / p - 1) if v is not None and p else None
            chg_y = (v / y - 1) if v is not None and y else None
            hist = (s / s.shift(4) - 1).iloc[8:cur].replace([np.inf, -np.inf], np.nan).dropna()
            z = None
            if chg_p is not None and len(hist) > 20:
                mad = float(np.median(np.abs(hist - hist.median()))) * 1.4826
                z = float((chg_p - hist.median()) / mad) if mad > 0 else None
            notes = [
                f"{text} in {int(g[col].to_numpy()[cur])} of the 4 weeks"
                for col, text in DQ_FLAGS.get(metric, [])
                if int(g[col].to_numpy()[cur]) > 0
            ]
            facts.append(
                Fact(
                    fact_id=f"{code}.{metric}",
                    scope=scope,
                    metric=metric,
                    metric_label=label,
                    evidence=evidence,
                    period=periods["current"],
                    current=v,
                    previous=p,
                    last_year=y,
                    change_vs_previous=chg_p,
                    change_vs_last_year=chg_y,
                    robust_z=z,
                    unusual=z is not None and abs(z) >= zcut,
                    dq_note="; ".join(notes) or None,
                    source="kpi_windows (sql/08_kpi_windows.sql)",
                    quantities=_with_z(_quantities(kind, [v, p, y], [chg_p, chg_y]), z),
                )
            )
    return facts, periods


def evidence_facts(cfg: Config) -> list[Fact]:
    """Validated findings from earlier phases that the commentary may cite as context."""
    t = cfg.path("tables_dir")
    out: list[Fact] = []
    ef = pd.read_csv(t / "experiment_effects.csv")
    dec: dict[Any, dict[Any, Any]] = (
        pd.read_csv(t / "experiment_decisions.csv").set_index("experiment").to_dict("index")
    )
    for r in ef.drop_duplicates("experiment").to_dict("records"):
        e = str(r["experiment"])
        d = dec.get(e)
        q: dict[str, list[float]] = {
            "percent": [abs(100 * float(r[k])) for k in ("relative_effect", "ci_low", "ci_high")]
        }
        stmt = (
            f"Randomised test '{e}': {r['metric']} changed by {100 * r['relative_effect']:+.1f}% "
            f"(95% range {100 * r['ci_low']:+.1f}% to {100 * r['ci_high']:+.1f}%)."
        )
        if d is not None:
            q["money"] = [abs(float(d[k])) for k in ("estimate", "low", "high")]
            stmt += (
                f" Rolling it out ('{d['decision']}') is worth ${d['estimate'] / 1e3:,.0f}k a year "
                f"(${d['low'] / 1e3:,.0f}k to ${d['high'] / 1e3:,.0f}k): {d['verdict']}."
            )
        out.append(
            Fact(
                fact_id=f"EXP.{e}",
                scope="experiment",
                metric="experiment_effect",
                metric_label=str(r["metric"]),
                evidence="causal",
                period="phase 3 test window",
                statement=stmt,
                source="reports/tables/experiment_effects.csv, experiment_decisions.csv",
                quantities=q,
            )
        )
    ev: dict[Any, dict[Any, Any]] = (
        pd.read_csv(t / "allocation_evaluation.csv").set_index("allocation").to_dict("index")
    )
    gain = float(ev["recommended"]["expected_profit"]) - float(ev["status_quo"]["expected_profit"])
    down = float(ev["recommended"]["downside_profit"]) - float(ev["status_quo"]["downside_profit"])
    out.append(
        Fact(
            fact_id="PLAN.recommended",
            scope="budget plan",
            metric="plan_gain",
            metric_label="expected annual gain of the recommended budget split",
            evidence="model",
            period="next 12 months",
            statement=(
                f"The recommended budget split is expected to add ${gain / 1e3:,.0f}k a year over last "
                f"year's split (pessimistic case ${down / 1e3:,.0f}k), by the calibrated model."
            ),
            source="reports/tables/allocation_evaluation.csv",
            quantities={"money": [gain, down]},
        )
    )
    return out


def fact_table(facts: list[Fact]) -> pd.DataFrame:
    """Every field of every fact, empty where it does not apply (stable columns for the appendix and CSV)."""
    return pd.DataFrame([asdict(f) for f in facts], columns=[*Fact.__dataclass_fields__]).drop(columns=["quantities"])
