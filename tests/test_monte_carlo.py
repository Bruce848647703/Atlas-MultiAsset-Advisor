from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from invest_agent.data.universe import build_universe
from invest_agent.portfolio import monte_carlo
from invest_agent.risk_profiler import profile_from_answers


def _plan():
    profile = profile_from_answers({i: 2 for i in range(9)}, capital=500_000)
    assets = build_universe()
    rng = np.random.default_rng(7)
    rets = rng.normal(0.005, 0.03, 96)
    equity = pd.Series(np.cumprod(1.0 + rets))
    return SimpleNamespace(
        profile=profile,
        monthly_contrib=3000.0,
        weights={"csi300_etf": 0.6, "bond_etf": 0.4},
        assets=assets,
        equity_curve=equity,
    )


def test_bootstrap_distribution_and_fan():
    out = monte_carlo.simulate_plan(_plan(), n_paths=300, horizon_years=3,
                                    method="bootstrap", seed=7)
    assert out["available"] is True
    assert len(out["fan"]) == 5
    assert len(out["months"]) == 37
    t = out["terminal"]
    assert t["p05"] <= t["p25"] <= t["p50"] <= t["p75"] <= t["p95"]
    assert 0 <= out["probability"]["loss"] <= 1
    assert 0 <= out["drawdown"]["p50"] <= out["drawdown"]["p95"] <= 1
    assert out["profit"]["var_95"] >= 0
    assert out["profit"]["es_95"] >= 0


def test_seed_is_reproducible():
    plan = _plan()
    a = monte_carlo.simulate_plan(plan, n_paths=200, horizon_years=2, seed=11)
    b = monte_carlo.simulate_plan(plan, n_paths=200, horizon_years=2, seed=11)
    assert a["terminal"]["p50"] == b["terminal"]["p50"]
    assert a["fan"][0]["values"] == b["fan"][0]["values"]


def test_parametric_and_goal_probability():
    out = monte_carlo.simulate_plan(_plan(), n_paths=200, horizon_years=3,
                                    method="parametric", target_value=600_000,
                                    seed=3)
    assert out["method"] == "parametric"
    assert 0 <= out["probability"]["goal"] <= 1


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        monte_carlo.simulate_plan(_plan(), n_paths=10)
    with pytest.raises(ValueError):
        monte_carlo.simulate_plan(_plan(), method="nope")
    with pytest.raises(ValueError):
        monte_carlo.simulate_plan(_plan(), horizon_years=0)


def test_stress_scenarios_are_sorted_and_use_class_exposure():
    out = monte_carlo.stress_scenarios(_plan())
    assert out["available"] is True
    assert len(out["rows"]) >= 5
    for row in out["rows"]:
        assert row["value_after"] == pytest.approx(
            out["capital"] * (1.0 + row["portfolio_shock"]), abs=0.01)
    eq = next(r for r in out["rows"] if r["id"] == "equity_shock")
    assert eq["loss"] > 0
    cny = next(r for r in out["rows"] if r["id"] == "cny_depreciation")
    assert cny["portfolio_shock"] >= 0