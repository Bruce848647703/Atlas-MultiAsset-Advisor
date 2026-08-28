"""Client segmentation (mass / mass-affluent / HNW) and product access.

Encodes the "observations across investor strata":
different capital levels imply different objectives, constraints and
product accessibility — the advisor adapts structure, ticket sizes and
language accordingly.
"""

from __future__ import annotations

from typing import Dict, List

from .config import client_segments
from .risk_profiler import RiskProfile

SEGMENT_ORDER = ["mass", "mass_affluent", "hnw"]

# Strata observations surfaced in reports (professional note).
SEGMENT_INSIGHTS: Dict[str, Dict[str, str]] = {
    "mass": {
        "constraint_zh": "本金规模有限，试错成本高；流动性约束强。",
        "constraint_en": "Limited principal: mistakes are costly; liquidity constraints bind.",
        "strategy_zh": "以指数基金定投构建核心仓位，保留3-6个月应急金，"
                      "卫星仓位不超过10%，优先低费率工具。",
        "strategy_en": "Core via index-fund DCA; keep 3-6m emergency fund; "
                       "satellites <=10%; prefer low-fee instruments.",
    },
    "mass_affluent": {
        "constraint_zh": "处于财富积累期，收入上升但负债(房贷)并存，回撤容忍中等。",
        "constraint_en": "Accumulation phase with rising income and mortgage; moderate drawdown tolerance.",
        "strategy_zh": "核心-卫星-机会三层：宽基核心+黄金/海外卫星+少量机会仓(加密/行业)，"
                      "利用衍生品做保护而非投机。",
        "strategy_en": "Core-satellite-opportunity layers; use derivatives for hedging, not speculation.",
    },
    "hnw": {
        "constraint_zh": "目标是跨周期保值增值与传承；尾部风险与合规成本权重高。",
        "constraint_en": "Cross-cycle preservation and legacy; tail risk and compliance weigh heavily.",
        "strategy_zh": "机构化多资产配置：股债商加密+管理期货分散；"
                      "控制单一资产敞口，考虑税务与代持结构。",
        "strategy_en": "Institutional multi-asset sleeve structure; cap single-name exposure; "
                       "mind tax and custody structures.",
    },
}


def segment_for_capital(capital: float) -> str:
    segs = client_segments()
    for name in SEGMENT_ORDER:
        lo, hi = segs[name]["range"]
        hi = hi if hi is not None else float("inf")
        if lo <= capital < hi:
            return name
    return "hnw"


def accessible_classes(profile: RiskProfile) -> Dict[str, float]:
    """Effective per-class caps = suitability caps intersected with
    segment-level product access and ticket requirements."""
    caps = dict(profile.tier_info["class_caps"])
    seg = client_segments()[segment_for_capital(profile.capital)]
    if not seg.get("allow_crypto", False):
        caps["crypto"] = 0.0
    futures_ok = bool(seg.get("allow_futures", False))
    ticket = seg.get("min_future_ticket")
    if (not futures_ok) or (ticket is not None and profile.capital < float(ticket)):
        caps["futures"] = 0.0
    return caps


def segment_insight(profile: RiskProfile) -> Dict[str, str]:
    return SEGMENT_INSIGHTS[segment_for_capital(profile.capital)]


def describe(profile: RiskProfile, lang: str = "zh") -> str:
    seg = segment_for_capital(profile.capital)
    info = SEGMENT_INSIGHTS[seg]
    seg_info = client_segments()[seg]
    if lang == "zh":
        return (
            f"客群分层: {seg_info['label_zh']}（可投资本 ¥{profile.capital:,.0f}）；"
            f"适当性等级: {profile.tier_info['label_zh']}(评分{profile.score:.0f})。\n"
            f"客群观察: {info['constraint_zh']}\n"
            f"建议框架: {info['strategy_zh']}"
        )
    return (
        f"Segment: {seg_info['label_en']} (investable capital {profile.capital:,.0f} CNY); "
        f"suitability tier: {profile.tier_info['label_en']} (score {profile.score:.0f}).\n"
        f"Strata observation: {info['constraint_en']}\n"
        f"Framework: {info['strategy_en']}"
    )
