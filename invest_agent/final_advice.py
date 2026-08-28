"""Final integrated advice — the organic fusion layer.

Combines four previously-separate pillars into ONE coherent, trend-aligned
recommendation (family-office style):

  1. quant plan        — the optimizer's allocation (the foundation)
  2. macro advice      — asset-class over/underweight views
  3. global situation  — risk-on / risk-off regime overlay
  4. global bases      — where each asset class is domiciled (friction-aware)

The fusion tilts the quant class-weights by the macro stance and the geopolitical
regime, renormalizes under suitability caps, redistributes within classes, maps
each class to its best base, and emits a single thesis + action list.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .global_base import GLOBAL_BASES

# ---------------------------------------------------------------------------
# class -> base-support tags (to pick the best base per asset class)
# ---------------------------------------------------------------------------
CLASS_TO_BASE_TAGS = {
    "equity_cn":     ["equity_cn"],
    "equity_global": ["equity_global", "equity_us", "equity_hk", "fund"],
    "fixed_income":  ["bond", "money", "bond_cn"],
    "cash":          ["money"],
    "hybrid":        ["fund", "wm"],
    "commodity":     ["commodity", "fund"],
    "crypto":        ["crypto"],
    "futures":       ["fund"],
}

RISKY_CLASSES = {"equity_cn", "equity_global", "crypto"}
DEFENSIVE_CLASSES = {"fixed_income", "cash"}

_STANCE_MULT = {"超配": 1.22, "标配": 1.0, "低配": 0.68}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _class_weights_from_plan(plan) -> Dict[str, float]:
    cw: Dict[str, float] = {}
    for a_id, w in plan.weights.items():
        cls = next(a.asset_class for a in plan.assets if a.id == a_id)
        cw[cls] = cw.get(cls, 0.0) + w
    return cw


def _apply_macro_tilt(cw: Dict[str, float], macro: Optional[Dict]) -> Dict[str, float]:
    if not macro:
        return cw
    stance_by_class = {a["class"]: a["stance"] for a in macro.get("advice", [])}
    out = {}
    for c, w in cw.items():
        mult = _STANCE_MULT.get(stance_by_class.get(c, "标配"), 1.0)
        out[c] = w * mult
    return out


def _apply_geo_tilt(cw: Dict[str, float], geo: Optional[Dict]) -> Dict[str, float]:
    if not geo:
        return cw
    appetite = float(geo.get("risk_appetite", 0.0))
    out = dict(cw)
    if appetite > 0.15:                      # risk-on: lean into risk assets
        for c in out:
            if c in RISKY_CLASSES:
                out[c] *= 1.12
            elif c in DEFENSIVE_CLASSES:
                out[c] *= 0.92
    elif appetite < -0.15:                   # risk-off: de-risk + hedge
        for c in out:
            if c in RISKY_CLASSES:
                out[c] *= 0.85
            elif c in DEFENSIVE_CLASSES:
                out[c] *= 1.15
            elif c == "commodity":           # gold as hedge
                out[c] *= 1.10
    return out


def _clip_caps(cw: Dict[str, float], caps: Dict[str, float]) -> Dict[str, float]:
    """Clip each class to its suitability cap and renormalize (water-fill)."""
    cw = {c: max(w, 0.0) for c, w in cw.items()}
    for _ in range(30):
        total = sum(cw.values())
        if total <= 0:
            return cw
        over = {c: w for c, w in cw.items() if c in caps and w > caps[c] * total + 1e-9}
        if not over:
            break
        for c in over:
            excess = cw[c] - caps[c] * total
            cw[c] = caps[c] * total
            others = [k for k in cw if k != c and (k not in caps or cw[k] < caps[k] * total)]
            if others:
                share = excess / len(others)
                for k in others:
                    cw[k] += share
    total = sum(cw.values())
    return {c: w / total for c, w in cw.items()} if total > 0 else cw


def _redistribute_to_assets(cw: Dict[str, float], plan) -> Dict[str, float]:
    """Spread each class's final weight across its assets, preserving the quant
    plan's within-class ratios where available."""
    by_class: Dict[str, Dict[str, float]] = {}
    for a in plan.assets:
        by_class.setdefault(a.asset_class, {})[a.id] = plan.weights.get(a.id, 0.0)
    final_assets: Dict[str, float] = {}
    for cls, target in cw.items():
        if target <= 1e-6:
            continue
        members = by_class.get(cls, {})
        positive = {k: v for k, v in members.items() if v > 1e-9}
        if positive:
            tot = sum(positive.values())
            for k, v in positive.items():
                final_assets[k] = final_assets.get(k, 0.0) + target * (v / tot)
        elif members:                        # class has assets but 0 quant weight
            each = target / len(members)
            for k in members:
                final_assets[k] = final_assets.get(k, 0.0) + each
    return final_assets


def _pick_base_for_class(cls: str, ranked_bases: List[Dict]) -> Optional[Dict]:
    tags = set(CLASS_TO_BASE_TAGS.get(cls, []))
    if not tags:
        return None
    base_supports = {b.id: set(b.supports) for b in GLOBAL_BASES}
    for r in ranked_bases:                  # ranked_bases already sorted by score
        sup = base_supports.get(r["id"], set())
        if sup & tags and r["score"] > 0:
            return r
    return None


