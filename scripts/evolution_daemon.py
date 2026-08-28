#!/usr/bin/env python3
"""Autonomous factor-evolution daemon.

Runs learning cycles in the background on a fixed interval, so the agent keeps
learning even when nobody is using Atlas. Each cycle: import knowledge base +
collect broker-report factor themes + empirically learn factors (measure IC) +
run online collectors, all persisted to the factor store with state tracking.

Usage:
    python scripts/evolution_daemon.py                 # default 6h interval
    python scripts/evolution_daemon.py --interval-hours 12
    python scripts/evolution_daemon.py --once          # single cycle then exit

Run it detached so it survives logout:
    nohup python scripts/evolution_daemon.py > data/evolution_daemon.log 2>&1 &
Or install the provided systemd unit / cron entry (see training/README.md).
"""

import argparse
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from invest_agent.factors.factor_evolution import run_cycle  # noqa: E402


def _log(msg: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval-hours", type=float, default=6.0,
                    help="hours between learning cycles (default 6)")
    ap.add_argument("--months", type=int, default=96)
    ap.add_argument("--provider", default="merged")
    ap.add_argument("--once", action="store_true", help="run a single cycle and exit")
    args = ap.parse_args()

    _log(f"evolution daemon started (interval={args.interval_hours}h, "
         f"provider={args.provider}, months={args.months})")
    while True:
        try:
            rep = run_cycle(provider_name=args.provider, months=args.months)
            _log(f"cycle done: factors {rep['factors_before']}->{rep['factors_after']} "
                 f"(kb {rep['knowledge_base_imported']}, broker {rep['broker_report_factors']}, "
                 f"empirical {len(rep['learned_empirical'])}, online {rep['collected_online']})")
        except Exception as e:  # noqa: BLE001 - daemon must never die
            _log(f"cycle failed: {type(e).__name__}: {e}")
        if args.once:
            break
        time.sleep(max(args.interval_hours, 0.1) * 3600)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
