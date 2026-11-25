"""Dashboard state regressions (real Streamlit script runs, network stubbed)."""

import re

import pandas as pd
import pytest

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest  # noqa: E402


MACRO = {
    "advice": [{"class": "equity_cn", "name": "A股", "stance": "超配",
                "score": 0.8, "reasons": ["动量"]}],
    "sector_tilt": {"style": "偏成长", "notes": ["成长强"]},
    "macro_context": {"china_pmi": "扩张", "equity_pe_percentile": 35.0,
                      "global_regime": "中性/观望", "risk_appetite": 0.1,
                      "themes": []},
    "narrative": "叙述",
}


@pytest.fixture()
def dashboard(monkeypatch):
    monkeypatch.setattr("invest_agent.global_indices.fetch_global_indices",
                        lambda *a, **k: {"source_ok": False, "regions": {},
                                         "note": "stubbed"})
    monkeypatch.setattr("invest_agent.geopolitics.fetch_global_news",
                        lambda *a, **k: {"items": [], "generated_at": "stub",
                                         "sources_ok": []})
    monkeypatch.setattr("invest_agent.factors.factor_evolution.maybe_autolearn",
                        lambda *a, **k: {"triggered": False})
    monkeypatch.setattr("invest_agent.macro_advice.generate_macro_advice",
                        lambda *a, **k: MACRO)
    monkeypatch.setattr("invest_agent.factors.enrich_universe",
                        lambda *a, **k: pd.DataFrame())
    at = AppTest.from_file("dashboard/app.py", default_timeout=300)
    at.session_state["atlas_lang"] = "en"
    at.run()
    assert not at.exception
    return at


def _button(at, label):
    return next(b for b in at.button if b.label == label)


def test_new_plan_invalidates_final_advice_and_council(dashboard):
    at = dashboard
    _button(at, "Generate plan").click().run()
    assert not at.exception

    _button(at, "Generate final advice").click().run()
    assert not at.exception
    _button(at, "Convene council").click().run()
    assert not at.exception
    assert at.session_state["atlas_final_advice"].get("error") is None
    assert at.session_state["atlas_council"].get("error") is None

    next(n for n in at.number_input if n.key == "capital").set_value(500_000).run()
    _button(at, "Generate plan").click().run()
    assert not at.exception

    assert "atlas_final_advice" not in at.session_state
    assert "atlas_council" not in at.session_state
    assert not any("final advice" in w.value.lower() and "stale" in w.value.lower()
                   for w in at.warning)


def _report_text(at):
    return next((m.value for m in at.markdown if "Multi-Asset Plan" in m.value), "")


def _fresh_dashboard(lang, result=None, **state):
    at = AppTest.from_file("dashboard/app.py", default_timeout=300)
    at.session_state["atlas_lang"] = lang
    if result is not None:
        at.session_state["atlas_result"] = result
    for key, value in state.items():
        at.session_state[key] = value
    at.run()
    return at


def _risk_metrics(at):
    return {m.label: m.value for m in at.metric
            if m.label in ("Questionnaire tier", "Final tier", "Text adjustment")}


def test_report_follows_language_switch(dashboard):
    at = dashboard
    _button(at, "Generate plan").click().run()
    assert not at.exception

    english = _report_text(at)
    assert "Atlas Multi-Asset Plan" in english
    assert len(re.findall(r"[\u4e00-\u9fff]", english)) == 0

    # The plan/report was produced in English; switching the page language must
    # rebuild it instead of showing the cached English markdown.
    result = at.session_state["atlas_result"]

    traditional = _fresh_dashboard("zh-Hant", result)
    assert not traditional.exception
    traditional_text = _report_text(traditional)
    assert "多元資產配置方案" in traditional_text
    assert len(re.findall(r"[\u4e00-\u9fff]", traditional_text)) > 100

    simplified = _fresh_dashboard("zh", result)
    assert not simplified.exception
    simplified_text = _report_text(simplified)
    assert "多元资产配置方案" in simplified_text
    assert "多元資產配置方案" not in simplified_text


