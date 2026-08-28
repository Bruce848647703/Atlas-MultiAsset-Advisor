"""Historical-simulation backtest with monthly rebalancing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .metrics import performance_metrics


@dataclass
class BacktestResult:
    portfolio_returns: pd.Series
    benchmark_returns: Optional[pd.Series]
    metrics: Dict[str, float]
    bench_metrics: Dict[str, float] = field(default_factory=dict)
    turnover_series: pd.Series = None  # type: ignore[assignment]

    def summary(self) -> Dict[str, object]:
        return {"portfolio": self.metrics, "benchmark": self.bench_metrics}


def run_backtest(
    monthly_returns: pd.DataFrame,
    weights: np.ndarray,
    fee: float = 0.0008,
    benchmark_col: Optional[str] = None,
    rebalance_every: int = 1,
) -> BacktestResult:
    """Rebalance to fixed target weights every `rebalance_every` months.

    Transaction cost = one-way fee applied on turnover (sum of |delta w|).
    This is the classical static-mix backtest; appropriate as a first-order
    check of an allocation thesis.
    """
    W = np.asarray(weights, dtype=float)
    W = W / W.sum()
    cols = list(monthly_returns.columns)
    R = monthly_returns.values.astype(float)
    T = R.shape[0]

    port_ret = np.zeros(T)
    turn = np.zeros(T)
    w = W.copy()
    for t in range(T):
        # drift
        grown = w * (1.0 + R[t])
        total = grown.sum()
        port_ret[t] = total - 1.0
        if (t + 1) % rebalance_every == 0 and t < T - 1:
            w_new = W
            to = float(np.abs(w_new - grown / total).sum())
            port_ret[t] -= fee * to
            turn[t] = to
            w = w_new.copy()
        else:
            w = grown / total

    idx = monthly_returns.index
    port = pd.Series(port_ret, index=idx, name="portfolio")
    metrics = performance_metrics(port_ret)

    bench_series = None
    bench_metrics: Dict[str, float] = {}
    if benchmark_col and benchmark_col in monthly_returns.columns:
        bench_series = monthly_returns[benchmark_col]
        bench_metrics = performance_metrics(bench_series.values)

    return BacktestResult(
        portfolio_returns=port,
        benchmark_returns=bench_series,
        metrics=metrics,
        bench_metrics=bench_metrics,
        turnover_series=pd.Series(turn, index=idx, name="turnover"),
    )


def equity_curve(monthly_returns: pd.Series, start_value: float = 100_000.0) -> pd.Series:
    return start_value * (1.0 + monthly_returns).cumprod()


def run_walkforward_backtest(
    monthly_returns: pd.DataFrame,
    build_weights,
    rebalance_every: int = 1,
    fee: float = 0.0008,
    warmup: int = 36,
    rf: float = 0.02,
    benchmark_col: Optional[str] = None,
) -> BacktestResult:
    """Honest out-of-sample backtest.

    At each rebalance date t, `build_weights(history_up_to_t)` is called with
    ONLY past data — no lookahead. Before `warmup` the portfolio sits in cash.
    This is the number an investor would actually have experienced.
    """
    R = monthly_returns.values.astype(float)
    T = R.shape[0]
    port_ret = np.zeros(T)
    turn = np.zeros(T)
    w = None

    for t in range(T):
        if w is None:
            port_ret[t] = rf / 12.0          # warmup: sit in cash
        else:
            grown = w * (1.0 + R[t])
            total = grown.sum()
            port_ret[t] = total - 1.0
            w = grown / total                # drift
        if t >= warmup and (t + 1) % rebalance_every == 0 and t < T - 1:
            hist = monthly_returns.iloc[: t + 1]
            w_new = build_weights(hist)
            if w_new is None:                    # builder declined -> hold drift
                continue
            w_new = np.asarray(w_new, dtype=float)
            w_new = np.clip(w_new, 0.0, None)
            w_new = w_new / max(w_new.sum(), 1e-12)
            base = w if w is not None else np.zeros(len(w_new))
            to = float(np.abs(w_new - base).sum())
            port_ret[t] -= fee * to
            turn[t] = to
            w = w_new.copy()

    idx = monthly_returns.index
    port = pd.Series(port_ret, index=idx, name="portfolio")
    metrics = performance_metrics(port_ret)

    bench_series = None
    bench_metrics: Dict[str, float] = {}
    if benchmark_col and benchmark_col in monthly_returns.columns:
        bench_series = monthly_returns[benchmark_col]
        bench_metrics = performance_metrics(bench_series.values)

    return BacktestResult(
        portfolio_returns=port,
        benchmark_returns=bench_series,
        metrics=metrics,
        bench_metrics=bench_metrics,
        turnover_series=pd.Series(turn, index=idx, name="turnover"),
    )


def goal_projection(
    start_value: float,
    monthly_contrib: float,
    ann_return: float,
    years: int,
) -> List[Dict[str, float]]:
    """Project portfolio milestones (motivational chart input)."""
    rm = ann_return / 12.0
    rows = []
    value = float(start_value)
    for m in range(1, years * 12 + 1):
        value = value * (1.0 + rm) + monthly_contrib
        if m % 12 == 0:
            rows.append({
                "year": m // 12,
                "value": value,
                "principal_in": start_value + monthly_contrib * m,
                "gain": value - start_value - monthly_contrib * m,
            })
    return rows
