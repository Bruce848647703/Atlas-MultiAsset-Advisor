"""Global market indices board (the flagship / 形象工程 panel).

Dual-source design for reliability (this panel is always on):

  * PRIMARY  — Tencent quote API (qt.gtimg.cn): very stable, covers the
    Chinese mainland, HK and US indices. Always attempted.
  * EXTENDED — eastmoney push2 API: broader coverage (Japan/Europe/Korea/
    India/Australia/Canada...). Best-effort; merged in when reachable.

Plus: retries with backoff, TTL cache (a transient failure still serves
fresh-enough data), and graceful degradation (stale cache > empty).

An approximate trading-session status (交易中/已收盘) per region is derived
from the current UTC time (session windows are approximations, DST ignored).
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests

_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "data_cache")
_CACHE_PATH = os.path.join(_CACHE_DIR, "global_indices.json")
_CACHE_TTL_MIN = 5.0

_HEADERS_EM = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
               "Referer": "https://quote.eastmoney.com/"}
_EM_API = "https://push2.eastmoney.com/api/qt/clist/get"

# (tencent_code, name_zh, region)  — reliable core
TENCENT_INDICES = [
    ("sh000001", "上证指数", "中国内地"),
    ("sz399001", "深证成指", "中国内地"),
    ("sz399006", "创业板指", "中国内地"),
    ("sh000300", "沪深300", "中国内地"),
    ("hkHSI",    "恒生指数", "亚太"),
    ("usINX",    "标普500", "美洲"),
    ("usIXIC",   "纳斯达克", "美洲"),
    ("usDJI",    "道琼斯", "美洲"),
]

# (eastmoney_secid, name_zh, region)  — extended, best-effort
EM_INDICES = [
    ("100.N225",  "日经225", "亚太"),
    ("100.KS11",  "韩国KOSPI", "亚太"),
    ("100.SENSEX", "印度SENSEX", "亚太"),
    ("100.STI",   "新加坡海峡时报", "亚太"),
    ("100.AS51",  "澳洲标普200", "亚太"),
    ("100.FTSE",  "英国富时100", "欧洲"),
    ("100.GDAXI", "德国DAX", "欧洲"),
    ("100.FCHI",  "法国CAC40", "欧洲"),
    ("100.TSX",   "加拿大TSX", "美洲"),
]

_REGION_ORDER = ["中国内地", "亚太", "欧洲", "美洲"]

# approximate trading sessions in UTC (ignores DST): region -> (start_h, end_h)
_SESSIONS_UTC = {
    "中国内地": (1, 7),      # 09:30-15:00 CST
    "亚太":     (0, 8),      # HK/JP/KR/SG/AU spread
    "欧洲":     (8, 17),     # London/Paris/Frankfurt
    "美洲":     (13, 21),    # US/Canada
}


def _trading_status(region: str) -> str:
    now = datetime.now(timezone.utc)
    start, end = _SESSIONS_UTC.get(region, (0, 24))
    h = now.hour + now.minute / 60.0
    return "交易中" if start <= h < end else "已收盘"


# ---------------------------------------------------------------------------
# sources
# ---------------------------------------------------------------------------
def _fetch_tencent() -> List[Dict]:
    codes = ",".join(c for c, _, _ in TENCENT_INDICES)
    r = requests.get(f"http://qt.gtimg.cn/q={codes}", timeout=15)
    r.encoding = "gbk"
    meta = {c: (n, reg) for c, n, reg in TENCENT_INDICES}
    out = []
    for line in r.text.strip().split(";"):
        line = line.strip()
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        code = key.split("v_", 1)[-1]
        f = val.strip('"').split("~")
        if code not in meta or len(f) < 33:
            continue
        name, region = meta[code]

        def _f(i):
            try:
                return float(f[i])
            except (ValueError, IndexError):
                return None

        price, chg, prev = _f(3), _f(32), _f(4)
        if price is None:
            continue
        out.append({"code": code, "name": name, "region": region,
                    "price": price, "chg_pct": chg, "prev_close": prev,
                    "status": _trading_status(region), "source": "tencent"})
    return out


def _fetch_em() -> List[Dict]:
    fs = ",".join(f"i:{sid}" for sid, _, _ in EM_INDICES)
    params = {"np": "2", "fltt": "2", "invt": "2", "fs": fs,
              "fields": "f12,f14,f2,f3,f18", "fid": "f3",
              "pn": "1", "pz": "100", "po": "1"}
    r = requests.get(_EM_API, params=params, headers=_HEADERS_EM, timeout=15)
    diff = (r.json().get("data") or {}).get("diff")
    items = list(diff.values()) if isinstance(diff, dict) else (diff or [])
    by_code = {str(x.get("f12")): x for x in items}
    out = []
    for sid, name, region in EM_INDICES:
        x = by_code.get(sid.split(".")[1], {})
        price, chg, prev = x.get("f2"), x.get("f3"), x.get("f18")
        if not isinstance(price, (int, float)):
            continue
        out.append({"code": sid, "name": name, "region": region,
                    "price": float(price),
                    "chg_pct": float(chg) if isinstance(chg, (int, float)) else None,
                    "prev_close": float(prev) if isinstance(prev, (int, float)) else None,
                    "status": _trading_status(region), "source": "eastmoney"})
    return out


# ---------------------------------------------------------------------------
# cache
# ---------------------------------------------------------------------------
def _read_cache(max_age_min: float) -> Optional[Dict]:
    if not os.path.exists(_CACHE_PATH):
        return None
    age_min = (time.time() - os.path.getmtime(_CACHE_PATH)) / 60.0
    if age_min > max_age_min:
        return None
    try:
        with open(_CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


def _write_cache(pack: Dict) -> None:
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        with open(_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(pack, f, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def fetch_global_indices(retries: int = 3, backoff: float = 1.0,
                         cache_ttl_min: float = _CACHE_TTL_MIN) -> Dict:
    """Return {updated_at, source_ok, note, regions: {region: [indices]}}.

    Tencent is retried (core must succeed); eastmoney is a single best-effort
    attempt. Falls back to cache on total failure."""
    indices: List[Dict] = []
    core_ok = False
    for attempt in range(1, retries + 1):
        try:
            t = _fetch_tencent()
            if t:
                indices = t
                core_ok = True
                break
        except Exception:  # noqa: BLE001
            time.sleep(backoff * attempt)

    note = None
    if core_ok:
        try:
            indices.extend(_fetch_em())          # best-effort extension
        except Exception:  # noqa: BLE001
            note = "部分国际指数(东财源)暂不可用"
    if indices:
        pack = {"updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "source_ok": core_ok, "note": note, "indices": indices}
        _write_cache(pack)
        return _group(pack)

    cached = _read_cache(max_age_min=60)
    if cached:
        cached["source_ok"] = False
        cached["note"] = "实时接口暂不可用，展示缓存数据"
        return _group(cached)
    return {"updated_at": None, "source_ok": False,
            "note": "全球指数数据暂不可用",
            "regions": {r: [] for r in _REGION_ORDER}}


def _group(pack: Dict) -> Dict:
    regions: Dict[str, List[Dict]] = {r: [] for r in _REGION_ORDER}
    for it in pack.get("indices", []):
        regions.setdefault(it["region"], []).append(it)
    return {"updated_at": pack.get("updated_at"),
            "source_ok": pack.get("source_ok", False),
            "note": pack.get("note"),
            "regions": regions}
