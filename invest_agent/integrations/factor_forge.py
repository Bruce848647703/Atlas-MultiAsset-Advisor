"""Optional Factor Forge bridge: research brief -> Factor JSON -> code -> Atlas.

The sibling ``factor-forge`` project turns a broker-report factor brief
(natural language + formula) into a structured ``Factor`` JSON and executable
Python, then validates the code on synthetic data. Atlas can use that output to
grow its own factor library with real provenance.

All calls are optional and side-effect free until ``import_factor`` /
``import_to_atlas`` is called. Missing sibling repo -> graceful ``{}``.
"""

from __future__ import annotations

import importlib
import os
import re
import sys
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional


def _settings() -> Dict[str, Any]:
    try:
        from ..config import get_config
        return (get_config().get("integrations", {}) or {}).get("factor_forge", {}) or {}
    except Exception:  # noqa: BLE001
        return {}


@lru_cache(maxsize=1)
def root() -> Optional[Path]:
    if not bool(_settings().get("enabled", True)):
        return None
    candidates = []
    configured = os.environ.get("FACTOR_FORGE_ROOT") or _settings().get("root")
    if configured:
        candidates.append(Path(str(configured)).expanduser())
    here = Path(__file__).resolve()
    candidates.append(here.parents[3] / "factor-forge")
    candidates.append(here.parents[3])
    for candidate in candidates:
        if (candidate / "factor_forge" / "__init__.py").is_file():
            return candidate.resolve()
    return None


@lru_cache(maxsize=1)
def _module():
    base = root()
    if base is None:
        return None
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))
    try:
        return importlib.import_module("factor_forge")
    except Exception:  # noqa: BLE001
        return None


def reset_cache() -> None:
    root.cache_clear()
    _module.cache_clear()


def available() -> bool:
    return _module() is not None


def status() -> Dict[str, Any]:
    mod = _module()
    base = root()
    return {
        "enabled": bool(_settings().get("enabled", True)),
        "root": str(base) if base else None,
        "available": mod is not None,
        "version": getattr(mod, "__version__", None) if mod else None,
        "operators": ["turnover_weighted_price", "momentum", "reversal",
                      "volatility", "generic"],
    }


def _safe_name(name: str, fallback: str = "factor") -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_]+", "_", name or "").strip("_")
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"f_{cleaned}" if cleaned else fallback
    return cleaned[:40]


def forge(brief: str, source: str = "", name: str = "",
          validate: bool = True) -> Dict[str, Any]:
    """Extract a Factor, generate code and optionally validate it."""
    mod = _module()
    if mod is None:
        return {"available": False, "reason": "factor-forge not detected"}
    text = (brief or "").strip()
    if not text:
        return {"available": False, "reason": "empty factor brief"}

    factor = mod.extract(text, source=source, name=name)
    factor.name = _safe_name(getattr(factor, "name", ""), "factor")
    code = mod.generate(factor)
    out: Dict[str, Any] = {
        "available": True,
        "factor": factor.to_dict(),
        "code": code,
        "source": source,
    }
    if validate:
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / f"{factor.name}.py"
                path.write_text(code, encoding="utf-8")
                ok, message, _ = mod.validate_code(str(path), factor)
            out["validation"] = {"ok": bool(ok), "message": message}
        except Exception as exc:  # noqa: BLE001
            out["validation"] = {"ok": False, "message": str(exc)}
    return out


_OPERATOR_FIELDS = {
    "momentum": {"close"},
    "reversal": {"close"},
    "volatility": {"close"},
    "turnover_weighted_price": {"close", "turnover", "vwap"},
    "generic": set(),
}


