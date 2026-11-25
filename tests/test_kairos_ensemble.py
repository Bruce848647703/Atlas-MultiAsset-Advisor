import pytest

from invest_agent.agent import InvestAgent
from invest_agent.integrations import kairos_ensemble, kairos_strategies


def test_ensemble_degrades_without_lab(monkeypatch):
    monkeypatch.setattr(kairos_strategies, "available", lambda: False)
    out = kairos_ensemble.build_ensemble()
    assert out["available"] is False


@pytest.mark.skipif(not kairos_strategies.available()
                    or not kairos_strategies.load_cached(),
                    reason="sibling strategy lab cache not available")
def test_build_ensemble_contract():
    out = kairos_ensemble.build_ensemble(n=3, corr_max=0.9,
                                        method="inverse_vol", force=True)
    assert out["available"] is True
    assert len(out["selected"]) >= 2
    assert out["metrics"]["sharpe"] == out["metrics"]["sharpe"]  # finite
    assert out["latest"]["weights"]
    assert 0 <= out["latest"]["invested"] <= 1.0 + 1e-6
    assert out["latest"]["name"] == kairos_ensemble.ENSEMBLE_NAME


@pytest.mark.skipif(not kairos_strategies.available()
                    or not kairos_strategies.load_cached(),
                    reason="sibling strategy lab cache not available")
def test_ensemble_route_for_satellite():
    info = kairos_strategies.latest_weights(kairos_ensemble.ENSEMBLE_NAME)
    assert info["name"] == kairos_ensemble.ENSEMBLE_NAME
    assert info["weights"]


@pytest.mark.skipif(not kairos_strategies.available()
                    or not kairos_strategies.load_cached(),
                    reason="sibling strategy lab cache not available")
def test_ensemble_satellite_overlay():
    res = InvestAgent().offline_plan(
        {i: 2 for i in range(9)}, capital=600_000,
        satellite_strategy=kairos_ensemble.ENSEMBLE_NAME,
        satellite_budget=0.10)
    sat = res["plan"].satellite
    assert sat is not None
    assert sat["name"] == kairos_ensemble.ENSEMBLE_NAME
    assert abs(res["plan"].weight_vector.sum() - 1) < 1e-6