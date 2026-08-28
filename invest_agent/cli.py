"""Interactive terminal session.

With DEEPSEEK_API_KEY set: conversational mode (the agent asks the
investor questions itself through the ask_investor tool).
Without it: guided questionnaire + deterministic pipeline.
"""

from __future__ import annotations

import sys

from .agent import InvestAgent
from .llm import LLMUnavailable
from .risk_profiler import QUESTIONS


def _input_float(prompt: str, default: float) -> float:
    raw = input(prompt).strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        print("  (无法解析, 使用默认值)")
        return default


def questionnaire_flow() -> dict:
    print("\n=== 适当性问卷 (Suitability Questionnaire) ===")
    answers = {}
    for i, (_w, q_zh, _q_en, opts) in enumerate(QUESTIONS):
        print(f"\n[{i}] {q_zh}")
        for j, (zh, _en, _s) in enumerate(opts):
            print(f"    {j}. {zh}")
        while True:
            raw = input("选择 0-3 (回车=2): ").strip()
            if raw == "":
                answers[i] = 2
                break
            if raw in {"0", "1", "2", "3"}:
                answers[i] = int(raw)
                break
    return answers


def chat_mode(agent: InvestAgent) -> None:
    print("\n[Atlas] 你好！我是 Atlas 多元资产投资顾问。请先告诉我: 您的可投资本金大约是多少?")
    history = None
    msg = input("> ").strip() or "先介绍你的能力"
    while True:
        res = agent.chat(msg, history)
        history = res.history
        if res.needs_user_input:
            print(f"\n[Atlas 提问] {res.pending_question}")
            msg = input("> ").strip()
            continue
        print(f"\n[Atlas] {res.final_text}\n")
        msg = input("继续(回车退出)> ").strip()
        if not msg:
            break


def main() -> int:
    provider = "merged" if "--real" in sys.argv else "synthetic"
    agent = InvestAgent(provider_name=provider)

    if agent.available():
        print("已连接 DeepSeek，进入对话模式。")
        chat_mode(agent)
        return 0

    print("未检测到 DEEPSEEK_API_KEY -> 使用本地确定性管线(离线模式)。")
    answers = questionnaire_flow()
    capital = _input_float("\n可投资本金(CNY, 回车=100000): ", 100000.0)
    free_text = input("补充说明风险态度/目标(可回车跳过): ").strip()

    res = agent.offline_plan(answers, capital, free_text=free_text or None)
    plan, profile = res["plan"], res["profile"]
    print(f"\n=== 结果 ===")
    print(f"适当性: {profile.tier} {profile.tier_info['label_zh']} (评分 {profile.score:.0f})")
    print(f"客群: {plan.segment} | 月度定投建议: ¥{plan.monthly_contrib:,.0f}")
    print("配置:")
    name_of = {a.id: a.name_zh for a in plan.assets}
    for a_id, wgt in sorted(plan.weights.items(), key=lambda kv: -kv[1]):
        print(f"  {name_of[a_id]:<16} {wgt:6.2%}")
    print(f"事前预期: 年化 {plan.expected['ann_return']:.1%}, "
          f"波动 {plan.expected['ann_vol']:.1%}, 夏普≈{plan.expected['sharpe_hint']:.2f}")
    print(f"回测({plan.n_months}个月): 年化 {plan.backtest['ann_return']:.1%}, "
          f"最大回撤 {plan.backtest['max_drawdown']:.1%}, 夏普 {plan.backtest['sharpe']:.2f}")
    print(f"\n图表: {list(res['charts'].values())}")
    print("完整报告已写入 examples/demo_outputs/report.md")
    from .report import build_report, save_report
    save_report(res["report"], "examples/demo_outputs/report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
