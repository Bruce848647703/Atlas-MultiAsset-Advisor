import numpy as np
import pandas as pd

from invest_agent.portfolio.backtest import equity_curve, goal_projection, run_backtest
from invest_agent.portfolio.metrics import (
    annualized_return, max_drawdown, performance_metrics, sharpe_ratio,
)


def _flat_series(r=0.01, n=48, k=3):
    idx = pd.period_range("2020-01", periods=n, freq="M")
    return pd.DataFrame({f"a{i}": r for i in range(k)}, index=idx)


def test_metrics_constant_returns():
    r = np.full(12, 0.01)
    assert abs(annualized_return(r) - (1.01 ** 12 - 1)) < 1e-9
    assert max_drawdown(r) == 0.0
    assert sharpe_ratio(r) > 0
    m = performance_metrics(r)
    assert set(m) == {"ann_return", "ann_vol", "sharpe", "max_drawdown",
                      "calmar", "win_rate", "best_month", "worst_month"}


def test_max_drawdown_known_value():
    r = np.array([0.10, -0.20, 0.05, 0.0])
    # peak 1.10, trough 0.88 -> dd = 0.22/1.10 = 0.20
    assert abs(max_drawdown(r) - 0.20) < 1e-9


def test_backtest_no_costs_matches_static_mix():
    df = _flat_series(0.01, n=24)
    res = run_backtest(df, np.array([0.5, 0.5, 0.0]), fee=0.0)
    assert np.allclose(res.portfolio_returns.values, 0.01)
    assert abs(res.metrics["ann_return"] - (1.01 ** 12 - 1)) < 1e-6


def test_backtest_costs_reduce_return():
    # unequal monthly returns create drift -> rebalancing turnover > 0
    idx = pd.period_range("2020-01", periods=24, freq="M")
    a = np.where(np.arange(24) % 2 == 0, 0.03, -0.01)
    b = np.full(24, 0.005)
    df = pd.DataFrame({"a": a, "b": b}, index=idx)
    w = np.array([0.5, 0.5])
    res_free = run_backtest(df, w, fee=0.0)
    res_cost = run_backtest(df, w, fee=0.01)
    assert res_cost.metrics["ann_return"] < res_free.metrics["ann_return"]
    assert res_cost.turnover_series.sum() > 0


def test_equity_curve():
    df = _flat_series(0.01, n=12, k=1)
    ec = equity_curve(df["a0"], start_value=100.0)
    assert abs(ec.iloc[-1] - 100.0 * 1.01 ** 12) < 1e-6


def test_goal_projection_compounding():
    rows = goal_projection(100_000, 0, 0.12, 10)
    assert len(rows) == 10
    assert rows[-1]["value"] > 100_000 * 1.12 ** 10 * 0.98
    with_contrib = goal_projection(0, 1000, 0.0, 5)
    assert abs(with_contrib[-1]["value"] - 1000 * 60) < 1e-6
