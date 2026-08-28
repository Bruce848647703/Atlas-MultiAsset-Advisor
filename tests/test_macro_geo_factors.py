import numpy as np
import pandas as pd
import pytest


def test_geo_topic_tagging():
    from invest_agent.geopolitics import _tag_topics
    t = _tag_topics("美联储宣布降息，全球市场反弹")
    assert "央行/利率" in t
    t2 = _tag_topics("地区冲突升级，避险情绪升温")
    assert "地缘冲突" in t2


def test_geo_assessment_offline_pack():
    from invest_agent.geopolitics import assess_global_situation
    pack = {"generated_at": "x", "sources_ok": [], "items": [
        {"title": "美联储降息利好市场", "topics": ["央行/利率"]},
        {"title": "经济复苏增长回暖", "topics": ["增长/景气"]},
        {"title": "地缘冲突升级避险", "topics": ["地缘冲突"]},
    ]}
    a = assess_global_situation(pack)
    assert -1.0 <= a["risk_appetite"] <= 1.0
    assert a["regime"] in ("风险偏好回升 (risk-on)", "避险情绪主导 (risk-off)", "中性/观望")
    assert isinstance(a["themes"], list)


def test_geo_digest_format():
    from invest_agent.geopolitics import assess_global_situation, situation_digest
    pack = {"generated_at": "x", "sources_ok": [], "items": [
        {"title": "央行降息", "topics": ["央行/利率"]},
    ]}
    d = situation_digest(assess_global_situation(pack))
    assert "全球政经局势" in d and "研判" in d


def test_macro_advice_structure():
    from invest_agent.macro_advice import generate_macro_advice
    adv = generate_macro_advice(provider_name="synthetic", months=48)
    assert set(adv) >= {"advice", "sector_tilt", "macro_context", "narrative"}
    classes = {a["class"] for a in adv["advice"]}
    assert {"equity_cn", "equity_global", "fixed_income", "crypto"} <= classes
    for a in adv["advice"]:
        assert a["stance"] in ("超配", "标配", "低配")
        assert -2.0 <= a["score"] <= 2.0
    assert "style" in adv["sector_tilt"]
    assert len(adv["narrative"]) > 20


def test_factor_store_add_dedup(tmp_path, monkeypatch):
    import invest_agent.factors.factor_store as fs
    monkeypatch.setattr(fs, "_STORE_PATH", str(tmp_path / "store.json"))
    fs.add_factor("mom", "动量", "empirical", name_cn="动量", ic=0.05)
    fs.add_factor("mom", "动量", "empirical", name_cn="动量", ic=0.08)  # dup -> refresh IC
    fs.add_factor("rev", "反转", "empirical", name_cn="反转", ic=0.3)
    store = fs.load_store()
    assert len(store) == 2
    mom = next(f for f in store if f["name"] == "mom")
    assert mom["ic"] == 0.08
    st = fs.stats()
    assert st["total"] == 2 and st["with_ic"] == 2


def test_empirical_factor_ic_shape():
    from invest_agent.factors.factor_evolution import measure_factor_ic
    idx = pd.period_range("2018-01", periods=60, freq="M")
    rng = np.random.default_rng(0)
    df = pd.DataFrame(rng.normal(0.005, 0.05, (60, 12)), index=idx,
                      columns=[f"a{i}" for i in range(12)])
    ic = measure_factor_ic("momentum_12_1", df)
    assert np.isfinite(ic) and -1.0 <= ic <= 1.0


def test_evolve_persists_factors(tmp_path, monkeypatch):
    import invest_agent.factors.factor_store as fs
    monkeypatch.setattr(fs, "_STORE_PATH", str(tmp_path / "store.json"))
    import invest_agent.factors.factor_evolution as fe
    learned = fe.learn_empirical_factors(provider_name="synthetic", months=60)
    assert len(learned) >= 1
    st = fs.stats()
    assert st["total"] >= 1 and st["by_source"].get("empirical", 0) >= 1


