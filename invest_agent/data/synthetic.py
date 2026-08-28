"""Offline synthetic market world.

A seeded, reproducible multi-asset return generator used for:
  * local development / CI without network access,
  * training-data generation for the LLM advisor,
  * backtest sanity checks.

The generator is deliberately stylized but realistic in shape: correlated
classes (cholesky sampling), vol clustering, fat tails via global shocks,
a bear regime and a boom regime.
"""

from __future__ import annotations

from datetime import date
from typing import Iterable, List, Optional

import numpy as np
import pandas as pd

from ..config import class_priors
from .base import DataProvider, register_provider

CLASS_ORDER = ["cash", "fixed_income", "hybrid", "commodity", "equity_cn", "equity_global", "crypto", "futures"]

# Annualized cross-class correlation skeleton.
CLASS_CORR = {
    "cash":          {"cash": 1.0, "fixed_income": 0.05, "hybrid": 0.05, "commodity": 0.02, "equity_cn": 0.02, "equity_global": 0.03, "crypto": 0.01, "futures": 0.01},
    "fixed_income":  {"fixed_income": 1.0, "hybrid": 0.35, "commodity": 0.15, "equity_cn": 0.10, "equity_global": 0.12, "crypto": 0.05, "futures": 0.08},
    "hybrid":        {"hybrid": 1.0, "commodity": 0.10, "equity_cn": 0.55, "equity_global": 0.35, "crypto": 0.10, "futures": 0.10},
    "commodity":     {"commodity": 1.0, "equity_cn": 0.12, "equity_global": 0.10, "crypto": 0.12, "futures": 0.35},
    "equity_cn":     {"equity_cn": 1.0, "equity_global": 0.30, "crypto": 0.22, "futures": 0.28},
    "equity_global": {"equity_global": 1.0, "crypto": 0.35, "futures": 0.20},
    "crypto":        {"crypto": 1.0, "futures": 0.10},
    "futures":       {"futures": 1.0},
}

WITHIN_CLASS_CORR = {"cash": 0.3, "fixed_income": 0.85, "hybrid": 0.70, "commodity": 0.6,
                     "equity_cn": 0.88, "equity_global": 0.85, "crypto": 0.90, "futures": 0.5}

# Per-asset tweaks on top of class priors: (drift adjustment, vol multiplier)
ASSET_TWEAKS = {
    "csi500_etf":         (+0.005, 1.15),
    "gem_etf":            (+0.005, 1.35),
    "star50_etf":         (+0.010, 1.50),
    "dividend_etf":       (-0.010, 0.70),
    "healthcare_etf":     (+0.005, 1.25),
    "consumer_etf":       (0.000, 0.95),
    "nasdaq_etf":         (+0.020, 1.20),
    "sp500_etf":          (0.000, 0.95),
    "hstech_etf":         (+0.005, 1.30),
    "nikkei_etf":         (-0.010, 0.85),
    "bond_etf":           (-0.005, 0.60),
    "oil_qdii":           (0.000, 1.10),
    "gold_etf":           (+0.005, 0.90),
    "eth":                (+0.030, 1.10),
    "sol":                (+0.040, 1.15),
    "bnb":                (+0.020, 1.00),
    "xrp":                (0.000, 1.10),
    "doge":               (0.000, 1.30),
    "stock_index_future": (-0.010, 0.80),
    "treasury_future":    (-0.015, 0.35),
}


def _make_psd(corr: np.ndarray) -> np.ndarray:
    vals, vecs = np.linalg.eigh(corr)
    vals = np.clip(vals, 1e-6, None)
    m = vecs @ np.diag(vals) @ vecs.T
    d = np.sqrt(np.diag(m))
    return m / np.outer(d, d)


def _asset_corr_matrix(assets: List) -> np.ndarray:
    n = len(assets)
    corr = np.eye(n)
    for i in range(n):
        for j in range(i + 1, n):
            ci, cj = assets[i].asset_class, assets[j].asset_class
            if ci == cj:
                c = WITHIN_CLASS_CORR[ci]
            else:
                c = CLASS_CORR[ci].get(cj, CLASS_CORR[cj].get(ci, 0.0))
            corr[i, j] = corr[j, i] = c
    return _make_psd(corr)


@register_provider
class SyntheticProvider(DataProvider):
    """Seeded multi-asset return generator (monthly, GBM-like)."""

    name = "synthetic"

    def __init__(self, universe=None, seed: int = 20240601, n_months: int = 120):
        from .universe import build_universe

        self.universe = universe or build_universe()
        self.seed = int(seed)
        self.n_months = int(n_months)
        self._full: Optional[pd.DataFrame] = None

    # -- generation -------------------------------------------------------
    def _generate(self) -> pd.DataFrame:
        assets = self.universe
        ids = [a.id for a in assets]
        n = len(assets)
        rng = np.random.default_rng(self.seed)
        priors = class_priors()

        ann_ret = np.array([
            priors[a.asset_class]["ann_ret"] + ASSET_TWEAKS.get(a.id, (0.0, 1.0))[0]
            for a in assets
        ])
        ann_vol = np.array([
            priors[a.asset_class]["ann_vol"] * ASSET_TWEAKS.get(a.id, (0.0, 1.0))[1]
            for a in assets
        ])
        mu_m = (ann_ret - 0.5 * ann_vol ** 2) / 12.0
        sig_m = ann_vol / np.sqrt(12.0)

        corr = _asset_corr_matrix(assets)
        L = np.linalg.cholesky(corr)

        T = self.n_months
        Z = rng.standard_normal((T, n))
        vol_cluster = np.exp(rng.normal(0.0, 0.22, T))      # vol clustering
        eps = Z @ L.T
        R = mu_m[None, :] + sig_m[None, :] * eps * vol_cluster[:, None]

        # regimes: bear m30..41, crypto crash at m36, boom m70..83
        classes = [a.asset_class for a in assets]
        risky = np.array([c in ("equity_cn", "equity_global", "crypto", "futures") for c in classes])
        for m in range(T):
            if 30 <= m < 42:
                R[m, risky] -= 0.018
            if 70 <= m < 84:
                R[m, risky] += 0.006
        R[36, [i for i, c in enumerate(classes) if c == "crypto"]] -= 0.22

        # cash never negative, tiny dispersion
        cash_idx = [i for i, c in enumerate(classes) if c == "cash"]
        for i in cash_idx:
            R[:, i] = np.abs(R[:, i]) * 0.3 + priors["cash"]["ann_ret"] / 12.0 * 0.9

        end = pd.Period(f"{date.today().year}-{date.today().month:02d}", freq="M") - 1
        idx = pd.period_range(end=end, periods=T, freq="M")
        return pd.DataFrame(R, index=idx, columns=ids)

    # -- API ---------------------------------------------------------------
    def full(self) -> pd.DataFrame:
        if self._full is None:
            self._full = self._generate()
        return self._full

    def get_monthly_returns(self, asset_ids: Iterable[str], n_months: int = 120) -> pd.DataFrame:
        df = self.full()
        n_months = min(n_months, len(df))
        df = df.iloc[-n_months:]
        missing = [a for a in asset_ids if a not in df.columns]
        if missing:
            raise KeyError(f"synthetic provider has no series for {missing}")
        return df[list(asset_ids)]
