import numpy as np

from invest_agent.data import get_provider
from invest_agent.data.universe import build_universe, asset_ids


def test_shape_and_determinism():
    ids = asset_ids(build_universe())
    p1 = get_provider("synthetic")
    p2 = get_provider("synthetic")
    r1 = p1.get_monthly_returns(ids, 120)
    r2 = p2.get_monthly_returns(ids, 120)
    assert r1.shape == (120, len(ids))
    assert np.allclose(r1.values, r2.values)


def test_columns_match_request():
    p = get_provider("synthetic")
    df = p.get_monthly_returns(["btc", "csi300_etf", "bond_fund"], 60)
    assert list(df.columns) == ["btc", "csi300_etf", "bond_fund"]
    assert len(df) == 60


def test_cash_is_stable_and_risky_has_regime():
    p = get_provider("synthetic")
    df = p.full()
    cash = df["money_fund"]
    assert cash.min() > 0
    assert cash.std() < 0.002
    crypto = df["btc"]
    assert crypto.min() < -0.15          # the seeded crash month
    assert df["csi300_etf"].iloc[30:42].mean() < df["csi300_etf"].mean()  # bear regime


def test_unknown_asset_raises():
    p = get_provider("synthetic")
    try:
        p.get_monthly_returns(["nope"], 12)
        raise AssertionError("expected KeyError")
    except KeyError:
        pass
