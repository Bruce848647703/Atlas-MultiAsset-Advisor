#!/usr/bin/env python3
"""Generate SFT training conversations for a local DeepSeek-distill model.

The deterministic pipeline is used as the *oracle advisor*: we simulate
multi-turn dialogues (investor asks -> agent questions -> investor answers
-> agent gives a compliant allocation) and emit them in OpenAI chat JSONL,
ready for LLaMA-Factory / swift fine-tuning of e.g.DeepSeek-R1-Distill-Qwen-7B.

Usage:
    python training/generate_sft_data.py --n 400 --out training/sft_data/train.jsonl
"""

import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from invest_agent.agent import InvestAgent                      # noqa: E402
from invest_agent.llm import SYSTEM_PROMPT                      # noqa: E402
from invest_agent.personas import accessible_classes, segment_for_capital  # noqa: E402
from invest_agent.risk_profiler import QUESTIONS, tier_from_score  # noqa: E402

DISCLAIMER = ("免责声明: 以上内容由量化模型生成，仅供研究参考，不构成投资建议；"
              "市场有风险，投资需谨慎。")

TEXT_POOL_CONSERVATIVE = [
    "这笔钱是应急的，绝对不能亏。", "我想稳健一点，跑赢余额宝就行。",
    "亏不起，养老金的一部分。", "保守为主，能保本最重要。",
]
TEXT_POOL_BALANCED = [
    "能接受短期波动，但不想亏掉本金。", "想跑赢通胀，可以配点股票和黄金。",
    "定投三年不动用，稳中求进。",
]
TEXT_POOL_AGGRESSIVE = [
    "追求高收益，能接受大幅波动，跌了敢加仓。", "看好纳斯达克和币圈，all in 的魄力有的。",
    "闲钱投资，杠杆和合约也可以研究。", "长期持有成长股，翻倍目标。",
]
OPENER_POOL = [
    "我有{cap}想投资，你帮我看看怎么配。",
    "手里有{cap}闲钱，想做多元配置。",
    "{cap}的资金，帮我出个投资方案吧。",
]


def _sample_answers(rng: random.Random, target_tier: str) -> dict:
    """Sample questionnaire answers biased toward the target tier."""
    tier_order = {"C1": 0.15, "C2": 0.35, "C3": 0.55, "C4": 0.75, "C5": 0.92}
    p = tier_order[target_tier]
    answers = {}
    for i, (_w, _q, _e, opts) in enumerate(QUESTIONS):
        r = rng.random()
        if r < p:
            oi = rng.choice([2, 3])
        elif r < p + (1 - p) / 2:
            oi = rng.choice([1, 2])
        else:
            oi = rng.choice([0, 1])
        answers[i] = min(oi, len(opts) - 1)
    return answers


def _capital_for(rng: random.Random, segment: str) -> float:
    if segment == "mass":
        return rng.uniform(30_000, 180_000)
    if segment == "mass_affluent":
        return rng.uniform(250_000, 950_000)
    return rng.uniform(1_200_000, 8_000_000)


def _fmt_cap(x: float) -> str:
    if x >= 10_000:
        return f"{x/10_000:.0f}万"
    return f"{x:.0f}元"


def _factor_note(plan) -> str:
    """Short factor-based justification for the chosen assets (teaches the
    fine-tuned model to cite factor logic). Degrades to '' if unavailable."""
    try:
        from invest_agent.data.base import get_provider
        from invest_agent.factors import compute_factor_scores, enrich_universe
        prov = get_provider(plan.provider_name)
        ids = [a.id for a in plan.assets if a.id in plan.weights]
        if not ids:
            return ""
        R = prov.get_monthly_returns([a.id for a in plan.assets], 60)
        try:
            enr = enrich_universe(plan.assets)
        except Exception:  # noqa: BLE001
            enr = None
        scores = compute_factor_scores(R[[i for i in ids if i in R.columns]],
                                       enrichment=enr)
        if scores.empty:
            return ""
        name_of = {a.id: a.name_zh for a in plan.assets}
        top = scores.head(2)
        bits = []
        for aid, row in top.iterrows():
            why = []
            if row["momentum"] > 0:
                why.append("动量向上")
            if row["low_vol"] < 0.15:
                why.append("波动较低")
            if row["drawdown"] < 0.15:
                why.append("回撤可控")
            if row.get("money_flow", float("nan")) > 0:
                why.append("主力资金净流入")
            bits.append(f"{name_of.get(aid, aid)}({'、'.join(why) or '因子分靠前'})")
        return "标的筛选(因子透镜): 依据动量/低波动/抗回撤/资金流因子，优选 " + "、".join(bits) + "。\n"
    except Exception:  # noqa: BLE001 - optional enrichment
        return ""


