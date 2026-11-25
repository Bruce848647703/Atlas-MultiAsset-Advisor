from types import SimpleNamespace

import numpy as np
import pandas as pd

from invest_agent.data.base import get_provider
from invest_agent.data.universe import build_universe
from invest_agent.portfolio import attribution


def _plan():
    assets = build_universe()
    idx = get_provider("synthetic").get_monthly_returns(
        [a.id for a in assets], 96).index
    rng = np.random.default_rng(7)
    rets = rng.normal(0.004, 0.03, 96)
    return SimpleNamespace(
        assets=assets,
        provider_name="synthetic",
        n_months=96,
        weights={"csi300_etf": 0.3, "sp500_etf": 0.2, "bond_etf": 0.3,
                 "gold_etf": 0.2},
        equity_curve=pd.Series(np.cumprod(1.0 + rets), index=idx),
    )


def test_attribution_structure():
    out = attribution.analyze(_plan())
    assert out["available"] is True
    assert out["n_months"] >= 24
    assert "equity_cn" in out["return"]["by_class"]
    assert abs(sum(out["risk"]["by_class"].values()) - 1.0) < 1e-3
    assert out["factor"]["available"] is True
    assert 0.0 <= out["factor"]["r2"] <= 1.0
    assert "market" in out["factor"]["betas"]
    assert out["risk"]["effective_n"] > 0


def test_attribution_is_deterministic():
    a = attribution.analyze(_plan())
    b = attribution.analyze(_plan())
    assert a["factor"] == b["factor"]
    assert a["risk"] == b["risk"]


def test_attribution_aligns_range_index_equity_curve():
    plan = _plan()
    plan.equity_curve = pd.Series(
        plan.equity_curve.values, index=pd.RangeIndex(len(plan.equity_curve)))
    out = attribution.analyze(plan)
    assert out["available"] is True
    assert out["factor"]["available"] is True
    assert out["factor"]["n_obs"] >= 24


def test_attribution_degrades_with_short_history():
    plan = _plan()
    plan.n_months = 6
    out = attribution.analyze(plan)
    assert out["available"] is False
    assert "24" in out["reason"]