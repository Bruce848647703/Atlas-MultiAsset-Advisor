"""Real-market provider based on akshare (A-share ETFs / public funds).

Crypto and futures columns are not served by akshare for retail access in
a stable way; the :class:`MergedProvider` transparently fills those from a
seeded synthetic source so the full multi-asset pipeline always works.

Network access is required only at construction time; results are cached
under ``data_cache/``.
"""

from __future__ import annotations

import os
from typing import Iterable, List, Optional

import numpy as np
import pandas as pd

from .base import DataProvider, register_provider

CASH_IDS = {"money_fund"}

_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data_cache")


_RESAMPLE_FREQ = "ME" if pd.__version__ >= "2.2" else "M"


def _to_monthly_returns(prices: pd.Series) -> pd.Series:
    prices = prices.sort_index()
    monthly = prices.resample(_RESAMPLE_FREQ).last().dropna()
    return monthly.pct_change().dropna()


@register_provider
class AkshareProvider(DataProvider):
    name = "akshare"

    def __init__(self, universe=None, use_cache: bool = True, n_months: int = 120):
        from .universe import build_universe

        self.universe = universe or build_universe()
        self.use_cache = use_cache
        self.n_months = n_months
        os.makedirs(_CACHE_DIR, exist_ok=True)

    def _cache_path(self, asset_id: str) -> str:
        return os.path.join(_CACHE_DIR, f"ak_{asset_id}_monthly.csv")

    def _fetch_asset(self, asset) -> pd.Series:
        if self.use_cache:
            p = self._cache_path(asset.id)
            if os.path.exists(p):
                s = pd.read_csv(p, index_col=0, parse_dates=True).iloc[:, 0]
                return s

        import akshare as ak  # lazy: heavy import

        meta = getattr(asset, "meta", {}) or {}
        source = str(meta.get("source", "none"))
        s: Optional[pd.Series] = None
        if asset.id in CASH_IDS:
            end = pd.Period(pd.Timestamp.today(), freq="M") - 1
            idx = pd.period_range(end=end, periods=self.n_months, freq="M")
            s = pd.Series(0.02 / 12.0, index=idx.to_timestamp(how="end"))
        elif source == "etf":
            df = ak.fund_etf_hist_em(symbol=str(meta.get("symbol_ak")), period="monthly", adjust="qfq")
            close_col = "收盘" if "收盘" in df.columns else df.columns[4]
            date_col = "日期" if "日期" in df.columns else df.columns[0]
            prices = pd.Series(df[close_col].astype(float).values, index=pd.to_datetime(df[date_col]))
            s = _to_monthly_returns(prices)
        elif source == "fund":
            df = ak.fund_open_fund_info_em(symbol=str(meta.get("symbol_ak")), indicator="累计净值")
            prices = pd.Series(df["累计净值"].astype(float).values, index=pd.to_datetime(df["净值日期"]))
            s = _to_monthly_returns(prices)
        else:
            raise NotImplementedError(f"akshare provider does not serve '{asset.id}' (source={source})")

        if s is not None and self.use_cache:
            s.to_csv(self._cache_path(asset.id))
        return s

    def get_monthly_returns(self, asset_ids: Iterable[str], n_months: int = 120) -> pd.DataFrame:
        series = {}
        errors = {}
        for asset in self.universe:
            if asset.id not in set(asset_ids):
                continue
            try:
                s = self._fetch_asset(asset)
                if s is not None:
                    series[asset.id] = s
            except Exception as e:  # noqa: BLE001 - per-asset fallback
                errors[asset.id] = str(e)
        if not series:
            raise RuntimeError(f"akshare provider failed for all assets: {errors}")
        df = pd.DataFrame(series).dropna(how="all")
        df.index = pd.to_datetime(df.index).to_period("M")
        df = df.iloc[-n_months:]
        return df


@register_provider
class MergedProvider(DataProvider):
    """akshare where possible, synthetic for the rest (crypto/futures)."""

    name = "merged"

    def __init__(self, universe=None, seed: int = 20240601, n_months: int = 120):
        from .synthetic import SyntheticProvider
        from .universe import build_universe

        self.universe = universe or build_universe()
        self.n_months = n_months
        self.ak = AkshareProvider(universe=self.universe, n_months=n_months)
        self.syn = SyntheticProvider(universe=self.universe, seed=seed, n_months=n_months)

    def get_monthly_returns(self, asset_ids: Iterable[str], n_months: int = 120) -> pd.DataFrame:
        ids = list(asset_ids)
        try:
            real = self.ak.get_monthly_returns(ids, n_months)
        except Exception:  # no network etc.
            return self.syn.get_monthly_returns(ids, n_months)
        missing = [a for a in ids if a not in real.columns]
        if missing:
            synth = self.syn.get_monthly_returns(ids, n_months)
            real = real.join(synth[missing], how="outer").sort_index()
        df = real[ids].iloc[-n_months:]
        df = df.dropna(how="all").ffill().bfill().fillna(0.0)
        return df
