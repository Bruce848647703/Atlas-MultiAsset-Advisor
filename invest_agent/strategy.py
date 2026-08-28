"""Strategy layer: named, philosophy-driven investment strategies.

Instead of dumping every accessible asset into one mean-variance blob, the
advisor chooses (or ranks) *strategies*. A strategy is a triple of:

  * selection  — which classes/assets are eligible (asset_filter), so each
                 strategy plays to its strength and ignores what it can't do well
  * objective  — how weights are set inside that universe
                 (max_sharpe / mean_variance / min_vol / risk_parity / equal)
  * cadence    — rebalance frequency class (high/mid/low) and its month count

Each strategy is backtested independently so the investor (and the agent) can
compare Sharpe / drawdown / turnover across a menu, and pick the one whose
risk-return shape matches the profile.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np

from .portfolio.metrics import performance_metrics
from .portfolio.optimizer import (
    optimize_max_sharpe, optimize_mean_variance, optimize_min_vol, risk_parity,
)
CADENCE = {"high": 1, "mid": 3, "low": 12}  # months between rebalances
CADENCE_LABEL = {"high": "高频(月度)", "mid": "中频(季度)", "low": "低频(年度)"}


@dataclass
class Strategy:
    id: str
    name_zh: str
    name_en: str
    philosophy: str                        # what strength it amplifies
    asset_filter: Dict[str, float]         # class -> max sleeve (0 = excluded)
    objective: str = "max_sharpe"
    cadence: str = "mid"
    risk_aversion: float = 4.0             # used by mean_variance objective
    momentum_kappa: float = 0.0            # return-tilt strength (strategy-specific)
    min_tier: str = "C1"
    max_tier: str = "C5"
    exclude_tags: List[str] = field(default_factory=list)   # asset-level screen
    tags: List[str] = field(default_factory=list)

    @property
    def rebalance_months(self) -> int:
        return CADENCE[self.cadence]

    @property
    def cadence_label(self) -> str:
        return CADENCE_LABEL[self.cadence]

    def allows(self, asset_class: str) -> bool:
        return self.asset_filter.get(asset_class, 0.0) > 0


_TIER_ORDER = {"C1": 1, "C2": 2, "C3": 3, "C4": 4, "C5": 5}


def tier_in_range(tier: str, lo: str, hi: str) -> bool:
    return _TIER_ORDER[lo] <= _TIER_ORDER[tier] <= _TIER_ORDER[hi]


# ---------------------------------------------------------------------------
# Strategy menu — each plays to a distinct strength.
# asset_filter values are class sleeves (relative to suitability caps).
# ---------------------------------------------------------------------------
STRATEGY_MENU: List[Strategy] = [
    Strategy(
        id="steady_carry",
        name_zh="稳健票息",
        name_en="Steady Carry",
        philosophy="放大固收的确定性现金流，几乎不承担权益波动；用货基+纯债+短久期构建，目标是低回撤的稳定增值。",
        asset_filter={"cash": 0.35, "fixed_income": 0.55, "hybrid": 0.10, "commodity": 0.0},
        objective="min_vol",
        cadence="low",
        min_tier="C1", max_tier="C3",
        exclude_tags=["high_beta", "sector", "speculative", "meme", "leveraged"],
        tags=["defensive", "income"],
    ),
    Strategy(
        id="balanced_core",
        name_zh="均衡核心",
        name_en="Balanced Core",
        philosophy="股债商均衡的核心仓位，用最大夏普在低相关资产间分散，牺牲少量收益换取显著更平滑的净值。",
        asset_filter={"fixed_income": 0.30, "hybrid": 0.15, "commodity": 0.15,
                      "equity_cn": 0.25, "equity_global": 0.25},
        objective="max_sharpe",
        cadence="mid",
        momentum_kappa=0.0,   # defensive-leaning: rely on trend gate, don't chase
        min_tier="C2", max_tier="C4",
        exclude_tags=["meme", "sector", "leveraged"],
        tags=["core", "diversified"],
    ),
    Strategy(
        id="global_equity_momentum",
        name_zh="全球权益动量",
        name_en="Global Equity Momentum",
        philosophy="放大权益资产的长期增长溢价，集中在高夏普的宽基与科技指数，用季度调仓捕捉动量、控制换手。",
        asset_filter={"equity_cn": 0.45, "equity_global": 0.50, "commodity": 0.10},
        objective="max_sharpe",
        cadence="mid",
        momentum_kappa=0.5,   # momentum IS the thesis for this strategy
        min_tier="C3", max_tier="C5",
        exclude_tags=["defensive", "meme", "sector", "leveraged"],
        tags=["growth", "momentum"],
    ),
    Strategy(
        id="all_weather_risk_parity",
        name_zh="全天候风险平价",
        name_en="All-Weather Risk Parity",
        philosophy="不预测方向，让每类资产对组合风险的贡献相等；放大分散化优势，在任何宏观环境下都不被单一资产绑架。",
        asset_filter={"fixed_income": 0.35, "commodity": 0.20, "equity_cn": 0.20,
                      "equity_global": 0.15, "cash": 0.10},
        objective="risk_parity",
        cadence="low",
        min_tier="C2", max_tier="C5",
        exclude_tags=["meme", "leveraged", "sector"],
        tags=["all_weather", "macro"],
    ),
    Strategy(
        id="aggressive_frontier",
        name_zh="进取前沿",
        name_en="Aggressive Frontier",
        philosophy="放大高成长资产(纳指/科创/加密)的弹性，用均值方差在高波动资产里找最优风险补偿；高频调仓及时止盈止损。",
        asset_filter={"equity_cn": 0.35, "equity_global": 0.45, "crypto": 0.20,
                      "commodity": 0.05},
        objective="mean_variance",
        risk_aversion=2.2,
        momentum_kappa=0.5,   # aggressive growth leans on momentum
        cadence="high",
        min_tier="C4", max_tier="C5",
        exclude_tags=["defensive", "meme", "leveraged"],
        tags=["aggressive", "high_beta", "crypto"],
    ),
    Strategy(
        id="crypto_barbell",
        name_zh="加密哑铃",
        name_en="Crypto Barbell",
        philosophy="哑铃结构：一端极安全(货基/短债)保流动性，一端高弹性(主流币)博非对称收益，规避中间地带；只适合明确能承受归零风险的资金。",
        asset_filter={"cash": 0.35, "fixed_income": 0.15, "crypto": 0.50},
        objective="mean_variance",
        risk_aversion=1.8,
        cadence="high",
        min_tier="C5", max_tier="C5",
        exclude_tags=["meme", "leveraged"],
        tags=["crypto", "barbell", "satellite"],
    ),
]


def menu_for_tier(tier: str) -> List[Strategy]:
    return [s for s in STRATEGY_MENU if tier_in_range(tier, s.min_tier, s.max_tier)]


def get_strategy(strategy_id: str) -> Optional[Strategy]:
    for s in STRATEGY_MENU:
        if s.id == strategy_id:
            return s
    return None


# ---------------------------------------------------------------------------
# Weight construction for a strategy inside its filtered universe.
# ---------------------------------------------------------------------------
def _reconcile_caps(sleeves: Dict[str, float], suitability: Dict[str, float]) -> Dict[str, float]:
    """Make (strategy sleeves ∩ suitability caps) feasible.

    If sum(min(sleeve, suit)) < 1 the allocation problem is infeasible.
    Water-fill the deficit into classes with remaining suitability headroom,
    prioritizing classes the strategy actually wants (sleeve > 0).
    Guarantees: eff <= suitability (never breach investor limits) and
    sum(eff) >= 1 (optimizer feasible) whenever suitability itself sums >= 1.
    """
    eff = {c: min(sleeves.get(c, 0.0), suitability.get(c, 0.0)) for c in suitability}
    for _ in range(60):
        deficit = 1.0 - sum(eff.values())
        if deficit <= 1e-9:
            break
        room = {c: suitability[c] - eff[c] for c in eff
                if eff[c] < suitability[c] - 1e-12 and sleeves.get(c, 0.0) > 0}
        if not room:  # fall back to any headroom if strategy classes are maxed
            room = {c: suitability[c] - eff[c] for c in eff
                    if eff[c] < suitability[c] - 1e-12}
        if not room:
            break
        wsum = sum(max(sleeves.get(c, 0.0), 0.05) for c in room)
        for c in room:
            add = deficit * max(sleeves.get(c, 0.0), 0.05) / wsum
            eff[c] = min(eff[c] + add, suitability[c])
    return eff


def build_strategy_weights(
    strategy: Strategy,
    mu: np.ndarray,
    cov: np.ndarray,
    asset_classes: Sequence[str],
    suitability_caps: Dict[str, float],
    max_weight: float = 0.65,
    assets=None,
    fast: bool = False,
    timing_view=None,
) -> np.ndarray:
    """Combine the strategy's sleeves with suitability caps, then optimize.

    Order matters for feasibility:
      1. determine *usable* classes = classes having ≥1 asset that passes the
         strategy's tag screen;
      2. reconcile sleeves against suitability restricted to usable classes
         (water-fills any shortfall so sum(caps) >= 1 without ever breaching
         suitability);
      2b. if a STRONG timing view is present, rewrite caps: exclude strongly
         disliked classes, concentrate strongly liked ones up to suitability,
         and open cash as the safe residual sink;
      3. optimize on the kept assets with those caps (zero caps kept explicit
         so excluded classes are hard-constrained to 0).
    """
    n = len(asset_classes)

    # 1. usable classes (have at least one asset passing the tag screen)
    usable = set()
    if assets is not None:
        for a in assets:
            tags = set(a.meta.get("tags", []) or [])
            if not (tags & set(strategy.exclude_tags)):
                usable.add(a.asset_class)
    else:
        usable = set(asset_classes)

    # 2. reconcile over usable classes only
    suit_masked = {c: (suitability_caps.get(c, 0.0) if c in usable else 0.0)
                   for c in suitability_caps}
    caps = _reconcile_caps(strategy.asset_filter, suit_masked)

    # 2b. strong timing views become hard constraints (exclude/concentrate/cash)
    from .timing import rewrite_caps_with_timing
    caps, timing_floors = rewrite_caps_with_timing(caps, suit_masked, timing_view)

    if max(caps.values()) <= 0:
        raise ValueError(f"strategy '{strategy.id}' has no viable asset class "
                         f"under this suitability profile")

    # 3. keep assets with positive cap that pass the tag screen
    keep = list(range(n))
    if assets is not None:
        keep = []
        for i, a in enumerate(assets):
            if caps.get(a.asset_class, 0.0) <= 0:
                continue
            tags = set(a.meta.get("tags", []) or [])
            if tags & set(strategy.exclude_tags):
                continue
            keep.append(i)
        if not keep:
            raise ValueError(f"strategy '{strategy.id}' screens out all assets")
        kept_sum = sum(caps[c] for c in {asset_classes[i] for i in keep})
        if kept_sum < 1.0 - 1e-9:
            raise ValueError(f"strategy '{strategy.id}' infeasible after asset "
                             f"screening (cap sum {kept_sum:.2f} < 1)")

    sub_classes = [asset_classes[i] for i in keep]
    sub_mu = mu[keep]
    sub_cov = cov[np.ix_(keep, keep)]
    mw = np.asarray(max_weight, dtype=float)
    mw_sub = float(mw) if mw.ndim == 0 else mw[keep]

    if strategy.objective == "max_sharpe":
        w_sub = optimize_max_sharpe(sub_mu, sub_cov, sub_classes, caps,
                                    max_weight=mw_sub, fast=fast)
    elif strategy.objective == "min_vol":
        w_sub = optimize_min_vol(sub_cov, sub_classes, caps, max_weight=mw_sub)
    elif strategy.objective == "risk_parity":
        w_sub = risk_parity(sub_cov, asset_classes=sub_classes, class_caps=caps)
    else:  # mean_variance
        w_sub = optimize_mean_variance(sub_mu, sub_cov, strategy.risk_aversion,
                                       sub_classes, caps, max_weight=mw_sub)

    # apply timing concentration floors (strong liking pushes the class up)
    if timing_floors:
        from .portfolio.optimizer import apply_satellite_floors
        w_sub = apply_satellite_floors(w_sub, sub_classes, caps, timing_floors,
                                       preference=sub_mu)

    w = np.zeros(n)
    w[keep] = w_sub
    return w / max(w.sum(), 1e-12)


def make_weight_builder(
    strategy: Strategy,
    assets,
    asset_classes: Sequence[str],
    prior_monthly: np.ndarray,
    suitability_caps: Dict[str, float],
    delta: float = 0.6,
    kappa: Optional[float] = None,
    max_weight: float = 0.65,
    timing_view=None,
):
    """Walk-forward weight builder: re-estimates shrinkage moments + momentum
    tilt from history-only data at each call. Returns None when the strategy
    is infeasible for the given window (caller keeps prior weights).

    `timing_view` (optional TimingView) injects a subjective market-timing
    tilt into expected returns. Pass it ONLY for the current decision — the
    historical walk-forward backtest must keep timing_view=None to stay honest.
    """
    from .portfolio.optimizer import cov_shrinkage
    from .portfolio.tactical import expected_returns_tactical, trend_gates
    from .timing import apply_timing_views

    k = strategy.momentum_kappa if kappa is None else kappa

    def build(hist) -> "np.ndarray | None":
        V = hist.values if hasattr(hist, "values") else np.asarray(hist)
        if len(V) < 30:
            return None
        mu_t = expected_returns_tactical(V, prior_monthly, delta=delta, kappa=k)
        cov_t, _ = cov_shrinkage(V)
        # subjective timing tilt (only when a view is supplied)
        if timing_view is not None and not timing_view.is_empty():
            vol_t = V.std(axis=0, ddof=1)
            mu_t = apply_timing_views(mu_t, vol_t, list(asset_classes), timing_view)
        # trend gate: shrink per-asset room while in downtrends (drawdown control);
        # defensive classes (cash/fixed income) are never gated.
        gates = trend_gates(V, lookback=12, floor=0.15)
        for i, c in enumerate(asset_classes):
            if c in ("cash", "fixed_income"):
                gates[i] = 1.0
        try:
            return build_strategy_weights(strategy, mu_t, cov_t, asset_classes,
                                          suitability_caps,
                                          max_weight=max_weight * gates,
                                          assets=assets, fast=True,
                                          timing_view=timing_view)
        except ValueError:
            return None

    return build


def evaluate_strategy(
    strategy: Strategy,
    monthly_returns,
    asset_classes: Sequence[str],
    mu: np.ndarray,
    cov: np.ndarray,
    suitability_caps: Dict[str, float],
    fee: float = 0.0008,
    assets=None,
    walk_forward: bool = True,
    prior_monthly: np.ndarray = None,
    kappa: Optional[float] = None,
):
    """Backtest a strategy at its own cadence.

    walk_forward=True (default): honest out-of-sample walk with momentum
    tilt, re-optimized each rebalance from history-only data.
    walk_forward=False: legacy static full-sample mix (lookahead; kept only
    for speed comparisons).

    Returns (metrics_dict, portfolio_returns_series).
    """
    from .portfolio.backtest import run_backtest, run_walkforward_backtest

    if walk_forward and assets is not None:
        builder = make_weight_builder(strategy, assets, asset_classes,
                                      prior_monthly, suitability_caps, kappa=kappa)
        bt = run_walkforward_backtest(monthly_returns, builder,
                                      rebalance_every=strategy.rebalance_months,
                                      fee=fee, warmup=36)
    else:
        w = build_strategy_weights(strategy, mu, cov, asset_classes, suitability_caps,
                                   assets=assets)
        bt = run_backtest(monthly_returns, w, fee=fee,
                          rebalance_every=strategy.rebalance_months)
    m = performance_metrics(bt.portfolio_returns.values)
    metrics = dict(m)
    metrics["turnover_annual"] = float(bt.turnover_series.sum()) / max(len(monthly_returns) / 12.0, 1e-9)
    return metrics, bt.portfolio_returns