def build_one(rng: random.Random, agent: InvestAgent, segment: str, tier: str):
    capital = round(_capital_for(rng, segment), -3)
    answers = _sample_answers(rng, tier)
    text_pool = {"C1": TEXT_POOL_CONSERVATIVE, "C2": TEXT_POOL_CONSERVATIVE + TEXT_POOL_BALANCED,
                 "C3": TEXT_POOL_BALANCED, "C4": TEXT_POOL_BALANCED + TEXT_POOL_AGGRESSIVE,
                 "C5": TEXT_POOL_AGGRESSIVE}[tier]
    free_text = rng.choice(text_pool)

    res = agent.offline_plan(answers, capital, free_text=free_text)
    profile, plan = res["profile"], res["plan"]
    caps = accessible_classes(profile)

    lines_alloc = []
    name_of = {a.id: a.name_zh for a in plan.assets}
    for a_id, wgt in sorted(plan.weights.items(), key=lambda kv: -kv[1]):
        lines_alloc.append(f"- {name_of[a_id]}: {wgt:.1%}")

    final = (
        f"根据您的回答，我将您评估为 {profile.tier} {profile.tier_info['label_zh']}"
        f"(评分 {profile.score:.0f}/100)，所属客群: {plan.segment}。\n"
        f"建议配置如下:\n" + "\n".join(lines_alloc) + "\n"
        f"事前预期: 年化约 {plan.expected['ann_return']:.1%}，波动 {plan.expected['ann_vol']:.1%}，"
        f"夏普≈{plan.expected['sharpe_hint']:.2f}。\n"
        f"历史回测({plan.n_months}个月): 年化 {plan.backtest['ann_return']:.1%}，"
        f"最大回撤 {plan.backtest['max_drawdown']:.1%}。\n"
        f"建议每月定投 ¥{plan.monthly_contrib:,.0f}，按预期收益估算，"
        f"{plan.projection[-1]['year']:.0f}年后组合价值约 ¥{plan.projection[-1]['value']:,.0f}。\n"
        f"{_factor_note(plan)}"
        f"请先配置3-6个月应急金再开始投资；单一资产不超过65%。\n{DISCLAIMER}"
    )

    q1 = "请问这笔资金的投资期限大概多久？您的主要目标是保值、稳健收益、增值还是追求高收益？"
    q2 = "若投入10万元一个月亏损1.5万元，您会立即卖出、减仓、持有还是加仓？"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": random.choice(OPENER_POOL).format(cap=_fmt_cap(capital))},
        {"role": "assistant", "content": f"收到。为了给出合适的方案，我先了解两个问题。\n1) {q1}\n2) {q2}"},
        {"role": "user", "content": f"期限约{profile.horizon_years}年；{free_text}"},
        {"role": "assistant", "content": final},
    ]
    return {
        "messages": messages,
        "meta": {"tier": profile.tier, "segment": plan.segment, "capital": capital,
                 "score": profile.score, "expected_tier_hint": tier},
    }


# ---------------------------------------------------------------------------
# Subjective market-timing conversations
# ---------------------------------------------------------------------------
TIMING_SCENARIOS = [
    ("我短期看空A股，觉得要回调，想先减点股票仓位避险", "看空A股、降低权益"),
    ("市场可能要见顶了，我想把股票换成债券和黄金稳一稳", "防御轮动(股→债/金)"),
    ("我看好纳斯达克和比特币，想趁势加仓", "看多海外与加密"),
    ("加密最近涨太多了，我怕回调，想先减一点币圈", "降低加密敞口"),
    ("美联储降息利好债和黄金，我想多配这两块", "增配债券与黄金"),
]

