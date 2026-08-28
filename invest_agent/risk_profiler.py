"""Investor risk profiling.

Two complementary paths, both deterministic and testable:

1. Structured questionnaire (scored 0..100, mapped to C1..C5 suitability
   tiers, consistent with CN investor-suitability convention).
2. Free-text inference: keyword heuristics (default, offline) plus an
   LLM prompt builder for conversational profiling through the harness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .config import risk_tiers

# (weight, question_zh, question_en, options: (label_zh, label_en, score 0..3))
QUESTIONS: List[Tuple[int, str, str, List[Tuple[str, str, int]]]] = [
    (2, "您的年龄阶段是？", "Your age group?",
     [("60岁以上", "Above 60", 0), ("46-60", "46-60", 1), ("31-45", "31-45", 2), ("18-30", "18-30", 3)]),
    (2, "您的家庭可投资资产（不含自住房）占总资产的比例？",
     "Share of investable assets (excl. home) in total wealth?",
     [("超过80%", ">80%", 0), ("50%-80%", "50%-80%", 1), ("20%-50%", "20%-50%", 2), ("低于20%", "<20%", 3)]),
    (2, "您是否有稳定的工资/经营性收入？", "Do you have stable income?",
     [("无收入来源", "No income", 0), ("收入不稳定", "Unstable", 1), ("稳定但依赖单一来源", "Stable, single source", 2), ("多元且稳定", "Diversified & stable", 3)]),
    (1, "您的投资知识水平如何？", "Your investment knowledge?",
     [("几乎没有", "Almost none", 0), ("了解基础概念", "Basic concepts", 1), ("熟悉股票/基金", "Familiar with stocks/funds", 2), ("熟悉衍生品与加密资产", "Familiar with derivatives & crypto", 3)]),
    (1, "您的实际投资经验？", "Actual investing experience?",
     [("无", "None", 0), ("仅银行理财/货基", "Bank WM / MMF only", 1), ("股票/基金2年以上", "Stocks/funds 2y+", 2), ("期货/期权/加密货币经验", "Futures/options/crypto experience", 3)]),
    (1, "本笔资金的投资期限？", "Investment horizon of this capital?",
     [("1年以内", "<1 year", 0), ("1-3年", "1-3 years", 1), ("3-5年", "3-5 years", 2), ("5年以上", ">5 years", 3)]),
    (1, "投资的主要目标？", "Primary objective?",
     [("资产保值", "Capital preservation", 0), ("获取稳定收益", "Stable income", 1), ("资产稳健增值", "Steady growth", 2), ("追求高收益", "Maximum growth", 3)]),
    (2, "若您投入10万元，一个月亏损15%（1.5万元），您会？",
     "You invest 100k and lose 15% in one month. You would...",
     [("立即全部卖出，无法承受", "Sell all immediately", 0), ("卖出部分以降低风险", "Sell part to cut risk", 1), ("持有并等待反弹", "Hold and wait", 2), ("视为机会，逢低加仓", "Buy more on the dip", 3)]),
    (1, "您对资金流动性（随时可取用）的要求？", "Liquidity requirement?",
     [("随时可能全部取用", "May need all anytime", 0), ("半年内可能部分取用", "Part within 6 months", 1), ("一年内基本不动用", "Mostly untouched for 1 year", 2), ("长期不动用", "Long-term untouched", 3)]),
]

MAX_SCORE = sum(w * 3 for w, *_ in QUESTIONS)

POSITIVE_KEYWORDS = {
    "高收益": 8, "翻倍": 10, "激进": 8, "all in": 10, "allin": 10, "抄底": 6, "加仓": 4,
    "杠杆": 8, "合约": 8, "长期上涨": 3, "定投": 2, "看好": 3, "牛市": 5, "成长股": 5,
}
# risky-asset mentions: signal interest ONLY when the investor is not exiting
ASSET_MENTION_KEYWORDS = {
    "币圈": 6, "币": 3, "btc": 4, "比特币": 4, "以太坊": 4, "纳斯达克": 3, "纳指": 3,
}
# exit / avoidance sentiment: mentioning a risky asset alongside these means
# the investor wants OUT, so asset mentions must not raise risk appetite
EXIT_KEYWORDS = {
    "清仓": -8, "别碰": -8, "千万别": -6, "暴跌": -8, "崩盘": -10, "看空": -6,
    "减仓": -5, "避险": -4, "逃顶": -6, "见顶": -5, "要跌": -6, "换成货基": -5,
    "卖出": -4, "止盈": -3, "做空": -6,
}
NEGATIVE_KEYWORDS = {
    "不能亏": -12, "不想亏": -10, "亏掉本金": -12, "亏本金": -12, "保本": -10, "保守": -8,
    "稳健": -5, "低风险": -8, "担心亏": -10, "害怕": -6, "焦虑": -5, "睡觉": -4,
    "养老金": -8, "生活费": -12, "应急": -8, "短期要用": -10, "马上要用": -12,
    "亏不起": -12, "稳妥": -6, "存款": -5, "国债": -4, "高风险": -6,
}
NEUTRAL_POSITIVE = {
    "接受波动": 5, "能承受波动": 5, "能接受短期波动": 5, "长期持有": 3, "闲钱": 4,
}


@dataclass
class RiskProfile:
    score: float
    tier: str                      # C1..C5
    capital: float = 0.0
    horizon_years: int = 3
    answers: Dict[int, int] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    free_text: str = ""

    @property
    def tier_info(self) -> dict:
        return risk_tiers()[self.tier]


def score_questionnaire(answers: Dict[int, int]) -> Tuple[float, str]:
    """answers: {question_index: option_index}. Returns (score 0..100, tier)."""
    raw = 0
    total_w = 0
    for i, (w, _, _, opts) in enumerate(QUESTIONS):
        total_w += w
        if i in answers:
            oi = max(0, min(int(answers[i]), len(opts) - 1))
            raw += w * opts[oi][2]
    score = 100.0 * raw / max(MAX_SCORE, 1)
    return round(score, 1), tier_from_score(score)


def tier_from_score(score: float) -> str:
    for tier, info in risk_tiers().items():
        lo, hi = info["score_range"]
        if lo <= score <= hi:
            return tier
    return "C5" if score > 100 else "C1"


def heuristic_text_adjustment(text: str) -> Tuple[float, List[str]]:
    """Keyword-based adjustment in [-25, +25] with human-readable reasons.

    Sentiment-aware: risky-asset mentions only count as risk appetite when the
    investor is not expressing exit/avoidance ("加密要暴跌了，清仓币圈" must not
    read as risk-seeking)."""
    t = text.lower()
    adj = 0.0
    reasons: List[str] = []
    # exit/avoidance words are TACTICAL (handled by the timing layer); here they
    # only serve to stop risky-asset mentions from counting as risk appetite.
    exiting = any(kw in t for kw in EXIT_KEYWORDS)
    for kw, v in POSITIVE_KEYWORDS.items():
        if kw in t:
            adj += v
            reasons.append(f"risk-seeking signal: '{kw}' (+{v})")
    if not exiting:
        for kw, v in ASSET_MENTION_KEYWORDS.items():
            if kw in t:
                adj += v
                reasons.append(f"risk-seeking signal: '{kw}' (+{v})")
    else:
        reasons.append("exit/avoidance sentiment: asset mentions not counted as appetite")
    for kw, v in NEGATIVE_KEYWORDS.items():
        if kw in t:
            adj += v
            reasons.append(f"risk-averse signal: '{kw}' ({v})")
    for kw, v in NEUTRAL_POSITIVE.items():
        if kw in t:
            adj += v
            reasons.append(f"risk-tolerant signal: '{kw}' (+{v})")
    return max(-25.0, min(25.0, adj)), reasons


def profile_from_answers(
    answers: Dict[int, int],
    capital: float = 0.0,
    free_text: str = "",
    horizon_years: Optional[int] = None,
) -> RiskProfile:
    base, tier = score_questionnaire(answers)
    notes: List[str] = [f"questionnaire score={base}"]
    if free_text:
        adj, reasons = heuristic_text_adjustment(free_text)
        if reasons:
            notes.extend(reasons)
        score = max(0.0, min(100.0, base + adj))
        tier = tier_from_score(score)
        notes.append(f"adjusted score={score}")
    else:
        score = base
    if horizon_years is None and 5 in answers:
        horizon_years = {0: 1, 1: 2, 2: 4, 3: 7}[max(0, min(int(answers[5]), 3))]
    return RiskProfile(
        score=score, tier=tier, capital=capital,
        horizon_years=horizon_years or 3, answers=answers, notes=notes,
        free_text=free_text,
    )


# Prompt used by the agent to convert conversational replies into
# structured questionnaire answers (validated locally afterwards).
LLM_PROFILING_PROMPT = """You are an investor-suitability analyst.
Map the investor's free-form replies onto this questionnaire by outputting
STRICT JSON of the form {{"answers": {{"<index>": <option_index>}}, "confidence": 0..1}}.
Only answer questions the text gives evidence for; omit the rest.

Questionnaire:
{questions}

Investor says:
\"\"\"{text}\"\"\"

Return JSON only."""


def profiling_prompt(text: str) -> str:
    lines = []
    for i, (_w, q_zh, q_en, opts) in enumerate(QUESTIONS):
        opt_str = "; ".join(f"{j}:{zh}" for j, (zh, _en, _s) in enumerate(opts))
        lines.append(f"[{i}] {q_zh} -- {opt_str}")
    return LLM_PROFILING_PROMPT.format(questions="\n".join(lines), text=text)
