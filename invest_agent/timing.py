"""Subjective market-timing layer.

Lets the investor (or the agent, reasoning over news/intel) express a
directional view per asset class — e.g. "我短期看空A股，看多加密". Views are
folded into expected returns before optimization (a simplified
Black-Litterman view), so the optimizer naturally shifts weight toward the
classes the investor is bullish on and away from bearish ones.

Two entry points:
  * extract_timing_views(text)  — parse Chinese bullish/bearish phrasing
  * apply_timing_views(...)     — tilt expected returns by the views
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

# ---------------------------------------------------------------------------
# Keyword maps
# ---------------------------------------------------------------------------
BULLISH = ["看多", "看涨", "做多", "牛市", "加仓", "抄底", "逢低买", "上涨", "利好",
           "反弹", "布局", "增持", "买入", "机会", "起飞", "突破"]
BEARISH = ["看空", "看跌", "做空", "熊市", "减仓", "止盈", "逃顶", "下跌", "利空",
           "回调", "避险", "减持", "卖出", "风险大", "泡沫", "见顶", "清仓"]

CLASS_TRIGGERS = {
    "equity_cn":     ["A股", "a股", "沪指", "沪深", "创业板", "科创", "大盘", "股市", "A 股", "国内股市"],
    "equity_global": ["美股", "纳指", "纳斯达克", "标普", "道指", "海外", "港股", "恒生", "日经", "全球股"],
    "crypto":        ["加密", "比特币", "BTC", "btc", "以太坊", "ETH", "eth", "币圈", "数字货币", "虚拟货币", "币"],
    "commodity":     ["黄金", "原油", "大宗", "商品", "贵金属"],
    "fixed_income":  ["债券", "债市", "利率债", "信用债", "固收"],
}

# sentiment that lacks a class target applies to risky assets broadly
_RISKY = ["equity_cn", "equity_global", "crypto"]

_SPLIT = re.compile(r"[，。；！？,;!\n]")


@dataclass
class TimingView:
    """Per-class directional tilt in [-1, +1] plus conviction in [0, 1]."""
    tilts: Dict[str, float] = field(default_factory=dict)
    conviction: float = 0.5
    source: str = "manual"           # manual | text | intel
    notes: List[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not any(abs(v) > 1e-9 for v in self.tilts.values())


def _clause_sentiment(clause: str) -> float:
    bull = sum(1 for k in BULLISH if k in clause)
    bear = sum(1 for k in BEARISH if k in clause)
    if bull and not bear:
        return 1.0
    if bear and not bull:
        return -1.0
    return 0.0


def _clause_classes(clause: str) -> List[str]:
    hits = [c for c, kws in CLASS_TRIGGERS.items() if any(k in clause for k in kws)]
    return hits or []


def extract_timing_views(text: str, conviction: float = 0.5) -> TimingView:
    """Parse free text into per-class tilts. Clause-level so that
    '看空A股但看多加密' yields opposing views on the two classes."""
    view = TimingView(conviction=conviction, source="text")
    if not text:
        return view
    acc: Dict[str, List[float]] = {}
    for clause in _SPLIT.split(text):
        clause = clause.strip()
        if not clause:
            continue
        sent = _clause_sentiment(clause)
        if sent == 0.0:
            continue
        classes = _clause_classes(clause)
        targets = classes if classes else _RISKY
        for c in targets:
            acc.setdefault(c, []).append(sent)
        view.notes.append(f"{clause[:24]} -> {targets} {'+' if sent>0 else '−'}")
    for c, vals in acc.items():
        view.tilts[c] = float(np.clip(np.mean(vals), -1.0, 1.0))
    return view


def apply_timing_views(
    mu: np.ndarray,
    vol_monthly: np.ndarray,
    asset_classes: List[str],
    view: Optional[TimingView],
    strength: Optional[float] = None,
) -> np.ndarray:
    """Tilt expected returns by the view. A tilt of ±1 moves the expected
    monthly return by ±1 monthly-vol, scaled by conviction*strength. Higher-
    vol assets therefore receive proportionally larger absolute tilts."""
    if view is None or view.is_empty():
        return mu
    s = (view.conviction if strength is None else strength)
    tilted = np.array(mu, dtype=float).copy()
    for i, c in enumerate(asset_classes):
        t = view.tilts.get(c, 0.0)
        if abs(t) > 1e-9:
            # ±1 tilt ≈ ±2 monthly-vols of expected move (scaled by conviction),
            # strong enough to visibly shift the optimizer's choice.
            tilted[i] += t * s * 2.0 * vol_monthly[i]
    return tilted


def views_from_args(views_arg) -> Optional[TimingView]:
    """Build a TimingView from a tool argument: either a dict of class->tilt
    or a free-text string."""
    if views_arg is None:
        return None
    if isinstance(views_arg, str):
        return extract_timing_views(views_arg)
    if isinstance(views_arg, dict):
        tilts = {str(c): float(np.clip(float(v), -1, 1)) for c, v in views_arg.items()}
        return TimingView(tilts=tilts, source="manual")
    return None


STRONG = 0.5
# a strong liking concentrates the class toward this fraction of its cap
CONCENTRATION = 0.8


def has_strong_view(view: Optional[TimingView]) -> bool:
    if view is None or view.is_empty():
        return False
    return any(abs(v) >= STRONG for v in view.tilts.values())


def rewrite_caps_with_timing(
    base_caps: Dict[str, float],
    suitability_caps: Dict[str, float],
    view: Optional[TimingView],
    strong: float = STRONG,
):
    """Turn strong views into hard allocation constraints.

    Returns (caps, floors). Semantics (all suitability-safe):
      * strong dislike (tilt <= -strong) -> class EXCLUDED (cap 0). Holding less
        risk than allowed is always compliant.
      * strong liking (tilt >= +strong)  -> class concentrated: cap raised to its
        suitability cap AND a floor set near it, so the optimizer actually
        overweights the class instead of just being allowed to.
      * residual cash                    -> cash is the safe sink; flight to cash
        is always compliant, so its cap is opened when a strong view is active.
    """
    if view is None or view.is_empty():
        return base_caps, {}
    caps = dict(base_caps)
    floors: Dict[str, float] = {}
    strong_active = has_strong_view(view)
    for c, tilt in view.tilts.items():
        suit = float(suitability_caps.get(c, 0.0))
        if tilt <= -strong:
            caps[c] = 0.0                                  # exclude disliked
        elif tilt >= strong:
            caps[c] = max(float(caps.get(c, 0.0)), suit)   # allow up to suitability
            floors[c] = min(abs(tilt), 1.0) * suit * CONCENTRATION
    if strong_active:
        # open cash as the residual safe-haven (de-risking never breaches suitability)
        caps["cash"] = max(float(caps.get("cash", 0.0)), 1.0)
        # FOCUS MODE: the investor both strongly likes something AND strongly
        # rejects something else -> they want concentration, so drop every class
        # that is neither liked nor the cash sink (no silent diversification).
        has_strong_dislike = any(t <= -strong for t in view.tilts.values())
        if has_strong_dislike:
            for c in list(caps.keys()):
                if c == "cash":
                    continue
                if view.tilts.get(c, 0.0) >= strong:
                    continue
                caps[c] = 0.0
    return caps, floors