TIMING_DICT = {
    "我短期看空A股，觉得要回调，想先减点股票仓位避险": {"equity_cn": -0.6},
    "市场可能要见顶了，我想把股票换成债券和黄金稳一稳": {"equity_cn": -0.8, "equity_global": -0.6},
    "我看好纳斯达克和比特币，想趁势加仓": {"equity_global": 0.7, "crypto": 0.7},
    "加密最近涨太多了，我怕回调，想先减一点币圈": {"crypto": -0.7},
    "美联储降息利好债和黄金，我想多配这两块": {"fixed_income": 0.6, "commodity": 0.6},
}


def _class_expo(plan):
    expo = {}
    for a_id, w in plan.weights.items():
        cls = next(a.asset_class for a in plan.assets if a.id == a_id)
        expo[cls] = expo.get(cls, 0.0) + w
    return expo


def build_timing_one(rng: random.Random, agent: InvestAgent, segment: str, tier: str):
    capital = round(_capital_for(rng, segment), -3)
    answers = _sample_answers(rng, tier)
    view_text, view_label = rng.choice(TIMING_SCENARIOS)
    timing_dict = TIMING_DICT[view_text]

    res_base = agent.offline_plan(answers, capital)
    res_timed = agent.offline_plan(answers, capital, timing=timing_dict)
    profile, plan = res_timed["profile"], res_timed["plan"]
    base_expo = _class_expo(res_base["plan"])
    timed_expo = _class_expo(plan)

    shifts = []
    for cls in sorted(set(base_expo) | set(timed_expo)):
        d = timed_expo.get(cls, 0.0) - base_expo.get(cls, 0.0)
        if abs(d) > 0.02:
            shifts.append(f"{cls} {'+' if d>0 else ''}{d:.0%}")
    shift_txt = "；".join(shifts) if shifts else "整体结构基本不变(受适当性上限约束)"

    name_of = {a.id: a.name_zh for a in plan.assets}
    alloc = "\n".join(f"- {name_of[k]}: {v:.1%}"
                      for k, v in sorted(plan.weights.items(), key=lambda kv: -kv[1]))
    tilts_txt = "、".join(f"{c}{'+' if v>0 else ''}{v:.1f}" for c, v in timing_dict.items())

    final = (
        f"我理解您的观点：{view_label}。已将该主观择时记录为 [{tilts_txt}]，"
        f"并注入预期收益(仅影响当前配置，不改变历史回测)。\n"
        f"您的适当性等级为 {profile.tier} {profile.tier_info['label_zh']}。\n"
        f"考虑择时后的配置:\n{alloc}\n"
        f"相比中性配置的调整: {shift_txt}。\n"
        f"事前预期: 年化约 {plan.expected['ann_return']:.1%}，波动 {plan.expected['ann_vol']:.1%}。\n"
        f"提示: 主观择时反映短期观点，建议与长期适当性配置结合，勿因短期判断过度集中。{DISCLAIMER}"
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"我有{_fmt_cap(capital)}，另外想说说我对市场的看法：{view_text}"},
        {"role": "assistant", "content": final},
    ]
    return {
        "messages": messages,
        "meta": {"tier": profile.tier, "segment": plan.segment, "capital": capital,
                 "type": "timing", "view": view_label, "tilts": timing_dict},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=400)
    ap.add_argument("--out", default="training/sft_data/train.jsonl")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--timing_ratio", type=float, default=0.3,
                    help="fraction of conversations that are timing scenarios")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    agent = InvestAgent()
    tiers = ["C1", "C2", "C3", "C4", "C5"]
    segments = ["mass", "mass_affluent", "hnw"]

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    written = n_timing = 0
    with open(args.out, "w", encoding="utf-8") as f:
        for i in range(args.n):
            tier = tiers[i % len(tiers)]
            segment = segments[i % len(segments)]
            use_timing = rng.random() < args.timing_ratio
            try:
                if use_timing:
                    row = build_timing_one(rng, agent, segment, tier)
                    n_timing += 1
                else:
                    row = build_one(rng, agent, segment, tier)
            except Exception as e:  # noqa: BLE001
                print(f"# skip sample {i}: {e}", file=sys.stderr)
                continue
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            written += 1
    print(f"wrote {written} conversations ({n_timing} timing) -> {args.out}")


if __name__ == "__main__":
    main()
