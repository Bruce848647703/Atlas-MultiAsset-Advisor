from invest_agent.risk_profiler import (
    QUESTIONS, heuristic_text_adjustment, profile_from_answers,
    score_questionnaire, tier_from_score, profiling_prompt,
)


def all_answers(option: int) -> dict:
    return {i: option for i in range(len(QUESTIONS))}


def test_score_bounds():
    lo, tier_lo = score_questionnaire(all_answers(0))
    hi, tier_hi = score_questionnaire(all_answers(3))
    assert lo == 0.0 and tier_lo == "C1"
    assert hi == 100.0 and tier_hi == "C5"


def test_partial_answers_missing_defaults_to_zero():
    score, tier = score_questionnaire({0: 3})
    assert 0.0 <= score <= 100.0
    assert tier in {"C1", "C2", "C3", "C4", "C5"}


def test_tier_boundaries_monotone():
    tiers = [tier_from_score(s) for s in (0, 20, 21, 40, 41, 60, 61, 80, 81, 100)]
    assert tiers == ["C1", "C1", "C2", "C2", "C3", "C3", "C4", "C4", "C5", "C5"]


def test_keyword_adjustment_directions():
    adj_pos, _ = heuristic_text_adjustment("追求高收益，跌了敢加仓，看好币圈")
    adj_neg, _ = heuristic_text_adjustment("这笔钱不能亏，保本最重要，短期要用")
    assert adj_pos > 0 > adj_neg
    assert -25 <= adj_pos <= 25 and -25 <= adj_neg <= 25


def test_free_text_can_downgrade_tier():
    answers = all_answers(2)
    p_plain = profile_from_answers(answers, capital=100000)
    p_scared = profile_from_answers(answers, capital=100000,
                                    free_text="但是我真的亏不起本金，不能亏")
    assert p_scared.score < p_plain.score
    assert p_scared.tier <= p_plain.tier


def test_horizon_inference():
    p = profile_from_answers(all_answers(2), capital=100000)
    assert p.horizon_years in (1, 2, 4, 7)


def test_profiling_prompt_contains_all_questions():
    prompt = profiling_prompt("我想要稳健收益")
    for i in range(len(QUESTIONS)):
        assert f"[{i}]" in prompt
