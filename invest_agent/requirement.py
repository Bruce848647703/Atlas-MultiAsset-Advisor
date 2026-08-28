"""Requirement understanding: parse an investor's free-form request into a
structured spec the advisor can act on.

This is the deterministic core of "理解需求". It unifies:
  * risk attitude      (delegated to risk_profiler keyword heuristics)
  * market-timing views (timing.extract_timing_views)
  * expressed interests (asset classes mentioned)
  * horizon hints      (短期/长期/N 年)

The same mapping is used to (a) drive the live advisor offline and (b) build
SFT/eval data so a fine-tuned LLM learns to produce the identical structure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .risk_profiler import heuristic_text_adjustment
from .timing import TimingView, extract_timing_views

CLASS_MENTIONS = {
    "equity_cn":     ["A股", "a股", "沪深", "创业板", "科创", "大盘", "股市", "股票"],
    "equity_global": ["美股", "纳指", "纳斯达克", "标普", "道指", "港股", "恒生", "日经", "海外"],
    "crypto":        ["加密", "比特币", "BTC", "btc", "以太坊", "ETH", "币圈", "数字货币", "虚拟货币", "币"],
    "commodity":     ["黄金", "原油", "大宗", "商品"],
    "fixed_income":  ["债券", "债", "固收"],
    "futures":       ["期货", "合约", "杠杆"],
}

_HORIZON_LONG = ["长期", "长线", "拿很久", "养老", "十年", "5年以上", "五年以上", "长期持有"]
_HORIZON_SHORT = ["短期", "短线", "几个月", "年内", "很快要用", "临时"]

_CN_NUM = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5,
           "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


@dataclass
class ParsedRequirement:
    risk_adj: float = 0.0                       # from keyword heuristics
    risk_reasons: List[str] = field(default_factory=list)
    timing: Optional[TimingView] = None
    interests: List[str] = field(default_factory=list)
    horizon_hint: Optional[int] = None          # years
    raw_text: str = ""

    def summary(self) -> Dict[str, object]:
        return {
            "risk_adj": round(self.risk_adj, 1),
            "timing_tilts": self.timing.tilts if self.timing else {},
            "timing_conviction": self.timing.conviction if self.timing else None,
            "interests": self.interests,
            "horizon_hint": self.horizon_hint,
        }


def _detect_interests(text: str) -> List[str]:
    out = []
    for cls, kws in CLASS_MENTIONS.items():
        if any(k in text for k in kws):
            out.append(cls)
    return out


def _detect_horizon(text: str) -> Optional[int]:
    if any(k in text for k in _HORIZON_SHORT):
        return 1
    m = re.search(r"(\d+)\s*年", text)
    if m:
        return max(1, min(int(m.group(1)), 30))
    for cn, num in _CN_NUM.items():
        if re.search(cn + r"\s*年", text):
            return num
    if any(k in text for k in _HORIZON_LONG):
        return 7
    return None


def parse_requirement(text: str, conviction: float = 0.5) -> ParsedRequirement:
    text = text or ""
    adj, reasons = heuristic_text_adjustment(text)
    timing = extract_timing_views(text, conviction=conviction)
    return ParsedRequirement(
        risk_adj=adj,
        risk_reasons=reasons,
        timing=timing if not timing.is_empty() else None,
        interests=_detect_interests(text),
        horizon_hint=_detect_horizon(text),
        raw_text=text,
    )
