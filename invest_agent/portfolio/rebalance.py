"""Rebalance and drift monitoring for an existing portfolio.

The advisor's plan is a target vector.  Real portfolios drift as prices move;
this module turns target vs current weights into a deterministic trade list
without assuming an order-management system or live prices.

Cash is the residual weight (``1 - sum(risky weights)``).  A negative cash
weight means the current holdings add up to more than the stated portfolio
value, which is rejected rather than silently normalized.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Mapping, Tuple

EPS = 1e-9


@dataclass(frozen=True)
class DriftLine:
    """One asset's target/current gap and the trade that closes it."""

    asset_id: str
    target_weight: float
    current_weight: float
    drift: float
    trade_weight: float
    trade_amount: float


@dataclass(frozen=True)
class RebalanceReport:
    """Deterministic rebalance diagnosis for one portfolio snapshot."""

    total_value: float
    threshold: float
    max_drift: float
    breached: bool
    turnover: float
    target_cash_weight: float
    current_cash_weight: float
    trades: Tuple[DriftLine, ...] = field(default_factory=tuple)
    notes: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def trade_count(self) -> int:
        return len(self.trades)


def weights_from_positions(
    positions: Mapping[str, float],
    prices: Mapping[str, float],
    cash: float = 0.0,
) -> Tuple[Dict[str, float], float]:
    """Convert held quantities and prices into weights and total value.

    Positions and prices must be finite and non-negative.  Unknown prices and
    zero-value portfolios are rejected: a drift report on a stale price is
    worse than no report.
    """
    if not isinstance(positions, Mapping):
        raise ValueError("positions must be a mapping")
    if not isinstance(prices, Mapping):
        raise ValueError("prices must be a mapping")
    if not isinstance(cash, (int, float)) or not float(cash) == float(cash):
        raise ValueError("cash must be finite")
    if float(cash) < 0:
        raise ValueError("cash must be non-negative")

    values: Dict[str, float] = {}
    for asset_id, quantity in positions.items():
        if not isinstance(asset_id, str) or not asset_id:
            raise ValueError("position asset ids must be non-empty strings")
        q = float(quantity)
        if not (q == q) or q < 0:
            raise ValueError(f"position for {asset_id} must be finite and non-negative")
        if q == 0:
            continue
        if asset_id not in prices:
            raise ValueError(f"missing price for held asset {asset_id}")
        price = float(prices[asset_id])
        if not (price == price) or price <= 0:
            raise ValueError(f"price for {asset_id} must be finite and positive")
        values[asset_id] = q * price

    total_value = sum(values.values()) + float(cash)
    if total_value <= EPS:
        raise ValueError("portfolio value must be positive")
    weights = {asset_id: value / total_value for asset_id, value in values.items()}
    return weights, total_value


def _validate_weights(weights: Mapping[str, float], label: str) -> Dict[str, float]:
    if not isinstance(weights, Mapping):
        raise ValueError(f"{label} must be a mapping")
    clean: Dict[str, float] = {}
    for asset_id, weight in weights.items():
        if not isinstance(asset_id, str) or not asset_id:
            raise ValueError(f"{label} asset ids must be non-empty strings")
        w = float(weight)
        if not (w == w) or w < 0:
            raise ValueError(f"{label} weight for {asset_id} must be finite and non-negative")
        if w > 0:
            clean[asset_id] = w
    total = sum(clean.values())
    if total > 1.0 + 1e-6:
        raise ValueError(f"{label} weights sum to {total:.6f}, above 1.0")
    return clean


def analyze_drift(
    target_weights: Mapping[str, float],
    current_weights: Mapping[str, float],
    *,
    total_value: float = 1.0,
    threshold: float = 0.05,
    min_trade_weight: float = 0.005,
) -> RebalanceReport:
    """Compare target and current weights and produce the rebalance trades.

    ``threshold`` is the absolute weight drift that marks the portfolio as
    breached.  ``min_trade_weight`` suppresses tiny orders; those assets still
    count toward ``max_drift`` and ``breached``.  A trade list line is emitted
    for every asset whose absolute trade weight is at least
    ``min_trade_weight``, including cash when it is a meaningful gap.
    """
    if not (total_value == total_value) or total_value <= 0:
        raise ValueError("total_value must be finite and positive")
    if not (0.0 <= threshold <= 1.0):
        raise ValueError("threshold must be between 0 and 1")
    if not (0.0 <= min_trade_weight <= 1.0):
        raise ValueError("min_trade_weight must be between 0 and 1")

    target = _validate_weights(target_weights, "target")
    current = _validate_weights(current_weights, "current")
    target_cash = max(0.0, 1.0 - sum(target.values()))
    current_cash = max(0.0, 1.0 - sum(current.values()))

    asset_ids = sorted(set(target) | set(current))
    lines: list[DriftLine] = []
    max_drift = 0.0
    for asset_id in asset_ids:
        target_weight = target.get(asset_id, 0.0)
        current_weight = current.get(asset_id, 0.0)
        drift = current_weight - target_weight
        max_drift = max(max_drift, abs(drift))
        trade_weight = target_weight - current_weight
        if abs(trade_weight) + EPS >= min_trade_weight:
            lines.append(
                DriftLine(
                    asset_id=asset_id,
                    target_weight=target_weight,
                    current_weight=current_weight,
                    drift=drift,
                    trade_weight=trade_weight,
                    trade_amount=trade_weight * total_value,
                )
            )
    cash_trade = target_cash - current_cash
    if abs(cash_trade) + EPS >= min_trade_weight:
        lines.append(
            DriftLine(
                asset_id="cash",
                target_weight=target_cash,
                current_weight=current_cash,
                drift=current_cash - target_cash,
                trade_weight=cash_trade,
                trade_amount=cash_trade * total_value,
            )
        )
    lines.sort(key=lambda line: abs(line.drift), reverse=True)
    turnover = 0.5 * sum(abs(line.trade_weight) for line in lines)
    return RebalanceReport(
        total_value=float(total_value),
        threshold=float(threshold),
        max_drift=float(max_drift),
        breached=max_drift > threshold + EPS,
        turnover=float(turnover),
        target_cash_weight=float(target_cash),
        current_cash_weight=float(current_cash),
        trades=tuple(lines),
        notes=(
            "Trades are target-minus-current weights; positive means buy.",
            "Cash is the residual 1 - sum(asset weights).",
        ),
    )