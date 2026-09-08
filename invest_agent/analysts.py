"""Analyst council — a virtual panel of ~30 investment legends / archetypes.

Each analyst is a persona with a distinct school, philosophy, asset focus and
market-regime affinity. Given the current plan + macro/geopolitical context, we
score every analyst for DIRECTIONAL MATCH and pick the top-N (default 5) whose
lens is most relevant, then render each one's view on the current allocation.

This is a "mixture of experts / council" layer: it does not replace the quant
optimizer — it adds human-style judgment, dissent and framing on top of it.
All output is deterministic (rule/keyword driven) and clearly attributed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

RISKY = {"equity_cn", "equity_global", "crypto", "futures"}
DEFENSIVE = {"fixed_income", "cash"}
HEDGE = {"commodity"}


@dataclass
class Analyst:
    id: str
    name_zh: str
    name_en: str
    school: str                    # 流派
    philosophy: str                # 一句话核心信念
    lens: str                      # 分析视角
    focus_classes: List[str] = field(default_factory=list)  # asset classes they weigh
    regimes: List[str] = field(default_factory=lambda: ["neutral"])
    tags: List[str] = field(default_factory=list)
    signature: str = ""            # 名言/原则
    contrarian: bool = False       # buys max pessimism
    crypto_friendly: bool = False
    quant: bool = False


# ---------------------------------------------------------------------------
# Registry: ~30 legends & archetypes (research/education; public philosophies)
# ---------------------------------------------------------------------------
REGISTRY: List[Analyst] = [
    Analyst("simons", "吉姆·西蒙斯", "Jim Simons", "量化统计套利",
            "市场存在微弱但可重复的统计规律，用模型而非直觉交易。",
            "从量价与因子数据中挖掘统计边际，纪律化执行。",
            ["equity_cn", "equity_global", "futures"], ["risk-on", "neutral"],
            ["quant", "momentum", "high_freq"], "我不预测市场，我识别模式。", quant=True),
    Analyst("thorp", "爱德华·索普", "Ed Thorp", "量化/凯利公式",
            "找到正的期望边际，再用凯利公式控制下注规模。",
            "统计优势 + 仓位管理，避免爆仓。",
            ["equity_global", "crypto"], ["neutral"],
            ["quant", "position_sizing"], "战胜市场的同时，先保证不出局。",
            crypto_friendly=True, quant=True),
    Analyst("asness", "克里夫·阿斯内斯", "Cliff Asness", "因子投资",
            "价值与动量长期有效，且低相关，应组合持有。",
            "跨资产做多因子，忍受短期难受。",
            ["equity_global", "equity_cn", "commodity"], ["neutral", "risk-on"],
            ["factor", "value", "momentum"], "好的因子投资有时很痛苦。", quant=True),
    Analyst("buffett", "沃伦·巴菲特", "Warren Buffett", "价值/护城河",
            "以合理价格买入优秀企业并长期持有。",
            "生意质量、护城河、安全边际、长期复利。",
            ["equity_cn", "equity_global"], ["neutral", "risk-off"],
            ["value", "quality", "long_term"], "别人贪婪我恐惧。"),
    Analyst("munger", "查理·芒格", "Charlie Munger", "质量/多元思维",
            "以合理价格买伟大公司，胜过以便宜价格买平庸公司。",
            "多元思维模型、集中投资、避免愚蠢。",
            ["equity_global", "equity_cn"], ["neutral"],
            ["quality", "concentration"], "反过来想，总是反过来想。"),
    Analyst("graham", "本杰明·格雷厄姆", "Benjamin Graham", "深度价值",
            "安全边际是投资的基石，买得便宜胜过买得好故事。",
            "估值、账面价值、防御性配置。",
            ["equity_cn", "equity_global", "fixed_income"], ["risk-off", "neutral"],
            ["value", "defensive"], "市场短期是投票机，长期是称重机。"),
    Analyst("lynch", "彼得·林奇", "Peter Lynch", "GARP 成长",
            "以合理价格买成长，投资你了解的公司。",
            "自下而上、PEG、成长确定性。",
            ["equity_cn", "equity_global"], ["risk-on", "neutral"],
            ["growth", "bottom_up"], "了解你所拥有的，并清楚为什么拥有它。"),
    Analyst("fisher", "菲利普·费雪", "Philip Fisher", "成长调研",
            "买入真正优秀的成长股并长期持有，深入调研。",
            "管理层、研发、长期成长空间。",
            ["equity_global", "equity_cn"], ["risk-on"],
            ["growth", "long_term"], "寻找卓越普通股。"),
    Analyst("oneil", "威廉·欧奈尔", "William O'Neil", "成长动量 CANSLIM",
            "买入创新高、盈利加速的强势股，及时止损。",
            "基本面 + 技术面共振，相对强度。",
            ["equity_cn", "equity_global"], ["risk-on"],
            ["momentum", "growth"], "让利润奔跑，快速止损。"),
    Analyst("livermore", "杰西·利弗莫尔", "Jesse Livermore", "趋势交易",
            "顺势而为，等待关键点，错了就认。",
            "价格趋势、突破、纪律止损。",
            ["equity_global", "commodity", "futures"], ["risk-on"],
            ["momentum", "trend"], "钱是坐着赚来的，不是靠频繁交易。"),
    Analyst("dennis", "理查德·丹尼斯", "Richard Dennis", "海龟趋势跟踪",
            "系统化跟踪趋势，用规则代替情绪。",
            "突破入场、ATR 止损、金字塔加仓。",
            ["futures", "commodity", "equity_global"], ["risk-on", "risk-off"],
            ["trend", "systematic"], "交易可以被教会，规则战胜情绪。"),
    Analyst("dalio", "瑞·达利欧", "Ray Dalio", "全天候/风险平价",
            "构建任何宏观环境下都能存活的风险均衡组合。",
            "增长/通胀四象限、风险平价、分散化。",
            ["fixed_income", "commodity", "equity_global", "cash"],
            ["risk-on", "risk-off", "neutral"],
            ["macro", "risk_parity", "all_weather"], "分散化是唯一的免费午餐。"),
    Analyst("soros", "乔治·索罗斯", "George Soros", "宏观/反身性",
            "市场认知与现实互相塑造，在反身性拐点下重注。",
            "宏观失衡、反身性、试错加码。",
            ["equity_global", "commodity", "futures"], ["risk-on", "risk-off"],
            ["macro", "contrarian", "reflexivity"], "重要的不是对错，而是对错时的盈亏大小。",
            contrarian=True),
    Analyst("druckenmiller", "斯坦利·德鲁肯米勒", "Stanley Druckenmiller", "宏观集中",
            "看准了就重仓，流动性是市场的关键驱动。",
            "宏观 + 流动性，集中高置信度头寸。",
            ["equity_global", "commodity", "fixed_income"], ["risk-on", "risk-off"],
            ["macro", "concentration", "liquidity"], "当你对的时候，要下重注。"),
    Analyst("tudor_jones", "保罗·都铎·琼斯", "Paul Tudor Jones", "宏观风控",
            "永远先想亏多少，用 200 日均线判断趋势。",
            "风险管理优先、趋势过滤、不对称下注。",
            ["futures", "commodity", "equity_global"], ["risk-off", "neutral"],
            ["macro", "risk_control", "trend"], "别当英雄，先控制回撤。"),
    Analyst("marks", "霍华德·马克斯", "Howard Marks", "周期/第二层思维",
            "理解周期位置，用第二层思维控制风险。",
            "周期、情绪温度、风险 vs 波动。",
            ["equity_cn", "equity_global", "fixed_income"], ["neutral", "risk-off"],
            ["cycles", "risk", "contrarian"], "你不能预测，但可以准备。", contrarian=True),
    Analyst("templeton", "约翰·邓普顿", "John Templeton", "全球逆向",
            "在最大悲观点买入，在全球范围找便宜货。",
            "跨市场估值、逆向、长期。",
            ["equity_global", "equity_cn"], ["risk-off"],
            ["contrarian", "value", "global"], "在枪炮声中买入。", contrarian=True),
    Analyst("burry", "迈克尔·伯里", "Michael Burry", "逆向深度价值",
            "深挖数据，敢于与市场共识作对。",
            "自下而上、做空泡沫、逆向。",
            ["equity_global", "equity_cn"], ["risk-off"],
            ["contrarian", "value", "short"], "有时众人皆醉。", contrarian=True),
    Analyst("klarman", "塞斯·卡拉曼", "Seth Klarman", "绝对价值/现金",
            "安全边际至上，没机会时持有现金。",
            "绝对回报、风险规避、耐心。",
            ["fixed_income", "cash", "equity_global"], ["risk-off", "neutral"],
            ["value", "defensive", "cash"], "规避亏损是成功投资的基石。"),
    Analyst("grantham", "杰里米·格兰瑟姆", "Jeremy Grantham", "均值回归/估值",
            "长期看一切终将均值回归，警惕泡沫。",
            "7 年估值预测、长期回归、绿色转型。",
            ["equity_global", "commodity"], ["risk-off", "neutral"],
            ["mean_reversion", "valuation", "contrarian"], "这次也不会不一样。", contrarian=True),
    Analyst("taleb", "纳西姆·塔勒布", "Nassim Taleb", "反脆弱/尾部对冲",
            "为黑天鹅做准备，构建反脆弱的杠铃结构。",
            "尾部风险、凸性、大部分安全 + 小部分高弹性。",
            ["cash", "commodity", "crypto"], ["risk-off"],
            ["tail_hedge", "barbell", "antifragile"], "别被随机性愚弄。",
            crypto_friendly=True),
    Analyst("swensen", "大卫·斯文森", "David Swensen", "耶鲁捐赠模型",
            "长期、分散、含另类资产、低成本的机构化配置。",
            "战略配置、再平衡、另类与权益倾斜。",
            ["equity_global", "equity_cn", "fixed_income", "commodity"],
            ["neutral", "risk-on"],
            ["endowment", "diversification", "rebalance"], "资产配置决定绝大部分收益。"),
    Analyst("bogle", "约翰·博格", "Jack Bogle", "指数/低成本",
            "别在草堆里找针，买下整个草堆，成本决定长期收益。",
            "宽基指数、低成本、长期持有、再平衡。",
            ["equity_global", "equity_cn", "fixed_income"], ["neutral"],
            ["index", "low_cost", "long_term"], "成本才是决定长期回报的关键。"),
    Analyst("wood", "凯西·伍德", "Cathie Wood", "颠覆式创新",
            "重仓押注颠覆性创新的指数级增长。",
            "创新主题、高成长、高波动容忍。",
            ["equity_global", "crypto"], ["risk-on"],
            ["growth", "innovation", "crypto"], "颠覆式创新的回报是非线性的。",
            crypto_friendly=True),
    Analyst("gross", "比尔·格罗斯", "Bill Gross", "债券之王",
            "债券总回报来自票息、收益率曲线与信用利差。",
            "久期、收益率曲线、信用。",
            ["fixed_income"], ["risk-off", "neutral"],
            ["bonds", "duration", "yield"], "债券是长期的股票替代。"),
    Analyst("fink", "拉里·芬克", "Larry Fink", "机构/风险配置",
            "长期资本配置需兼顾风险、通胀与可持续性。",
            "机构视角、通胀对冲、长期负债匹配。",
            ["fixed_income", "equity_global", "commodity"], ["neutral", "risk-off"],
            ["institutional", "risk", "inflation"], "长期投资要与目标匹配。"),
    Analyst("icahn", "卡尔·伊坎", "Carl Icahn", "激进逆向价值",
            "在被低估处寻找价值，必要时主动改变。",
            "深度价值、集中、事件驱动。",
            ["equity_cn", "equity_global"], ["risk-off", "neutral"],
            ["contrarian", "value", "activist"], "别人不看的地方才有便宜货。", contrarian=True),
    Analyst("loeb", "丹·勒布", "Dan Loeb", "事件驱动",
            "在并购、分拆、重组等事件中寻找定价错误。",
            "催化剂、事件套利、绝对回报。",
            ["equity_global", "fixed_income"], ["neutral"],
            ["event_driven", "absolute_return"], "催化剂是价值兑现的钥匙。"),
    Analyst("miller", "比尔·米勒", "Bill Miller", "价值+科技逆向",
            "价值投资也能拥抱科技，在恐慌中布局。",
            "逆向、现金流估值、科技成长。",
            ["equity_global", "equity_cn"], ["risk-off", "neutral"],
            ["value", "growth", "contrarian"], "价值与成长并非对立。", contrarian=True),
    Analyst("andreessen", "马克·安德森", "Marc Andreessen", "科技/风险成长",
            "软件吞噬世界，押注早期高成长与网络效应。",
            "科技主题、网络效应、长期期权。",
            ["equity_global", "crypto"], ["risk-on"],
            ["growth", "tech", "crypto"], "软件正在吞噬世界。", crypto_friendly=True),
]


# ---------------------------------------------------------------------------
# Directional-match scoring
# ---------------------------------------------------------------------------
def score_analyst(a: Analyst, ctx: Dict) -> float:
    """Score how well this analyst's direction matches the current situation.

    ctx keys: regime, plan_classes {class: weight}, tier, strategy_tags,
    macro_stance {class: stance}, has_crypto.
    """
    s = 0.0
    plan_classes = ctx.get("plan_classes", {})
    # 1) asset-class relevance: weight of classes the analyst focuses on
    focus = sum(plan_classes.get(c, 0.0) for c in a.focus_classes)
    s += 0.6 * focus
    # 2) regime alignment
    if ctx.get("regime") in a.regimes:
        s += 0.25
    # 3) tag fit with the chosen strategy
    strat_tags = set(ctx.get("strategy_tags", []))
    tag_overlap = len(strat_tags & set(a.tags))
    s += 0.12 * tag_overlap
    # 4) crypto alignment
    if ctx.get("has_crypto") and a.crypto_friendly:
        s += 0.2
    # 5) quant analysts resonate with high-frequency / factor strategies
    if a.quant and ("high_freq" in strat_tags or "momentum" in strat_tags):
        s += 0.1
    # 6) defensive analysts resonate with conservative tiers
    tier = ctx.get("tier", "C3")
    if tier in ("C1", "C2") and ("defensive" in a.tags or "value" in a.tags):
        s += 0.15
    if tier in ("C4", "C5") and ("growth" in a.tags or "momentum" in a.tags):
        s += 0.15
    return round(s, 4)


def select_analysts(ctx: Dict, n: int = 5) -> List[Analyst]:
    ranked = sorted(REGISTRY, key=lambda a: score_analyst(a, ctx), reverse=True)
    return ranked[:n]


# ---------------------------------------------------------------------------
# Persona advice generation (deterministic, rule-driven)
# ---------------------------------------------------------------------------
def analyst_view(a: Analyst, ctx: Dict) -> Dict:
    """Render one analyst's view on the current allocation."""
    regime = ctx.get("regime", "neutral")
    plan_classes = ctx.get("plan_classes", {})
    macro = ctx.get("macro_stance", {})

    # numeric tilt drives a PERSONALIZED stance (risk assets vs defensive),
    # so contrarians genuinely dissent from momentum analysts in the same regime
    numeric = _numeric_tilt(a, regime)
    risky_mean = (numeric.get("equity_cn", 0.0) + numeric.get("equity_global", 0.0)
                  + numeric.get("crypto", 0.0)) / 3.0
    defensive_mean = (numeric.get("fixed_income", 0.0) + numeric.get("cash", 0.0)) / 2.0
    posture = risky_mean - defensive_mean
    stance = "偏进攻" if posture > 0.2 else ("偏防御" if posture < -0.2 else "中性")

    # persona tilt: combine their tag bias with the current regime
    tilt: Dict[str, str] = {}
    tags = set(a.tags)
    if "value" in tags or "defensive" in tags:
        tilt["fixed_income"] = "增配"; tilt["equity_global"] = "谨慎追高"
    if "momentum" in tags or "trend" in tags:
        tilt["equity_global"] = "顺势持有"; tilt["equity_cn"] = "跟随相对强度"
    if "growth" in tags or "innovation" in tags or "tech" in tags:
        tilt["equity_global"] = "增配成长"; tilt["crypto"] = "小仓位高弹性" if a.crypto_friendly else "回避"
    if "macro" in tags or "all_weather" in tags or "risk_parity" in tags:
        tilt["commodity"] = "对冲"; tilt["fixed_income"] = "均衡"
    if "bonds" in tags or "duration" in tags:
        tilt["fixed_income"] = "拉长久期" if regime == "risk-off" else "缩短久期"
    if "tail_hedge" in tags or "barbell" in tags:
        tilt["cash"] = "厚尾保护"; tilt["commodity"] = "黄金对冲"
    if "contrarian" in tags:
        # contrarians lean against the crowd
        tilt["equity_cn"] = "逢悲观布局" if regime == "risk-off" else "警惕过热"
    if "index" in tags or "low_cost" in tags:
        tilt["equity_global"] = "宽基定投"; tilt["fixed_income"] = "指数化"
    # apply regime direction to generic equity if not yet set
    if "equity_global" not in tilt:
        tilt["equity_global"] = {"risk-on": "增配", "risk-off": "减仓"}.get(regime, "标配")

    # tie to the macro stance if the analyst focuses on those classes
    macro_note = ""
    for c, st in macro.items():
        if c in a.focus_classes and st in ("超配", "低配"):
            macro_note = f"结合大类观点：{c} 当前{st}。"
            break

    advice = (f"从{a.school}视角看，本人当前研判「{stance}」。"
              f"{a.lens.rstrip('。')}。")
    tilt_txt = "；".join(f"{k}:{v}" for k, v in list(tilt.items())[:4])
    return {
        "id": a.id, "name_zh": a.name_zh, "name_en": a.name_en,
        "school": a.school, "stance": stance,
        "philosophy": a.philosophy,
        "focus": "、".join(a.focus_classes),
        "tilt": tilt,
        "numeric_tilt": numeric,
        "advice": f"{advice}{macro_note}",
        "tilt_text": tilt_txt,
        "signature": a.signature,
        "relevance": score_analyst(a, ctx),
    }


