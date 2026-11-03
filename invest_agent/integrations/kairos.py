"""Optional integration with the sibling Kairos quant suite.

Kairos is a set of small, zero-heavy-dependency packages checked out next to
Atlas (``../kairos-data``, ``../kairos-risk``, ...). This module:

* discovers the sibling checkouts (``KAIROS_ROOT`` or the parent directory);
* exposes their package versions and local data/research assets;
* reads real cross-asset ETF data from ``kairos-data`` for the Kairos provider;
* overlays ``kairos-risk`` VaR/ES/risk-decomposition metrics on an Atlas plan;
* reads the committed ``kairos-research`` findings for the dashboard/LLM.

Everything is optional: if a sibling repo or package is missing, functions
return ``{}`` / ``None`` and Atlas keeps working with its own implementations.
"""

from __future__ import annotations

import csv
import importlib
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# Atlas asset id -> committed Kairos ETF CSV symbol.
# Only mappings that genuinely exist in kairos-data/data/etf are listed.
ATLAS_TO_KAIROS = {
    "csi300_etf": "sh510300",
    "csi500_etf": "sh510500",
    "gem_etf": "sz159915",
    "dividend_etf": "sh510880",
    "sp500_etf": "sh513500",
    "nasdaq_etf": "sh513100",
    "hstech_etf": "sz159920",      # HK broad proxy (no Hang Seng Tech ETF in the pool)
    "bond_etf": "sh511010",
    "bond_fund": "sh511260",       # 10y treasury ETF proxy
    "gold_etf": "sh518880",
    "money_fund": "sh511990",
}

_PKG_REPOS = {
    "kairos_data": "kairos-data",
    "kairos_portfolio": "kairos-portfolio",
    "kairos_risk": "kairos-risk",
    "kairos_backtest": "kairos-backtest",
    "kairos_strategies": "kairos-strategies",
    "kairos_lab": "kairos-lab",
}


def _settings() -> Dict[str, Any]:
    try:
        from ..config import get_config
        return (get_config().get("integrations", {}) or {}).get("kairos", {}) or {}
    except Exception:  # noqa: BLE001 - config must never break optional integration
        return {}


@lru_cache(maxsize=1)
def root() -> Optional[Path]:
    """Parent directory containing the sibling ``kairos-*`` checkouts."""
    if not bool(_settings().get("enabled", True)):
        return None
    candidates: List[Path] = []
    configured = os.environ.get("KAIROS_ROOT") or _settings().get("root")
    if configured:
        candidates.append(Path(str(configured)).expanduser())
    here = Path(__file__).resolve()
    # .../Atlas-MultiAsset-Advisor/invest_agent/integrations/kairos.py
    candidates.extend([here.parents[3], Path.cwd().parent, Path.cwd()])
    for candidate in candidates:
        if (candidate / "kairos-data").is_dir() or (candidate / "kairos_data").is_dir():
            return candidate.resolve()
    return None


@lru_cache(maxsize=1)
def _modules() -> Dict[str, Any]:
    modules: Dict[str, Any] = {name: None for name in _PKG_REPOS}
    base = root()
    if base is None:
        return modules
    for repo in _PKG_REPOS.values():
        path = base / repo
        if path.is_dir() and str(path) not in sys.path:
            sys.path.insert(0, str(path))
    for name in _PKG_REPOS:
        try:
            modules[name] = importlib.import_module(name)
        except Exception:  # noqa: BLE001 - one broken package must not block others
            modules[name] = None
    return modules


def reset_cache() -> None:
    """Clear discovery caches (used by tests / after changing KAIROS_ROOT)."""
    root.cache_clear()
    _modules.cache_clear()
    load_etf_monthly.cache_clear()


def pkg(name: str):
    return _modules().get(name)


def available() -> bool:
    return any(mod is not None for mod in _modules().values())


def etf_dir() -> Optional[Path]:
    base = root()
    if base is None:
        return None
    path = base / "kairos-data" / "data" / "etf"
    return path if path.is_dir() else None


def research_dir() -> Optional[Path]:
    base = root()
    if base is None:
        return None
    path = base / "kairos-research" / "data"
    return path if path.is_dir() else None


