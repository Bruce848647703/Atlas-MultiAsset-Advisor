#!/usr/bin/env python3
"""End-to-end offline demo: three investor strata, one deterministic pipeline.

Shows how the same quant core adapts to mass / mass-affluent / HNW clients
with different suitability tiers. Outputs land in examples/demo_outputs/.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from invest_agent.agent import InvestAgent            # noqa: E402
from invest_agent.report import save_report          # noqa: E402

PROFILES = {
    "01_mass_C2": dict(
        desc="大众客群 · 稳健型 · 刚工作三年，攒下第一笔闲钱",
        answers={0: 3, 1: 0, 2: 2, 3: 1, 4: 1, 5: 1, 6: 1, 7: 0, 8: 1},
        capital=80_000,
        free_text="这笔钱是攒下来的工资，求稳，别让我亏本金，以后每个月还能定投一点。",
    ),
    "02_mass_affluent_C3": dict(
        desc="富裕客群 · 平衡型 · 家庭支柱，有房贷，想要跑赢通胀",
        answers={0: 2, 1: 2, 2: 3, 3: 2, 4: 2, 5: 2, 6: 2, 7: 1, 8: 2},
        capital=500_000,
        free_text="能接受短期波动，看好纳斯达克，但不想亏掉本金，黄金能不能配一点？",
    ),
    "03_hnw_C5": dict(
        desc="高净值客群 · 激进型 · 企业主，追求高收益并愿承担波动",
        answers={0: 3, 1: 3, 2: 3, 3: 3, 4: 3, 5: 3, 6: 3, 7: 3, 8: 3},
        capital=5_000_000,
        free_text="追求高收益，币圈和期货都可以研究，长期持有，跌了敢加仓。",
    ),
}


def main() -> int:
    for name, spec in PROFILES.items():
        out_dir = os.path.join("examples", "demo_outputs", name)
        agent = InvestAgent(output_dir=out_dir)
        res = agent.offline_plan(
            answers=spec["answers"], capital=spec["capital"], free_text=spec["free_text"]
        )
        plan = res["plan"]
        save_report(res["report"], os.path.join(out_dir, "report.md"))
        top = ", ".join(f"{k}={v:.1%}" for k, v in sorted(plan.weights.items(), key=lambda kv: -kv[1])[:4])
        print(f"[{name}] {spec['desc']}")
        print(f"   tier={res['profile'].tier} score={res['profile'].score:.0f} "
              f"E[ret]={plan.expected['ann_return']:.1%} vol={plan.expected['ann_vol']:.1%} "
              f"Sharpe={plan.expected['sharpe_hint']:.2f}")
        print(f"   配置: {top}")
        print(f"   产出: {out_dir}/report.md + {len(res['charts'])} charts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