def build_council(ctx: Dict, n: int = 5) -> Dict:
    """Select top-n analysts, render the council, aggregate a weighted vote,
    and measure divergence (higher heterogeneity => more caution)."""
    picked = select_analysts(ctx, n=n)
    views = [analyst_view(a, ctx) for a in picked]
    # aggregate stance
    from collections import Counter
    stances = Counter(v["stance"] for v in views)
    consensus = stances.most_common(1)[0][0] if stances else "中性"
    # dissent: analysts whose personalized stance differs from the majority
    dissent = [v["name_zh"] for v in views if v["stance"] != consensus]
    vote = council_vote(ctx, n=n)
    divergence = council_divergence(vote["votes"], views,
                                    plan_classes=ctx.get("plan_classes"))
    summary = _council_summary(views, consensus, dissent)
    summary += _DIVERGENCE_CAUTION.get(divergence["level"], "")
    return {
        "regime": ctx.get("regime", "neutral"),
        "consensus": consensus,
        "dissent": dissent,
        "n_analysts_total": len(REGISTRY),
        "council": views,
        "net_tilt": vote["net_tilt"],
        "votes": vote["votes"],
        "divergence": divergence,
        "summary": summary,
    }


def _council_summary(views, consensus, dissent) -> str:
    names = "、".join(v["name_zh"] for v in views)
    tilt_hint = ""
    # most-mentioned tilt class
    from collections import Counter
    c = Counter()
    for v in views:
        for k in v["tilt"]:
            c[k] += 1
    if c:
        top_cls, _ = c.most_common(1)[0]
        tilt_hint = f"，多数关注「{top_cls}」的仓位调整"
    dissent_txt = f"（{('、'.join(dissent))} 持不同意见）" if dissent else ""
    return (f"本次从 {len(REGISTRY)} 位分析师中选出方向最匹配的 {len(views)} 位：{names}。"
            f"共识研判：{consensus}{tilt_hint}。{dissent_txt}"
            f"以下为各分析师基于其流派视角的观点，仅供参考、不构成投资建议。")


