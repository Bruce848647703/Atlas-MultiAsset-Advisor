from types import SimpleNamespace

import numpy as np

from invest_agent.advisor import _selection_score
from invest_agent.portfolio.metrics import (
    deflated_sharpe_ratio, expected_max_sharpe, period_sharpe,
    probabilistic_sharpe_ratio,
)
from invest_agent.strategy import get_strategy


def _strong_series(n=120, seed=7):
    rng = np.random.default_rng(seed)
    return 0.012 + rng.normal(0.0, 0.01, n)


def test_psr_high_for_strong_series_and_near_half_for_noise():
    strong = _strong_series()
    assert probabilistic_sharpe_ratio(strong) > 0.99

    noise = np.random.default_rng(11).normal(0.0, 0.01, 600)
    assert 0.1 < probabilistic_sharpe_ratio(noise) < 0.9


def test_expected_max_sharpe_grows_with_trials():
    assert expected_max_sharpe(1, 0.01) == 0.0
    assert expected_max_sharpe(5, 0.01) < expected_max_sharpe(50, 0.01)


def test_dsr_penalises_multiple_trials():
    r = _strong_series(seed=3)
    single = deflated_sharpe_ratio(r, n_trials=1)
    trials = [period_sharpe(r) + d for d in (-0.15, -0.05, 0.0, 0.05, 0.15)]
    many = deflated_sharpe_ratio(r, n_trials=30, trial_sharpes=trials)
    assert 0.0 <= many < single <= 1.0


def test_dsr_uses_cross_sectional_trial_dispersion():
    r = _strong_series(seed=5)
    tight = deflated_sharpe_ratio(r, n_trials=10, trial_sharpes=[0.2, 0.21, 0.19])
    wide = deflated_sharpe_ratio(r, n_trials=10, trial_sharpes=[-0.5, 0.2, 1.2])
    assert wide < tight  # a wider search raises the best-of-N hurdle


def test_selection_score_rewards_evidence():
    profile = SimpleNamespace(
        tier="C3", free_text="",
        tier_info={"max_vol_hint": 0.15, "target_return": 0.07},
    )
    strategy = get_strategy("balanced_core")
    base = {"ann_return": 0.08, "ann_vol": 0.10, "sharpe": 0.6}
    weak = _selection_score(strategy, {**base, "dsr": 0.2}, profile)
    strong = _selection_score(strategy, {**base, "dsr": 0.9}, profile)
    assert strong > weak
    assert abs((strong - weak) - 0.8 * 0.7) < 1e-9