def test_factor_theme_matching():
    from invest_agent.factors.factor_evolution import match_factor_theme
    assert match_factor_theme("高股息价值凸显，低估值修复") == "momentum" or \
        match_factor_theme("高股息价值凸显，低估值修复") in ("value", "momentum")
    assert match_factor_theme("低波动策略穿越震荡市") == "low_volatility"
    assert match_factor_theme("景气度向上，业绩高增长") in ("growth", "momentum")
    assert match_factor_theme("公司发布日常经营公告") is None


def test_evolution_state_roundtrip(tmp_path, monkeypatch):
    import invest_agent.factors.factor_evolution as fe
    monkeypatch.setattr(fe, "_STATE_PATH", str(tmp_path / "state.json"))
    st0 = fe.read_state()
    assert st0["last_run"] is None and st0["cycles"] == 0
    fe.write_state({"last_run": "2026-01-01T00:00:00", "cycles": 3, "history": []})
    st1 = fe.read_state()
    assert st1["cycles"] == 3 and st1["last_run"].startswith("2026")
    assert fe.hours_since_last_run() is not None


def test_maybe_autolearn_noop_when_fresh(tmp_path, monkeypatch):
    import invest_agent.factors.factor_evolution as fe
    from datetime import datetime
    monkeypatch.setattr(fe, "_STATE_PATH", str(tmp_path / "state.json"))
    fe.write_state({"last_run": datetime.now().isoformat(timespec="seconds"),
                    "cycles": 1, "history": []})
    res = fe.maybe_autolearn(threshold_hours=24.0)
    assert res["triggered"] is False      # recent run -> no spawn


def test_pdf_miner_concept_mining():
    from invest_agent.factors.report_pdf_miner import mine_factors_from_text
    text = ("公司估值处于低位，市盈率具备吸引力。"
            "高股息带来稳定股东回报，红利属性突出。"
            "行业景气度向上，业绩增长确定性强。"
            "本报告构建了一个动量因子，计算过去12个月收益。")
    found = mine_factors_from_text(text, "测试报告")
    assert "value" in found["concepts"]
    assert "dividend" in found["concepts"]
    assert "growth" in found["concepts"]
    assert len(found["literal"]) >= 1            # has explicit 因子 sentence
    assert any("动量因子" in n for n in found["names"])


def test_pdf_miner_empty_text():
    from invest_agent.factors.report_pdf_miner import mine_factors_from_text
    found = mine_factors_from_text("", "x")
    assert found["literal"] == [] and found["concepts"] == {} and found["names"] == []


def test_scan_factor_reports_url_and_filter(monkeypatch):
    import invest_agent.factors.report_pdf_miner as rpm

    class _FakeResp:
        def __init__(self, data):
            self._d = data
        def json(self):
            return self._d

    fake = {"data": [
        {"title": "多因子选股模型月度跟踪", "infoCode": "AP123",
         "orgSName": "测试证券", "publishDate": "2026-08-01 00:00:00.000"},
        {"title": "某公司中报点评", "infoCode": "AP456",
         "orgSName": "测试证券", "publishDate": "2026-08-02 00:00:00.000"},
        {"title": "金融工程：动量因子表现复盘", "infoCode": "AP789",
         "orgSName": "测试证券", "publishDate": "2026-08-03 00:00:00.000"},
    ]}
    monkeypatch.setattr(rpm.requests if hasattr(rpm, "requests") else rpm,
                        "requests", type("M", (), {"get": staticmethod(
                            lambda *a, **k: _FakeResp(fake))}), raising=False)
    # patch requests import inside the function
    import types
    fake_mod = types.ModuleType("requests")
    fake_mod.get = lambda *a, **k: _FakeResp(fake)
    monkeypatch.setitem(__import__("sys").modules, "requests", fake_mod)

    rows = rpm.scan_factor_reports(pages_per_type=1, size=10, qtypes=["0"])
    titles = [r["title"] for r in rows]
    assert any("多因子" in t for t in titles)
    assert any("金融工程" in t for t in titles)
    assert not any("中报点评" in t for t in titles)   # non-factor report filtered out
    for r in rows:
        assert r["pdf_url"] == rpm._PDF_URL.format(infoCode=r["infoCode"])
