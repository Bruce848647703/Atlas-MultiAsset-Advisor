from types import SimpleNamespace

from invest_agent.final_advice import (synthesize_final_advice, final_digest,
                                       _apply_geo_tilt, _apply_macro_tilt,
                                       _clip_caps, _pick_base_for_class)


def _mock_plan():
    assets = [
        SimpleNamespace(id="csi300", asset_class="equity_cn", name_zh="沪深300"),
        SimpleNamespace(id="sp500", asset_class="equity_global", name_zh="标普500"),
        SimpleNamespace(id="bond", asset_class="fixed_income", name_zh="债基"),
        SimpleNamespace(id="gold", asset_class="commodity", name_zh="黄金"),
        SimpleNamespace(id="btc", asset_class="crypto", name_zh="比特币"),
    ]
    return SimpleNamespace(
        assets=assets,
        weights={"csi300": 0.30, "sp500": 0.30, "bond": 0.20, "gold": 0.10, "btc": 0.10},
        class_caps={"equity_cn": 0.5, "equity_global": 0.5, "fixed_income": 0.6,
                    "commodity": 0.2, "crypto": 0.2, "cash": 1.0},
        strategy=SimpleNamespace(name_zh="测试策略"),
        expected={"ann_return": 0.08, "ann_vol": 0.12, "sharpe_hint": 0.5},
    )


def test_synthesize_structure_and_sums():
    adv = synthesize_final_advice(_mock_plan(), macro_advice=None, geo=None,
                                  ranked_bases=None)
    assert set(adv) >= {"final_class_weights", "final_asset_weights", "base_map",
                        "overlays", "thesis", "actions", "expected"}
    assert abs(sum(adv["final_class_weights"].values()) - 1.0) < 1e-6
    assert abs(sum(adv["final_asset_weights"].values()) - 1.0) < 1e-6


def test_geo_risk_off_reduces_risky():
    cw = {"equity_cn": 0.4, "equity_global": 0.3, "fixed_income": 0.2, "cash": 0.1}
    geo_off = {"risk_appetite": -0.5}
    geo_on = {"risk_appetite": 0.5}
    off = _apply_geo_tilt(dict(cw), geo_off)
    on = _apply_geo_tilt(dict(cw), geo_on)
    # risk-off: risky down, defensive up
    assert off["equity_cn"] < cw["equity_cn"]
    assert off["fixed_income"] > cw["fixed_income"]
    assert on["equity_cn"] > cw["equity_cn"]
    assert on["fixed_income"] < cw["fixed_income"]


def test_macro_tilt_overweight():
    cw = {"equity_global": 0.5, "fixed_income": 0.5}
    macro = {"advice": [{"class": "equity_global", "stance": "超配"},
                        {"class": "fixed_income", "stance": "低配"}]}
    out = _apply_macro_tilt(dict(cw), macro)
    assert out["equity_global"] > cw["equity_global"]
    assert out["fixed_income"] < cw["fixed_income"]


def test_clip_caps_respects_caps():
    cw = {"equity_cn": 0.9, "crypto": 0.5, "fixed_income": 0.1}
    caps = {"equity_cn": 0.5, "crypto": 0.2, "fixed_income": 0.6}
    out = _clip_caps(cw, caps)
    total = sum(out.values())
    for c, w in out.items():
        assert w <= caps[c] * total + 1e-6


def test_pick_base_for_class():
    from invest_agent.global_base import AssetProfile, recommend_bases
    ap = AssetProfile(asset_types=["a_share", "hk_us_stock", "crypto"],
                      overseas_accounts=["hk"], total_capital=2_000_000, overseas_pct=10)
    ranked = recommend_bases("C4", ap)
    b_eq = _pick_base_for_class("equity_cn", ranked)
    b_crypto = _pick_base_for_class("crypto", ranked)
    assert b_eq is not None
    assert b_crypto is not None and b_crypto["score"] > 0


def test_full_fusion_with_overlays():
    macro = {"advice": [{"class": "equity_global", "stance": "超配"},
                        {"class": "fixed_income", "stance": "低配"},
                        {"class": "equity_cn", "stance": "标配"},
                        {"class": "commodity", "stance": "标配"},
                        {"class": "crypto", "stance": "标配"}],
             "macro_context": {"equity_pe_percentile": 78.0, "china_pmi": "扩张(51.0)"}}
    geo = {"risk_appetite": 0.4, "regime": "风险偏好回升 (risk-on)",
           "themes": [{"theme": "增长/景气"}]}
    from invest_agent.global_base import AssetProfile, recommend_bases
    ap = AssetProfile(asset_types=["a_share", "hk_us_stock", "crypto"],
                      overseas_accounts=["hk"], total_capital=2_000_000, overseas_pct=10)
    ranked = recommend_bases("C4", ap)
    adv = synthesize_final_advice(_mock_plan(), macro, geo, ranked)
    assert adv["base_map"], "base map should be populated"
    assert "risk-on" in adv["overlays"]["geo_regime"]
    d = final_digest(adv)
    assert "最终综合建议" in d and "执行清单" in d
    assert abs(sum(adv["final_class_weights"].values()) - 1.0) < 1e-6
