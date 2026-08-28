"""Factor lens: screen assets using factor-family proxies + live factors.

Two data layers, combined into one composite score per asset:

A. Return-based proxies (computable for the whole universe):
     Momentum (+), short-term reversal (−), low volatility (−), drawdown (−)

B. Live factors from free online endpoints (ETFs only, via enrich.py):
     Valuation   (−):  tracking-index rolling-PE percentile (10y window)
     Liquidity   (+):  log turnover amount
     Money flow  (+):  main-force net inflow percentage

Per-asset z-scores are computed cross-sectionally on available values only;
each asset's composite renormalizes factor weights over the factors it
actually has — nothing is fabricated for data-poor assets.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .loader import FactorCatalog

# (factor, direction, weight, source)
FACTORS = [
    ("momentum",           +1, 0.30, "return"),
    ("reversal_1m",        -1, 0.10, "return"),
    ("low_vol",            -1, 0.15, "return"),
    ("drawdown",           -1, 0.10, "return"),
    ("pe_percentile",      -1, 0.15, "live"),   # cheaper (low pct) = better
    ("liquidity",          +1, 0.10, "live"),
    ("money_flow",         +1, 0.10, "live"),
]

# families still not computable even with online endpoints (need daily
# single-stock fundamentals/analyst data)
NOT_COMPUTABLE = ["财务", "盈利", "成长因子", "投资因子", "分析师", "注意力", "另类"]


def _trailing_features(rets: pd.Series) -> Dict[str, float]:
    r = rets.dropna().values
    n = len(r)
    if n < 13:
        return {}
    last12 = r[-12:]
    mom_12_1 = float(np.prod(1.0 + r[-13:-1]) - 1.0)
    rev_1m = float(r[-1])
    vol = float(np.std(last12, ddof=1) * np.sqrt(12))
    wealth = np.cumprod(1.0 + last12)
    peak = np.maximum.accumulate(np.concatenate(([1.0], wealth)))[1:]
    maxdd = float((1.0 - wealth / peak).max())
    return {"momentum": mom_12_1, "reversal_1m": rev_1m,
            "low_vol": vol, "drawdown": maxdd}


def _live_features(enrichment: pd.DataFrame, asset_id: str) -> Dict[str, float]:
    if enrichment is None or enrichment.empty or asset_id not in enrichment.index:
        return {}
    row = enrichment.loc[asset_id]
    out = {}
    pe_pct = row.get("pe_percentile", np.nan)
    if pd.notna(pe_pct):
        out["pe_percentile"] = float(pe_pct)
    amt = row.get("turnover_amount", np.nan)
    if pd.notna(amt) and amt > 0:
        out["liquidity"] = float(np.log10(amt))
    flow = row.get("main_net_inflow_pct", np.nan)
    if pd.notna(flow):
        out["money_flow"] = float(flow)
    return out


def compute_factor_scores(
    monthly_returns: pd.DataFrame,
    enrichment: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Per-asset factor values + composite score (missing-aware weighting)."""
    rows = []
    for col in monthly_returns.columns:
        feats = _trailing_features(monthly_returns[col])
        if not feats:
            continue
        feats.update(_live_features(enrichment, col))
        rows.append({"asset": col, **feats})
    df = pd.DataFrame(rows).set_index("asset")
    if df.empty:
        return df

    # cross-sectional z-scores on available values per factor
    z = pd.DataFrame(index=df.index)
    for name, _d, _w, _src in FACTORS:
        if name not in df.columns:
            continue
        x = df[name].astype(float)
        ok = x.notna()
        if ok.sum() >= 2:
            mu, sd = x[ok].mean(), x[ok].std(ddof=1)
            z.loc[ok, name] = (x[ok] - mu) / (sd + 1e-12)

    # per-asset weighted composite over its AVAILABLE factors
    score = np.zeros(len(df))
    coverage = np.zeros(len(df))
    for name, direction, weight, _src in FACTORS:
        if name not in z.columns:
            continue
        vals = z[name].values
        ok = ~np.isnan(vals)
        score += np.where(ok, direction * weight * np.nan_to_num(vals), 0.0)
        coverage += np.where(ok, weight, 0.0)
    df["score"] = score / np.maximum(coverage, 1e-9)
    df["factor_coverage"] = coverage
    live_names = [n for n, _d, _w, s in FACTORS if s == "live" and n in z.columns]
    df["n_live_factors"] = [
        int(sum(1 for n in live_names if pd.notna(z[n].iloc[i])))
        for i in range(len(df))
    ]
    return df.sort_values("score", ascending=False)


def screen_universe(
    monthly_returns: pd.DataFrame,
    assets,
    catalog: Optional[FactorCatalog] = None,
    enrichment: Optional[pd.DataFrame] = None,
) -> Dict[str, object]:
    """Rank the universe by composite factor score with full provenance."""
    scores = compute_factor_scores(monthly_returns, enrichment=enrichment)
    id_of = {a.id: a for a in assets}
    ranked = []
    for aid, row in scores.iterrows():
        a = id_of.get(aid)
        item = {
            "asset": aid,
            "name_zh": a.name_zh if a else aid,
            "class": a.asset_class if a else "?",
            "score": round(float(row["score"]), 3),
            "momentum": round(float(row["momentum"]), 4),
            "low_vol": round(float(row["low_vol"]), 4),
            "drawdown": round(float(row["drawdown"]), 4),
            "n_live_factors": int(row.get("n_live_factors", 0)),
        }
        for opt in ("pe_percentile", "liquidity", "money_flow"):
            if opt in row and pd.notna(row[opt]):
                item[opt] = round(float(row[opt]), 2)
        ranked.append(item)

    used_live = any(r["n_live_factors"] > 0 for r in ranked)
    skipped = []
    if catalog is not None:
        for cat in catalog.categories:
            if any(nc in cat for nc in NOT_COMPUTABLE):
                skipped.append(cat)

    return {
        "ranked": ranked,
        "factors": [
            {"factor": n, "direction": "+" if d > 0 else "−", "weight": w, "source": s}
            for n, d, w, s in FACTORS
        ],
        "live_data_used": used_live,
        "skipped_families": skipped[:12],
    }
