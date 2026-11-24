"""Monte Carlo wealth paths and deterministic scenario stress tests.

The plan gives one historical path. This module answers the questions that a
single path cannot:

* what is the distribution of terminal wealth and goal attainment probability?
* how bad can drawdowns get across simulated paths?
* what happens under equity/rate/crypto/FX shocks?

Historical returns are the selected strategy's walk-forward monthly series
(`Plan.equity_curve`), so the simulation inherits the actual volatility and
autocorrelation of the plan. Two engines:

* ``bootstrap`` — circular block bootstrap, preserving volatility clustering;
* ``parametric`` — Student-t fit on the historical monthly mean/vol.

Everything is seeded and JSON-serializable. This is research/education, not a
guarantee or investment advice.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

_METHODS = {"bootstrap", "parametric"}
_EPS = 1e-12


def _historical_returns(plan) -> np.ndarray:
    eq = getattr(plan, "equity_curve", None)
    if eq is None or len(eq) < 24:
        raise ValueError("plan has too little history for Monte Carlo (need >= 24 months)")
    returns = np.asarray(eq.pct_change().dropna(), dtype=float)
    if len(returns) < 24 or not np.isfinite(returns).all():
        raise ValueError("plan return history is empty or non-finite")
    return returns


def _simulate_returns(returns: np.ndarray, n_paths: int, horizon: int,
                      method: str, block: int, rng: np.random.Generator) -> np.ndarray:
    n_hist = len(returns)
    if method == "parametric":
        mu = float(returns.mean())
        sd = float(returns.std(ddof=1))
        if sd < _EPS:
            return np.full((n_paths, horizon), mu)
        # Student-t with 5 df, scaled to unit variance; clip catastrophic tails.
        df = 5.0
        raw = rng.standard_t(df, size=(n_paths, horizon))
        raw /= np.sqrt(df / (df - 2.0))
        return np.clip(mu + sd * raw, -0.95, 0.95)

    # circular block bootstrap
    out = np.empty((n_paths, horizon), dtype=float)
    for i in range(n_paths):
        pos = 0
        while pos < horizon:
            start = int(rng.integers(0, n_hist))
            take = min(block, horizon - pos)
            idx = (start + np.arange(take)) % n_hist
            out[i, pos:pos + take] = returns[idx]
            pos += take
    return out


def _drawdowns(paths: np.ndarray) -> np.ndarray:
    running = np.maximum.accumulate(paths, axis=1)
    dd = 1.0 - paths / np.maximum(running, _EPS)
    return dd.max(axis=1)


def simulate_plan(plan, *, n_paths: int = 2000, horizon_years: Optional[int] = None,
                  method: str = "bootstrap", block: int = 6,
                  target_value: float = 0.0,
                  seed: int = 20240601) -> Dict[str, Any]:
    """Simulate terminal wealth, drawdowns and goal attainment for a plan."""
    n_paths = int(n_paths)
    if not 100 <= n_paths <= 20000:
        raise ValueError("n_paths 必须在 100-20000 之间")
    method = str(method or "bootstrap").lower()
    if method not in _METHODS:
        raise ValueError(f"method 必须是 {sorted(_METHODS)}")
    years = int(plan.profile.horizon_years if horizon_years is None else horizon_years)
    if not 1 <= years <= 50:
        raise ValueError("horizon_years 必须在 1-50 之间")
    block = int(block)
    if not 1 <= block <= 24:
        raise ValueError("block 必须在 1-24 之间")
    target_value = float(target_value or 0.0)
    if not np.isfinite(target_value) or target_value < 0:
        raise ValueError("target_value 必须是非负有限数字")
    seed = int(seed)

    returns = _historical_returns(plan)
    horizon = years * 12
    rng = np.random.default_rng(seed)
    sim = _simulate_returns(returns, n_paths, horizon, method, block, rng)

    capital = float(plan.profile.capital)
    contrib = float(plan.monthly_contrib)
    if not np.isfinite(capital) or capital <= 0:
        raise ValueError("plan capital must be positive")
    if not np.isfinite(contrib) or contrib < 0:
        raise ValueError("plan monthly contribution must be non-negative")

    paths = np.empty((n_paths, horizon + 1), dtype=float)
    paths[:, 0] = capital
    for m in range(horizon):
        paths[:, m + 1] = paths[:, m] * (1.0 + sim[:, m]) + contrib

    terminal = paths[:, -1]
    principal = capital + contrib * horizon
    profit = terminal - principal
    dd = _drawdowns(paths)
    def q(arr, p):
        return float(np.percentile(arr, p))
    loss95 = max(0.0, -q(profit, 5))
    tail = profit[profit <= np.percentile(profit, 5)]
    es95 = max(0.0, float(-tail.mean())) if len(tail) else 0.0
    prob_loss = float((profit < 0).mean())
    prob_goal = float((terminal >= target_value).mean()) if target_value > 0 else None

    months = np.arange(horizon + 1)
    fan = []
    for p in (5, 25, 50, 75, 95):
        fan.append({"percentile": p,
                    "values": [round(float(x), 2) for x in np.percentile(paths, p, axis=0)]})
    return {
        "available": True,
        "method": method,
        "seed": seed,
        "n_paths": n_paths,
        "horizon_years": years,
        "months": [int(x) for x in months],
        "fan": fan,
        "terminal": {
            "p05": q(terminal, 5), "p25": q(terminal, 25), "p50": q(terminal, 50),
            "p75": q(terminal, 75), "p95": q(terminal, 95),
            "mean": float(terminal.mean()),
        },
        "profit": {
            "p05": q(profit, 5), "p50": q(profit, 50), "p95": q(profit, 95),
            "var_95": round(loss95, 2), "es_95": round(es95, 2),
        },
        "drawdown": {
            "p50": q(dd, 50), "p95": q(dd, 95), "worst": float(dd.max()),
        },
        "probability": {
            "loss": round(prob_loss, 4),
            "goal": None if prob_goal is None else round(prob_goal, 4),
        },
        "target_value": target_value or None,
        "principal": round(principal, 2),
        "capital": round(capital, 2),
        "monthly_contrib": round(contrib, 2),
    }


# ---------------------------------------------------------------------------
# Scenario stress tests
# ---------------------------------------------------------------------------
DEFAULT_SCENARIOS: List[Dict[str, Any]] = [
    {"id": "equity_shock", "name_zh": "股票 -20%", "name_en": "Equities -20%",
     "shocks": {"equity_cn": -0.20, "equity_global": -0.20}},
    {"id": "rates_up_100bp", "name_zh": "利率 +100bp", "name_en": "Rates +100bp",
     "shocks": {"fixed_income": -0.05, "cash": 0.0}},
    {"id": "crypto_crash", "name_zh": "加密 -50%", "name_en": "Crypto -50%",
     "shocks": {"crypto": -0.50}},
    {"id": "cny_depreciation", "name_zh": "人民币贬值 10%", "name_en": "CNY -10%",
     "shocks": {"equity_global": 0.10, "commodity": 0.05}},
    {"id": "stagflation", "name_zh": "滞胀冲击", "name_en": "Stagflation",
     "shocks": {"equity_cn": -0.15, "equity_global": -0.15,
                "fixed_income": -0.05, "commodity": 0.10}},
]


def stress_scenarios(plan, scenarios: Optional[List[Dict[str, Any]]] = None
                     ) -> Dict[str, Any]:
    """Apply one-time class shocks to the current plan value."""
    from .optimizer import class_exposures

    weights = np.array([plan.weights.get(a.id, 0.0) for a in plan.assets])
    classes = [a.asset_class for a in plan.assets]
    exposure = class_exposures(weights, classes)
    capital = float(plan.profile.capital)
    scenarios = scenarios or DEFAULT_SCENARIOS
    rows = []
    for sc in scenarios:
        shocks = sc.get("shocks") or {}
        pnl = 0.0
        contributions = []
        for cls, shock in shocks.items():
            w = float(exposure.get(cls, 0.0))
            contribution = w * float(shock)
            pnl += contribution
            if abs(contribution) > 1e-9:
                contributions.append({"class": cls, "weight": round(w, 4),
                                      "shock": round(float(shock), 4),
                                      "contribution": round(contribution, 4)})
        rows.append({
            "id": sc.get("id", sc.get("name_en", "scenario")),
            "name_zh": sc.get("name_zh", sc.get("id", "")),
            "name_en": sc.get("name_en", sc.get("id", "")),
            "portfolio_shock": round(pnl, 4),
            "value_after": round(capital * (1.0 + pnl), 2),
            "loss": round(-capital * pnl, 2),
            "contributions": sorted(contributions, key=lambda x: x["contribution"]),
        })
    return {"available": True, "capital": round(capital, 2), "rows": rows,
            "class_exposure": {k: round(v, 4) for k, v in exposure.items()}}