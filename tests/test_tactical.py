import numpy as np
import pandas as pd

from invest_agent.portfolio.backtest import run_walkforward_backtest
from invest_agent.portfolio.tactical import (
    expected_returns_tactical, momentum_scores, trend_gates,
)


def test_momentum_scores_known_value():
    R = np.array([[0.10], [-0.05], [0.02]])
    s = momentum_scores(R, lookback=3)
    assert abs(s[0] - (1.10 * 0.95 * 1.02 - 1)) < 1e-12


def test_tactical_fallback_on_short_history():
    R = np.random.default_rng(0).normal(0.005, 0.05, (12, 4))
    prior = np.full(4, 0.005)
    base = expected_returns_tactical(R, prior, delta=1.0)  # delta=1 -> prior only
    assert np.allclose(base, prior)


def test_tactical_tilt_direction():
    rng = np.random.default_rng(1)
    R = rng.normal(0.0, 0.05, (60, 3))
    R[-12:, 0] += 0.04     # strong recent uptrend for asset 0
    R[-12:, 2] -= 0.04     # downtrend for asset 2
    prior = np.zeros(3)
    mu = expected_returns_tactical(R, prior, delta=0.5, kappa=0.5)
    assert mu[0] > mu[1] > mu[2]


def test_trend_gates_bounds():
    R = np.random.default_rng(2).normal(0.0, 0.05, (24, 5))
    g = trend_gates(R)
    assert ((g >= 0.15) & (g <= 1.0)).all()


def test_walkforward_no_lookahead():
    """Builder must only ever see history up to the decision date."""
    idx = pd.period_range("2015-01", periods=60, freq="M")
    df = pd.DataFrame({"a": np.full(60, 0.01), "b": np.full(60, 0.005)}, index=idx)
    seen_max = {"n": 0}

    def builder(hist):
        seen_max["n"] = max(seen_max["n"], len(hist))
        assert len(hist) <= 60
        return np.array([0.5, 0.5])

    res = run_walkforward_backtest(df, builder, rebalance_every=3, warmup=12)
    # last rebuild is at t=58 -> sees 59 rows, never the full 60-with-future
    assert seen_max["n"] <= 59
    # warmup months earned cash, not the risky mix
    assert abs(res.portfolio_returns.iloc[0] - 0.02 / 12) < 1e-12
    assert len(res.portfolio_returns) == 60


def test_walkforward_builder_none_holds():
    idx = pd.period_range("2015-01", periods=48, freq="M")
    df = pd.DataFrame({"a": np.full(48, 0.01)}, index=idx)
    calls = {"n": 0}

    def builder(hist):
        calls["n"] += 1
        return None

    res = run_walkforward_backtest(df, builder, rebalance_every=1, warmup=12)
    assert calls["n"] > 0
    # never invested -> cash return throughout
    assert np.allclose(res.portfolio_returns.values, 0.02 / 12)
