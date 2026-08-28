"""Performance metrics used across the advisor and the dashboard."""

from __future__ import annotations

from typing import Dict

import numpy as np

TRADING_MONTHS = 12


def annualized_return(monthly_returns: np.ndarray) -> float:
    cum = float(np.prod(1.0 + np.asarray(monthly_returns, dtype=float)))
    n = len(monthly_returns)
    if n == 0 or cum <= 0:
        return -1.0
    return cum ** (TRADING_MONTHS / n) - 1.0


def annualized_vol(monthly_returns: np.ndarray) -> float:
    r = np.asarray(monthly_returns, dtype=float)
    if len(r) < 2:
        return 0.0
    return float(np.std(r, ddof=1) * np.sqrt(TRADING_MONTHS))


def sharpe_ratio(monthly_returns: np.ndarray, rf: float = 0.02) -> float:
    vol = annualized_vol(monthly_returns)
    if vol < 1e-12:
        return 99.0 if annualized_return(monthly_returns) > rf else 0.0
    return (annualized_return(monthly_returns) - rf) / vol


def max_drawdown(monthly_returns: np.ndarray) -> float:
    """Return max drawdown as a positive fraction (e.g. 0.25 == -25%)."""
    r = np.asarray(monthly_returns, dtype=float)
    if len(r) == 0:
        return 0.0
    wealth = np.cumprod(1.0 + r)
    peak = np.maximum.accumulate(np.concatenate(([1.0], wealth)))[1:]
    dd = 1.0 - wealth / peak
    return float(dd.max())


def calmar_ratio(monthly_returns: np.ndarray) -> float:
    mdd = max_drawdown(monthly_returns)
    if mdd < 1e-12:
        return 0.0
    return annualized_return(monthly_returns) / mdd


def win_rate(monthly_returns: np.ndarray) -> float:
    r = np.asarray(monthly_returns, dtype=float)
    if len(r) == 0:
        return 0.0
    return float((r > 0).mean())


def performance_metrics(monthly_returns, rf: float = 0.02) -> Dict[str, float]:
    r = np.asarray(monthly_returns, dtype=float)
    return {
        "ann_return": annualized_return(r),
        "ann_vol": annualized_vol(r),
        "sharpe": sharpe_ratio(r, rf),
        "max_drawdown": max_drawdown(r),
        "calmar": calmar_ratio(r),
        "win_rate": win_rate(r),
        "best_month": float(r.max()) if len(r) else 0.0,
        "worst_month": float(r.min()) if len(r) else 0.0,
    }
