"""Composite scoring from Factor Forge-generated factors.

Forged factors live in ``data/factor_store.json`` with executable ``code`` and
``meta.operator``. This module evaluates the close-based ones on the Atlas
monthly panel, converts each factor into a cross-sectional z-score, signs it by
its declared direction (or measured IC when unknown), weights by |IC|, and
averages the latest months into a per-asset custom score.

The score is research evidence for the dashboard/LLM; it is not fed into the
optimizer automatically.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_CACHE = Path(__file__).resolve().parents[2] / "data_cache" / "custom_factor_scores.json"


def _store_path() -> Path:
    from .factor_store import _STORE_PATH
    return Path(_STORE_PATH)


def forged_records() -> List[Dict[str, Any]]:
    from .factor_store import load_store
    return [r for r in load_store() if r.get("code")]


def _cache_key(provider_name: str, n_months: int) -> str:
    path = _store_path()
    mtime = path.stat().st_mtime_ns if path.exists() else 0
    return f"v1|{provider_name}|{n_months}|{mtime}"


def load_cached() -> Optional[Dict[str, Any]]:
    if not _CACHE.exists():
        return None
    try:
        data = json.loads(_CACHE.read_text(encoding="utf-8"))
        if data.get("cache_key") != _cache_key(data.get("provider", ""),
                                              int(data.get("n_months", 0))):
            return None
        return data
    except Exception:  # noqa: BLE001
        return None


def _write_cache(pack: Dict[str, Any]) -> None:
    _CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _CACHE.with_suffix(".tmp")
    tmp.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, _CACHE)


def compute(provider_name: str = "synthetic", n_months: int = 120,
            force: bool = False, recent_months: int = 6) -> Dict[str, Any]:
    """Evaluate forged factors and build a latest cross-sectional score."""
    records = forged_records()
    if not records:
        return {"available": False, "reason": "no forged factors in the store"}
    cached = load_cached()
    if cached and not force and cached.get("cache_key") == _cache_key(provider_name, n_months):
        return cached

    try:
        import numpy as np
        import pandas as pd

        from ..integrations import factor_forge
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": str(exc)}

    factors: List[Dict[str, Any]] = []
    composites = []
    for rec in records:
        meta = rec.get("meta") or {}
        factor = {
            "name": rec.get("name", ""),
            "operator": meta.get("operator", ""),
            "variables": meta.get("variables", []),
            "direction": int(rec.get("direction", 0) or 0),
        }
        evaluation = factor_forge.evaluate_on_atlas(
            factor, rec.get("code", ""), provider_name=provider_name,
            n_months=n_months)
        if not evaluation.get("available"):
            factors.append({
                "name": rec.get("name", ""),
                "category": rec.get("category", ""),
                "available": False,
                "reason": evaluation.get("reason", ""),
            })
            continue
        panel_pack = factor_forge.factor_panel_on_atlas(
            factor, rec.get("code", ""), provider_name=provider_name,
            n_months=n_months)
        if not panel_pack.get("available"):
            continue
        panel = panel_pack["panel"]
        z = panel.sub(panel.mean(axis=1), axis=0).div(
            panel.std(axis=1).replace(0.0, np.nan), axis=0)
        direction = int(factor["direction"] or 0)
        sign = direction if direction else (1 if evaluation["mean_ic"] >= 0 else -1)
        weight = min(max(abs(evaluation["mean_ic"]), 0.005), 0.20)
        composites.append(z * sign * weight)
        factors.append({
            "name": rec.get("name", ""),
            "category": rec.get("category", ""),
            "available": True,
            "mean_ic": evaluation["mean_ic"],
            "icir": evaluation["icir"],
            "t_stat": evaluation["t_stat"],
            "positive_rate": evaluation["positive_rate"],
            "direction": direction,
            "direction_match": evaluation.get("direction_match"),
            "weight": round(weight, 4),
            "n_periods": evaluation["n_periods"],
        })

    if not composites:
        return {"available": False, "reason": "no forged factor could be evaluated",
                "factors": factors}

    reference = composites[0]
    aligned = [df.reindex(index=reference.index, columns=reference.columns).values
               for df in composites]
    with np.errstate(invalid="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            mean_values = np.nanmean(np.stack(aligned), axis=0)
    composite = pd.DataFrame(mean_values, index=reference.index,
                             columns=reference.columns)
    recent = composite.tail(max(1, int(recent_months))).mean(axis=0, skipna=True)
    recent = recent.replace([np.inf, -np.inf], np.nan).dropna()
    if recent.empty:
        return {"available": False, "reason": "no composite scores"}
    ranked = sorted(((str(k), float(v)) for k, v in recent.items()),
                    key=lambda kv: -kv[1])
    pack = {
        "available": True,
        "cache_key": _cache_key(provider_name, n_months),
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "provider": provider_name,
        "n_months": n_months,
        "recent_months": int(recent_months),
        "n_factors": sum(1 for f in factors if f.get("available")),
        "factors": factors,
        "scores": {k: round(v, 6) for k, v in ranked},
        "ranked": [{"asset": k, "score": round(v, 6)} for k, v in ranked],
    }
    _write_cache(pack)
    return pack


def summary(provider_name: str = "synthetic", limit: int = 8) -> Dict[str, Any]:
    pack = load_cached()
    if not pack:
        pack = compute(provider_name=provider_name)
    if not pack.get("available"):
        return pack
    return {
        **{k: pack[k] for k in ("generated_at", "provider", "n_factors",
                                "recent_months")},
        "top_factors": [f for f in pack["factors"] if f.get("available")][:limit],
        "top_assets": pack["ranked"][:limit],
        "bottom_assets": list(reversed(pack["ranked"][-limit:])),
    }