"""Portfolio construction.

Implements, deliberately without heavy QP dependencies:

* Ledoit-Wolf-style shrinkage for the covariance matrix
  (constant-correlation target, analytical oracle intensity).
* Expected-return shrinkage toward class priors (Black-Litterman spirit:
  temper noisy sample means with structured priors).
* Mean-variance optimization (SLSQP) with per-asset-class caps driven by
  the investor's suitability tier.
* Risk-parity fallback and an efficient-frontier scanner.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy.optimize import minimize

# ---------------------------------------------------------------------------
# Estimators
# ---------------------------------------------------------------------------


def expected_returns_shrinkage(
    monthly_returns: np.ndarray,
    prior_monthly: Optional[np.ndarray] = None,
    delta: float = 0.5,
) -> np.ndarray:
    """Shrink sample means toward structured priors.

    monthly_returns : (T, N)
    prior_monthly   : (N,) prior (e.g. class prior / 12)
    delta           : weight on the prior, in [0, 1]
    """
    mu = np.asarray(monthly_returns, dtype=float).mean(axis=0)
    if prior_monthly is None:
        return mu
    prior_monthly = np.asarray(prior_monthly, dtype=float)
    return delta * prior_monthly + (1.0 - delta) * mu


def cov_shrinkage(
    monthly_returns: np.ndarray,
) -> Tuple[np.ndarray, float]:
    """Ledoit-Wolf shrinkage toward a constant-correlation target.

    Returns (sigma_hat, shrinkage_intensity).
    Reference: Ledoit & Wolf (2003), "Honey, I Shrunk the Sample Covariance
    Matrix", oracle intensity for the constant-correlation target.
    """
    X = np.asarray(monthly_returns, dtype=float)
    T, N = X.shape
    X = X - X.mean(axis=0)
    S = X.T @ X / T

    X2 = X ** 2
    Phi = X2.T @ X2 / T - S ** 2            # pi_ij: asyvar of sqrt(T)*s_ij
    pi_total = float(Phi.sum())

    var = np.diag(S).copy()
    var = np.maximum(var, 1e-12)
    sd = np.sqrt(var)
    corr = S / np.outer(sd, sd)
    rbar = (float(corr.sum()) - N) / (N * (N - 1)) if N > 1 else 0.0
    rbar = float(np.clip(rbar, -0.99, 0.99))

    diag_part = float(np.trace(Phi))
    off = 0.0
    for i in range(N):
        for j in range(N):
            if i != j:
                off += 0.5 * rbar * (
                    Phi[i, i] * var[j] / var[i] + Phi[j, j] * var[i] / var[j]
                )
    rho_total = diag_part + off

    F = rbar * np.outer(sd, sd)
    np.fill_diagonal(F, var)
    gamma = float(((F - S) ** 2).sum())

    if gamma < 1e-16:
        delta = 1.0
    else:
        delta = float(np.clip((pi_total - rho_total) / (gamma * T), 0.0, 1.0))
    return (1.0 - delta) * S + delta * F, delta


# ---------------------------------------------------------------------------
# Constraints / helpers
# ---------------------------------------------------------------------------


def class_exposures(weights: np.ndarray, asset_classes: Sequence[str]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for i, c in enumerate(asset_classes):
        out[c] = out.get(c, 0.0) + float(weights[i])
    return out


def _clip_to_class_caps(
    w: np.ndarray, asset_classes: Sequence[str], class_caps: Dict[str, float]
) -> np.ndarray:
    """Water-filling clip: shrink the most-violated class to its cap and
    redistribute the freed mass proportionally to remaining assets."""
    w = np.clip(np.asarray(w, dtype=float), 0.0, None)
    if w.sum() <= 0:
        return np.full(len(w), 1.0 / len(w))
    w = w / w.sum()
    for _ in range(100):
        expo = class_exposures(w, asset_classes)
        viol = [(c, v) for c, v in expo.items()
                if c in class_caps and v > class_caps[c] + 1e-9]
        if not viol:
            break
        c, v = max(viol, key=lambda kv: kv[1] - class_caps[kv[0]])
        cap = class_caps[c]
        excess = v - cap
        idx = [i for i, cc in enumerate(asset_classes) if cc == c]
        others = [i for i in range(len(w)) if i not in idx]
        if v > 1e-12:
            w[idx] *= cap / v
        wo = w[others]
        if wo.sum() > 1e-12:
            w[others] = wo + excess * wo / wo.sum()
        elif others:
            w[others] += excess / len(others)
    return w / w.sum()


# ---------------------------------------------------------------------------
# Optimizers
# ---------------------------------------------------------------------------


def optimize_mean_variance(
    mu: np.ndarray,
    cov: np.ndarray,
    risk_aversion: float,
    asset_classes: Sequence[str],
    class_caps: Optional[Dict[str, float]] = None,
    max_weight: float = 1.0,
) -> np.ndarray:
    """Maximize  w'mu - (lambda/2) w'cov w  under class caps.

    Returns optimal weights (sum to 1, non-negative).
    Falls back to capped risk-parity if SLSQP fails.
    """
    mu = np.asarray(mu, dtype=float)
    cov = np.asarray(cov, dtype=float)
    n = len(mu)
    class_caps = class_caps or {}

    def neg_util(w):
        return -(w @ mu - 0.5 * risk_aversion * (w @ cov @ w))

    def neg_util_grad(w):
        return -(mu - risk_aversion * cov @ w)

    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1.0, "jac": lambda w: np.ones(n)}]
    classes = sorted(set(asset_classes))
    for c in classes:
        if c in class_caps:
            mask = np.array([1.0 if cc == c else 0.0 for cc in asset_classes])
            cap = float(class_caps[c])
            cons.append({"type": "ineq", "fun": lambda w, m=mask, cap=cap: cap - m @ w})

    mw = np.broadcast_to(np.asarray(max_weight, dtype=float), (n,))
    bounds = [(0.0, float(mw[i])) for i in range(n)]
    w0 = np.full(n, 1.0 / n)

    res = minimize(
        neg_util, w0, jac=neg_util_grad, method="SLSQP",
        bounds=bounds, constraints=cons,
        options={"maxiter": 300, "ftol": 1e-10},
    )
    if res.success and np.isfinite(res.x).all():
        w = np.clip(res.x, 0.0, None)
        w = w / w.sum()
        return _clip_to_class_caps(w, asset_classes, class_caps)
    return risk_parity(cov, asset_classes=asset_classes, class_caps=class_caps)


def _cap_constraints(asset_classes: Sequence[str], class_caps: Dict[str, float]):
    cons = []
    for c in sorted(set(asset_classes)):
        if c in class_caps:
            mask = np.array([1.0 if cc == c else 0.0 for cc in asset_classes])
            cap = float(class_caps[c])
            cons.append({"type": "ineq", "fun": lambda w, m=mask, cap=cap: cap - m @ w})
    return cons


def optimize_max_sharpe(
    mu: np.ndarray,
    cov: np.ndarray,
    asset_classes: Sequence[str],
    class_caps: Optional[Dict[str, float]] = None,
    rf: float = 0.02,
    max_weight: float = 1.0,
    fast: bool = False,
) -> np.ndarray:
    """Max-Sharpe portfolio under class caps and no-leverage bounds.

    Directly maximizes (w'μ − rf)/(w'Σw)^{1/2} subject to sum(w)=1, 0≤w≤cap.
    This is non-convex, so we run SLSQP from several starts and keep the best.
    (The classical w'(μ−rf)=1 normalization trick is infeasible once box/no-
    leverage bounds are imposed, hence the direct formulation.)
    """
    mu = np.asarray(mu, dtype=float)
    cov = np.asarray(cov, dtype=float)
    n = len(mu)
    class_caps = class_caps or {}
    rf_m = rf / 12.0

    def neg_sharpe(w):
        ret = w @ mu - rf_m
        vol = np.sqrt(max(w @ cov @ w, 1e-16))
        return -(ret / vol)

    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]
    cons += _cap_constraints(asset_classes, class_caps)
    mw = np.broadcast_to(np.asarray(max_weight, dtype=float), (n,))
    bounds = [(0.0, float(mw[i])) for i in range(n)]

    starts = [np.full(n, 1.0 / n)]
    # start from a return-weighted guess
    pos = np.clip(mu - rf_m, 0, None)
    if pos.sum() > 0:
        starts.append(pos / pos.sum())
    if not fast:
        # start from min-variance (usually Sharpe-strong)
        starts.append(optimize_min_vol(cov, asset_classes, class_caps, max_weight))

    opts = {"maxiter": 150, "ftol": 1e-8} if fast else {"maxiter": 300, "ftol": 1e-9}
    best_w, best_val = None, np.inf
    for w0 in starts:
        res = minimize(neg_sharpe, w0, method="SLSQP", bounds=bounds,
                       constraints=cons, options=opts)
        if res.success and np.isfinite(res.x).all():
            val = neg_sharpe(res.x)
            if val < best_val:
                best_val, best_w = val, res.x
    if best_w is not None:
        w = np.clip(best_w, 0.0, None)
        w = w / w.sum()
        return _clip_to_class_caps(w, asset_classes, class_caps)
    return optimize_mean_variance(mu, cov, 3.0, asset_classes, class_caps, max_weight)


def optimize_min_vol(
    cov: np.ndarray,
    asset_classes: Sequence[str],
    class_caps: Optional[Dict[str, float]] = None,
    max_weight: float = 1.0,
) -> np.ndarray:
    """Global minimum-variance portfolio under class caps."""
    cov = np.asarray(cov, dtype=float)
    n = cov.shape[0]
    class_caps = class_caps or {}
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]
    cons += _cap_constraints(asset_classes, class_caps)
    mw = np.broadcast_to(np.asarray(max_weight, dtype=float), (n,))
    res = minimize(
        lambda w: w @ cov @ w, np.full(n, 1.0 / n), method="SLSQP",
        bounds=[(0.0, float(mw[i])) for i in range(n)], constraints=cons,
        options={"maxiter": 400, "ftol": 1e-11},
    )
    if res.success and np.isfinite(res.x).all():
        w = np.clip(res.x, 0.0, None)
        w = w / w.sum()
        return _clip_to_class_caps(w, asset_classes, class_caps)
    return risk_parity(cov, asset_classes=asset_classes, class_caps=class_caps)


def apply_satellite_floors(
    w: np.ndarray,
    asset_classes: Sequence[str],
    class_caps: Dict[str, float],
    floors: Dict[str, float],
    preference: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Core-satellite overlay: guarantee a minimum sleeve for designated
    classes (e.g. crypto for aggressive tiers) by trimming other holdings
    proportionally. Within the sleeve, mass is split by `preference`
    (e.g. expected returns) when given, else equally.
    Preserves sum(w)=1 and non-negativity."""
    w = np.clip(np.asarray(w, dtype=float), 0.0, None).copy()
    if w.sum() <= 0:
        return w
    w = w / w.sum()
    for cls, floor in (floors or {}).items():
        cap = class_caps.get(cls, 0.0)
        if cap <= 0:
            continue
        target = min(float(floor), cap)
        idx = [i for i, c in enumerate(asset_classes) if c == cls]
        if not idx:
            continue
        cur = float(sum(w[i] for i in idx))
        need = target - cur
        if need <= 1e-9:
            continue
        donors = [i for i in range(len(w)) if i not in idx and w[i] > 0]
        donor_total = float(sum(w[i] for i in donors))
        if donor_total <= 1e-9:
            continue
        if preference is not None:
            pref = np.clip(np.asarray(preference, dtype=float)[idx], 0.0, None)
            pref = pref / pref.sum() if pref.sum() > 0 else np.full(len(idx), 1.0 / len(idx))
        else:
            pref = np.full(len(idx), 1.0 / len(idx))
        for k, i in enumerate(idx):
            w[i] += need * float(pref[k])
        for i in donors:
            w[i] -= need * (w[i] / donor_total)
        w = np.clip(w, 0.0, None)
    return w / w.sum()


