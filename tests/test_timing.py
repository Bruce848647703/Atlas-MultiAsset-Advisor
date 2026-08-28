import numpy as np

from invest_agent.timing import (
    TimingView, apply_timing_views, extract_timing_views, views_from_args,
)
from invest_agent.requirement import parse_requirement


def test_extract_opposing_views_per_clause():
    v = extract_timing_views("我短期看空A股，但看多加密货币")
    assert v.tilts.get("equity_cn", 0) < 0
    assert v.tilts.get("crypto", 0) > 0


def test_general_sentiment_hits_risky_classes():
    v = extract_timing_views("市场要见顶了，减仓避险")
    assert v.tilts.get("equity_cn", 0) < 0
    assert v.tilts.get("equity_global", 0) < 0
    assert v.tilts.get("crypto", 0) < 0


def test_apply_timing_tilts_mu():
    mu = np.array([0.005, 0.005])
    vol = np.array([0.06, 0.10])
    classes = ["equity_cn", "crypto"]
    view = TimingView(tilts={"crypto": 1.0}, conviction=0.5)
    tilted = apply_timing_views(mu, vol, classes, view)
    assert tilted[1] > mu[1]          # bullish crypto lifted
    assert abs(tilted[0] - mu[0]) < 1e-12  # untouched class unchanged


def test_apply_timing_none_is_noop():
    mu = np.array([0.005, 0.005])
    vol = np.array([0.06, 0.10])
    out = apply_timing_views(mu, vol, ["a", "b"], None)
    assert np.allclose(out, mu)


def test_views_from_args_text_and_dict():
    v1 = views_from_args("看空A股")
    assert v1.tilts.get("equity_cn", 0) < 0
    v2 = views_from_args({"crypto": 2.5, "equity_cn": -3})   # clamped
    assert v2.tilts["crypto"] == 1.0 and v2.tilts["equity_cn"] == -1.0
    assert views_from_args(None) is None


def test_parse_requirement_full():
    req = parse_requirement("我看好纳斯达克，想加仓，打算拿五年，风险我扛得住")
    assert req.timing is not None and req.timing.tilts.get("equity_global", 0) > 0
    assert "equity_global" in req.interests
    assert req.horizon_hint == 5


def test_parse_requirement_bearish_not_risk_seeking():
    # mentioning crypto while exiting must NOT read as risk appetite
    req = parse_requirement("加密要暴跌了，清仓币圈，全部换成货基")
    assert req.timing.tilts.get("crypto", 0) < 0
    assert req.risk_adj <= 3  # not pushed risk-seeking by the mention


def test_advisor_timing_rotates_to_defensive():
    """Bearish-equity timing must rotate an aggressive profile away from a
    pure-equity strategy (integration through build_plan)."""
    from invest_agent.agent import InvestAgent
    ans = {i: 2 for i in range(9)}          # C4 profile
    base = InvestAgent().offline_plan(ans, 800_000)
    timed = InvestAgent().offline_plan(ans, 800_000,
                                       timing="市场要见顶了，减仓股票避险")

    def equity_share(res):
        p = res["plan"]
        return sum(v for k, v in p.weights.items()
                   if next(a.asset_class for a in p.assets if a.id == k)
                   in ("equity_cn", "equity_global"))

    assert timed["plan"].timing is not None
    assert equity_share(timed) < equity_share(base) - 0.05


def _expo(plan, cls):
    return sum(v for k, v in plan.weights.items()
               if next(a.asset_class for a in plan.assets if a.id == k) == cls)


def test_focus_mode_excludes_disliked_and_concentrates_liked():
    """crypto +1 with everything else -1 must exclude the disliked classes,
    concentrate crypto near its suitability cap, and park the rest in cash."""
    from invest_agent.agent import InvestAgent
    ans = {i: 3 for i in range(9)}          # C5
    timing = {"crypto": 1.0, "equity_cn": -1.0, "equity_global": -1.0,
              "commodity": -1.0, "fixed_income": -1.0}
    p = InvestAgent().offline_plan(ans, 2_000_000, timing=timing)["plan"]
    # disliked classes excluded
    for c in ("equity_cn", "equity_global", "commodity", "fixed_income"):
        assert _expo(p, c) <= 1e-6, f"{c} should be excluded"
    # crypto concentrated near (not beyond) its suitability cap
    cap = p.class_caps.get("crypto", 1.0)
    assert _expo(p, "crypto") > 0.5 * cap
    assert _expo(p, "crypto") <= cap + 1e-6
    # residual sits in cash
    assert _expo(p, "cash") > 0.5


def test_flight_to_cash_full_de_risk():
    """Everything -1 with nothing liked -> (nearly) 100% cash."""
    from invest_agent.agent import InvestAgent
    ans = {i: 3 for i in range(9)}
    timing = {"equity_cn": -1.0, "equity_global": -1.0,
              "crypto": -1.0, "commodity": -1.0}
    p = InvestAgent().offline_plan(ans, 2_000_000, timing=timing)["plan"]
    assert _expo(p, "cash") > 0.9
    for c in ("equity_cn", "equity_global", "crypto", "commodity"):
        assert _expo(p, c) <= 1e-6


def test_positive_only_view_keeps_diversification():
    """A strong like WITHOUT strong dislikes concentrates the class but does
    not silently wipe out other (neutral) classes."""
    from invest_agent.agent import InvestAgent
    ans = {i: 3 for i in range(9)}
    p = InvestAgent().offline_plan(ans, 2_000_000,
                                   timing={"equity_global": 0.8})["plan"]
    assert _expo(p, "equity_global") > 0.5      # concentrated
    # some diversification remains (at least one other non-cash class present)
    others = [c for c in ("equity_cn", "commodity", "fixed_income", "hybrid")
              if _expo(p, c) > 1e-3]
    assert others, "neutral classes should not all be wiped in non-focus mode"


