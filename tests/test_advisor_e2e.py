import pytest

from invest_agent.agent import InvestAgent
from invest_agent.personas import accessible_classes
from invest_agent.portfolio.optimizer import class_exposures

ANSWERS = {i: v for i, v in enumerate([3, 2, 3, 2, 2, 2, 2, 2, 2])}


def test_plan_respects_suitability_and_gate():
    agent = InvestAgent(output_dir="examples/demo_outputs/_t")
    res = agent.offline_plan(ANSWERS, capital=300_000,
                             free_text="能接受短期波动，但不想亏掉本金")
    plan, profile = res["plan"], res["profile"]

    w = plan.weight_vector
    assert abs(w.sum() - 1) < 1e-6
    assert (w >= -1e-9).all()
    assert (w <= 0.65 + 1e-6).all()

    caps = accessible_classes(profile)
    expo = class_exposures(w, [a.asset_class for a in plan.assets])
    for c, cap in caps.items():
        assert expo.get(c, 0.0) <= cap + 1e-6

    assert "免责声明" in res["report"]
    assert plan.expected["ann_return"] > 0
    assert 0 < plan.backtest["max_drawdown"] < 1


def test_mass_client_gets_no_futures_even_if_eager():
    agent = InvestAgent()
    res = agent.offline_plan({i: 3 for i in range(9)}, capital=100_000,
                             free_text="我想玩期货合约加杠杆")
    expo = class_exposures(res["plan"].weight_vector,
                           [a.asset_class for a in res["plan"].assets])
    assert expo.get("futures", 0.0) == 0.0


ANSWERS_BY_TIER = {
    "C1": {i: 0 for i in range(9)},
    "C2": {i: 1 for i in range(9)},
    # mixed 1s/2s lands in the C3 band (41-60)
    "C3": {0: 1, 1: 1, 2: 1, 3: 2, 4: 2, 5: 1, 6: 1, 7: 2, 8: 2},
    "C4": {i: 2 for i in range(9)},
    "C5": {i: 3 for i in range(9)},
}


@pytest.mark.parametrize("tier", ["C1", "C2", "C3", "C4", "C5"])
def test_all_tiers_produce_valid_plan(tier):
    agent = InvestAgent()
    res = agent.offline_plan(ANSWERS_BY_TIER[tier], capital=600_000)
    assert res["profile"].tier == tier
    assert abs(sum(res["plan"].weights.values()) - 1) < 1e-3


def test_charts_written(tmp_path):
    agent = InvestAgent(output_dir=str(tmp_path))
    res = agent.offline_plan(ANSWERS, capital=800_000)
    import os
    for name, path in res["charts"].items():
        assert os.path.exists(path), name
        assert os.path.getsize(path) > 10_000, name