def risk_parity(
    cov: np.ndarray,
    budget: Optional[np.ndarray] = None,
    asset_classes: Optional[Sequence[str]] = None,
    class_caps: Optional[Dict[str, float]] = None,
    n_iter: int = 500,
) -> np.ndarray:
    """Classical risk budgeting via fixed-point iteration."""
    cov = np.asarray(cov, dtype=float)
    n = cov.shape[0]
    budget = np.asarray(budget, dtype=float) if budget is not None else np.full(n, 1.0 / n)
    w = np.full(n, 1.0 / n)
    for _ in range(n_iter):
        sigma_w = cov @ w
        mrc = np.maximum(sigma_w, 1e-12)
        w_new = budget / mrc
        w_new = w_new / w_new.sum()
        if np.max(np.abs(w_new - w)) < 1e-10:
            w = w_new
            break
        w = w_new
    if asset_classes is not None:
        w = _clip_to_class_caps(w, asset_classes, class_caps or {})
        w = w / w.sum()
    return w


def efficient_frontier(
    mu: np.ndarray,
    cov: np.ndarray,
    asset_classes: Sequence[str],
    class_caps: Optional[Dict[str, float]] = None,
    n_points: int = 25,
) -> List[Dict[str, object]]:
    """Scan the minimum-variance frontier under class caps.

    Returns list of dicts: {ret, vol, weights}.
    """
    from scipy.optimize import linprog

    mu = np.asarray(mu, dtype=float)
    cov = np.asarray(cov, dtype=float)
    n = len(mu)
    class_caps = class_caps or {}
    classes = sorted(set(asset_classes))

    A_ub = []
    b_ub = []
    for c in classes:
        if c in class_caps:
            row = np.array([1.0 if cc == c else 0.0 for cc in asset_classes])
            A_ub.append(row)
            b_ub.append(float(class_caps[c]))

    def _w0():
        return np.full(n, 1.0 / n)

    def min_var(t_lo: float, t_hi: float):
        cons = [
            {"type": "eq", "fun": lambda w: w.sum() - 1.0},
            {"type": "ineq", "fun": lambda w: w @ mu - t_lo},
            {"type": "ineq", "fun": lambda w: t_hi - w @ mu},
        ]
        for c in classes:
            if c in class_caps:
                mask = np.array([1.0 if cc == c else 0.0 for cc in asset_classes])
                cap = float(class_caps[c])
                cons.append({"type": "ineq", "fun": lambda w, m=mask, cap=cap: cap - m @ w})
        res = minimize(
            lambda w: w @ cov @ w, _w0(), method="SLSQP",
            bounds=[(0.0, 1.0)] * n, constraints=cons,
            options={"maxiter": 300, "ftol": 1e-11},
        )
        return res.x if res.success else None

    # feasible return range under caps via LP
    lp = linprog(-mu, A_ub=A_ub or None, b_ub=b_ub or None,
                 A_eq=np.ones((1, n)), b_eq=[1.0], bounds=[(0, 1)] * n, method="highs")
    if lp.x is None:
        return []
    r_max = float(lp.x @ mu)

    w_minvol = min_var(-1e9, 1e9)
    if w_minvol is None:
        return []
    r_lo = float(w_minvol @ mu)

    tol = max((r_max - r_lo) / max(n_points * 4, 1), 1e-6)
    points = []
    for t in np.linspace(r_lo, r_max, n_points):
        w = min_var(float(t) - tol, float(t) + tol)
        if w is None:
            continue
        w = np.clip(w, 0, None)
        if w.sum() <= 0:
            continue
        w = w / w.sum()
        ret = float(w @ mu)
        vol = float(np.sqrt(max(w @ cov @ w, 0.0)))
        points.append({"ret": ret * 12, "vol": vol * np.sqrt(12), "weights": w})
    return points
