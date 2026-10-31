"""Budget constraints from config, turned into annual dollar bounds per business-channel line, plus a
feasibility check so contradictory policies are caught before any optimisation runs.

Lines are keyed "B1.search_brand". `last_year_spend` is annual spend per line; in the analysis it comes from
the SQL layer, never from the ground truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from marketing_budget.config import Config


@dataclass(frozen=True)
class Bounds:
    lines: pd.DataFrame  # line, business, last_year, min, max (annual dollars)
    business: pd.DataFrame  # business, min, max after combining business and channel limits
    total: float
    problems: list[str]

    @property
    def feasible(self) -> bool:
        return not self.problems


def line_bounds(cfg: Config, last_year_spend: dict[str, float]) -> Bounds:
    b = cfg.section("budget")
    total = float(b["annual_total"])
    default, overrides = b["channel_limits"]["default"], b["channel_limits"].get("overrides", {})
    line_cap = float(b["concentration"]["max_line_share"]) * total
    rows: list[dict[str, Any]] = []
    for line, spend in last_year_spend.items():
        lim = {**default, **overrides.get(line, {})}
        rows.append(
            {
                "line": line,
                "business": line.split(".")[0],
                "last_year": float(spend),
                "min": float(lim["min_multiple"]) * spend,
                "max": min(float(lim["max_multiple"]) * spend, line_cap),
            }
        )
    lines = pd.DataFrame(rows)
    problems = [
        f"{r['line']}: minimum {r['min']:,.0f} exceeds maximum {r['max']:,.0f}" for r in rows if r["min"] > r["max"]
    ]

    biz_cap = float(b["concentration"]["max_business_share"]) * total
    brows = []
    for biz, lim in b["business_limits"].items():
        sub = lines[lines["business"] == biz]
        lo = max(float(lim["min"]), float(sub["min"].sum()))
        hi = min(float(lim["max"]), float(sub["max"].sum()), biz_cap)
        if lo > hi:
            problems.append(f"{biz}: combined minimum {lo:,.0f} exceeds combined maximum {hi:,.0f}")
        brows.append({"business": biz, "min": lo, "max": hi})
    business = pd.DataFrame(brows)
    if business["min"].sum() > total:
        problems.append(f"business minimums sum to {business['min'].sum():,.0f}, above the budget {total:,.0f}")
    if business["max"].sum() < total:
        problems.append(f"business maximums sum to {business['max'].sum():,.0f}, below the budget {total:,.0f}")
    return Bounds(lines, business, total, problems)
