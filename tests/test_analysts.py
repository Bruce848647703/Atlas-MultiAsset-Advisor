from invest_agent.analysts import (REGISTRY, analyst_view, build_council,
                                   score_analyst, select_analysts)


def _ctx(regime="neutral", plan_classes=None, tier="C3", tags=None, crypto=False):
    return {"regime": regime,
            "plan_classes": plan_classes or {"equity_global": 0.4, "fixed_income": 0.6},
            "tier": tier, "strategy_tags": tags or [], "has_crypto": crypto,
            "macro_stance": {}}


def test_registry_size_and_unique():
    assert len(REGISTRY) >= 30
    ids = [a.id for a in REGISTRY]
    assert len(ids) == len(set(ids))          # unique ids
    for a in REGISTRY:
        assert a.name_zh and a.name_en and a.school and a.philosophy


def test_select_top_n():
    council = select_analysts(_ctx(), n=5)
    assert len(council) == 5


def test_risk_on_selects_offensive():
    ctx = _ctx(regime="risk-on",
               plan_classes={"equity_global": 0.5, "crypto": 0.2, "equity_cn": 0.3},
               tier="C5", tags=["aggressive", "crypto"], crypto=True)
    council = build_council(ctx, n=5)
    assert council["consensus"] == "偏进攻"
    # crypto-friendly growth/quant analysts should be selected
    names = {v["id"] for v in council["council"]}
    assert any(a.crypto_friendly for a in REGISTRY if a.id in names)


def test_risk_off_selects_defensive():
    ctx = _ctx(regime="risk-off",
               plan_classes={"fixed_income": 0.7, "cash": 0.2, "commodity": 0.1},
               tier="C1", tags=["defensive"])
    council = build_council(ctx, n=5)
    assert council["consensus"] == "偏防御"
    # value/defensive legends should rank high
    ids = {v["id"] for v in council["council"]}
    assert ids & {"klarman", "graham", "dalio", "marks"}


def test_analyst_view_structure():
    a = next(x for x in REGISTRY if x.id == "simons")
    v = analyst_view(a, _ctx(regime="risk-on", plan_classes={"equity_global": 0.6},
                             tier="C4", tags=["momentum"]))
    assert set(v) >= {"id", "name_zh", "school", "stance", "advice", "tilt",
                      "signature", "relevance"}
    assert v["stance"] == "偏进攻"
    assert v["advice"] and v["signature"]


def test_score_monotone_in_focus():
    """An analyst scores higher when the plan holds their focus classes."""
    a = next(x for x in REGISTRY if x.id == "gross")   # bond king
    low = score_analyst(a, _ctx(plan_classes={"equity_global": 1.0}))
    high = score_analyst(a, _ctx(plan_classes={"fixed_income": 1.0}))
    assert high > low


def test_council_dissent_and_summary():
    council = build_council(_ctx(regime="neutral"), n=5)
    assert "summary" in council and len(council["summary"]) > 10
    assert council["n_analysts_total"] == len(REGISTRY)
    assert isinstance(council["dissent"], list)


def test_numeric_tilt_bounded_and_regime_aware():
    from invest_agent.analysts import _numeric_tilt
    a = next(x for x in REGISTRY if x.id == "wood")   # growth, risk-on leaning
    t_on = _numeric_tilt(a, "risk-on")
    t_off = _numeric_tilt(a, "risk-off")
    for v in list(t_on.values()) + list(t_off.values()):
        assert -1.0 <= v <= 1.0
    # growth analyst is more bullish on equity in risk-on than risk-off
    assert t_on["equity_global"] > t_off["equity_global"]


def test_council_vote_direction():
    from invest_agent.analysts import council_vote
    # risk-off bond-heavy -> net defensive (equity down, bonds up)
    off = council_vote(_ctx(regime="risk-off",
                            plan_classes={"fixed_income": 0.7, "cash": 0.2, "commodity": 0.1},
                            tier="C1", tags=["defensive"]), n=5)
    assert off["net_tilt"]["equity_global"] < 0
    assert off["net_tilt"]["fixed_income"] > 0
    # risk-on equity/crypto-heavy -> net offensive
    on = council_vote(_ctx(regime="risk-on",
                           plan_classes={"equity_global": 0.5, "crypto": 0.2, "equity_cn": 0.3},
                           tier="C5", tags=["aggressive", "crypto"], crypto=True), n=5)
    assert on["net_tilt"]["equity_global"] > 0
    assert on["net_tilt"]["fixed_income"] < 0
    # each vote carries weight + tilt
    assert all(v["weight"] > 0 and isinstance(v["tilt"], dict) for v in on["votes"])


def test_build_council_includes_vote():
    c = build_council(_ctx(regime="risk-on",
                           plan_classes={"equity_global": 0.6, "crypto": 0.1},
                           tier="C5", tags=["momentum"], crypto=True), n=5)
    assert "net_tilt" in c and "votes" in c
    assert len(c["votes"]) == 5
