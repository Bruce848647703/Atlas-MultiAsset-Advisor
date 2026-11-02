"""Performance metrics used across the advisor and the dashboard."""

from __future__ import annotations

import math
from statistics import NormalDist
from typing import Dict, Optional, Sequence

import numpy as np

TRADING_MONTHS = 12
_EULER_GAMMA = 0.5772156649015329


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


# ---------------------------------------------------------------------------
# Multiple-testing-aware significance
# ---------------------------------------------------------------------------
def period_sharpe(returns) -> float:
    """Non-annualized (per-period) Sharpe ratio, used by PSR/DSR."""
    r = np.asarray(returns, dtype=float)
    if len(r) < 2:
        return 0.0
    sd = float(np.std(r, ddof=1))
    return float(np.mean(r) / sd) if sd > 1e-12 else 0.0


def probabilistic_sharpe_ratio(returns, benchmark_sr: float = 0.0) -> float:
    """Probability that the true Sharpe exceeds ``benchmark_sr``.

    Bailey & López de Prado (2012), adjusted for skewness and kurtosis:
        PSR = Φ((SR - SR*)·sqrt(n-1) / sqrt(1 - γ3·SR + (γ4-1)/4·SR²))
    where SR/SR* are per-period and γ4 is non-excess kurtosis.
    """
    r = np.asarray(returns, dtype=float)
    n = len(r)
    if n < 3:
        return 0.0
    sr = period_sharpe(r)
    sd = float(np.std(r, ddof=0))
    if sd < 1e-12:
        return 1.0 if sr > benchmark_sr else 0.0
    z = (r - r.mean()) / sd
    skew = float(np.mean(z ** 3))
    kurt = float(np.mean(z ** 4))          # non-excess
    var_term = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr
    stat = (sr - benchmark_sr) * math.sqrt(n - 1) / math.sqrt(max(var_term, 1e-12))
    return 0.5 * (1.0 + math.erf(stat / math.sqrt(2.0)))


def expected_max_sharpe(n_trials: int, sr_variance: float) -> float:
    """Expected maximum per-period Sharpe under the null of zero skill.

    Extreme-value approximation from Bailey & López de Prado (2014):
        E[max SR] ≈ sqrt(V[SR]) · ((1-γ)Φ⁻¹(1-1/N) + γΦ⁻¹(1-1/(N·e)))
    """
    if n_trials <= 1 or sr_variance <= 0:
        return 0.0
    nd = NormalDist()
    a = nd.inv_cdf(1.0 - 1.0 / n_trials)
    b = nd.inv_cdf(1.0 - 1.0 / (n_trials * math.e))
    return math.sqrt(sr_variance) * ((1.0 - _EULER_GAMMA) * a + _EULER_GAMMA * b)


def deflated_sharpe_ratio(
    returns,
    n_trials: int = 1,
    trial_sharpes: Optional[Sequence[float]] = None,
) -> float:
    """Deflated Sharpe Ratio: PSR against the best-of-N null benchmark.

    ``n_trials`` is the number of strategies/configurations that were compared
    before selecting this one. Pass the per-period Sharpe of those trials so
    the benchmark uses their observed cross-sectional dispersion; otherwise a
    single-series variance estimate is used.
    """
    srs = [float(s) for s in (trial_sharpes or []) if np.isfinite(s)]
    if len(srs) > 1:
        sr_variance = float(np.var(srs, ddof=1))
    else:
        sr = period_sharpe(returns)
        n = max(len(np.asarray(returns, dtype=float)) - 1, 1)
        sr_variance = (1.0 + 0.5 * sr * sr) / n
    sr0 = expected_max_sharpe(max(int(n_trials), 1), sr_variance)
    return probabilistic_sharpe_ratio(returns, benchmark_sr=sr0)
