"""Deterministic advisory pipeline (strategy-driven).

profile -> accessible universe -> shrinkage estimators -> STRATEGY MENU
(each strategy = asset filter + objective + cadence) -> select the strategy
whose realized risk/return shape best matches the profile -> backtest at the
strategy's own rebalance frequency -> projection.

The LLM layer wraps this pipeline; the pipeline itself is fully
unit-testable and reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .config import class_priors, get_config
from .data.base import DataProvider
from .data.universe import Asset, build_universe
from .personas import accessible_classes, segment_for_capital
from .portfolio.backtest import goal_projection
from .portfolio.metrics import performance_metrics
from .portfolio.optimizer import (
    apply_satellite_floors, class_exposures, cov_shrinkage, efficient_frontier,
)
from .portfolio.tactical import expected_returns_tactical
from .risk_profiler import RiskProfile
from .strategy import (
    STRATEGY_MENU, Strategy, build_strategy_weights, make_weight_builder,
    menu_for_tier,
)

# walk-forward menu results are deterministic per (data, caps) -> cache them
_MENU_CACHE: Dict[tuple, Dict[str, Dict[str, object]]] = {}


@dataclass
class Plan:
    profile: RiskProfile
    segment: str
    strategy: Strategy
    menu: List[Dict[str, object]]          # all viable strategies + metrics
    assets: List[Asset]
    weights: Dict[str, float]
    class_caps: Dict[str, float]
    mu_ann: Dict[str, float]
    vol_ann: Dict[str, float]
    expected: Dict[str, float]
    backtest: Dict[str, float]
    bench_backtest: Dict[str, float]
    equity_curve: pd.Series
    frontier: List[Dict[str, object]]
    projection: List[Dict[str, float]]
    monthly_contrib: float
    provider_name: str
    n_months: int
    timing: Optional[Dict[str, float]] = None      # applied subjective tilts
    notes: List[str] = field(default_factory=list)

    @property
    def weight_vector(self) -> np.ndarray:
        return np.array([self.weights.get(a.id, 0.0) for a in self.assets])


def default_monthly_contrib(capital: float, segment: str) -> float:
    base = {"mass": 1500.0, "mass_affluent": 5000.0, "hnw": 20000.0}[segment]
    return round(min(max(base, capital * 0.01), capital * 0.05), -2)


# ---------------------------------------------------------------------------
# Strategy auto-selection
# ---------------------------------------------------------------------------
def _selection_score(strategy: Strategy, metrics: Dict[str, float],
                     profile: RiskProfile, timing_view=None) -> float:
    """Sharpe-first, penalize vol above the tier envelope AND returns that
    fall short of the tier's target — so a 'high-return' profile never gets
    parked in a low-yield strategy just because it has the best Sharpe."""
    tier = profile.tier_info
    vol_hint = float(tier["max_vol_hint"])
    target_ret = float(tier["target_return"])
    vol_excess = max(0.0, metrics["ann_vol"] - vol_hint) / max(vol_hint, 1e-6)
    ret_shortfall = max(0.0, target_ret - metrics["ann_return"]) / max(target_ret, 1e-6)
    score = metrics["sharpe"] - 1.5 * vol_excess - 1.2 * ret_shortfall
    t = (profile.free_text or "").lower()
    # text boosts are tier-gated so they can't override suitability signals:
    # a C3 saying "稳健增值" must NOT be pushed into pure bonds.
    if profile.tier in ("C1", "C2") and \
            any(k in t for k in ("保本", "不能亏", "低风险", "保守", "稳")) and \
            "defensive" in strategy.tags:
        score += 0.4
    if profile.tier in ("C4", "C5") and \
            any(k in t for k in ("币", "加密", "btc", "比特币", "以太坊", "crypto")) and \
            "crypto" in strategy.tags:
        score += 0.6
    # subjective timing alignment: reward strategies whose sleeve composition
    # matches the investor's directional views (so "看空股票避险" rotates toward
    # defensive strategies instead of just reweighting inside an equity fund)
    if timing_view is not None and not timing_view.is_empty():
        align = 0.0
        for c, tilt in timing_view.tilts.items():
            align += tilt * strategy.asset_filter.get(c, 0.0)
        score += 1.2 * timing_view.conviction * align
    return float(score)


def select_strategy(profile: RiskProfile, menu_metrics: Dict[str, Dict[str, float]],
                    timing_view=None) -> Strategy:
    from .timing import STRONG, has_strong_view
    viable = [s for s in menu_for_tier(profile.tier) if s.id in menu_metrics]
    if not viable:
        viable = [s for s in STRATEGY_MENU if s.id in menu_metrics]
    # strong positive view: restrict to strategies that actually hold that class,
    # so e.g. a strong crypto view lands on a crypto-holding strategy.
    if has_strong_view(timing_view):
        liked = [c for c, t in timing_view.tilts.items() if t >= STRONG]
        if liked:
            holding = [s for s in viable
                       if any(s.asset_filter.get(c, 0.0) > 0 for c in liked)]
            if holding:
                viable = holding
    best = max(viable, key=lambda s: _selection_score(s, menu_metrics[s.id], profile,
                                                      timing_view))
    return best


# ---------------------------------------------------------------------------
# Plan builder
# ---------------------------------------------------------------------------
def _factor_blend_preference(returns, universe, mu) -> np.ndarray:
    """Blend expected returns with the factor-lens screening score for use as
    satellite-sleeve preference. Degrades to mu alone if the factor library
    is unavailable."""
    cfg_f = (get_config().get("factors", {}) or {})
    sw = float(cfg_f.get("screen_weight", 0.0))
    if sw <= 0:
        return mu
    try:
        from .factors import compute_factor_scores, default_catalog, enrich_universe
        cat = default_catalog()
        if not cat.factors:
            return mu
        try:
            enrichment = enrich_universe(universe)
        except Exception:  # noqa: BLE001
            enrichment = None
        scores = compute_factor_scores(returns, enrichment=enrichment)
        if scores.empty:
            return mu
    except Exception:  # noqa: BLE001 - factor layer is optional
        return mu

    fscore = np.array([float(scores["score"].get(a.id, 0.0)) for a in universe])
    # normalize both to z-scores, then blend
    def _z(x):
        x = np.asarray(x, dtype=float)
        sd = x.std(ddof=1)
        return (x - x.mean()) / sd if sd > 1e-12 else np.zeros_like(x)
    return (1.0 - sw) * _z(mu) + sw * _z(fscore)


def build_plan(
    profile: RiskProfile,
    provider: DataProvider,
    n_months: Optional[int] = None,
    monthly_contrib: Optional[float] = None,
    bench_id: str = "csi300_etf",
    strategy_id: Optional[str] = None,
    timing_view=None,
) -> Plan:
    cfg = get_config()
    n_months = n_months or int(cfg["backtest"]["years"]) * 12
    fee_overhead = float(cfg["backtest"]["start_cost"])

    # 1. accessible universe (suitability)
    caps = accessible_classes(profile)
    open_classes = [c for c, v in caps.items() if v > 0]
    universe = build_universe(include_classes=open_classes)
    if not universe:
        raise ValueError("no accessible assets for this profile")

    # 2. data + estimators over the full accessible universe
    ids = [a.id for a in universe]
    classes = [a.asset_class for a in universe]
    returns = provider.get_monthly_returns(ids, n_months)[ids]

    priors_ann = class_priors()
    prior_monthly = np.array([priors_ann[c]["ann_ret"] / 12.0 for c in classes])
    # base expectation (no tilt) for frontier/menu display
    mu = expected_returns_tactical(returns.values, prior_monthly, delta=0.6, kappa=0.0)
    cov, shrink_intensity = cov_shrinkage(returns.values)
    eff_caps = {c: caps[c] for c in open_classes if c in caps}
    avg_fee = float(np.mean([a.fee for a in universe])) + fee_overhead

    # 3. strategy menu: honest out-of-sample walk-forward, cached per (data, caps)
    from .strategy import evaluate_strategy
    cache_key = (getattr(provider, "name", ""), n_months,
                 tuple(sorted(eff_caps.items())))
    cached = _MENU_CACHE.get(cache_key, {})
    menu_metrics: Dict[str, Dict[str, float]] = {}
    menu_returns: Dict[str, pd.Series] = {}
    menu_rows: List[Dict[str, object]] = []
    for s in menu_for_tier(profile.tier):
        if s.id in cached:
            m, r = cached[s.id]["metrics"], cached[s.id]["returns"]
        else:
            try:
                m, r = evaluate_strategy(
                    s, returns, classes, mu, cov, eff_caps, fee=avg_fee,
                    assets=universe, walk_forward=True,
                    prior_monthly=prior_monthly)
            except ValueError:
                continue  # not viable under this profile
            cached[s.id] = {"metrics": m, "returns": r}
        menu_metrics[s.id] = m
        menu_returns[s.id] = r
        menu_rows.append({
            "id": s.id, "name_zh": s.name_zh, "name_en": s.name_en,
            "objective": s.objective, "cadence": s.cadence,
            "cadence_label": s.cadence_label, **{k: round(v, 4) for k, v in m.items()},
        })
    _MENU_CACHE[cache_key] = cached

    # 4. choose strategy (explicit override or auto-selection)
    if strategy_id:
        strategy = next((s for s in STRATEGY_MENU if s.id == strategy_id), None)
        if strategy is None:
            raise ValueError(f"unknown strategy '{strategy_id}'")
        if strategy.id not in menu_metrics:  # override not in tier menu -> eval now
            m, r = evaluate_strategy(strategy, returns, classes, mu, cov, eff_caps,
                                     fee=avg_fee, assets=universe, walk_forward=True,
                                     prior_monthly=prior_monthly)
            menu_metrics[strategy.id] = m
            menu_returns[strategy.id] = r
    else:
        if not menu_metrics:
            raise ValueError("no viable strategy for this profile")
        strategy = select_strategy(profile, menu_metrics, timing_view)

    # 5. today's allocation = the strategy's latest decision, with any
    #    subjective market-timing view injected (walk-forward history stays clean).
    builder = make_weight_builder(strategy, universe, classes, prior_monthly,
                                  eff_caps, timing_view=timing_view)
    w = builder(returns)
    if w is None:
        w = build_strategy_weights(strategy, mu, cov, classes, eff_caps,
                                   max_weight=0.65, assets=universe,
                                   timing_view=timing_view)

    # 5b. core-satellite overlay — only for classes the strategy admits.
    #     Sleeve preference blends expected return with the factor-lens score.
    floors = dict(profile.tier_info.get("satellite_floors") or {})
    floors = {c: f for c, f in floors.items() if strategy.allows(c)}
    if floors:
        pref = _factor_blend_preference(returns, universe, mu)
        w = apply_satellite_floors(w, classes, eff_caps, floors, preference=pref)

    # 6. ex-ante stats with a DAMPED momentum tilt + the subjective timing view
    #    (full momentum extrapolation would overstate forward expectations)
    kappa_display = min(strategy.momentum_kappa * 0.5, 0.25)
    mu = expected_returns_tactical(returns.values, prior_monthly, delta=0.6,
                                   kappa=kappa_display)
    if timing_view is not None and not timing_view.is_empty():
        from .timing import apply_timing_views
        vol_diag = np.sqrt(np.diag(cov))
        mu = apply_timing_views(mu, vol_diag, classes, timing_view)
    port_mu_m = float(w @ mu)
    port_vol_m = float(np.sqrt(max(w @ cov @ w, 0.0)))
    expected = {
        "ann_return": port_mu_m * 12,
        "ann_vol": port_vol_m * np.sqrt(12),
        "sharpe_hint": (port_mu_m * 12 - 0.02) / max(port_vol_m * np.sqrt(12), 1e-9),
        "cov_shrinkage": shrink_intensity,
        "objective": strategy.objective,
    }

    # 7. plan backtest = the selected strategy's walk-forward result (honest)
    port_ret_series = menu_returns.get(strategy.id)
    if port_ret_series is not None:
        bt_metrics = menu_metrics[strategy.id]
    else:
        bt_metrics = performance_metrics(np.zeros(1))
    bench_series = returns[bench_id] if bench_id in returns.columns else None
    bench_metrics = performance_metrics(bench_series.values) if bench_series is not None else {}

    # 8. frontier + projection
    frontier = efficient_frontier(mu, cov, classes, eff_caps, n_points=20)
    segment = segment_for_capital(profile.capital)
    contrib = monthly_contrib if monthly_contrib is not None else \
        default_monthly_contrib(profile.capital, segment)
    horizon = max(1, int(profile.horizon_years))
    proj = goal_projection(profile.capital, contrib, expected["ann_return"],
                           max(3, min(horizon, 30)))

    weights = {a.id: float(w[i]) for i, a in enumerate(universe) if w[i] > 1e-4}
    equity_curve = (1.0 + port_ret_series).cumprod() if port_ret_series is not None \
        else pd.Series(dtype=float)
    plan = Plan(
        profile=profile, segment=segment, strategy=strategy, menu=menu_rows,
        assets=universe, weights=weights, class_caps=eff_caps,
        mu_ann={a.id: float(mu[i]) * 12 for i, a in enumerate(universe)},
        vol_ann={a.id: float(np.sqrt(cov[i, i])) * np.sqrt(12) for i, a in enumerate(universe)},
        expected=expected,
        backtest=bt_metrics, bench_backtest=bench_metrics,
        equity_curve=equity_curve,
        frontier=frontier,
        projection=proj, monthly_contrib=contrib,
        provider_name=getattr(provider, "name", provider.__class__.__name__),
        n_months=n_months,
        timing=(dict(timing_view.tilts) if timing_view is not None
                and not timing_view.is_empty() else None),
    )

    # suitability gate: never violated, by construction — verify anyway.
    # Exception: a strong timing view may flight-to-cash beyond the strategic
    # cash sleeve; holding extra cash is always suitability-safe (de-risking),
    # so it is exempt from the cap check.
    from .timing import has_strong_view as _has_strong
    _timing_strong = _has_strong(timing_view)
    expo = class_exposures(w, classes)
    for c, cap in eff_caps.items():
        if c == "cash" and _timing_strong:
            continue
        if expo.get(c, 0.0) > cap + 1e-6:
            raise RuntimeError(f"suitability violated: {c} {expo[c]:.4f} > cap {cap}")
    plan.notes.append(
        f"provider={plan.provider_name}, strategy={strategy.id}, "
        f"cadence={strategy.cadence_label}, lambda/obj={strategy.objective}"
    )
    if plan.timing:
        plan.notes.append("subjective timing: " +
                          ", ".join(f"{c}{'+' if v>0 else ''}{v:.2f}" for c, v in plan.timing.items()))
    return plan
