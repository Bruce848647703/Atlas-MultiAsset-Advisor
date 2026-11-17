#!/usr/bin/env python3
"""Compare an Atlas target allocation with the current portfolio.

Examples
--------
python scripts/rebalance_check.py --target target.json --current current.json \
    --value 1000000 --threshold 0.05

python scripts/rebalance_check.py --target target.json \
    --positions positions.json --prices prices.json --cash 50000
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from typing import Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from invest_agent.portfolio.rebalance import (  # noqa: E402
    analyze_drift,
    weights_from_positions,
)


def _load_json(path: str) -> Dict[str, object]:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _load_weights(path: str) -> Dict[str, float]:
    data = _load_json(path)
    weights = data.get("weights", data)
    if not isinstance(weights, dict):
        raise ValueError(f"{path}: 'weights' must be an object")
    return {str(key): float(value) for key, value in weights.items()}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, help="target weights JSON or Atlas plan JSON")
    parser.add_argument("--current", help="current weights JSON")
    parser.add_argument("--positions", help="held quantities JSON (asset -> quantity)")
    parser.add_argument("--prices", help="prices JSON (asset -> price)")
    parser.add_argument("--cash", type=float, default=0.0, help="uninvested cash")
    parser.add_argument("--value", type=float, default=1.0, help="portfolio value for --current")
    parser.add_argument("--threshold", type=float, default=0.05, help="absolute drift threshold")
    parser.add_argument("--min-trade", type=float, default=0.005, help="suppress smaller trades")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        target = _load_weights(args.target)
        if args.current:
            current = _load_weights(args.current)
            total_value = args.value
        elif args.positions and args.prices:
            positions = {str(k): float(v) for k, v in _load_json(args.positions).items()}
            prices = {str(k): float(v) for k, v in _load_json(args.prices).items()}
            current, total_value = weights_from_positions(positions, prices, cash=args.cash)
        else:
            raise ValueError("provide --current, or both --positions and --prices")
        report = analyze_drift(
            target,
            current,
            total_value=total_value,
            threshold=args.threshold,
            min_trade_weight=args.min_trade,
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
        return 0 if not report.breached else 1

    print("Atlas rebalance monitor")
    print(f"portfolio value : {report.total_value:,.2f}")
    print(f"threshold       : {report.threshold:.2%}")
    print(f"max drift       : {report.max_drift:.2%}")
    print(f"turnover        : {report.turnover:.2%}")
    print(f"breached        : {'YES' if report.breached else 'no'}")
    print()
    print(f"{'asset':<20}{'target':>10}{'current':>10}{'drift':>10}{'trade':>12}{'amount':>16}")
    for line in report.trades:
        print(
            f"{line.asset_id:<20}{line.target_weight:>10.2%}"
            f"{line.current_weight:>10.2%}{line.drift:>+10.2%}"
            f"{line.trade_weight:>+12.2%}{line.trade_amount:>16,.2f}"
        )
    if not report.trades:
        print("(no trades above the minimum size)")
    return 0 if not report.breached else 1


if __name__ == "__main__":
    raise SystemExit(main())