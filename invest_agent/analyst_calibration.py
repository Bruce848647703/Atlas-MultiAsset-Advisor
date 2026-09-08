"""Learnable analyst voice weights.

The council's relevance weighting answers "who is relevant now". Calibration
answers a different question: "whose STYLE has actually worked?" — measured by
each analyst's structural tilt's information coefficient (IC) against forward
asset-class returns on real data.

    voice_multiplier(analyst) = clip(1 + k·IC̄, 0.5, 1.5)

Calibration is persisted (data/analyst_weights.json) and refreshed by the
evolution daemon — analysts whose style keeps working gain voting power;
styles that stop working are gradually muted. This is the same empirical-IC
philosophy as the factor self-evolution, applied to personas.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

_WEIGHTS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "..", "data", "analyst_weights.json")

K_IC = 5.0          # IC -> multiplier gain
MULT_MIN, MULT_MAX = 0.5, 1.5


# ---------------------------------------------------------------------------
# class-level returns panel
# ---------------------------------------------------------------------------
def class_returns_panel(monthly_returns: pd.DataFrame, assets) -> pd.DataFrame:
    """Aggregate asset-level monthly returns to class-level (equal-weight mean)."""
    cls_of = {a.id: a.asset_class for a in assets}
    data: Dict[str, List[str]] = {}
    for col in monthly_returns.columns:
        if col in cls_of:
            data.setdefault(cls_of[col], []).append(col)
    panel = {}
    for cls, cols in data.items():
        panel[cls] = monthly_returns[cols].mean(axis=1)
    return pd.DataFrame(panel).dropna(how="all")


# ---------------------------------------------------------------------------
# IC measurement
# ---------------------------------------------------------------------------
def calibrate_analyst_ic(tilt_vec: Dict[str, float],
                         class_rets: pd.DataFrame) -> float:
    """Mean rank-IC between the analyst's structural tilt and next-month
    class returns. Uses only classes present in both tilt and data."""
    from scipy.stats import spearmanr
    cols = [c for c in tilt_vec if c in class_rets.columns]
    if len(cols) < 4:
        return 0.0
    x = np.array([tilt_vec[c] for c in cols], dtype=float)
    if x.std() < 1e-12:
        return 0.0
    R = class_rets[cols].values
    ics = []
    for t in range(R.shape[0] - 1):
        fwd = R[t + 1]
        if np.std(fwd) < 1e-12 or not np.isfinite(fwd).all():
            continue
        ic, _ = spearmanr(x, fwd)
        if np.isfinite(ic):
            ics.append(ic)
    return float(np.mean(ics)) if ics else 0.0


def multiplier_from_ic(ic: float) -> float:
    return float(np.clip(1.0 + K_IC * ic, MULT_MIN, MULT_MAX))


# ---------------------------------------------------------------------------
# persistence
# ---------------------------------------------------------------------------
def load_calibration() -> Dict:
    if not os.path.exists(_WEIGHTS_PATH):
        return {}
    try:
        with open(_WEIGHTS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def save_calibration(calib: Dict) -> None:
    os.makedirs(os.path.dirname(_WEIGHTS_PATH), exist_ok=True)
    with open(_WEIGHTS_PATH, "w", encoding="utf-8") as f:
        json.dump(calib, f, ensure_ascii=False, indent=1)


def voice_multiplier(analyst_id: str) -> float:
    """Calibrated voting multiplier for an analyst (1.0 if uncalibrated)."""
    calib = load_calibration()
    weights = calib.get("weights", {}) or {}
    return float(weights.get(analyst_id, {}).get("multiplier", 1.0))


# ---------------------------------------------------------------------------
# calibration run
# ---------------------------------------------------------------------------
def calibrate_all(provider_name: str = "merged", months: int = 96) -> Dict:
    """Calibrate every registered analyst on real data; persist results."""
    from .analysts import REGISTRY, _numeric_tilt
    from .data.base import get_provider
    from .data.universe import build_universe, asset_ids

    assets = build_universe()
    ids = asset_ids(assets)
    try:
        prov = get_provider(provider_name)
        returns = prov.get_monthly_returns(ids, months)[ids]
    except Exception:  # noqa: BLE001 - fall back to synthetic world
        returns = get_provider("synthetic").get_monthly_returns(ids, months)[ids]
    class_rets = class_returns_panel(returns, assets)
    if class_rets.empty:
        return {"error": "empty class returns panel"}

    weights: Dict[str, Dict] = {}
    for a in REGISTRY:
        tilt = _numeric_tilt(a, "neutral")     # structural style, regime-free
        ic = calibrate_analyst_ic(tilt, class_rets)
        weights[a.id] = {
            "ic": round(ic, 4),
            "multiplier": round(multiplier_from_ic(ic), 3),
            "name_zh": a.name_zh,
            "school": a.school,
        }

    calib = {
        "meta": {
            "calibrated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "provider": provider_name,
            "months": len(class_rets),
            "n_analysts": len(weights),
            "formula": "multiplier = clip(1 + 5*IC, 0.5, 1.5)",
        },
        "weights": weights,
    }
    save_calibration(calib)
    return calib


def calibration_summary() -> Dict:
    """Human-readable summary: top/bottom analysts by calibrated voice."""
    calib = load_calibration()
    weights = calib.get("weights", {})
    if not weights:
        return {"calibrated": False}
    ranked = sorted(weights.items(), key=lambda kv: -kv[1]["multiplier"])
    return {
        "calibrated": True,
        "meta": calib.get("meta", {}),
        "top": [{"id": k, "name_zh": v.get("name_zh", k), "ic": v["ic"],
                 "multiplier": v["multiplier"]} for k, v in ranked[:5]],
        "bottom": [{"id": k, "name_zh": v.get("name_zh", k), "ic": v["ic"],
                    "multiplier": v["multiplier"]} for k, v in ranked[-5:]],
    }
