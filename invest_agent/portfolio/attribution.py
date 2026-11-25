"""Return, risk and factor attribution for a plan.

Answers three different questions:

* **Return**: how much did each asset/class contribute to the portfolio return?
* **Risk**: where does current volatility come from (Euler component risk)?
* **Factor**: how much is market beta / value / momentum / low-vol / size /
  rates / commodity / crypto, and how much is unexplained alpha?

The factor proxies are built from the Atlas universe itself, so this works with
the synthetic, akshare and Kairos providers without extra data dependencies.
Attribution is research/education, not a performance guarantee.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

_CLASS_EN = {
    "cash": "Cash", "fixed_income": "Fixed income", "hybrid": "Hybrid",
    "commodity": "Commodities", "equity_cn": "China equities",
    "equity_global": "Global equities", "crypto": "Crypto", "futures": "Futures",
}


def _returns(plan, n_months: Optional[int] = None) -> pd.DataFrame:
    from ..data.base import get_provider
    ids = [a.id for a in plan.assets]
    provider = get_provider(plan.provider_name)
    months = int(n_months or plan.n_months or 96)
    return provider.get_monthly_returns(ids, months)[ids].fillna(0.0)


def _class_map(plan) -> Dict[str, str]:
    return {a.id: a.asset_class for a in plan.assets}


def _factor_frame(returns: pd.DataFrame, plan) -> pd.DataFrame:
    cls = _class_map(plan)
    equity = [aid for aid in returns.columns if cls.get(aid) in ("equity_cn", "equity_global")]
    factors: Dict[str, pd.Series] = {}
    if equity:
        factors["market"] = returns[equity].mean(axis=1)
    if "csi500_etf" in returns and "csi300_etf" in returns:
        factors["size"] = returns["csi500_etf"] - returns["csi300_etf"]
    if "dividend_etf" in returns and "gem_etf" in returns:
        factors["value"] = returns["dividend_etf"] - returns["gem_etf"]
    if "bond_etf" in returns:
        factors["rates"] = returns["bond_etf"]
    if "gold_etf" in returns:
        factors["commodity"] = returns["gold_etf"]
    crypto = [aid for aid in returns.columns if cls.get(aid) == "crypto"]
    if crypto:
        factors["crypto"] = returns[crypto].mean(axis=1)

    # Time-series momentum / low-vol factors: rank on trailing 12m data, hold
    # next month's return (signal shifted one month -> no look-ahead).
    if equity:
        mom_signal = returns[equity].rolling(12).mean().shift(1)
        vol_signal = returns[equity].rolling(12).std().shift(1)
        mom = pd.Series(np.nan, index=returns.index)
        lowvol = pd.Series(np.nan, index=returns.index)
        for t in range(12, len(returns)):
            m = mom_signal.iloc[t].dropna()
            v = vol_signal.iloc[t].dropna()
            if len(m) >= 4:
                top = m.nlargest(max(2, len(m) // 3)).index
                bottom = m.nsmallest(max(2, len(m) // 3)).index
                mom.iloc[t] = returns.loc[returns.index[t], top].mean() - \
                    returns.loc[returns.index[t], bottom].mean()
            if len(v) >= 4:
                low = v.nsmallest(max(2, len(v) // 3)).index
                high = v.nlargest(max(2, len(v) // 3)).index
                lowvol.iloc[t] = returns.loc[returns.index[t], low].mean() - \
                    returns.loc[returns.index[t], high].mean()
        factors["momentum"] = mom
        factors["low_vol"] = lowvol
    frame = pd.DataFrame(factors).dropna(how="all")
    return frame.dropna(axis=1, how="all")


def _factor_regression(port: pd.Series, factors: pd.DataFrame) -> Dict[str, Any]:
    joined = pd.concat([port.rename("portfolio"), factors], axis=1).dropna()
    if len(joined) < 24:
        return {"available": False, "reason": "not enough aligned factor observations"}
    y = joined["portfolio"].values
    X = np.column_stack([np.ones(len(joined)), joined[factors.columns].values])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    alpha = float(coef[0])
    betas = {c: float(b) for c, b in zip(factors.columns, coef[1:])}
    fitted = X @ coef
    resid = y - fitted
    var_y = float(np.var(y, ddof=1))
    var_fit = float(np.var(fitted, ddof=1))
    r2 = max(0.0, min(1.0, var_fit / var_y)) if var_y > 1e-16 else 0.0
    return {
        "available": True,
        "n_obs": int(len(joined)),
        "alpha_monthly": round(alpha, 6),
        "alpha_annual": round(alpha * 12, 4),
        "betas": {k: round(v, 4) for k, v in betas.items()},
        "r2": round(r2, 4),
        "factor_risk_share": round(r2, 4),
        "residual_vol_annual": round(float(np.std(resid, ddof=1) * np.sqrt(12)), 4),
    }


def _return_contribution(returns: pd.DataFrame, weights: np.ndarray, plan) -> Dict[str, Any]:
    cls = _class_map(plan)
    contrib = returns.mul(weights, axis=1)
    class_contrib: Dict[str, float] = {}
    for aid in returns.columns:
        c = cls.get(aid, "unknown")
        class_contrib[c] = class_contrib.get(c, 0.0) + float(contrib[aid].sum())
    total = float(contrib.values.sum())
    return {
        "total": round(total, 4),
        "by_class": {k: round(v, 4) for k, v in
                     sorted(class_contrib.items(), key=lambda kv: -abs(kv[1]))},
        "by_asset": {aid: round(float(contrib[aid].sum()), 4)
                     for aid in returns.columns
                     if abs(float(contrib[aid].sum())) > 1e-6},
    }


def _risk_contribution(returns: pd.DataFrame, weights: np.ndarray, plan) -> Dict[str, Any]:
    cov = returns.cov().values
    w = np.asarray(weights, dtype=float)
    port_var = float(w @ cov @ w)
    port_vol = float(np.sqrt(max(port_var, 0.0)))
    if port_vol <= 1e-12:
        return {"available": False, "reason": "zero portfolio volatility"}
    marginal = cov @ w / port_vol
    component = w * marginal
    total = float(component.sum())
    pct = component / total if abs(total) > 1e-12 else np.zeros_like(component)
    cls = _class_map(plan)
    by_class: Dict[str, float] = {}
    for aid, p in zip(returns.columns, pct):
        c = cls.get(aid, "unknown")
        by_class[c] = by_class.get(c, 0.0) + float(p)
    hhi = float(np.sum(pct ** 2))
    return {
        "available": True,
        "vol_annual": round(float(port_vol) * float(np.sqrt(12)), 4),
        "by_asset": {aid: round(float(p), 4)
                     for aid, p in zip(returns.columns, pct)},
        "by_class": {k: round(v, 4) for k, v in
                     sorted(by_class.items(), key=lambda kv: -abs(kv[1]))},
        "effective_n": round(1.0 / hhi, 2) if hhi > 0 else 0.0,
    }


def analyze(plan, n_months: Optional[int] = None) -> Dict[str, Any]:
    """Return, risk and factor attribution for the current plan."""
    try:
        returns = _returns(plan, n_months=n_months)
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": f"returns unavailable: {exc}"}
    if len(returns) < 24:
        return {"available": False, "reason": "need at least 24 months of returns"}

    ids = list(returns.columns)
    w = np.array([plan.weights.get(aid, 0.0) for aid in ids])
    eq = getattr(plan, "equity_curve", None)
    if eq is None or len(eq) < 24:
        port = returns.mul(w, axis=1).sum(axis=1)
    else:
        port = eq.pct_change().dropna()
        port = port.reindex(returns.index).dropna()
    factors = _factor_frame(returns, plan)
    factor = _factor_regression(port, factors) if not factors.empty else {
        "available": False, "reason": "no factor proxies"}
    return {
        "available": True,
        "n_months": int(len(returns)),
        "total_return": round(float((1.0 + port).prod() - 1.0), 4),
        "return": _return_contribution(returns, w, plan),
        "risk": _risk_contribution(returns, w, plan),
        "factor": factor,
    }