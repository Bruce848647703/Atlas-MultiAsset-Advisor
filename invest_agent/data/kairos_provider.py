"""Real cross-asset ETF returns from the sibling Kairos data repository.

``kairos-data`` commits a clean, offline ETF panel (``data/etf/*.csv``). This
provider maps the overlapping Atlas assets onto those CSVs and fills the rest
from the deterministic synthetic world, so the full multi-asset universe keeps
working even when a symbol is not covered.

Provider name: ``kairos``.
"""

from __future__ import annotations

from typing import Iterable

import pandas as pd

from ..integrations.kairos import ATLAS_TO_KAIROS, etf_dir, load_etf_monthly
from .base import DataProvider, register_provider
from .synthetic import SyntheticProvider


@register_provider
class KairosProvider(DataProvider):
    name = "kairos"

    def __init__(self, universe=None, seed: int = 20240601, n_months: int = 120,
                 data_dir=None):
        from .universe import build_universe
        self.universe = universe or build_universe()
        self.n_months = n_months
        self.syn = SyntheticProvider(universe=self.universe, seed=seed,
                                     n_months=n_months)
        self.data_dir = data_dir or etf_dir()

    @property
    def mapped_ids(self):
        return {a.id for a in self.universe if a.id in ATLAS_TO_KAIROS}

    def get_monthly_returns(self, asset_ids: Iterable[str], n_months: int = 120) -> pd.DataFrame:
        ids = list(asset_ids)
        base = self.syn.get_monthly_returns(ids, n_months)
        if self.data_dir is None:
            return base

        idx = base.index
        out = base.copy()
        for aid in ids:
            symbol = ATLAS_TO_KAIROS.get(aid)
            if symbol is None:
                continue
            series = load_etf_monthly(symbol, str(self.data_dir) if self.data_dir else None)
            if series is None or series.empty:
                continue
            # Align to the provider's month-end PeriodIndex; keep synthetic for
            # the early history where the ETF did not exist yet.
            monthly = series.copy()
            monthly.index = monthly.index.to_period("M")
            aligned = monthly.reindex(idx)
            if aligned.notna().sum() < 12:
                continue
            out[aid] = aligned.where(aligned.notna(), base[aid])
        return out