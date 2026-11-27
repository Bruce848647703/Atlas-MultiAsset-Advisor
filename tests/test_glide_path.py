import re

import pytest

from invest_agent.agent import InvestAgent
from invest_agent.portfolio import glide_path
from invest_agent.report import build_report
from invest_agent.tools import AdvisorContext, build_tools


@pytest.fixture(scope="module")
def plan():
    return InvestAgent(output_dir="examples/demo_outputs/_glide_test").offline_plan(
        {i: 2 for i in range(9)}, capital=600_000)["plan"]


def test_glide_path_structure_and_de_risking(plan):
    out = glide_path.build(plan, target_value=1_200_000, years=6,
                           monthly_contrib=3_000)
    assert out["available"] is True
    assert out["years"] == 6
    assert len(out["glide"]) == 7
    risky = [row["risky_share"] for row in out["glide"]]
    assert all(risky[i] >= risky[i + 1] - 1e-9 for i in range(len(risky) - 1))
    assert out["terminal"]["risky_share"] <= 0.35 + 1e-6
    for row in out["glide"]:
        assert abs(sum(row["class_weights"].values()) - 1.0) < 1e-6
        for cls, w in row["class_weights"].items():
            cap = plan.class_caps.get(cls)
            if cap is not None and cap > 0:
                assert w <= cap + 1e-6, (row["year"], cls, w, cap)
    assert out["summary"]["projected_value"] > out["start_value"]
    assert 0 <= out["summary"]["target_progress"] <= 10
    assert out["summary"]["required_monthly"] is not None


def test_glide_path_no_target(plan):
    out = glide_path.build(plan, years=3, monthly_contrib=1_000)
    assert out["available"] is True
    assert out["summary"]["target_progress"] is None
    assert out["summary"]["target_gap"] is None
    assert out["summary"]["required_monthly"] is None
    assert out["summary"]["on_track"] is True


def test_glide_path_required_contribution_and_shortfall(plan):
    easy = glide_path.build(plan, target_value=1, years=3, monthly_contrib=1_000)
    hard = glide_path.build(plan, target_value=3_000_000, years=3,
                            monthly_contrib=1_000)
    impossible = glide_path.build(plan, target_value=10**9, years=3,
                                  monthly_contrib=1_000)
    assert easy["summary"]["required_monthly"] == 0
    assert hard["summary"]["required_monthly"] > 0
    assert hard["summary"]["on_track"] is False
    assert hard["summary"]["target_gap"] > 0
    assert hard["summary"]["required_ann_return"] is not None
    assert impossible["summary"]["required_ann_return"] is None


def test_glide_path_validation(plan):
    with pytest.raises(ValueError):
        glide_path.build(plan, monthly_contrib=-1)
    with pytest.raises(ValueError):
        glide_path.build(plan, target_value=-1)
    with pytest.raises(ValueError):
        glide_path.build(plan, terminal_risky=1.5)


def test_glide_path_tool_requires_plan_then_builds(plan):
    ctx = AdvisorContext(provider_name="synthetic")
    tools = {t.name: t for t in build_tools(ctx)}
    assert "error" in tools["get_glide_path"].handler({})
    ctx.plan = plan
    out = tools["get_glide_path"].handler(
        {"target_value": 1_200_000, "years": 5, "monthly_contrib": 2_000})
    assert out["available"] is True
    assert len(out["glide"]) == 6


def test_glide_path_report_is_localised(plan):
    gp = glide_path.build(plan, target_value=1_200_000, years=5,
                          monthly_contrib=2_000)
    zh = build_report(plan, {}, lang="zh", glide_path=gp)
    en = build_report(plan, {}, lang="en", glide_path=gp)
    assert "目标规划与 Glide Path" in zh
    assert "Goal Plan & Glide Path" in en
    assert not re.search(r"[\u4e00-\u9fff]", en)
