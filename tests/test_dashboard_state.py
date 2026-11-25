"""Dashboard state regressions (real Streamlit script runs, network stubbed)."""

import re

import pandas as pd
import pytest

from streamlit.testing.v1 import AppTest


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


def _fresh_dashboard(lang, result):
    at = AppTest.from_file("dashboard/app.py", default_timeout=300)
    at.session_state["atlas_lang"] = lang
    at.session_state["atlas_result"] = result
    at.run()
    return at


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