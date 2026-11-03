#!/usr/bin/env python3
"""Run the Kairos 106-strategy lab on the committed real ETF panel.

Examples:
    python scripts/kairos_strategy_lab.py
    python scripts/kairos_strategy_lab.py --top 30 --force
    python scripts/kairos_strategy_lab.py --strategy low_beta_timing
    python scripts/kairos_strategy_lab.py --channel trend --channel allocation
    python scripts/kairos_strategy_lab.py --json > /tmp/lab.json

The result is cached under ``data_cache/kairos_strategy_lab.json`` so the
dashboard can load it instantly. Requires sibling ``kairos-strategies`` and
``kairos-data`` checkouts (or KAIROS_ROOT).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from invest_agent.integrations import kairos_strategies as lab  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--force", action="store_true", help="recompute even if cached")
    parser.add_argument("--strategy", help="show one strategy's metrics/equity")
    parser.add_argument("--channel", action="append", default=[],
                        help="restrict to a channel (repeatable)")
    parser.add_argument("--json", action="store_true", help="emit raw JSON")
    args = parser.parse_args()

    if not lab.available():
        print("Kairos strategy lab unavailable: need kairos-strategies + kairos-data "
              "(set KAIROS_ROOT or place them next to Atlas).", file=sys.stderr)
        return 2

    if args.strategy:
        detail = lab.run_strategy(args.strategy)
        if not detail.get("available"):
            print(detail.get("reason", "strategy unavailable"), file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(detail, ensure_ascii=False, indent=1))
        else:
            print(f"{detail['name']} [{detail['channel']}]")
            print(f"  {detail.get('description', '')}")
            for key in ("cagr", "volatility", "sharpe", "max_drawdown", "calmar",
                        "avg_turnover", "total_return"):
                if key in detail["metrics"]:
                    print(f"  {key:14s} {detail['metrics'][key]}")
            print(f"  equity points  {len(detail['equity'])}")
        return 0

    pack = lab.run_lab(force=args.force, channels=args.channel or None)
    if args.json:
        print(json.dumps(pack, ensure_ascii=False, indent=1))
        return 0

    u = pack.get("universe", {})
    print(f"Kairos Strategy Lab · {pack['n_strategies']} long-only strategies · "
          f"{u.get('n_assets')} ETFs · {u.get('start')} → {u.get('end')} "
          f"({pack.get('elapsed_sec', 0)}s)")
    print(f"{'rank':>4}  {'strategy':28s} {'channel':16s} {'sharpe':>7} "
          f"{'cagr':>7} {'mdd':>7} {'turn':>6}")
    for i, row in enumerate(pack["strategies"][:args.top], 1):
        print(f"{i:4d}  {row['name']:28s} {row['channel']:16s} "
              f"{row['sharpe']:7.2f} {row['cagr']:7.1%} "
              f"{row['max_drawdown']:7.1%} {row['avg_turnover']:6.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())