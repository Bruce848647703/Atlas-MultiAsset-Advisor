"""Kairos strategy ensemble / meta-allocator.

The Strategy Lab ranks individual strategies, but stacking the single best one
is fragile. This module:

1. takes the top candidates from the cached lab leaderboard;
2. **correlation-prunes** them (greedy, highest Sharpe first);
3. blends the survivors with equal / inverse-vol / risk-parity weights;
4. reports ensemble vs best-single vs equal-weight metrics;
5. combines their latest target weights for the bounded satellite overlay.

No live trading. Optional dependency: sibling `kairos-strategies` + data.
"""

from __future__ import annotations

import json
import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from . import kairos_strategies as lab

ENSEMBLE_NAME = "__kairos_ensemble__"
_CACHE = Path(__file__).resolve().parents[2] / "data_cache" / "kairos_ensemble.json"


def _cache_key(n: int, corr_max: float, method: str, lab_generated: str) -> str:
    return f"v1|{lab_generated}|{n}|{corr_max:.2f}|{method}"


def load_cached() -> Optional[Dict[str, Any]]:
    if not _CACHE.exists() or not lab.available():
        return None
    try:
        data = json.loads(_CACHE.read_text(encoding="utf-8"))
        current = _cache_key(int(data.get("n", 0)), float(data.get("corr_max", 0)),
                             data.get("method", ""), data.get("lab_generated_at", ""))
        if data.get("cache_key") != current:
            return None
        return data
    except Exception:  # noqa: BLE001
        return None


def _write_cache(pack: Dict[str, Any]) -> None:
    _CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _CACHE.with_suffix(".tmp")
    tmp.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, _CACHE)


@lru_cache(maxsize=128)
def strategy_returns(name: str):
    """Daily net-return series for one strategy (cached per process)."""
    ks = lab._pkg()
    data = lab.market_data()
    strategy = next((s for s in ks.discover() if s.name == name), None)
    if strategy is None or data is None:
        return None
    try:
        result = ks.Backtester(cost_rate=lab.DEFAULT_COST,
                               periods_per_year=252).run(
            data, strategy.generate_weights(data))
        return result.returns.rename(name)
    except Exception:  # noqa: BLE001
        return None


def _blend_weights(returns, method: str) -> tuple[np.ndarray, str]:
    n = returns.shape[1]
    if method == "equal" or n == 0:
        return np.full(n, 1.0 / max(n, 1)), "equal"
    std = returns.std(axis=0).values
    std = np.where(std > 1e-12, std, np.inf)
    inv = 1.0 / std
    if method == "inverse_vol":
        return inv / inv.sum(), "inverse_vol"
    # risk parity: use sibling implementation if available, else inverse vol
    try:
        kp = __import__("kairos_portfolio", fromlist=["risk_parity"])
        cov = returns.cov()
        w = np.asarray(kp.risk_parity(cov), dtype=float)
        w = np.clip(w, 0, None)
        if w.sum() > 0:
            return w / w.sum(), "risk_parity"
    except Exception:  # noqa: BLE001
        pass
    return inv / inv.sum(), "inverse_vol"


