import pytest

import invest_agent.factors.custom as custom
import invest_agent.factors.factor_store as fs
from invest_agent.integrations import factor_forge


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "_STORE_PATH", str(tmp_path / "store.json"))
    monkeypatch.setattr(custom, "_CACHE", tmp_path / "custom.json")


def test_no_forged_factors(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    out = custom.compute(force=True)
    assert out["available"] is False


@pytest.mark.skipif(not factor_forge.available(),
                    reason="sibling factor-forge not available")
def test_compute_composite_from_forged_factor(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    forged = factor_forge.forge(factor_forge.sample_brief("momentum"),
                                source="unit-test")
    factor_forge.import_factor(forged["factor"], forged["code"], source="unit-test")
    out = custom.compute(force=True)
    assert out["available"] is True
    assert out["n_factors"] == 1
    assert out["factors"][0]["name"] == "MOM"
    assert len(out["ranked"]) == 26
    assert all(isinstance(r["score"], float) for r in out["ranked"])
    assert custom.summary()["top_assets"]


@pytest.mark.skipif(not factor_forge.available(),
                    reason="sibling factor-forge not available")
def test_daily_only_factor_is_skipped(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    forged = factor_forge.forge(factor_forge.sample_brief("cgo"),
                                source="unit-test")
    factor_forge.import_factor(forged["factor"], forged["code"], source="unit-test")
    out = custom.compute(force=True)
    assert out["available"] is False
    assert out["factors"][0]["name"] == "CGO"
    assert out["factors"][0]["available"] is False