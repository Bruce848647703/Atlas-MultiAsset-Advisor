import numpy as np
import pandas as pd

from invest_agent.factors.loader import (
    FactorCatalog, _direction_of, load_catalog,
)
from invest_agent.factors.lens import compute_factor_scores, screen_universe
from invest_agent.data.universe import build_universe
from invest_agent.data import get_provider


def test_direction_mining():
    assert _direction_of("该因子与未来收益正相关") == 1
    assert _direction_of("因子值越大，未来收益越低，负相关") == -1
    assert _direction_of("没有方向信息") == 0
    # conflicting -> unknown
    assert _direction_of("正相关，但某些情况下负相关") == 0


def test_load_missing_dir_returns_empty():
    cat = load_catalog("/nonexistent/path/xyz")
    assert isinstance(cat, FactorCatalog)
    assert len(cat.factors) == 0
    assert cat.n_records == 0


def test_catalog_search_and_summary(tmp_path):
    import json
    d = tmp_path / "2020"
    d.mkdir()
    sig = {
        "year": 2020, "page_no": 1, "image_file": "x", "calendar_month": "2020-01",
        "calendar_dates": ["2020-01-01"],
        "signals": [
            {"date": "2020-01-01", "signal_name_cn": "测试动量因子",
             "signal_type_cn": "动量因子", "manual_factor_name": "TMOM",
             "formula": "r_t", "variables": [],
             "raw_text": "动量因子，与未来收益正相关", "confidence_note": "清晰"},
            {"date": "2020-01-01", "signal_name_cn": "低波动因子",
             "signal_type_cn": "波动率因子", "manual_factor_name": "LVOL",
             "formula": "sigma", "variables": [],
             "raw_text": "低波动，与未来收益负相关", "confidence_note": "清晰"},
        ],
        "page_raw_text": "", "warnings": [],
    }
    (d / "page_0001.json").write_text(json.dumps(sig, ensure_ascii=False))
    cat = load_catalog(str(tmp_path))
    assert len(cat.factors) == 2
    assert cat.factors["TMOM"].direction == 1
    assert cat.factors["LVOL"].direction == -1
    hits = cat.search("动量")
    assert any(f.name == "TMOM" for f in hits)
    assert {c["category"] for c in cat.category_summary()} == {"动量因子", "波动率因子"}


def _monthly_df(n=48):
    rng = np.random.default_rng(3)
    idx = pd.period_range("2020-01", periods=n, freq="M")
    a = rng.normal(0.010, 0.03, n)          # steady winner
    b = rng.normal(0.002, 0.10, n)          # volatile
    c = np.concatenate([np.full(n - 6, 0.008), np.full(6, -0.05)])  # crash recently
    return pd.DataFrame({"a": a, "b": b, "c": c}, index=idx)


def test_factor_scores_ranking_sane():
    df = _monthly_df()
    sc = compute_factor_scores(df)
    order = list(sc.index)
    assert order[0] == "a"       # steady low-vol winner ranks first
    assert order[-1] == "b"      # high-vol negative-momentum asset ranks last
    assert {"momentum", "reversal_1m", "low_vol", "drawdown", "score"} <= set(sc.columns)


def test_screen_universe_provenance():
    uni = build_universe()
    ids = [a.id for a in uni]
    R = get_provider("synthetic").get_monthly_returns(ids, 60)
    res = screen_universe(R, uni, catalog=None)
    assert len(res["ranked"]) == len(ids)
    assert len(res["factors"]) == 7
    assert res["live_data_used"] is False
    scores = [r["score"] for r in res["ranked"]]
    assert scores == sorted(scores, reverse=True)
    for r in res["ranked"]:
        assert abs(r["score"]) < 10  # z-score composite stays bounded


def test_live_enrichment_changes_scores():
    """Assets with live factor data get renormalized composites."""
    idx = pd.period_range("2020-01", periods=40, freq="M")
    rng = np.random.default_rng(7)
    df = pd.DataFrame({
        "etf_a": rng.normal(0.008, 0.04, 40),
        "etf_b": rng.normal(0.008, 0.04, 40),
        "fund_c": rng.normal(0.004, 0.01, 40),
    }, index=idx)
    # no enrichment: all equal coverage
    sc0 = compute_factor_scores(df, enrichment=None)
    assert (sc0["n_live_factors"] == 0).all()
    # enrichment only for etf_a/etf_b -> they gain live factors, fund_c doesn't
    enrich = pd.DataFrame({
        "pe_percentile": [20.0, 80.0],
        "turnover_amount": [5e9, 1e8],
        "main_net_inflow_pct": [5.0, -5.0],
    }, index=["etf_a", "etf_b"])
    sc1 = compute_factor_scores(df, enrichment=enrich)
    assert sc1.loc["etf_a", "n_live_factors"] == 3
    assert sc1.loc["etf_b", "n_live_factors"] == 3
    assert sc1.loc["fund_c", "n_live_factors"] == 0
    # etf_a: cheap + liquid + inflow must beat etf_b: expensive + outflow
    assert sc1.loc["etf_a", "score"] > sc1.loc["etf_b", "score"]


def test_enrich_degrades_offline(monkeypatch):
    import invest_agent.factors.enrich as en

    def boom(*a, **k):
        raise RuntimeError("offline")
    monkeypatch.setattr(en, "fetch_etf_live_factors", boom)
    monkeypatch.setattr(en, "fetch_index_pe_percentile", boom)
    uni = build_universe()
    out = en.enrich_universe(uni)
    assert out.empty