def status() -> Dict[str, Any]:
    """Detection report used by the dashboard and the LLM tool."""
    base = root()
    edir = etf_dir()
    rdir = research_dir()
    modules = _modules()
    packages = {
        name: (getattr(mod, "__version__", None) if mod is not None else None)
        for name, mod in modules.items()
    }
    return {
        "enabled": bool(_settings().get("enabled", True)),
        "root": str(base) if base else None,
        "available": any(mod is not None for mod in modules.values()),
        "packages": packages,
        "etf_dir": str(edir) if edir else None,
        "etf_count": len(list(edir.glob("*.csv"))) if edir else 0,
        "research_dir": str(rdir) if rdir else None,
        "mapped_assets": list(ATLAS_TO_KAIROS),
        "n_mapped_assets": len(ATLAS_TO_KAIROS),
    }


# ---------------------------------------------------------------------------
# Real ETF CSVs (kairos-data)
# ---------------------------------------------------------------------------
def _read_close(path: Path):
    import pandas as pd

    df = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    close = pd.to_numeric(df["close"], errors="coerce")
    close = close.where(close > 0).dropna()
    monthly = close.resample("ME").last().dropna()
    return monthly.pct_change().dropna()


@lru_cache(maxsize=64)
def load_etf_monthly(symbol: str, base_dir: Optional[str] = None):
    """Monthly simple returns for one committed Kairos ETF CSV, or None."""
    edir = Path(base_dir) if base_dir else etf_dir()
    if edir is None:
        return None
    path = edir / f"{symbol}.csv"
    if not path.exists():
        return None
    try:
        return _read_close(path)
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Risk overlay (kairos-risk)
# ---------------------------------------------------------------------------
def risk_overlay(
    asset_returns,
    weights,
    asset_classes: Sequence[str],
    asset_ids: Sequence[str],
) -> Dict[str, Any]:
    """VaR/ES + Euler risk decomposition from kairos-risk, or ``{}``."""
    kr = pkg("kairos_risk")
    if kr is None:
        return {}
    try:
        import numpy as np
        import pandas as pd

        R = pd.DataFrame(asset_returns)
        w = pd.Series(np.asarray(weights, dtype=float), index=list(asset_ids)).reindex(R.columns)
        w = w.fillna(0.0)
        if float(w.abs().sum()) <= 0:
            return {}
        port = R.mul(w, axis=1).sum(axis=1).dropna()
        if len(port) < 12:
            return {}
        cov = R.cov()
        decomposition = kr.component_risk(w, cov)

        pct = getattr(decomposition, "pct", None)
        class_risk: Dict[str, float] = {}
        if pct is not None:
            cls_of = dict(zip(asset_ids, asset_classes))
            for aid, share in pd.Series(pct).items():
                cls = cls_of.get(aid)
                if cls:
                    class_risk[cls] = class_risk.get(cls, 0.0) + float(share)
            total = sum(class_risk.values())
            if total > 0:
                class_risk = {k: round(v / total, 4) for k, v in class_risk.items()}

        return {
            "source": "kairos-risk",
            "observations": int(len(port)),
            "var_95": round(float(kr.historical_var(port, 0.95)), 6),
            "var_99": round(float(kr.historical_var(port, 0.99)), 6),
            "es_95": round(float(kr.expected_shortfall(port, 0.95)), 6),
            "es_99": round(float(kr.expected_shortfall(port, 0.99)), 6),
            "diversification_ratio": round(float(decomposition.diversification_ratio), 4),
            "effective_n": round(float(decomposition.effective_n), 3),
            "class_risk": class_risk,
        }
    except Exception:  # noqa: BLE001 - overlay is optional
        return {}


# ---------------------------------------------------------------------------
# Research brief (kairos-research)
# ---------------------------------------------------------------------------
def _read_csv(path: Path, limit: int) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return rows[:limit]


def research_brief(limit: int = 4) -> Dict[str, Any]:
    """Top findings + robust strategy champions committed by kairos-research."""
    rdir = research_dir()
    if rdir is None:
        return {}
    findings = _read_csv(rdir / "key_findings.csv", limit)
    champions = _read_csv(rdir / "robust_champions.csv", limit)
    if not findings and not champions:
        return {}
    return {
        "source": "kairos-research",
        "findings": findings,
        "champions": champions,
    }


def context(plan=None) -> Dict[str, Any]:
    """One-shot pack for the dashboard panel and the LLM tool."""
    pack = status()
    pack["research"] = research_brief()
    if plan is not None and getattr(plan, "kairos_risk", None):
        pack["plan_risk"] = plan.kairos_risk
    try:
        from . import kairos_strategies as lab
        summary = lab.cached_summary()
        if summary:
            pack["strategy_lab"] = summary
    except Exception:  # noqa: BLE001 - optional
        pass
    return pack