def evaluate_on_atlas(factor: Dict[str, Any], code: str,
                      provider_name: str = "synthetic",
                      n_months: int = 120) -> Dict[str, Any]:
    """Cross-sectional IC of a forged factor on the Atlas monthly asset pool.

    Only factors whose inputs are available in Atlas (currently ``close``)
    can be evaluated. The generated function is executed on cumulative price
    proxies; forward 1-month returns are used for rank IC.
    """
    if not factor or not code:
        return {"available": False, "reason": "missing factor/code"}
    op = str(factor.get("operator", ""))
    fields = set(_OPERATOR_FIELDS.get(op, set()))
    for var in factor.get("variables", []) or []:
        if var.get("data_field"):
            fields.add(var["data_field"])
    missing = fields - {"close"}
    if missing:
        return {
            "available": False,
            "reason": f"factor needs {sorted(missing)}; Atlas monthly panel only has close",
            "fields": sorted(fields),
        }

    try:
        import importlib.util
        import numpy as np
        import pandas as pd
        from scipy.stats import spearmanr

        from ..data.base import get_provider
        from ..data.universe import asset_ids, build_universe

        universe = build_universe()
        ids = asset_ids(universe)
        returns = get_provider(provider_name).get_monthly_returns(ids, n_months)[ids]
        returns = returns.fillna(0.0)
        prices = (1.0 + returns).cumprod()

        name = _safe_name(str(factor.get("name", "")), "factor")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"{name}.py"
            path.write_text(code, encoding="utf-8")
            spec = importlib.util.spec_from_file_location(f"atlas_forged_{name}", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            fn = getattr(mod, name)
            cols = {}
            for aid in ids:
                try:
                    cols[aid] = pd.Series(fn(close=prices[aid]), index=prices.index)
                except Exception:  # noqa: BLE001
                    continue
        if not cols:
            return {"available": False, "reason": "generated factor produced no series"}
        fac = pd.DataFrame(cols)
        fwd = returns.shift(-1)

        ics = []
        for t in fac.index[:-1]:
            x = fac.loc[t].replace([np.inf, -np.inf], np.nan).dropna()
            y = fwd.loc[t].reindex(x.index).dropna()
            common = x.index.intersection(y.index)
            if len(common) < 5:
                continue
            xv, yv = x.loc[common], y.loc[common]
            if xv.std() < 1e-12 or yv.std() < 1e-12:
                continue
            ic, _ = spearmanr(xv, yv)
            if np.isfinite(ic):
                ics.append(float(ic))
        if not ics:
            return {"available": False, "reason": "not enough cross-sections for IC"}
        arr = np.asarray(ics)
        mean_ic = float(arr.mean())
        std = float(arr.std(ddof=1)) if len(arr) > 1 else 0.0
        direction = int(factor.get("direction", 0) or 0)
        return {
            "available": True,
            "provider": provider_name,
            "n_periods": len(arr),
            "n_assets": int(fac.shape[1]),
            "mean_ic": round(mean_ic, 5),
            "ic_std": round(std, 5),
            "icir": round(mean_ic / std, 3) if std > 1e-12 else 0.0,
            "t_stat": round(float(mean_ic / std * np.sqrt(len(arr))), 2) if std > 1e-12 else 0.0,
            "positive_rate": round(float((arr > 0).mean()), 4),
            "direction": direction,
            "direction_match": (None if direction == 0 else bool(mean_ic * direction > 0)),
            "fields": sorted(fields),
        }
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": f"evaluation failed: {exc}"}


def import_factor(factor: Dict[str, Any], code: str, source: str = "",
                  overwrite: bool = False) -> Dict[str, Any]:
    """Write a forged factor (JSON + code) into the Atlas factor store."""
    if not factor:
        return {"error": "missing factor"}
    from ..factors.factor_store import add_factor

    name = _safe_name(str(factor.get("name", "")), "factor")
    rationale = " ".join(x for x in (
        str(factor.get("description", "") or ""),
        str(factor.get("direction_note", "") or ""),
        f"来源: {source}" if source else str(factor.get("source", "") or ""),
    ) if x)
    record = add_factor(
        name,
        category=str(factor.get("category") or "研报因子"),
        source="factor_forge",
        name_cn=str(factor.get("name_cn") or name),
        formula=str(factor.get("formula") or ""),
        direction=int(factor.get("direction", 0) or 0),
        rationale=rationale[:500],
        code=code,
        overwrite=overwrite,
    )
    return {"record": record, "name": name}


def import_to_atlas(brief: str, source: str = "", name: str = "",
                    overwrite: bool = False) -> Dict[str, Any]:
    """One-shot: brief -> factor + code + validation -> Atlas factor store."""
    forged = forge(brief, source=source, name=name, validate=True)
    if not forged.get("available"):
        return forged
    stored = import_factor(forged["factor"], forged["code"], source=source,
                           overwrite=overwrite)
    forged.update(stored)
    return forged


def pdf_available() -> bool:
    try:
        import fitz  # noqa: F401
        return _module() is not None
    except Exception:  # noqa: BLE001
        return False


def forge_pdf(path: str, source: str = "", max_briefs: int = 3,
              validate: bool = True) -> Dict[str, Any]:
    """PDF research report -> top factor-brief candidates -> forged factors."""
    mod = _module()
    if mod is None:
        return {"available": False, "reason": "factor-forge not detected"}
    try:
        candidates = mod.pdf_to_briefs(str(path), top_k=max(1, min(int(max_briefs), 8)))
    except Exception as exc:  # noqa: BLE001 - missing PyMuPDF / bad PDF
        return {"available": False, "reason": str(exc)}
    briefs = []
    for cand in candidates:
        forged = forge(cand.text, source=source or str(getattr(cand, "anchor", "")),
                       validate=validate)
        if forged.get("available"):
            forged["brief"] = cand.text
            forged["score"] = round(float(getattr(cand, "score", 0.0)), 2)
            forged["anchor"] = getattr(cand, "anchor", "")
            briefs.append(forged)
    return {"available": True, "n": len(briefs), "briefs": briefs}


def sample_brief(name: str = "cgo") -> Optional[str]:
    """Read a bundled factor-forge example brief (handy for demos/tests)."""
    base = root()
    if base is None:
        return None
    path = base / "examples" / "input" / f"{name}.txt"
    return path.read_text(encoding="utf-8") if path.is_file() else None