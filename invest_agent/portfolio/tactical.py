"""Tactical signals: time-series momentum tilt.

Academic basis: Moskowitz, Ooi & Pedersen (2012), "Time Series Momentum".
Holding assets with positive trailing returns and avoiding negative ones
cuts left tails (drawdowns) and lifts Sharpe across asset classes.

Everything here is computed strictly from history up to the decision date —
walk-forward backtests call these with truncated windows, so no lookahead.
"""

from __future__ import annotations

from typing import Optional

import numpy as np


def momentum_scores(monthly_returns: np.ndarray, lookback: int = 12) -> np.ndarray:
    """Trailing `lookback`-month total return per asset."""
    R = np.asarray(monthly_returns, dtype=float)
    win = R[-lookback:]
    return np.prod(1.0 + win, axis=0) - 1.0


def expected_returns_tactical(
    monthly_returns: np.ndarray,
    prior_monthly: Optional[np.ndarray],
    delta: float = 0.6,
    kappa: float = 0.4,
    lookback: int = 12,
    min_obs: int = 24,
) -> np.ndarray:
    """Shrinkage baseline + vol-scaled cross-sectional momentum tilt.

    mu_i = [delta*prior + (1-delta)*sample_mean]_i + kappa * z_i * vol_i
    where z is the cross-sectional z-score of trailing momentum. Vol-scaling
    makes the tilt comparable between a bond fund and Bitcoin.
    Falls back to the plain shrinkage estimate when history is too short.
    """
    from .optimizer import expected_returns_shrinkage

    R = np.asarray(monthly_returns, dtype=float)
    base = expected_returns_shrinkage(R, prior_monthly, delta)
    if len(R) < max(lookback + 6, min_obs):
        return base

    scores = momentum_scores(R, lookback)
    sd = float(scores.std(ddof=1))
    if sd < 1e-9:
        return base
    z = (scores - float(scores.mean())) / sd
    vol = R.std(axis=0, ddof=1)
    return base + kappa * z * vol


def trend_gates(
    monthly_returns: np.ndarray,
    lookback: int = 12,
    floor: float = 0.15,
) -> np.ndarray:
    """Per-asset soft trend gate in [floor, 1]:  0.5 + 0.5*tanh(2*score).

    Assets in strong downtrends get their allowable weight scaled toward
    `floor`; uptrending assets keep full room. Used as per-asset max_weight
    in the walk-forward optimizer pass.
    """
    scores = momentum_scores(monthly_returns, lookback)
    gates = 0.5 + 0.5 * np.tanh(2.0 * scores)
    return np.clip(gates, floor, 1.0)
