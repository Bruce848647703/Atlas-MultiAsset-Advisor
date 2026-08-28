#!/usr/bin/env python3
"""Rule-based evaluation suite for the advisory pipeline (local QA gate).

Checks compliance-critical invariants for a battery of investor cases:
  * weights form a proper allocation (sum=1, no shorts, single-name cap)
  * suitability caps per class are respected (hard gate)
  * segment gates hold (e.g. mass clients never get futures exposure)
  * realized/suggested vol stays near the tier's tolerance envelope
  * the report contains the disclaimer and risk-first product notes

Usage:
    python training/eval/eval_suite.py [--cases training/eval/cases.jsonl]
Exit code 0 iff all hard gates pass.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from invest_agent.agent import InvestAgent                      # noqa: E402
from invest_agent.personas import accessible_classes          # noqa: E402
from invest_agent.portfolio.optimizer import class_exposures  # noqa: E402

HARD = []


def check(case_name: str, ok: bool, detail: str, hard: bool = True):
    HARD.append((case_name, ok, detail, hard))
    mark = "PASS" if ok else ("FAIL" if hard else "WARN")
    print(f"  [{mark}] {detail}")


def eval_case(agent: InvestAgent, case: dict) -> None:
    name = case["name"]
    print(f"\n=== case: {name} ===")
    answers = {int(k): int(v) for k, v in case["answers"].items()}
    res = agent.offline_plan(answers, capital=case["capital"], free_text=case.get("free_text", ""))
    plan, profile = res["plan"], res["profile"]

    w = plan.weight_vector
    check(name, abs(w.sum() - 1) < 1e-6, f"weights sum = {w.sum():.6f}")
    check(name, bool((w >= -1e-9).all()), "no short positions")
    check(name, bool((w <= 0.65 + 1e-6).all()), f"single-name cap 65% respected (max {w.max():.2%})")

    classes = [a.asset_class for a in plan.assets]
    expo = class_exposures(w, classes)
    caps = accessible_classes(profile)
    ok_caps = all(expo.get(c, 0.0) <= cap + 1e-6 for c, cap in caps.items())
    check(name, ok_caps, f"class caps respected; caps={ {k: round(v,2) for k,v in caps.items()} }")

    for banned in case.get("expect_no_exposure", []):
        check(name, expo.get(banned, 0.0) <= 1e-9, f"no exposure to '{banned}' (got {expo.get(banned,0):.2%})")

    vol = plan.expected["ann_vol"]
    vmax = case.get("expect_max_vol_ann")
    if vmax is not None:
        check(name, vol <= vmax, f"ex-ante vol {vol:.1%} <= envelope {vmax:.0%}", hard=False)

    report = res["report"]
    check(name, "免责声明" in report, "report carries disclaimer")
    check(name, "风险" in report, "report mentions risk")

    from invest_agent.risk_profiler import tier_from_score
    check(name, tier_from_score(profile.score) == profile.tier,
          f"tier {profile.tier} consistent with score {profile.score:.0f}", hard=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="training/eval/cases.jsonl")
    ap.add_argument("--provider", default="synthetic")
    args = ap.parse_args()

    cases = []
    with open(args.cases, "r", encoding="utf-8") as f:
        raw = f.read().strip()
    if raw.startswith("["):  # a JSON array
        cases = json.loads(raw)
    else:                     # strict JSONL
        for line in raw.splitlines():
            line = line.strip()
            if line:
                cases.append(json.loads(line))

    agent = InvestAgent(provider_name=args.provider)
    for case in cases:
        eval_case(agent, case)

    fails = [(c, d) for c, ok, d, hard in HARD if not ok and hard]
    print(f"\nTOTAL checks: {len(HARD)}, hard failures: {len(fails)}")
    for c, d in fails:
        print(f"  FAIL [{c}] {d}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
