"""Global political-economic situation board.

Aggregates real-time news (eastmoney flashes, CCTV policy news, Baidu economic
calendar) and macro indicators, then produces a rule-based assessment of the
global situation: risk appetite, dominant themes, macro trend, watch items.

Everything degrades gracefully to an "offline" pack when endpoints fail.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional

_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "data_cache")
_TTL_H = 3.0

GEOPOLITICS_KW = {
    "地缘冲突": ["冲突", "战争", "军事", "袭击", "局势紧张", "对峙", "空袭", "导弹"],
    "贸易/关税": ["关税", "贸易战", "制裁", "出口管制", "贸易谈判", "加征"],
    "央行/利率": ["美联储", "降息", "加息", "央行", "利率", "缩表", "QE", "LPR", "MLF"],
    "通胀/就业": ["通胀", "CPI", "非农", "就业", "失业", "PCE"],
    "增长/景气": ["GDP", "PMI", "增长", "复苏", "景气", "衰退", "软着陆"],
    "资本市场政策": ["证监会", "注册制", "IPO", "退市", "印花税", "降准"],
}

RISK_OFF_KW = ["冲突", "战争", "制裁", "衰退", "暴跌", "危机", "违约", "避险", "加息",
               "通胀超预期", "局势升级", "空袭", "对抗"]
RISK_ON_KW = ["降息", "复苏", "增长", "利好", "反弹", "刺激", "降准", "软着陆", "回暖",
              "超预期改善", "谈判进展", "缓和"]


def _cache_path(name: str) -> str:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    return os.path.join(_CACHE_DIR, f"geo_{name}.json")


def _fresh(path: str) -> Optional[Dict]:
    if os.path.exists(path):
        age_h = (datetime.now().timestamp() - os.path.getmtime(path)) / 3600.0
        if age_h < _TTL_H:
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:  # noqa: BLE001
                return None
    return None


def _tag_topics(text: str) -> List[str]:
    return [t for t, kws in GEOPOLITICS_KW.items() if any(k in text for k in kws)]


def fetch_global_news(max_items: int = 40, use_cache: bool = True) -> Dict:
    """Merge real-time news from all reachable sources, tagged by topic."""
    path = _cache_path("news")
    if use_cache:
        c = _fresh(path)
        if c:
            return c
    items: List[Dict] = []
    sources_ok = []

    # 1) eastmoney financial flashes (reuse intel fetcher)
    try:
        from .intel import fetch_market_intel
        pack = fetch_market_intel(max_items=max_items)
        for it in pack.get("items", []):
            items.append({"title": it["title"], "source": "东财快讯",
                          "topics": _tag_topics(it["title"])})
        if pack.get("items"):
            sources_ok.append("eastmoney")
    except Exception:  # noqa: BLE001
        pass

    # 2) CCTV policy news (yesterday + today)
    try:
        import akshare as ak
        for back in (1, 0):
            d = (datetime.now() - timedelta(days=back)).strftime("%Y%m%d")
            try:
                df = ak.news_cctv(date=d)
            except Exception:  # noqa: BLE001
                continue
            for _, row in df.head(12).iterrows():
                title = str(row.get("title", "") or "")
                if title:
                    items.append({"title": title, "source": "新闻联播",
                                  "topics": _tag_topics(title)})
        sources_ok.append("cctv")
    except Exception:  # noqa: BLE001
        pass

    # 3) Baidu economic calendar (high-importance macro events)
    try:
        import akshare as ak
        df = ak.news_economic_baidu()
        if "重要性" in df.columns:
            hi = df[df["重要性"].astype(str).isin(["2", "3"])]
            for _, row in hi.head(15).iterrows():
                ev = f"{row.get('地区','')} {row.get('事件','')}"
                items.append({"title": ev, "source": "财经日历",
                              "topics": _tag_topics(ev)})
            sources_ok.append("calendar")
    except Exception:  # noqa: BLE001
        pass

    # dedup by title
    seen, uniq = set(), []
    for it in items:
        if it["title"] not in seen:
            seen.add(it["title"])
            uniq.append(it)
    pack = {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "sources_ok": sources_ok, "items": uniq[:max_items]}
    if uniq:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(pack, f, ensure_ascii=False)
    return pack


def assess_global_situation(news_pack: Optional[Dict] = None,
                            use_cache: bool = True) -> Dict:
    """Rule-based global situation assessment.

    Returns risk_appetite in [-1,1] (>0 risk-on), dominant themes, a macro
    trend label, and watch items. Pure keyword/vote aggregation — transparent
    and reproducible.
    """
    if news_pack is None:
        news_pack = fetch_global_news(use_cache=use_cache)
    items = news_pack.get("items", [])
    text_blob = " ".join(it["title"] for it in items)

    risk_off = sum(text_blob.count(k) for k in RISK_OFF_KW)
    risk_on = sum(text_blob.count(k) for k in RISK_ON_KW)
    denom = max(risk_on + risk_off, 1)
    appetite = (risk_on - risk_off) / denom  # [-1,1]

    # theme frequency
    theme_count: Dict[str, int] = {}
    for it in items:
        for t in it["topics"]:
            theme_count[t] = theme_count.get(t, 0) + 1
    themes = sorted(theme_count.items(), key=lambda kv: -kv[1])[:4]

    if appetite > 0.15:
        regime = "风险偏好回升 (risk-on)"
    elif appetite < -0.15:
        regime = "避险情绪主导 (risk-off)"
    else:
        regime = "中性/观望"

    watch = [it["title"] for it in items if it["topics"]][:5]
    return {
        "generated_at": news_pack.get("generated_at"),
        "sources_ok": news_pack.get("sources_ok", []),
        "n_items": len(items),
        "risk_appetite": round(appetite, 3),
        "regime": regime,
        "risk_on_hits": risk_on,
        "risk_off_hits": risk_off,
        "themes": [{"theme": t, "count": c} for t, c in themes],
        "watch_items": watch,
    }


def situation_digest(assessment: Dict, max_watch: int = 4) -> str:
    """Compact human-readable digest for reports / LLM context."""
    lines = [
        f"[全球政经局势 {assessment.get('generated_at','')}] "
        f"研判: {assessment['regime']} (风险偏好 {assessment['risk_appetite']:+.2f})",
        "主导议题: " + "、".join(t["theme"] for t in assessment["themes"]) or "无",
    ]
    if assessment["watch_items"]:
        lines.append("关注事件:")
        for w in assessment["watch_items"][:max_watch]:
            lines.append(f"  - {w[:50]}")
    return "\n".join(lines)
