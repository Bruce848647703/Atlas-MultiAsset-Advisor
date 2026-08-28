import numpy as np
import pytest

from invest_agent.data.universe import build_universe, asset_ids, asset_classes
from invest_agent.data import get_provider
from invest_agent.config import risk_tiers
from invest_agent.portfolio.optimizer import (
    cov_shrinkage, expected_returns_shrinkage, optimize_max_sharpe, optimize_min_vol,
)
from invest_agent.strategy import (
    STRATEGY_MENU, _reconcile_caps, build_strategy_weights, evaluate_strategy,
    menu_for_tier, tier_in_range,
)
from invest_agent.config import class_priors

ALL_CLASSES = ["cash", "fixed_income", "hybrid", "commodity", "equity_cn",
               "equity_global", "crypto", "futures"]
C5_CAPS = {c: 1.0 for c in ALL_CLASSES}


def _estimators():
    uni = build_universe()
    ids = asset_ids(uni)
    R = get_provider("synthetic").get_monthly_returns(ids, 120)
    priors = class_priors()
    classes = asset_classes(uni)
    prior_m = np.array([priors[c]["ann_ret"] / 12 for c in classes])
    mu = expected_returns_shrinkage(R.values, prior_m, 0.6)
    cov, _ = cov_shrinkage(R.values)
    return uni, R, classes, mu, cov


def test_menu_tier_coverage():
    for tier in ["C1", "C2", "C3", "C4", "C5"]:
        assert len(menu_for_tier(tier)) >= 1
    assert all(tier_in_range("C5", s.min_tier, s.max_tier)
               for s in menu_for_tier("C5"))
    assert not any(s.id == "crypto_barbell" for s in menu_for_tier("C4"))


def test_max_sharpe_and_min_vol_valid():
    uni, R, classes, mu, cov = _estimators()
    w_ms = optimize_max_sharpe(mu, cov, classes, C5_CAPS)
    w_mv = optimize_min_vol(cov, classes, C5_CAPS)
    for w in (w_ms, w_mv):
        assert abs(w.sum() - 1) < 1e-6
        assert (w >= -1e-9).all()
    sharpe_ms = (w_ms @ mu * 12 - 0.02) / (np.sqrt(w_ms @ cov @ w_ms) * np.sqrt(12))
    sharpe_mv = (w_mv @ mu * 12 - 0.02) / (np.sqrt(w_mv @ cov @ w_mv) * np.sqrt(12))
    assert sharpe_ms >= sharpe_mv - 1e-6  # tangency dominates on Sharpe


def test_strategy_weights_respect_caps_and_screen():
    uni, R, classes, mu, cov = _estimators()
    for s in STRATEGY_MENU:
        w = build_strategy_weights(s, mu, cov, classes, C5_CAPS, assets=uni)
        assert abs(w.sum() - 1) < 1e-6
        assert (w >= -1e-9).all()
        # class sleeve respected
        for i, a in enumerate(uni):
            sleeve = s.asset_filter.get(a.asset_class, 0.0)
            if sleeve <= 0:
                assert w[i] <= 1e-9, f"{s.id} leaks into {a.asset_class}"
            tags = set(a.meta.get("tags", []) or [])
            if tags & set(s.exclude_tags):
                assert w[i] <= 1e-9, f"{s.id} holds excluded {a.id}"


def test_strategy_excluded_class_hard_zero():
    """regression: classes absent from a strategy sleeve must be 0, not free."""
    uni, R, classes, mu, cov = _estimators()
    s = next(x for x in STRATEGY_MENU if x.id == "steady_carry")
    w = build_strategy_weights(s, mu, cov, classes, C5_CAPS, assets=uni)
    futures_idx = [i for i, a in enumerate(uni) if a.asset_class == "futures"]
    crypto_idx = [i for i, a in enumerate(uni) if a.asset_class == "crypto"]
    assert sum(w[i] for i in futures_idx) <= 1e-9
    assert sum(w[i] for i in crypto_idx) <= 1e-9


def test_evaluate_strategy_metrics():
    uni, R, classes, mu, cov = _estimators()
    s = next(x for x in STRATEGY_MENU if x.id == "balanced_core")
    from invest_agent.config import class_priors as _cp
    prior_m = np.array([_cp()[c]["ann_ret"] / 12 for c in classes])
    m, rets = evaluate_strategy(s, R, classes, mu, cov, C5_CAPS, assets=uni,
                                walk_forward=True, prior_monthly=prior_m)
    for k in ("ann_return", "ann_vol", "sharpe", "max_drawdown", "calmar",
              "turnover_annual", "win_rate"):
        assert k in m
    assert m["ann_vol"] > 0
    assert len(rets) == len(R)


def test_evaluate_strategy_static_mode():
    uni, R, classes, mu, cov = _estimators()
    s = next(x for x in STRATEGY_MENU if x.id == "balanced_core")
    m, rets = evaluate_strategy(s, R, classes, mu, cov, C5_CAPS, assets=uni,
                                walk_forward=False)
    assert m["ann_vol"] > 0 and len(rets) == len(R)


def test_reconcile_caps_feasible_and_never_breach():
    suit = {"cash": 0.15, "fixed_income": 0.30, "hybrid": 0.70, "commodity": 0.15,
            "equity_cn": 0.50, "equity_global": 0.50, "crypto": 0.15, "futures": 0.05}
    sleeves = {"cash": 0.35, "fixed_income": 0.15, "crypto": 0.50}  # raw sum w/ suit = .5
    eff = _reconcile_caps(sleeves, suit)
    assert all(eff[c] <= suit[c] + 1e-9 for c in eff)
    assert sum(eff.values()) >= 1.0 - 1e-9


@pytest.mark.parametrize("tier", ["C1", "C2", "C3", "C4", "C5"])
@pytest.mark.parametrize("gate_futures", [False, True], ids=["fut_open", "fut_gated"])
def test_every_strategy_feasible_for_every_tier(tier, gate_futures):
    """regression: sleeves ∩ suitability must be reconciled to a feasible,
    suitability-respecting allocation for EVERY strategy×tier combination."""
    uni, R, classes, mu, cov = _estimators()
    caps = dict(risk_tiers()[tier]["class_caps"])
    if gate_futures:
        caps["futures"] = 0.0  # segment gate (mass clients)
    for s in STRATEGY_MENU:
        try:
            w = build_strategy_weights(s, mu, cov, classes, caps, assets=uni)
        except ValueError:
            continue  # genuinely no viable asset -> acceptable, but must not crash
        assert abs(w.sum() - 1) < 1e-6, f"{s.id}/{tier}"
        assert (w >= -1e-9).all(), f"{s.id}/{tier}"
        expo = {}
        for i, a in enumerate(uni):
            expo[a.asset_class] = expo.get(a.asset_class, 0.0) + w[i]
        for c, cap in caps.items():
            assert expo.get(c, 0.0) <= cap + 1e-6, \
                f"{s.id}/{tier}: {c}={expo.get(c,0):.4f} > cap {cap}"
