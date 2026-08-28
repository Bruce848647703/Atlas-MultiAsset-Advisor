"""Market intelligence: recent news / research flash for the advisor.

Pulls the latest financial news flashes (via akshare public endpoints),
tags each item with topics, and caches the result. The advisor tool
``get_market_intel`` feeds this into the LLM's context so allocation
decisions can reference the current macro/sector narrative.

Graceful degradation: if every source fails (offline / API change), the
module returns an empty intel pack with ``source_status="offline"`` and
the advisor continues purely on quant signals.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List

os.environ.setdefault("TQDM_DISABLE", "1")  # silence akshare progress bars

_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "data_cache")

TOPIC_KEYWORDS = {
    "crypto":    ["比特币", "加密", "以太坊", "数字货币", "币", "BTC", "ETH", "区块链", "稳定币"],
    "equity_cn": ["A股", "沪指", "深成指", "创业板", "科创板", "北交所", "证监会", "两市"],
    "equity_us": ["美股", "纳斯达克", "标普", "道指", "美联储", "华尔街", "英伟达", "苹果"],
    "bonds":     ["国债", "债市", "收益率", "利率", "降息", "加息", "LPR", "MLF"],
    "commodity": ["黄金", "原油", "大宗商品", "铜", "期货", "OPEC", "白银"],
    "macro":     ["GDP", "CPI", "PMI", "通胀", "就业", "非农", "央行", "财政", "关税", "汇率"],
    "real_estate": ["楼市", "房地产", "房贷", "公积金"],
}


def tag_topics(text: str) -> List[str]:
    out = []
    for topic, kws in TOPIC_KEYWORDS.items():
        if any(k.lower() in text.lower() for k in kws):
            out.append(topic)
    return out or ["general"]


def _cache_path() -> str:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    return os.path.join(_CACHE_DIR, f"intel_{datetime.now():%Y%m%d}.json")


def _load_cache(max_age_hours: float = 6.0):
    p = _cache_path()
    if os.path.exists(p):
        age_h = (datetime.now().timestamp() - os.path.getmtime(p)) / 3600.0
        if age_h < max_age_hours:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    return None


def _fetch_em_global() -> List[Dict]:
    import akshare as ak
    df = ak.stock_info_global_em()
    items = []
    for _, row in df.iterrows():
        title = str(row.get("标题", "") or "")
        summary = str(row.get("摘要", "") or "")
        t = str(row.get("发布时间", "") or "")
        if not title:
            continue
        items.append({"time": t, "title": title, "summary": summary[:200],
                      "source": "东方财富-全球财经快讯"})
    return items


def _fetch_cctv(days: int = 2) -> List[Dict]:
    import akshare as ak
    items = []
    for i in range(days):
        d = (datetime.now() - timedelta(days=i + 1)).strftime("%Y%m%d")
        try:
            df = ak.news_cctv(date=d)
        except Exception:  # noqa: BLE001
            continue
        for _, row in df.head(10).iterrows():
            title = str(row.get("title", "") or "")
            items.append({"time": d, "title": title,
                          "summary": str(row.get("content", "") or "")[:150],
                          "source": "新闻联播"})
    return items


def fetch_market_intel(max_items: int = 40, cache_hours: float = 6.0) -> Dict:
    """Return {"generated_at", "source_status", "topics_covered", "items"}."""
    cached = _load_cache(cache_hours)
    if cached:
        return cached

    items: List[Dict] = []
    failures = []
    for fn in (_fetch_em_global, _fetch_cctv):
        try:
            items.extend(fn())
        except Exception as e:  # noqa: BLE001 - per-source fallback
            failures.append(f"{fn.__name__}: {type(e).__name__}")

    for it in items:
        it["topics"] = tag_topics(f"{it['title']} {it['summary']}")

    # de-dup by title, keep newest first
    seen, uniq = set(), []
    for it in items:
        if it["title"] in seen:
            continue
        seen.add(it["title"])
        uniq.append(it)
    uniq = uniq[:max_items]

    topics_covered = sorted({t for it in uniq for t in it["topics"]})
    pack = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source_status": "ok" if uniq else ("degraded: " + "; ".join(failures) if failures else "empty"),
        "topics_covered": topics_covered,
        "items": uniq,
    }
    if uniq:
        with open(_cache_path(), "w", encoding="utf-8") as f:
            json.dump(pack, f, ensure_ascii=False)
    return pack


def summarize_for_prompt(pack: Dict, max_items: int = 12) -> str:
    """Compact text block for LLM context injection."""
    if not pack["items"]:
        return f"[市场情报] 数据源状态: {pack['source_status']}；本次无可用新闻，仅依赖量化信号。"
    lines = [f"[市场情报 {pack['generated_at']}] 覆盖话题: {', '.join(pack['topics_covered'])}"]
    for it in pack["items"][:max_items]:
        lines.append(f"- ({','.join(it['topics'][:2])}) {it['title']}")
    lines.append("请结合以上最新信息评估配置建议的时效性风险。")
    return "\n".join(lines)