# ---------------------------------------------------------------------------
# Weighted voting -> net class tilt (feeds back into allocation)
# ---------------------------------------------------------------------------
def _numeric_tilt(a: Analyst, regime: str) -> Dict[str, float]:
    """Map an analyst's archetype + current regime to a numeric per-class tilt
    in [-1, +1] (+ = overweight). Deterministic and explainable."""
    tags = set(a.tags)
    aggressive = tags & {"momentum", "trend", "growth", "innovation", "tech", "high_freq"}
    defensive = tags & {"value", "defensive", "cash", "tail_hedge", "barbell",
                        "duration", "bonds"}
    posture = 0.0
    if aggressive:
        posture += 0.5
    if defensive:
        posture -= 0.5
    if a.contrarian:
        posture -= 0.2
    regime_mod = {"risk-on": 0.4, "risk-off": -0.4, "neutral": 0.0}.get(regime, 0.0)
    posture = max(-1.0, min(1.0, posture + regime_mod))

    t: Dict[str, float] = {
        "equity_cn":     posture * 0.6,
        "equity_global": posture * 0.6,
        "crypto":        posture * (0.8 if a.crypto_friendly else 0.3),
        "futures":       posture * 0.3,
        "fixed_income":  -posture * 0.5,
        "cash":          -posture * 0.4,
        "commodity":     -posture * 0.4,
    }
    if "bonds" in tags or "duration" in tags:
        t["fixed_income"] += 0.4
    if tags & {"macro", "all_weather", "risk_parity"}:
        t["commodity"] += 0.2
        t["fixed_income"] += 0.2
    if "index" in tags or "low_cost" in tags:
        t["equity_global"] += 0.15
    return {k: round(max(-1.0, min(1.0, v)), 3) for k, v in t.items()}


