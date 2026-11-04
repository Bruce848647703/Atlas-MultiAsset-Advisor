from types import SimpleNamespace

import pytest

import invest_agent.factors.factor_store as fs
from invest_agent.integrations import factor_forge
from invest_agent.tools import AdvisorContext, build_tools


def test_status_shape():
    status = factor_forge.status()
    assert {"enabled", "root", "available", "version", "operators"} <= set(status)
    assert "turnover_weighted_price" in status["operators"]


def test_forge_degrades_without_sibling(monkeypatch):
    monkeypatch.setattr(factor_forge, "_module", lambda: None)
    out = factor_forge.forge("anything")
    assert out["available"] is False


@pytest.mark.skipif(not factor_forge.available(),
                    reason="sibling factor-forge not available")
def test_forge_cgo_contract():
    brief = factor_forge.sample_brief("cgo")
    assert brief
    out = factor_forge.forge(brief, source="unit-test")
    assert out["available"] is True
    assert out["factor"]["name"] == "CGO"
    assert out["factor"]["operator"] == "turnover_weighted_price"
    assert out["factor"]["direction"] == -1
    assert "def CGO(" in out["code"]
    assert out["validation"]["ok"] is True


@pytest.mark.skipif(not factor_forge.available(),
                    reason="sibling factor-forge not available")
def test_import_factor_into_store(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "_STORE_PATH", str(tmp_path / "store.json"))
    brief = factor_forge.sample_brief("cgo")
    out = factor_forge.import_to_atlas(brief, source="unit-test")
    assert out["available"] is True
    records = fs.load_store()
    rec = next(r for r in records if r["name"] == "CGO")
    assert rec["source"] == "factor_forge"
    assert rec["direction"] == -1
    assert rec["formula"]
    assert "def CGO(" in rec["code"]
    assert "unit-test" in rec["rationale"]

    tools = {t.name: t for t in build_tools(AdvisorContext())}
    out = tools["get_factor_knowledge"].handler({"query": "CGO"})
    assert any(m["name"] == "CGO" for m in out["matched"])


@pytest.mark.skipif(not factor_forge.available(),
                    reason="sibling factor-forge not available")
def test_evaluate_momentum_on_atlas_panel():
    forged = factor_forge.forge(factor_forge.sample_brief("momentum"),
                                source="unit-test")
    out = factor_forge.evaluate_on_atlas(forged["factor"], forged["code"])
    assert out["available"] is True
    assert out["n_periods"] > 20
    assert out["fields"] == ["close"]
    assert -1 <= out["mean_ic"] <= 1


@pytest.mark.skipif(not factor_forge.available(),
                    reason="sibling factor-forge not available")
def test_evaluate_rejects_daily_only_fields():
    forged = factor_forge.forge(factor_forge.sample_brief("cgo"),
                                source="unit-test")
    out = factor_forge.evaluate_on_atlas(forged["factor"], forged["code"])
    assert out["available"] is False
    assert "turnover" in out["reason"]


def test_forge_pdf_wiring(monkeypatch):
    candidate = SimpleNamespace(score=9.0, text="fake brief", anchor="因子定义")
    fake_mod = SimpleNamespace(pdf_to_briefs=lambda path, top_k: [candidate])
    monkeypatch.setattr(factor_forge, "_module", lambda: fake_mod)
    monkeypatch.setattr(factor_forge, "forge",
                        lambda text, source="", validate=True: {
                            "available": True, "factor": {"name": "X"}, "code": ""})
    out = factor_forge.forge_pdf("fake.pdf")
    assert out["available"] is True
    assert out["n"] == 1
    assert out["briefs"][0]["anchor"] == "因子定义"