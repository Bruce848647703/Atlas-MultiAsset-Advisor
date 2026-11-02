import numpy as np
import pandas as pd
import pytest

from invest_agent.data.kairos_provider import KairosProvider
from invest_agent.data.universe import build_universe
from invest_agent.integrations import kairos


def test_status_has_stable_shape():
    status = kairos.status()
    assert set(status) >= {
        "enabled", "root", "available", "packages", "etf_dir",
        "etf_count", "research_dir", "mapped_assets", "n_mapped_assets",
    }
    assert "csi300_etf" in status["mapped_assets"]


def test_research_brief_reads_committed_csvs(tmp_path, monkeypatch):
    (tmp_path / "key_findings.csv").write_text(
        "指标,值,单位,来源仓库,来源文件,备注\n"
        "A股标的数,38,只,kairos-data,universe.py,demo\n",
        encoding="utf-8",
    )
    (tmp_path / "robust_champions.csv").write_text(
        "strategy,channel,robustness_score,rank\n"
        "equal_weight_rebal,allocation,0.79,1\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(kairos, "research_dir", lambda: tmp_path)
    brief = kairos.research_brief(limit=3)
    assert brief["findings"][0]["指标"] == "A股标的数"
    assert brief["champions"][0]["strategy"] == "equal_weight_rebal"


def test_risk_overlay_degrades_without_kairos(monkeypatch):
    monkeypatch.setattr(kairos, "pkg", lambda name: None)
    out = kairos.risk_overlay(
        pd.DataFrame({"a": [0.01] * 24}), np.array([1.0]), ["equity_cn"], ["a"])
    assert out == {}


def test_provider_uses_synthetic_when_data_missing(tmp_path):
    universe = build_universe(include_classes=["equity_cn"])
    provider = KairosProvider(universe=universe, seed=7, n_months=96,
                              data_dir=tmp_path / "empty")
    got = provider.get_monthly_returns([a.id for a in universe], 96)
    assert isinstance(got.index, pd.PeriodIndex)
    assert got.shape == (96, len(universe))
    assert not got.isna().any().any()


def test_provider_reads_real_etf_csv(tmp_path):
    symbol = "sh510300"
    last_month_end = pd.Timestamp.today().replace(day=1) - pd.Timedelta(days=1)
    months = pd.date_range(end=last_month_end.normalize(), periods=36, freq="ME")
    close = 100.0 * (1.01 ** np.arange(len(months)))
    pd.DataFrame({
        "date": months.strftime("%Y-%m-%d"),
        "open": close, "high": close, "low": close, "close": close,
        "volume": 1_000_000,
    }).to_csv(tmp_path / f"{symbol}.csv", index=False)

    universe = [a for a in build_universe() if a.id == "csi300_etf"]
    provider = KairosProvider(universe=universe, seed=7, n_months=96,
                              data_dir=tmp_path)
    got = provider.get_monthly_returns(["csi300_etf"], 96)
    assert list(got.columns) == ["csi300_etf"]
    assert got["csi300_etf"].iloc[-1] == pytest.approx(0.01, rel=1e-3)
    assert not got.isna().any().any()


@pytest.mark.skipif(kairos.pkg("kairos_risk") is None,
                    reason="sibling kairos-risk not installed")
def test_risk_overlay_contract_with_real_kairos():
    universe = build_universe()
    ids = [a.id for a in universe]
    classes = [a.asset_class for a in universe]
    rng = np.random.default_rng(7)
    R = pd.DataFrame(
        rng.normal(0.004, 0.03, size=(96, len(ids))), columns=ids)
    w = np.full(len(ids), 1.0 / len(ids))
    out = kairos.risk_overlay(R, w, classes, ids)
    assert out["source"] == "kairos-risk"
    assert 0 <= out["var_95"] <= out["var_99"]
    assert 0 <= out["es_95"] <= out["es_99"]
    assert out["diversification_ratio"] >= 1.0
    assert 1.0 <= out["effective_n"] <= len(ids)
    assert abs(sum(out["class_risk"].values()) - 1.0) < 1e-6