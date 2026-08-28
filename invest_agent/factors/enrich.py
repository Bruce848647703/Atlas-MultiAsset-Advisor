"""Live factor enrichment via free online data endpoints (akshare).

Turns previously-skipped factor families into REAL computed factors for the
ETF part of the universe:

  * 资金流因子   -> 主力净流入净占比 / 超大单净流入净占比  (fund_etf_spot_em)
  * 流动性因子   -> 换手率 / 成交额 / 量比                 (fund_etf_spot_em)
  * 规模因子     -> 流通市值                               (fund_etf_spot_em)
  * 估值因子     -> 跟踪指数滚动PE的历史分位(近10年)        (stock_index_pe_lg)

Assets without exchange data (crypto / futures proxies / OTC funds) get NaN
and fall back to return-based proxies — the composite scorer renormalizes
weights per asset so nothing is fabricated.

All fetches are cached under data_cache/ with TTLs (intraday snapshot 4h,
valuation 24h) and degrade to empty on any network failure.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, Optional

import pandas as pd

_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data_cache")

# universe ETF asset id -> index whose PE history we can pull (legu endpoint)
INDEX_PE_MAP = {"csi300_etf": "沪深300", "csi500_etf": "中证500"}

ETF_LIVE_TTL_H = 4.0
INDEX_VAL_TTL_H = 24.0


def _cache_fresh(path: str, ttl_hours: float) -> bool:
    if not os.path.exists(path):
        return False
    age_h = (datetime.now().timestamp() - os.path.getmtime(path)) / 3600.0
    return age_h < ttl_hours


def fetch_etf_live_factors(etf_symbols: Dict[str, str], use_cache: bool = True) -> pd.DataFrame:
    """Real-time liquidity / money-flow / size factors for exchange ETFs.

    etf_symbols: {asset_id: akshare ETF code}
    Returns DataFrame indexed by asset_id (empty on failure).
    """
    os.makedirs(_CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(_CACHE_DIR, "etf_live_factors.csv")
    if use_cache and _cache_fresh(cache_path, ETF_LIVE_TTL_H):
        try:
            df = pd.read_csv(cache_path, index_col=0)
            keep = [a for a in etf_symbols if a in df.index]
            return df.loc[keep] if keep else df.iloc[0:0]
        except Exception:  # noqa: BLE001 - corrupt cache -> refetch
            pass
    try:
        import akshare as ak
        spot = ak.fund_etf_spot_em()
    except Exception:  # noqa: BLE001 - offline / endpoint down
        return pd.DataFrame()

    spot = spot.set_index("代码")
    rows = {}
    for asset_id, code in etf_symbols.items():
        if str(code) not in spot.index:
            continue
        r = spot.loc[str(code)]
        rows[asset_id] = {
            "turnover_rate": _num(r.get("换手率")),
            "turnover_amount": _num(r.get("成交额")),
            "main_net_inflow_pct": _num(r.get("主力净流入-净占比")),
            "big_order_pct": _num(r.get("超大单净流入-净占比")),
            "float_mcap": _num(r.get("流通市值")),
            "volume_ratio": _num(r.get("量比")),
            "discount_rate": _num(r.get("基金折价率")),
            "pct_chg_1d": _num(r.get("涨跌幅")),
        }
    df = pd.DataFrame.from_dict(rows, orient="index")
    if not df.empty:
        df.to_csv(cache_path)
    return df


def fetch_index_pe_percentile(index_symbol: str, lookback_years: int = 10,
                              use_cache: bool = True) -> Optional[Dict[str, float]]:
    """Latest rolling PE of an index + its percentile over the lookback window.

    Low percentile = historically cheap. Returns None on failure.
    """
    os.makedirs(_CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(_CACHE_DIR, f"index_pe_{index_symbol}.csv")
    hist = None
    if use_cache and _cache_fresh(cache_path, INDEX_VAL_TTL_H):
        try:
            hist = pd.read_csv(cache_path)
        except Exception:  # noqa: BLE001
            hist = None
    if hist is None:
        try:
            import akshare as ak
            hist = ak.stock_index_pe_lg(symbol=index_symbol)
            hist.to_csv(cache_path, index=False)
        except Exception:  # noqa: BLE001
            return None

    try:
        pe_col = "滚动市盈率"
        hist["日期"] = pd.to_datetime(hist["日期"])
        win = hist[hist["日期"] >= hist["日期"].max() - pd.Timedelta(days=365 * lookback_years)]
        series = pd.to_numeric(win[pe_col], errors="coerce").dropna()
        if len(series) < 100:
            return None
        latest = float(series.iloc[-1])
        pct = float((series < latest).mean() * 100.0)
        return {"pe": latest, "pe_percentile": pct, "as_of": str(hist["日期"].max().date())}
    except Exception:  # noqa: BLE001
        return None


def enrich_universe(assets, use_cache: bool = True) -> pd.DataFrame:
    """Full enrichment panel for the universe (NaN where data unavailable)."""
    etf_symbols = {}
    for a in assets:
        code = (a.meta or {}).get("symbol_ak")
        if (a.meta or {}).get("source") == "etf" and code:
            etf_symbols[a.id] = str(code)

    try:
        live = fetch_etf_live_factors(etf_symbols, use_cache=use_cache)
    except Exception:  # noqa: BLE001 - defensive: live layer is optional
        live = pd.DataFrame()
    val_rows = {}
    for asset_id, idx_sym in INDEX_PE_MAP.items():
        if asset_id in etf_symbols:
            try:
                v = fetch_index_pe_percentile(idx_sym, use_cache=use_cache)
            except Exception:  # noqa: BLE001
                v = None
            if v:
                val_rows[asset_id] = v
    val = pd.DataFrame.from_dict(val_rows, orient="index")

    if live.empty and val.empty:
        return pd.DataFrame()
    out = live.join(val, how="outer") if not live.empty else val
    return out


def _num(x):
    try:
        import math
        v = float(x)
        return v if math.isfinite(v) else float("nan")
    except (TypeError, ValueError):
        return float("nan")
