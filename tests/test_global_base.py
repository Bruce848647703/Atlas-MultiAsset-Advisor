from invest_agent.global_base import (AssetProfile, GLOBAL_BASES, base_digest,
                                      base_friction, recommend_bases)


def _profile(**kw):
    base = dict(asset_types=["cash_deposit", "cn_fund"], overseas_pct=0,
                overseas_accounts=["none"], total_capital=500_000)
    base.update(kw)
    return AssetProfile(**base)


def test_catalog_friction_bounded():
    for b in GLOBAL_BASES:
        f = base_friction(b)
        assert 0.0 <= f <= 1.0
        assert b.min_capital >= 0


def test_recommend_sorted_and_structured():
    ranked = recommend_bases("C3", _profile())
    assert len(ranked) == len(GLOBAL_BASES)
    scores = [r["score"] for r in ranked]
    assert scores == sorted(scores, reverse=True)
    for r in ranked:
        assert set(r) >= {"id", "name_zh", "category", "score", "friction",
                          "fit_breakdown", "reasons", "min_capital"}
        assert 0 <= r["score"] <= 100


def test_low_friction_onshore_ranks_high_for_mass():
    ranked = recommend_bases("C3", _profile(total_capital=300_000))
    top3_ids = [r["id"] for r in ranked[:3]]
    # a pure-onshore mass investor should see onshore bases on top
    assert any(recommend_bases("C3", _profile())[i]["category"] == "onshore"
               for i in range(3))


def test_offshore_needs_experience():
    p_no = _profile(asset_types=["hk_us_stock"], overseas_accounts=["none"],
                    overseas_pct=0, total_capital=2_000_000)
    p_yes = _profile(asset_types=["hk_us_stock"], overseas_accounts=["hk"],
                     overseas_pct=15, total_capital=2_000_000)
    r_no = {r["id"]: r for r in recommend_bases("C4", p_no)}
    r_yes = {r["id"]: r for r in recommend_bases("C4", p_yes)}
    # with overseas experience/account the HK brokerage scores higher
    assert r_yes["hk_brokerage"]["score"] >= r_no["hk_brokerage"]["score"]


def test_capital_threshold_gating():
    poor = _profile(total_capital=100_000)
    rich = _profile(total_capital=20_000_000)
    rp = {r["id"]: r for r in recommend_bases("C4", poor)}
    rr = {r["id"]: r for r in recommend_bases("C4", rich)}
    # Singapore family office (10M threshold) scores higher for the rich
    assert rr["sg_family_office"]["score"] > rp["sg_family_office"]["score"]


def test_digest_format():
    ranked = recommend_bases("C3", _profile())
    d = base_digest(ranked, top_n=3)
    assert "全球资产落位建议" in d and "评分" in d
    assert d.count("评分") >= 1


def test_crypto_base_tier_gated():
    p = _profile(asset_types=["crypto"], crypto_held=True, total_capital=500_000,
                 overseas_accounts=["hk"])
    r_c1 = {r["id"]: r for r in recommend_bases("C1", p)}
    r_c5 = {r["id"]: r for r in recommend_bases("C5", p)}
    # crypto exchange is tier-gated to C4-C5, so C1 scores it lower
    assert r_c5["crypto_exchange"]["score"] >= r_c1["crypto_exchange"]["score"]


def test_overseas_intent_boosts_offshore():
    """100% intended overseas allocation must rank offshore/crossborder bases
    above pure-onshore ones (bank WM cannot hold overseas assets)."""
    p_full = _profile(asset_types=["cash_deposit", "hk_us_stock", "overseas_fund"],
                      overseas_pct=100, overseas_accounts=["hk"], total_capital=3_000_000)
    ranked = recommend_bases("C4", p_full)
    top_cat = [r["category"] for r in ranked[:3]]
    assert "onshore" not in top_cat, "onshore should not dominate at 100% overseas"
    assert any(c in ("offshore", "crossborder") for c in top_cat)
    # offshore base scores higher with 100% overseas than with 0%
    p_zero = _profile(asset_types=["cash_deposit", "hk_us_stock", "overseas_fund"],
                      overseas_pct=0, overseas_accounts=["hk"], total_capital=3_000_000)
    r_full = {r["id"]: r for r in ranked}
    r_zero = {r["id"]: r for r in recommend_bases("C4", p_zero)}
    assert r_full["hk_brokerage"]["score"] > r_zero["hk_brokerage"]["score"]
    assert r_full["bank_wm_deposit"]["score"] < r_zero["bank_wm_deposit"]["score"]
