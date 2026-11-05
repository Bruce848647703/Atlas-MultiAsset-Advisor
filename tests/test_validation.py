import pytest

from invest_agent.advisor import build_plan
from invest_agent.data.synthetic import SyntheticProvider
from invest_agent.risk_profiler import QUESTIONS, profile_from_answers
from invest_agent.timing import views_from_args
from invest_agent.tools import AdvisorContext, build_tools
from invest_agent.validation import (
    InputValidationError, finite_number, integer, normalize_answers, text_value,
)

ANSWERS = {i: 2 for i in range(9)}


def test_number_validation():
    assert finite_number("12.5", "x", minimum=0, maximum=20) == 12.5
    with pytest.raises(InputValidationError):
        finite_number("abc", "x")
    with pytest.raises(InputValidationError):
        finite_number(float("nan"), "x")
    with pytest.raises(InputValidationError):
        finite_number(-1, "x", minimum=0)
    with pytest.raises(InputValidationError):
        integer(1.5, "x")


def test_text_validation():
    assert text_value(None, "x") == ""
    with pytest.raises(InputValidationError):
        text_value(123, "x")
    with pytest.raises(InputValidationError):
        text_value("x" * 10, "x", max_chars=5)


def test_answer_validation():
    assert normalize_answers({"0": "3"}, QUESTIONS) == {0: 3}
    with pytest.raises(InputValidationError):
        normalize_answers({"99": 1}, QUESTIONS)
    with pytest.raises(InputValidationError):
        normalize_answers({"0": 99}, QUESTIONS)
    with pytest.raises(InputValidationError):
        normalize_answers(None, QUESTIONS)


def test_profile_rejects_bad_inputs():
    with pytest.raises(InputValidationError):
        profile_from_answers(ANSWERS, capital=-1)
    with pytest.raises(InputValidationError):
        profile_from_answers(ANSWERS, capital=float("nan"))
    with pytest.raises(InputValidationError):
        profile_from_answers({"0": "bad"}, capital=100_000)
    with pytest.raises(InputValidationError):
        profile_from_answers(ANSWERS, capital=100_000, free_text=123)


def test_timing_dict_validation():
    with pytest.raises(InputValidationError):
        views_from_args({"equity_cn": "abc"})
    with pytest.raises(InputValidationError):
        views_from_args({"not_a_class": 0.5})
    assert views_from_args({"equity_cn": 0.5}).tilts["equity_cn"] == 0.5


def test_build_plan_rejects_zero_capital():
    profile = profile_from_answers(ANSWERS, capital=0)
    with pytest.raises(InputValidationError):
        build_plan(profile, SyntheticProvider(), n_months=96)


def test_tools_return_friendly_errors():
    ctx = AdvisorContext(provider_name="synthetic")
    tools = {t.name: t for t in build_tools(ctx)}
    assert "error" in tools["assess_risk_profile"].handler(
        {"answers": {"0": "bad"}, "capital": 100_000})
    assert "error" in tools["get_market_summary"].handler({"n_months": -5})
    assert "error" in tools["apply_timing_views"].handler(
        {"views": "看多A股", "conviction": "bad"})
    assert "error" in tools["screen_assets_by_factors"].handler({"n_months": -5})

    ctx.profile = profile_from_answers(ANSWERS, capital=500_000)
    assert "error" in tools["build_investment_plan"].handler(
        {"capital": 0})
    assert "error" in tools["build_investment_plan"].handler(
        {"satellite_budget": "bad"})
    assert "error" in tools["recommend_global_bases"].handler(
        {"overseas_pct": "bad", "capital": 500_000})