def council_vote(ctx: Dict, n: int = 5) -> Dict:
    """Top-n analysts cast relevance-weighted votes; returns the aggregated net
    per-class tilt (in [-1,1]) plus each analyst's ballot.

    Vote weight = directional relevance × calibrated voice multiplier (learned
    from each analyst's historical style IC — see analyst_calibration.py).
    """
    from .analyst_calibration import voice_multiplier
    picked = select_analysts(ctx, n=n)
    regime = ctx.get("regime", "neutral")
    votes, agg, total_w = [], {}, 0.0
    for a in picked:
        rel = score_analyst(a, ctx)
        voice = voice_multiplier(a.id)
        w = max(rel, 0.05) * voice
        tilt = _numeric_tilt(a, regime)
        votes.append({"name_zh": a.name_zh, "school": a.school,
                      "relevance": rel, "voice": voice,
                      "weight": round(w, 3), "tilt": tilt})
        for c, s in tilt.items():
            agg[c] = agg.get(c, 0.0) + w * s
        total_w += w
    net = {c: round(v / total_w, 3) for c, v in agg.items()} if total_w else {}
    return {"regime": regime, "net_tilt": net, "votes": votes,
            "total_weight": round(total_w, 3)}


# ---------------------------------------------------------------------------
# Divergence / disagreement — higher heterogeneity => more caution
# ---------------------------------------------------------------------------
def council_divergence(votes: List[Dict], views: List[Dict],
                       plan_classes: Optional[Dict[str, float]] = None) -> Dict:
    """Measure cross-analyst disagreement.

    Two components:
      * tilt_divergence   — relevance-weighted std of analysts' numeric tilts
                            per class (aggregated by the plan's class exposure)
      * stance_divergence — 1 − majority share of personalized stances
    score = 0.7·tilt + 0.3·stance, in [0,1]. Interpretation:
      <0.20 高度共识 | 0.20-0.45 中度分歧 | >0.45 高度分歧(建议降低置信、以量化基础为主)
    """
    n = len(votes)
    if n == 0:
        return {"score": 0.0, "level": "—", "tilt_divergence": 0.0,
                "stance_divergence": 0.0}

    classes = sorted({c for v in votes for c in v["tilt"]})
    total_w = sum(v["weight"] for v in votes) or 1.0
    per_class: Dict[str, float] = {}
    for c in classes:
        vals = [(v["tilt"].get(c, 0.0), v["weight"]) for v in votes]
        m = sum(x * w for x, w in vals) / total_w
        var = sum(w * (x - m) ** 2 for x, w in vals) / total_w
        per_class[c] = var ** 0.5

    if plan_classes:
        ws = {c: plan_classes.get(c, 0.0) for c in per_class}
        tw = sum(ws.values())
        tilt_div = (sum(per_class[c] * ws[c] for c in per_class) / tw) if tw > 0 \
            else sum(per_class.values()) / len(per_class)
    else:
        tilt_div = sum(per_class.values()) / len(per_class)
    tilt_div = min(1.0, float(tilt_div))

    from collections import Counter
    st = Counter(v["stance"] for v in views)
    stance_div = 1.0 - (max(st.values()) / n) if n else 0.0

    score = round(0.7 * tilt_div + 0.3 * stance_div, 3)
    level = "高度共识" if score < 0.20 else ("中度分歧" if score < 0.45 else "高度分歧")
    return {"score": score, "level": level,
            "tilt_divergence": round(tilt_div, 3),
            "stance_divergence": round(stance_div, 3),
            "stance_counts": dict(st)}


_DIVERGENCE_CAUTION = {
    "高度共识": "智囊团意见高度一致，观点置信度较高。",
    "中度分歧": "智囊团存在中等分歧，建议结合自身判断权衡采纳。",
    "高度分歧": "⚠ 智囊团分歧显著：建议降低主观观点权重，以量化基础配置与纪律为主。",
}

