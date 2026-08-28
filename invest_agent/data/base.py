"""Pluggable market-data providers.

The advisor never talks to an exchange/API directly; it asks a
:class:`DataProvider` for a DataFrame of monthly returns. Providers can be
swapped freely (offline synthetic world, akshare, broker feeds...).
"""

from __future__ import annotations

from typing import Dict, Iterable, Type

import pandas as pd


class DataProvider:
    """Interface: monthly simple returns, index = month-end Period, columns = asset ids."""

    name = "base"

    def get_monthly_returns(self, asset_ids: Iterable[str], n_months: int = 120) -> pd.DataFrame:
        raise NotImplementedError


_REGISTRY: Dict[str, Type[DataProvider]] = {}


def register_provider(cls: Type[DataProvider]) -> Type[DataProvider]:
    _REGISTRY[cls.name] = cls
    return cls


def get_provider(name: str = "synthetic", **kwargs) -> DataProvider:
    if name not in _REGISTRY:
        # lazy import of optional providers (registers AkshareProvider + MergedProvider)
        if name in ("akshare", "merged"):
            from . import akshare_provider  # noqa: F401
    if name not in _REGISTRY:
        raise KeyError(f"unknown provider '{name}'; available: {sorted(_REGISTRY)}")
    return _REGISTRY[name](**kwargs)
