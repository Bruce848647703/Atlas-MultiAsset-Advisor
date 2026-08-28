#!/usr/bin/env python3
"""Requirement-understanding benchmark.

Scores the deterministic requirement parser (risk_profiler + timing + interest
+ horizon extraction) against curated ground-truth cases. This is the
benchmark a fine-tuned LLM must match or beat — run the same cases through the
model's structured output and compare.

Usage:
    python training/eval/eval_requirement.py [--cases training/eval/requirement_cases.jsonl]
Exit code 0 iff every case passes all hard checks.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from invest_agent.requirement import parse_requirement  # noqa: E402

RESULTS = []


def check(case_id, ok, detail):
    RESULTS.append((case_id, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {detail}")


def _sign(x):
    if x > 3:
        return 1
    if x < -3:
        return -1
    return 0


def eval_case(case):
    cid = case["id"]
    text = case["text"]
    exp = case.get("expect", {})
    print(f"\n=== {cid}: {text[:30]}... ===")
    req = parse_requirement(text)
    got = req.summary()

    # risk sign
    if "risk_sign" in exp:
        g = _sign(req.risk_adj)
        check(cid, g == exp["risk_sign"],
              f"risk_sign expect {exp['risk_sign']:+d} got {g:+d} (adj={req.risk_adj:.0f})")

    # timing tilts
    exp_t = exp.get("timing", {})
    if exp_t:
        for cls, want in exp_t.items():
            gotv = req.timing.tilts.get(cls, 0.0) if req.timing else 0.0
            got_sign = 1 if gotv > 0.15 else (-1 if gotv < -0.15 else 0)
            check(cid, got_sign == want,
                  f"timing[{cls}] expect {want:+d} got {got_sign:+d} ({gotv:+.2f})")
    else:
        strong = {c: v for c, v in (req.timing.tilts if req.timing else {}).items()
                  if abs(v) > 0.5}
        check(cid, not strong, f"no strong timing expected, got {strong}")

    # interests recall
    if "interests" in exp:
        got_int = set(req.interests)
        missing = [c for c in exp["interests"] if c not in got_int]
        check(cid, not missing, f"interests recall (missing={missing}, got={sorted(got_int)})")

    # horizon
    if "horizon" in exp:
        check(cid, req.horizon_hint == exp["horizon"],
              f"horizon expect {exp['horizon']} got {req.horizon_hint}")
    if "horizon_long" in exp:
        if exp["horizon_long"]:
            check(cid, req.horizon_hint is not None and req.horizon_hint >= 5,
                  f"long horizon expected, got {req.horizon_hint}")
        else:
            check(cid, req.horizon_hint is None or req.horizon_hint <= 2,
                  f"short/no-long horizon expected, got {req.horizon_hint}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="training/eval/requirement_cases.jsonl")
    args = ap.parse_args()

    cases = []
    with open(args.cases, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))

    for c in cases:
        eval_case(c)

    fails = [(c, d) for c, ok, d in RESULTS if not ok]
    total = len(RESULTS)
    print(f"\nTOTAL checks: {total}, passed: {total - len(fails)}, failed: {len(fails)}")
    for c, d in fails:
        print(f"  FAIL [{c}] {d}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