def test_free_text_cannot_override_questionnaire_upward(dashboard):
    at = _fresh_dashboard(
        "en",
        atlas_answers_persist={i: 0 for i in range(9)},
        free_text_persist="追求高收益 all in 加杠杆",
    )
    assert not at.exception
    metrics = _risk_metrics(at)
    assert metrics["Questionnaire tier"].startswith("C1")
    assert metrics["Final tier"].startswith("C1")
    assert any("higher tier" in w.value for w in at.warning)
    strategies = next(s for s in at.selectbox if s.key == "strategy_choice")
    assert all("Steady Carry" in o or "Auto" in o for o in strategies.options)


def test_free_text_downgrade_is_explained(dashboard):
    at = _fresh_dashboard(
        "en",
        atlas_answers_persist={i: 2 for i in range(9)},
        free_text_persist="我真的亏不起本金，不能亏",
    )
    assert not at.exception
    metrics = _risk_metrics(at)
    assert metrics["Questionnaire tier"].startswith("C4")
    assert metrics["Final tier"].startswith("C3")
    assert any("more conservative" in i.value for i in at.info)


def test_basing_liquidity_follows_questionnaire_q8(dashboard):
    high = _fresh_dashboard("en", atlas_answers_persist={i: 2 for i in range(9)},
                            atlas_q8=0)
    assert any("Liquidity need" in c.value and "High" in c.value
               for c in high.caption)
    low = _fresh_dashboard("en", atlas_answers_persist={i: 2 for i in range(9)},
                           atlas_q8=3)
    assert any("Liquidity need" in c.value and "Low" in c.value
               for c in low.caption)


def test_basing_rejects_total_assets_below_investable_capital(dashboard):
    at = _fresh_dashboard("en")
    next(n for n in at.number_input if n.key == "ap_capital").set_value(10_000).run()
    _button(at, "Generate basing advice").click().run()
    assert not at.exception
    assert any("cannot be lower than investable capital" in e.value
               for e in at.error)
    assert "atlas_bases" not in at.session_state


def test_stale_result_warning_names_both_tiers(dashboard):
    at = dashboard
    _button(at, "Generate plan").click().run()
    assert not at.exception
    old_tier = at.session_state["atlas_result"]["profile"].tier

    next(t for t in at.text_input if t.key == "free_text").set_value(
        "我真的亏不起本金，不能亏").run()
    assert not at.exception
    new_tier = _risk_metrics(at)["Final tier"].split(" · ")[0]
    assert new_tier != old_tier
    stale = [w.value for w in at.warning
             if "generated for" in w.value and old_tier in w.value
             and new_tier in w.value]
    assert stale


def test_basing_input_change_clears_advice_and_flags_bases(dashboard):
    at = dashboard
    _button(at, "Generate plan").click().run()
    _button(at, "Generate basing advice").click().run()
    assert not at.exception
    _button(at, "Generate final advice").click().run()
    assert not at.exception
    assert "atlas_final_advice" in at.session_state

    next(s for s in at.slider if s.key == "ap_overseas_pct").set_value(20).run()
    assert not at.exception
    assert "atlas_final_advice" not in at.session_state
    assert any("inputs changed" in i.value for i in at.info)
    assert any("regenerate it" in w.value for w in at.warning)


def test_plan_input_change_clears_narrative_outputs(dashboard):
    at = dashboard
    _button(at, "Generate plan").click().run()
    _button(at, "Generate final advice").click().run()
    _button(at, "Convene council").click().run()
    assert "atlas_final_advice" in at.session_state
    assert "atlas_council" in at.session_state

    next(t for t in at.text_input if t.key == "free_text").set_value(
        "我亏不起本金").run()
    assert not at.exception
    assert "atlas_final_advice" not in at.session_state
    assert "atlas_council" not in at.session_state
    assert any("inputs changed" in i.value for i in at.info)


def test_stale_plan_blocks_final_advice_and_council(dashboard):
    at = dashboard
    _button(at, "Generate plan").click().run()
    next(t for t in at.text_input if t.key == "free_text").set_value(
        "我亏不起本金").run()
    _button(at, "Generate final advice").click().run()
    assert not at.exception
    assert "atlas_final_advice" not in at.session_state
    _button(at, "Convene council").click().run()
    assert not at.exception
    assert "atlas_council" not in at.session_state
    assert any("regenerate the plan" in e.value for e in at.error)