def build_ensemble(n: int = 5, corr_max: float = 0.7,
                   method: str = "inverse_vol",
                   force: bool = False) -> Dict[str, Any]:
    if not lab.available():
        return {"available": False, "reason": "kairos-strategies / kairos-data unavailable"}
    n = int(n)
    corr_max = float(corr_max)
    method = str(method or "inverse_vol")
    if not 2 <= n <= 12:
        raise ValueError("n 必须在 2-12 之间")
    if not 0.0 <= corr_max <= 0.99:
        raise ValueError("corr_max 必须在 0-0.99 之间")
    if method not in ("equal", "inverse_vol", "risk_parity"):
        raise ValueError("method 必须是 equal / inverse_vol / risk_parity")

    leaderboard = lab.load_cached()
    if not leaderboard:
        return {"available": False,
                "reason": "run the Strategy Lab first (no cached leaderboard)"}
    cached = load_cached()
    key = _cache_key(n, corr_max, method, leaderboard.get("generated_at", ""))
    if cached and not force and cached.get("cache_key") == key:
        return cached

    candidates = [r for r in leaderboard.get("strategies", [])
                  if r.get("sharpe", 0) > 0][:24]
    series: Dict[str, Any] = {}
    for row in candidates:
        s = strategy_returns(row["name"])
        if s is not None and len(s) >= 252:
            series[row["name"]] = s

    selected: List[str] = []
    for row in candidates:
        name = row["name"]
        if name not in series:
            continue
        if selected:
            aligned = pd.concat(
                [series[x] for x in selected] + [series[name]], axis=1).dropna()
            if len(aligned) < 252:
                continue
            corr = aligned.corr().iloc[-1, :-1].abs()
            if (corr >= corr_max).any():
                continue
        selected.append(name)
        if len(selected) >= n:
            break
    if len(selected) < 2:
        return {"available": False, "reason": "not enough low-correlation strategies"}

    matrix = pd.concat([series[x].rename(x) for x in selected], axis=1).dropna()
    sleeve_w, used_method = _blend_weights(matrix, method)
    ensemble_ret = matrix.mul(sleeve_w, axis=1).sum(axis=1)
    ks = lab._pkg()
    metrics = ks.metrics.summarize(
        ensemble_ret, turnover=pd.Series(0.0, index=ensemble_ret.index),
        periods_per_year=252)

    equal_ret = matrix.mean(axis=1)
    equal_metrics = ks.metrics.summarize(
        equal_ret, turnover=pd.Series(0.0, index=equal_ret.index),
        periods_per_year=252)
    best_name = selected[0]
    best_metrics = ks.metrics.summarize(
        matrix[best_name], turnover=pd.Series(0.0, index=matrix.index),
        periods_per_year=252)

    # latest target weights, mapped to Atlas ids
    latest: Dict[str, float] = {}
    invested = 0.0
    coverage = 0.0
    as_of = ""
    for name, weight in zip(selected, sleeve_w):
        info = lab.latest_weights(name)
        if not info:
            continue
        invested += float(weight) * float(info.get("invested", 0.0))
        coverage += float(weight) * float(info.get("coverage", 0.0))
        as_of = max(as_of, str(info.get("as_of", "")))
        for aid, w in (info.get("weights") or {}).items():
            latest[aid] = latest.get(aid, 0.0) + float(weight) * float(w)

    pack = {
        "available": True,
        "cache_key": key,
        "lab_generated_at": leaderboard.get("generated_at", ""),
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "n": n,
        "corr_max": corr_max,
        "requested_method": method,
        "method": used_method,
        "selected": [
            {"name": name, "weight": round(float(w), 4),
             "sharpe": next((r["sharpe"] for r in candidates if r["name"] == name), None)}
            for name, w in zip(selected, sleeve_w)
        ],
        "metrics": {k: round(float(v), 4) for k, v in metrics.items()},
        "best_single": {"name": best_name,
                        "metrics": {k: round(float(v), 4) for k, v in best_metrics.items()}},
        "equal_weight": {k: round(float(v), 4) for k, v in equal_metrics.items()},
        "latest": {
            "name": ENSEMBLE_NAME,
            "channel": "ensemble",
            "as_of": as_of,
            "weights": {k: round(v, 4) for k, v in latest.items() if v > 1e-4},
            "invested": round(invested, 4),
            "coverage": round(coverage, 4),
        },
        "n_observations": int(len(matrix)),
    }
    _write_cache(pack)
    return pack


def summary() -> Dict[str, Any]:
    pack = load_cached()
    if not pack:
        return {"available": False,
                "reason": "no cached ensemble; run the Strategy Lab and build it first"}
    return {k: pack[k] for k in ("generated_at", "n", "method", "selected",
                                 "metrics", "latest", "n_observations")}


def latest_weights() -> Dict[str, Any]:
    # Prefer the ensemble the user actually built (which may have a different
    # N / correlation threshold / method), not a fresh default configuration.
    pack = load_cached() or build_ensemble()
    return pack.get("latest", {}) if pack.get("available") else {}