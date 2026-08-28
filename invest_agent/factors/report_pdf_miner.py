"""Research-report PDF miner: deep factor extraction from broker reports.

Goes beyond title-level theme matching — downloads report PDFs, extracts the
full text, and mines factor definitions/mentions:

  * factor mention     — any sentence discussing a 因子 (factor)
  * factor definition  — a sentence that pairs a factor with formula-like
                         content (=, 计算, 定义, 公式, 指标, 构建)
  * factor name        — patterns like "XX因子" pulled from the text

Downloaded text is cached so repeated cycles don't refetch. This is best-effort:
most broker reports are earnings reviews, so genuine factor formulas are rare —
the miner records what it finds with full provenance and never fabricates.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
from typing import Dict, List, Optional

_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                          "data_cache", "report_pdfs")

_REPORT_BASKET = ["300059", "600519", "000858", "601318", "002594", "600036"]
_HEADERS = {"User-Agent": "Mozilla/5.0 (research/learning; contact atlas)"}

# keywords that mark a report as factor / quant research (title-level filter)
FACTOR_REPORT_KEYWORDS = ["因子", "多因子", "选股", "金融工程", "alpha", "Alpha",
                          "因子选股", "智能选股", "量化选股", "因子测试", "因子表现"]

_LIST_API = "https://reportapi.eastmoney.com/report/list"
_PDF_URL = "https://pdf.dfcfw.com/pdf/H3_{infoCode}_1.pdf"

_FORMULA_HINTS = ["=", "计算", "定义", "公式", "构建", "指标", "构造", "衡量", "刻画"]
_SENT_SPLIT = re.compile(r"[。；;！!？?\n]")
_FACTOR_NAME = re.compile(r"([\u4e00-\u9fa5A-Za-z0-9]{2,12}因子)")

# factor-concept keywords: real reports discuss investment logic with these
# terms rather than the literal word 因子, so we mine concepts, not just 因子.
CONCEPT_KEYWORDS = {
    "value": ["估值", "市盈率", "市净率", "低估值", "破净", "性价比"],
    "dividend": ["股息", "分红", "高股息", "红利", "股东回报"],
    "growth": ["增长", "景气", "景气度", "高成长", "业绩弹性", "增速"],
    "quality": ["盈利质量", "ROE", "盈利能力", "护城河", "竞争优势", "毛利率"],
    "momentum": ["动量", "趋势", "强势", "涨势", "持续上行"],
    "low_volatility": ["低波动", "稳健", "防御", "抗跌", "回撤可控"],
    "liquidity": ["流动性", "换手", "成交额", "交投活跃"],
}


# ---------------------------------------------------------------------------
# PDF fetch + text extraction
# ---------------------------------------------------------------------------
def _cache_path(key: str) -> str:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    return os.path.join(_CACHE_DIR, f"{key}.json")


def _fetch_report_rows(basket: Optional[List[str]], max_per_symbol: int) -> List[Dict]:
    """Collect report metadata (title/institution/date/pdf_url) from akshare."""
    try:
        import akshare as ak
    except Exception:  # noqa: BLE001
        return []
    rows, seen = [], set()
    for sym in (basket or _REPORT_BASKET):
        try:
            df = ak.stock_research_report_em(symbol=sym)
        except Exception:  # noqa: BLE001
            continue
        if df is None or df.empty or "报告PDF链接" not in df.columns:
            continue
        for _, r in df.head(max_per_symbol).iterrows():
            url = str(r.get("报告PDF链接", "") or "")
            title = str(r.get("报告名称", "") or "")
            if not url or not title or url in seen:
                continue
            seen.add(url)
            rows.append({"title": title,
                         "institution": str(r.get("机构", "") or ""),
                         "date": str(r.get("日期", "") or ""),
                         "pdf_url": url})
    return rows


def scan_factor_reports(pages_per_type: int = 4, size: int = 100,
                        qtypes: Optional[List[str]] = None) -> List[Dict]:
    """Scan the eastmoney report API across report types and return reports whose
    titles match factor/quant keywords (金融工程/多因子/选股/alpha...). These are
    the factor-specialized reports most likely to contain real factor formulas.
    PDF url is derived from infoCode."""
    import datetime
    import requests
    qtypes = qtypes or ["0", "1", "2"]
    out, seen = [], set()
    end = f"{datetime.datetime.now().year + 1}-01-01"
    for qt in qtypes:
        for p in range(1, pages_per_type + 1):
            params = {"industryCode": "*", "pageSize": str(size), "industry": "*",
                      "rating": "*", "ratingChange": "*", "beginTime": "2023-01-01",
                      "endTime": end, "pageNo": str(p), "fields": "", "qType": qt,
                      "orgCode": "", "code": "*", "rcode": "", "p": str(p),
                      "pageNum": str(p), "pageNumber": str(p)}
            try:
                d = requests.get(_LIST_API, params=params, timeout=15,
                                 headers=_HEADERS).json()
            except Exception:  # noqa: BLE001
                continue
            for x in d.get("data", []) or []:
                title = str(x.get("title", "") or "")
                info = str(x.get("infoCode", "") or "")
                if not title or not info or not any(k in title for k in FACTOR_REPORT_KEYWORDS):
                    continue
                if info in seen:
                    continue
                seen.add(info)
                out.append({"title": title,
                            "institution": str(x.get("orgSName", "") or ""),
                            "date": str(x.get("publishDate", "") or "")[:10],
                            "infoCode": info,
                            "pdf_url": _PDF_URL.format(infoCode=info),
                            "qType": qt})
    return out


def _download_text(url: str, timeout: int = 25) -> Optional[str]:
    key = hashlib.md5(url.encode()).hexdigest()
    cp = _cache_path(key)
    if os.path.exists(cp):
        try:
            with open(cp, encoding="utf-8") as f:
                return json.load(f).get("text")
        except Exception:  # noqa: BLE001
            pass
    try:
        import requests
        from pypdf import PdfReader
        resp = requests.get(url, timeout=timeout, headers=_HEADERS)
        if resp.status_code != 200 or resp.content[:4] != b"%PDF":
            return None
        reader = PdfReader(io.BytesIO(resp.content))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
        with open(cp, "w", encoding="utf-8") as f:
            json.dump({"url": url, "text": text}, f, ensure_ascii=False)
        return text
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Factor mining
# ---------------------------------------------------------------------------
def mine_factors_from_text(text: str, title: str = "") -> Dict[str, object]:
    """Mine factor content from report text.

    Returns:
      literal:   sentences with the explicit word 因子 (rare, genuine factor text)
      concepts:  {theme: [evidence sentences]} for factor-concept keywords
                 (估值/股息/景气度/成长/动量/低波/流动性) — the investment logic
                 that real reports actually discuss.
      names:     explicit 'XX因子' names found
    """
    empty = {"literal": [], "concepts": {}, "names": []}
    if not text:
        return empty
    literal, names = [], set()
    concepts: Dict[str, List[str]] = {}
    for raw in _SENT_SPLIT.split(text):
        s = raw.strip()
        if not s:
            continue
        if "因子" in s:
            literal.append(s[:160])
            for m in _FACTOR_NAME.findall(s):
                names.add(m)
        for theme, kws in CONCEPT_KEYWORDS.items():
            if any(k in s for k in kws):
                concepts.setdefault(theme, [])
                if len(concepts[theme]) < 3 and len(s) > 12:
                    concepts[theme].append(s[:150])
    return {"literal": literal[:20], "concepts": concepts, "names": sorted(names)[:30]}


def mine_report_pdfs(basket: Optional[List[str]] = None,
                     max_reports: int = 8,
                     max_per_symbol: int = 6,
                     prefer_factor_reports: bool = True) -> Dict:
    """Download report PDFs and mine factor content. Prioritizes factor-
    specialized reports (金融工程/多因子/选股, located via the report API title
    scan) since those contain real factor formulas; falls back to individual-
    stock basket reports. Registers discovered factor concepts/names with the
    report's own reasoning as evidence."""
    from .factor_store import add_factor

    rows: List[Dict] = []
    if prefer_factor_reports:
        try:
            rows = scan_factor_reports(pages_per_type=4, size=100)
        except Exception:  # noqa: BLE001
            rows = []
    # supplement with basket reports if few factor-specialized ones found
    if len(rows) < max_reports:
        try:
            rows.extend(_fetch_report_rows(basket, max_per_symbol))
        except Exception:  # noqa: BLE001
            pass

    mined, registered = [], []
    downloads = 0
    for row in rows:
        if downloads >= max_reports:
            break
        text = _download_text(row["pdf_url"])
        if not text:
            continue
        downloads += 1
        found = mine_factors_from_text(text, row["title"])
        concepts = found["concepts"]
        if not (concepts or found["names"] or found["literal"]):
            continue
        mined.append({"title": row["title"][:60], "institution": row["institution"],
                      "date": row["date"],
                      "themes": sorted(concepts.keys()),
                      "n_literal": len(found["literal"]),
                      "names": found["names"][:5]})
        prov = f"{row['title'][:40]}|{row['institution']}|{row['date']}"
        # register explicit factor names (highest value)
        for nm in found["names"][:5]:
            add_factor(f"pdf_{nm}", category="研报PDF", source="report_pdf",
                       name_cn=nm, formula="", direction=0,
                       rationale=f"来源: {prov}", overwrite=False)
            registered.append({"name": nm, "type": "factor_name", "report": row["title"][:40]})
        # register factor concepts with the report's own reasoning as evidence
        for theme, evidence in concepts.items():
            if not evidence:
                continue
            add_factor(f"pdfconcept_{theme}", category="研报PDF", source="report_pdf",
                       name_cn=f"研报概念-{theme}", formula="", direction=0,
                       rationale=f"来源: {prov} | 论据: {evidence[0][:80]}",
                       overwrite=False)
            registered.append({"name": theme, "type": "concept", "report": row["title"][:40]})
    return {"reports_downloaded": downloads, "reports_with_factors": len(mined),
            "factor_reports_found": len(rows),
            "mined": mined, "registered_factors": registered}
