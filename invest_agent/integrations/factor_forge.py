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


def sample_brief(name: str = "cgo") -> Optional[str]:
    """Read a bundled factor-forge example brief (handy for demos/tests)."""
    base = root()
    if base is None:
        return None
    path = base / "examples" / "input" / f"{name}.txt"
    return path.read_text(encoding="utf-8") if path.is_file() else None