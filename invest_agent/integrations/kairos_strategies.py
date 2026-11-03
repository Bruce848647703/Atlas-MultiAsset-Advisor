"""Kairos Strategy Lab — run the sibling 106-strategy library on real ETF data.

`kairos-strategies` ships 106 original strategies across 27 channels with a
uniform ``generate_weights(data) -> weight panel`` contract. This module builds
a real daily ETF panel from the committed ``kairos-data`` CSVs, runs the
long-only subset, and caches a leaderboard under ``data_cache/`` so the
dashboard does not pay the ~30s cost on every page load.

Everything is optional: without the sibling repos / packages, callers get
``{"available": False, ...}`` and Atlas continues normally.
"""

from __future__ import annotations

import json
import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import kairos as bridge

LAB_VERSION = 1
DEFAULT_COST = 0.001


def _pkg():
    return bridge.pkg("kairos_strategies")


def available() -> bool:
    return _pkg() is not None and bridge.etf_dir() is not None


def _cache_path() -> Path:
    root = Path(__file__).resolve().parents[2]
    out = root / "data_cache"
    out.mkdir(parents=True, exist_ok=True)
    return out / "kairos_strategy_lab.json"


@lru_cache(maxsize=1)
def market_data():
    """Daily close panel from kairos-data/data/etf, aligned and ffilled."""
    if not available():
        return None
    import pandas as pd
    from kairos_strategies import MarketData

    edir = bridge.etf_dir()
    panel = {}
    for path in sorted(edir.glob("*.csv")):
        try:
            df = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
            close = pd.to_numeric(df["close"], errors="coerce").where(lambda s: s > 0)
            if close.notna().sum() >= 252:
                panel[path.stem] = close
        except Exception:  # noqa: BLE001
            continue
    if not panel:
        return None
    prices = pd.DataFrame(panel).sort_index().ffill()
    return MarketData(prices=prices, periods_per_year=252, name="kairos-etf")


def _cache_key(etf_dir: Path, cost_rate: float) -> str:
    parts = [f"v{LAB_VERSION}", f"cost={cost_rate:.6f}"]
    for path in sorted(etf_dir.glob("*.csv")):
        st = path.stat()
        parts.append(f"{path.name}:{st.st_mtime_ns}:{st.st_size}")
    return "|".join(parts)


def load_cached() -> Optional[Dict[str, Any]]:
    path = _cache_path()
    if not path.exists() or not available():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("cache_key") != _cache_key(bridge.etf_dir(), DEFAULT_COST):
            return None
        return data
    except Exception:  # noqa: BLE001
        return None


def _write_cache(pack: Dict[str, Any]) -> None:
    path = _cache_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def _serializable_params(params: Any) -> Dict[str, Any]:
    out = {}
    for key, value in (params or {}).items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            out[key] = value
        else:
            out[key] = str(value)
    return out


def run_lab(force: bool = False, cost_rate: float = DEFAULT_COST,
            channels: Optional[List[str]] = None) -> Dict[str, Any]:
    """Run the long-only Kairos strategies and return a cached leaderboard."""
    if not available():
        return {"available": False, "reason": "kairos-strategies or kairos-data not detected"}
    cached = load_cached()
    if cached and not force and not channels:
        return cached

    ks = _pkg()
    data = market_data()
    if data is None:
        return {"available": False, "reason": "no usable ETF price panel"}
    channel_set = set(channels or [])
    rows: List[Dict[str, Any]] = []
    started = time.time()
    for strategy in ks.discover():
        if not getattr(strategy, "long_only", False):
            continue
        if channel_set and strategy.channel not in channel_set:
            continue
        try:
            weights = strategy.generate_weights(data)
            result = ks.Backtester(cost_rate=cost_rate, periods_per_year=252).run(data, weights)
            m = result.metrics
            rows.append({
                "name": strategy.name,
                "channel": strategy.channel,
                "universe": getattr(strategy, "universe", ""),
                "description": getattr(strategy, "description", ""),
                "hypothesis": getattr(strategy, "hypothesis", ""),
                "source": getattr(strategy, "source", ""),
                "params": _serializable_params(getattr(strategy, "params", {})),
                "sharpe": round(float(m.get("sharpe", 0.0)), 4),
                "cagr": round(float(m.get("cagr", 0.0)), 4),
                "volatility": round(float(m.get("volatility", 0.0)), 4),
                "max_drawdown": round(float(m.get("max_drawdown", 0.0)), 4),
                "calmar": round(float(m.get("calmar", 0.0)), 4),
                "avg_turnover": round(float(m.get("avg_turnover", 0.0)), 4),
                "total_return": round(float(m.get("total_return", 0.0)), 4),
            })
        except Exception:  # noqa: BLE001 - one strategy must not fail the lab
            continue

    rows.sort(key=lambda r: r["sharpe"], reverse=True)
    pack = {
        "available": True,
        "cache_key": _cache_key(bridge.etf_dir(), cost_rate),
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_sec": round(time.time() - started, 2),
        "cost_rate": cost_rate,
        "universe": {
            "n_assets": int(data.n_assets),
            "n_days": int(len(data.prices)),
            "start": str(data.prices.index.min().date()),
            "end": str(data.prices.index.max().date()),
            "symbols": list(data.symbols),
        },
        "n_strategies": len(rows),
        "strategies": rows,
    }
    if not channel_set:
        _write_cache(pack)
    return pack


def cached_summary(limit: int = 5) -> Dict[str, Any]:
    """Small leaderboard snippet for the LLM context / status panel."""
    pack = load_cached()
    if not pack:
        return {}
    return {
        "generated_at": pack["generated_at"],
        "n_strategies": pack["n_strategies"],
        "data": pack["universe"],
        "top": [
            {k: r[k] for k in ("name", "channel", "sharpe", "cagr", "max_drawdown")}
            for r in pack["strategies"][:limit]
        ],
    }


def run_strategy(name: str, cost_rate: float = DEFAULT_COST) -> Dict[str, Any]:
    """Recompute one strategy and return metrics + a downsampled equity curve."""
    if not available():
        return {"available": False}
    ks = _pkg()
    data = market_data()
    strategy = next((s for s in ks.discover() if s.name == name), None)
    if strategy is None or data is None:
        return {"available": False, "reason": f"unknown strategy '{name}'"}
    try:
        result = ks.Backtester(cost_rate=cost_rate, periods_per_year=252).run(
            data, strategy.generate_weights(data))
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": str(exc)}
    eq = result.equity
    step = max(1, len(eq) // 400)
    eq = eq.iloc[::step]
    return {
        "available": True,
        "name": strategy.name,
        "channel": strategy.channel,
        "description": getattr(strategy, "description", ""),
        "hypothesis": getattr(strategy, "hypothesis", ""),
        "source": getattr(strategy, "source", ""),
        "params": _serializable_params(getattr(strategy, "params", {})),
        "metrics": {k: round(float(v), 4) for k, v in result.metrics.items()},
        "equity": [{"date": str(idx.date()), "value": round(float(val), 6)}
                   for idx, val in eq.items()],
    }