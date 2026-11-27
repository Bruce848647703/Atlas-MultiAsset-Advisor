"""Goal-based glide path and multi-objective projection.

The optimizer answers "what is the best allocation today?". This module answers
the follow-up: "how should that allocation de-risk as the goal approaches, and
what contribution is needed to stay on track?".

It is deliberately transparent (no hidden optimiser):

* start from the plan's current class weights;
* linearly de-risk risky assets to a terminal risky share (default 35%);
* project wealth with each year's expected class return and monthly
  contributions;
* if a target value is provided, compute target progress, the required monthly
  contribution at the projected return, and the required annual return at the
  current contribution.

Everything is deterministic and JSON-serialisable. It is a planning aid, not a
guarantee or investment advice.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

RISKY_CLASSES = ("equity_cn", "equity_global", "crypto", "futures", "commodity")
DEFENSIVE_CLASSES = ("cash", "fixed_income", "hybrid")
CLASS_ORDER = ("cash", "fixed_income", "hybrid", "commodity",
               "equity_cn", "equity_global", "crypto", "futures")
MAX_YEARS = 40
DEFAULT_TERMINAL_RISKY = 0.35


def _class_weights(plan) -> Dict[str, float]:
    cls_of = {a.id: a.asset_class for a in plan.assets}
    weights: Dict[str, float] = {c: 0.0 for c in CLASS_ORDER}
    for aid, w in plan.weights.items():
        cls = cls_of.get(aid)
        if cls:
            weights[cls] = weights.get(cls, 0.0) + float(w)
    total = sum(weights.values())
    if total <= 1e-12:
        raise ValueError("plan has no positive weights")
    return {c: w / total for c, w in weights.items()}


def _class_expected_returns(plan) -> Dict[str, float]:
    cls_of = {a.id: a.asset_class for a in plan.assets}
    weighted: Dict[str, float] = {}
    mass: Dict[str, float] = {}
    for aid, w in plan.weights.items():
        cls = cls_of.get(aid)
        if cls is None:
            continue
        w = float(w)
        weighted[cls] = weighted.get(cls, 0.0) + w * float(plan.mu_ann.get(aid, 0.0))
        mass[cls] = mass.get(cls, 0.0) + w
    neutral = float(plan.expected.get("ann_return", 0.0))
    out: Dict[str, float] = {}
    for cls in CLASS_ORDER:
        if mass.get(cls, 0.0) > 1e-12:
            out[cls] = weighted[cls] / mass[cls]
        else:
            # No current exposure: use the average estimate for that class
            # rather than pretending a new defensive sleeve earns the plan's
            # overall (riskier) expected return.
            vals = [float(plan.mu_ann.get(a.id, 0.0)) for a in plan.assets
                    if a.asset_class == cls]
            out[cls] = float(np.mean(vals)) if vals else neutral
    return out


def _normalise_with_caps(weights: Dict[str, float],
                         caps: Dict[str, float]) -> Dict[str, float]:
    out = {c: max(0.0, float(weights.get(c, 0.0))) for c in CLASS_ORDER}
    for c in CLASS_ORDER:
        cap = float(caps.get(c, 1.0))
        if cap > 0:
            out[c] = min(out[c], cap)
    total = sum(out.values())
    if total > 1.0 + 1e-9:
        return {c: w / total for c, w in out.items()}
    deficit = 1.0 - total
    if deficit > 1e-9:
        for c in DEFENSIVE_CLASSES + CLASS_ORDER:
            cap = float(caps.get(c, 1.0))
            room = max(0.0, cap - out[c])
            take = min(room, deficit)
            out[c] += take
            deficit -= take
            if deficit <= 1e-9:
                break
    if deficit > 1e-9:
        out["cash"] += deficit
    total = sum(out.values())
    return {c: w / total for c, w in out.items()}


def _fill_defensive(need: float, caps: Dict[str, float]) -> Dict[str, float]:
    """Allocate a defensive sleeve without exceeding class caps."""
    out = {c: 0.0 for c in DEFENSIVE_CLASSES}
    remaining = max(0.0, float(need))
    # Prefer fixed income and cash, then hybrid, each up to its cap.
    for cls in ("fixed_income", "cash", "hybrid"):
        room = max(0.0, float(caps.get(cls, 0.0)) - out[cls])
        take = min(room, remaining)
        out[cls] += take
        remaining -= take
    if remaining > 1e-9:
        # Caps cannot absorb the residual (unusual); park it in cash.
        out["cash"] += remaining
    return out


def _terminal_weights(current: Dict[str, float], caps: Dict[str, float],
                      terminal_risky: float) -> Dict[str, float]:
    risky_now = sum(current.get(c, 0.0) for c in RISKY_CLASSES)
    target_risky = min(risky_now, max(0.0, float(terminal_risky)))
    out: Dict[str, float] = {c: 0.0 for c in CLASS_ORDER}

    if risky_now > 1e-12:
        scale = target_risky / risky_now
        for c in RISKY_CLASSES:
            out[c] = current.get(c, 0.0) * scale
    else:
        target_risky = 0.0

    defensive_now = sum(current.get(c, 0.0) for c in DEFENSIVE_CLASSES)
    defensive_need = max(0.0, 1.0 - target_risky)
    if defensive_now > 1e-12:
        scale_d = defensive_need / defensive_now
        for c in DEFENSIVE_CLASSES:
            out[c] = current.get(c, 0.0) * scale_d
    else:
        out.update(_fill_defensive(defensive_need, caps))

    return _normalise_with_caps(out, caps)


def _blend(a: Dict[str, float], b: Dict[str, float], t: float) -> Dict[str, float]:
    out = {c: (1.0 - t) * a.get(c, 0.0) + t * b.get(c, 0.0) for c in CLASS_ORDER}
    total = sum(out.values())
    if total > 1e-12:
        out = {c: w / total for c, w in out.items()}
    return out


def _project(start: float, monthly: float, returns: List[float],
             contributions: bool = True) -> List[Dict[str, float]]:
    rows = [{"year": 0, "value": float(start), "principal": float(start)}]
    value = float(start)
    n_months = 0
    for year, ann in enumerate(returns, 1):
        rm = (1.0 + float(ann)) ** (1.0 / 12.0) - 1.0
        for _ in range(12):
            value = value * (1.0 + rm) + (float(monthly) if contributions else 0.0)
            n_months += 1
        rows.append({
            "year": year,
            "value": value,
            "principal": start + (float(monthly) if contributions else 0.0) * n_months,
        })
    return rows


def _required_monthly(start: float, target: float, annual_return: float,
                      years: int) -> float:
    n = int(years) * 12
    rm = (1.0 + float(annual_return)) ** (1.0 / 12.0) - 1.0
    fv_pv = float(start) * (1.0 + rm) ** n
    need = max(0.0, float(target) - fv_pv)
    if need <= 1e-9:
        return 0.0
    if abs(rm) < 1e-12:
        return need / max(n, 1)
    annuity = ((1.0 + rm) ** n - 1.0) / rm
    return need / max(annuity, 1e-12)


def _required_annual_return(start: float, monthly: float, target: float,
                            years: int) -> Optional[float]:
    if target <= start:
        return 0.0
    lo, hi = -0.5, 1.0
    def fv(r: float) -> float:
        return _project(start, monthly, [r] * int(years))[-1]["value"]
    if fv(hi) < target:
        return None
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if fv(mid) >= target:
            hi = mid
        else:
            lo = mid
    return float(hi)


def build(plan, *, target_value: float = 0.0,
          years: Optional[int] = None,
          monthly_contrib: Optional[float] = None,
          terminal_risky: float = DEFAULT_TERMINAL_RISKY) -> Dict[str, Any]:
    """Build a de-risking schedule and goal projection for a plan."""
    years = int(years if years is not None else plan.profile.horizon_years)
    years = max(1, min(MAX_YEARS, years))
    monthly = float(plan.monthly_contrib if monthly_contrib is None
                    else monthly_contrib)
    target = float(target_value or 0.0)
    if not np.isfinite(monthly) or monthly < 0:
        raise ValueError("monthly_contrib must be a finite non-negative number")
    if not np.isfinite(target) or target < 0:
        raise ValueError("target_value must be a finite non-negative number")
    if not 0.0 <= float(terminal_risky) <= 1.0:
        raise ValueError("terminal_risky must be between 0 and 1")

    current = _class_weights(plan)
    caps = dict(plan.class_caps or {})
    terminal = _terminal_weights(current, caps, terminal_risky)
    class_mu = _class_expected_returns(plan)

    start = float(plan.profile.capital)
    glide: List[Dict[str, Any]] = []
    returns: List[float] = []
    for year in range(years + 1):
        t = year / years
        weights = _blend(current, terminal, t)
        ann = sum(weights.get(c, 0.0) * class_mu.get(c, 0.0) for c in CLASS_ORDER)
        risky = sum(weights.get(c, 0.0) for c in RISKY_CLASSES)
        equity = weights.get("equity_cn", 0.0) + weights.get("equity_global", 0.0)
        glide.append({
            "year": year,
            "class_weights": {c: round(weights.get(c, 0.0), 4) for c in CLASS_ORDER},
            "risky_share": round(risky, 4),
            "equity_share": round(equity, 4),
            "expected_return": round(ann, 4),
            "projected_value": 0.0,
            "principal": 0.0,
            "target_progress": None,
        })
        if year > 0:
            returns.append(ann)

    path = _project(start, monthly, returns)
    for row, p in zip(glide, path):
        row["projected_value"] = round(float(p["value"]), 2)
        row["principal"] = round(float(p["principal"]), 2)
        if target > 0:
            row["target_progress"] = round(float(p["value"]) / target, 4)

    final = glide[-1]
    projected = float(final["projected_value"])
    required_monthly = None
    required_return = None
    gap = None
    progress = None
    on_track = True
    if target > 0:
        gap = round(target - projected, 2)
        progress = round(projected / target, 4)
        avg_return = float(np.mean(returns)) if returns else 0.0
        required_monthly = round(
            max(0.0, _required_monthly(start, target, avg_return, years)), -2)
        required_return = _required_annual_return(start, monthly, target, years)
        on_track = bool(projected >= target)

    risky_now = glide[0]["risky_share"]
    risky_end = final["risky_share"]
    return {
        "available": True,
        "years": years,
        "target_value": round(target, 2),
        "monthly_contrib": round(monthly, 2),
        "start_value": round(start, 2),
        "terminal_risky": float(terminal_risky),
        "class_returns": {c: round(class_mu.get(c, 0.0), 4) for c in CLASS_ORDER},
        "current": {
            "class_weights": {c: round(current.get(c, 0.0), 4) for c in CLASS_ORDER},
            "risky_share": round(risky_now, 4),
            "equity_share": glide[0]["equity_share"],
            "expected_return": glide[0]["expected_return"],
        },
        "terminal": {
            "class_weights": {c: round(terminal.get(c, 0.0), 4) for c in CLASS_ORDER},
            "risky_share": round(risky_end, 4),
            "equity_share": final["equity_share"],
            "expected_return": final["expected_return"],
        },
        "glide": glide,
        "summary": {
            "projected_value": round(projected, 2),
            "principal": final["principal"],
            "gain": round(projected - final["principal"], 2),
            "target_gap": gap,
            "target_progress": progress,
            "required_monthly": required_monthly,
            "required_ann_return": (None if required_return is None
                                    else round(required_return, 4)),
            "on_track": on_track,
            "risky_reduction": round(risky_now - risky_end, 4),
        },
        "assumptions": [
            "de-risking is linear from the current mix to the terminal mix",
            "expected returns come from the plan's asset estimates; no taxes/fees",
            "contributions are invested at month-end; deterministic projection",
        ],
    }