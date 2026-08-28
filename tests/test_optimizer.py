import numpy as np

from invest_agent.portfolio.optimizer import (
    _clip_to_class_caps, class_exposures, cov_shrinkage,
    efficient_frontier, expected_returns_shrinkage,
    optimize_mean_variance, risk_parity,
)

RNG = np.random.default_rng(0)


def _toy_market(n_assets=6, n_obs=96):
    mu = RNG.uniform(0.002, 0.012, n_assets)
    A = RNG.standard_normal((n_obs, n_assets)) * 0.05
    R = A + mu
    return R, mu, ["equity_cn", "equity_cn", "equity_global", "fixed_income", "crypto", "cash"]


def test_shrinkage_mean_between_sample_and_prior():
    R, mu_hat, _ = _toy_market()
    prior = np.full(R.shape[1], 0.005)
    out = expected_returns_shrinkage(R, prior, delta=0.5)
    sample = R.mean(axis=0)
    assert np.allclose(out, 0.5 * prior + 0.5 * sample)


def test_cov_shrinkage_psd_and_symmetric():
    R, _, _ = _toy_market()
    cov, delta = cov_shrinkage(R)
    assert 0.0 <= delta <= 1.0
    assert np.allclose(cov, cov.T)
    eig = np.linalg.eigvalsh(cov)
    assert (eig > -1e-12).all()


def test_mv_weights_valid_and_caps_respected():
    R, _, classes = _toy_market()
    mu = R.mean(axis=0)
    cov, _ = cov_shrinkage(R)
    caps = {"equity_cn": 0.4, "crypto": 0.1, "fixed_income": 1.0, "equity_global": 1.0, "cash": 1.0}
    w = optimize_mean_variance(mu, cov, 3.0, classes, caps)
    assert abs(w.sum() - 1) < 1e-6
    assert (w >= -1e-9).all()
    expo = class_exposures(w, classes)
    for c, cap in caps.items():
        assert expo.get(c, 0.0) <= cap + 1e-6


def test_risk_parity_equal_risk_budgets():
    R, _, _ = _toy_market()
    cov, _ = cov_shrinkage(R)
    w = risk_parity(cov)
    rc = w * (cov @ w)
    assert abs(w.sum() - 1) < 1e-8
    rel = rc / rc.sum()
    assert np.abs(rel - 1.0 / len(w)).max() < 1e-3


def test_clip_respects_caps():
    w = np.array([0.6, 0.3, 0.05, 0.05])
    classes = ["crypto", "crypto", "cash", "cash"]
    out = _clip_to_class_caps(w, classes, {"crypto": 0.2})
    expo = class_exposures(out, classes)
    assert expo["crypto"] <= 0.2 + 1e-6
    assert abs(out.sum() - 1) < 1e-6


def test_frontier_ret_increasing_with_vol():
    R, _, classes = _toy_market()
    caps = {"crypto": 0.15}
    mu = expected_returns_shrinkage(R, np.full(R.shape[1], 0.006), 0.5)
    cov, _ = cov_shrinkage(R)
    fr = efficient_frontier(mu, cov, classes, caps, n_points=6)
    assert len(fr) >= 3
    rets = [p["ret"] for p in fr]
    vols = [p["vol"] for p in fr]
    assert all(b >= a - 1e-6 for a, b in zip(rets, rets[1:]))
    assert all(b >= a - 1e-6 for a, b in zip(vols, vols[1:]))