# ---------------------------------------------------------------------------
# main synthesis
# ---------------------------------------------------------------------------
def synthesize_final_advice(plan, macro_advice=None, geo=None,
                            ranked_bases=None) -> Dict:
    """Fuse quant plan + macro views + geopolitical regime + global bases into
    one final, trend-aligned recommendation."""
    cw = _class_weights_from_plan(plan)
    cw = _apply_macro_tilt(cw, macro_advice)
    cw = _apply_geo_tilt(cw, geo)
    cw = _clip_caps(cw, plan.class_caps)
    # renormalize after clipping
    tot = sum(cw.values())
    if tot > 0:
        cw = {c: w / tot for c, w in cw.items()}
    final_assets = _redistribute_to_assets(cw, plan)

    # base mapping per class
    base_map = {}
    if ranked_bases:
        for cls in cw:
            if cw.get(cls, 0) <= 1e-6:
                continue
            b = _pick_base_for_class(cls, ranked_bases)
            if b:
                base_map[cls] = {"base": b["name_zh"], "category": b["category"],
                                 "score": b["score"], "friction": b["friction"]}

    # thesis narrative
    regime = (geo or {}).get("regime", "未知")
    appetite = (geo or {}).get("risk_appetite", 0.0)
    themes = "、".join(t["theme"] for t in (geo or {}).get("themes", [])[:3]) or "—"
    macro_over = [a.get("name", a.get("class", "")) for a in (macro_advice or {}).get("advice", [])
                  if a["stance"] == "超配"]
    macro_under = [a.get("name", a.get("class", "")) for a in (macro_advice or {}).get("advice", [])
                   if a["stance"] == "低配"]
    pe_pct = (macro_advice or {}).get("macro_context", {}).get("equity_pe_percentile")
    pmi = (macro_advice or {}).get("macro_context", {}).get("china_pmi")

    thesis_lines = [
        f"全球局势研判「{regime}」(风险偏好 {appetite:+.2f}，主导议题: {themes})，"
        f"国内宏观 {pmi or '—'}" + (f"，A股估值处近10年 {pe_pct:.0f}% 分位" if pe_pct else "") + "。",
    ]
    if macro_over:
        thesis_lines.append(f"结合大类观点超配 {'、'.join(macro_over)}"
                            + (f"，低配 {'、'.join(macro_under)}。" if macro_under else "。"))
    thesis_lines.append(
        f"在上述研判下对量化基础配置(策略: {plan.strategy.name_zh})做了有机倾斜，"
        f"并按适当性上限约束、落到摩擦最优的全球 base。")
    if base_map:
        place = "；".join(f"{c}→{v['base']}" for c, v in list(base_map.items())[:4])
        thesis_lines.append(f"落位: {place}。")

    # actions
    actions = []
    top_assets = sorted(final_assets.items(), key=lambda kv: -kv[1])[:5]
    name_of = {a.id: a.name_zh for a in plan.assets}
    for a_id, w in top_assets:
        cls = next(a.asset_class for a in plan.assets if a.id == a_id)
        bm = base_map.get(cls)
        where = f"(落位: {bm['base']})" if bm else ""
        actions.append(f"{name_of[a_id]} 配 {w:.1%} {where}")

    return {
        "strategy": plan.strategy.name_zh,
        "final_class_weights": {c: w for c, w in sorted(cw.items(), key=lambda kv: -kv[1])},
        "final_asset_weights": {k: v for k, v in final_assets.items()},
        "base_map": base_map,
        "overlays": {
            "macro_stance": {a["class"]: a["stance"] for a in (macro_advice or {}).get("advice", [])},
            "geo_regime": regime, "geo_appetite": appetite, "geo_themes": themes,
        },
        "thesis": "".join(thesis_lines),
        "actions": actions,
        "expected": plan.expected,
    }


def final_digest(advice: Dict) -> str:
    lines = ["【最终综合建议 · 量化×大类×地缘×落位 有机融合】", advice["thesis"], "执行清单:"]
    for i, a in enumerate(advice["actions"], 1):
        lines.append(f"  {i}. {a}")
    lines.append("免责: 以上为量化模型与新闻情绪融合的研究性建议，不构成投资意见；"
                 "市场有风险，投资需谨慎。")
    return "\n".join(lines)


def build_final_advice(plan, profile, asset_profile=None,
                       provider_name: str = "merged") -> Dict:
    """One-stop: compute macro advice + geopolitical situation + global bases,
    then fuse with the quant plan into the final integrated advice. Each pillar
    degrades gracefully if its data source is unavailable."""
    from .macro_advice import generate_macro_advice
    from .geopolitics import assess_global_situation, fetch_global_news
    from .global_base import AssetProfile, recommend_bases

    try:
        macro = generate_macro_advice(provider_name=provider_name, months=60)
    except Exception:  # noqa: BLE001
        macro = None
    try:
        geo = assess_global_situation(fetch_global_news(max_items=40))
    except Exception:  # noqa: BLE001
        geo = None
    ranked_bases = None
    try:
        ap = asset_profile or AssetProfile(
            asset_types=["cash_deposit", "cn_fund"],
            total_capital=profile.capital or 0.0)
        ranked_bases = recommend_bases(profile.tier, ap)
    except Exception:  # noqa: BLE001
        ranked_bases = None

    advice = synthesize_final_advice(plan, macro, geo, ranked_bases)
    advice["digest"] = final_digest(advice)
    return advice
