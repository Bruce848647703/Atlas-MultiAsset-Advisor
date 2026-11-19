"""Interactive terminal session.

With DEEPSEEK_API_KEY set: conversational mode (the agent asks the
investor questions itself through the ask_investor tool).
Without it: guided questionnaire + deterministic pipeline, or a fully
non-interactive run with ``--answers`` / ``--text``.

Examples
--------
python -m invest_agent.cli
python -m invest_agent.cli --answers 2,2,2,2,2,2,2,2,2 --capital 200000
python -m invest_agent.cli --text "稳健增值，能接受一点波动" --capital 500000
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional

from .agent import InvestAgent
from .risk_profiler import QUESTIONS

PROVIDERS = ("synthetic", "merged", "akshare", "kairos")


def _input_float(prompt: str, default: float) -> float:
    raw = input(prompt).strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        print("  (无法解析, 使用默认值)")
        return default


def questionnaire_flow() -> Dict[int, int]:
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


def _parse_answers(raw: str) -> Dict[int, int]:
    fields = [field.strip() for field in raw.split(",")]
    if len(fields) != len(QUESTIONS):
        raise ValueError(f"--answers needs {len(QUESTIONS)} comma-separated values")
    answers: Dict[int, int] = {}
    for index, field in enumerate(fields):
        if field not in {"0", "1", "2", "3"}:
            raise ValueError(f"--answers value {index} must be 0-3")
        answers[index] = int(field)
    return answers


def chat_mode(agent: InvestAgent) -> None:
    print("\n[Atlas] 你好！我是 Atlas 多元资产投资顾问。请先告诉我: 您的可投资本金大约是多少?")
    history = None
    try:
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
    except (EOFError, KeyboardInterrupt):
        print("\n[Atlas] 已结束对话。")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m invest_agent.cli",
        description="Atlas interactive / non-interactive investment advisor",
    )
    parser.add_argument("--provider", choices=PROVIDERS, help="data provider")
    parser.add_argument("--real", action="store_true",
                        help="use the merged live provider (alias for --provider merged)")
    parser.add_argument("--offline", action="store_true",
                        help="skip the LLM even if DEEPSEEK_API_KEY is set")
    parser.add_argument("--answers",
                        help=f"{len(QUESTIONS)} comma-separated questionnaire answers (0-3)")
    parser.add_argument("--capital", type=float, help="investable capital in CNY")
    parser.add_argument("--text", default="", help="free-text risk attitude / goals")
    parser.add_argument("--output", default="examples/demo_outputs/report.md",
                        help="Markdown report path")
    parser.add_argument("--no-report", action="store_true", help="do not write a report")
    return parser


def _offline_answers(args: argparse.Namespace) -> Optional[Dict[int, int]]:
    if args.answers is not None:
        return _parse_answers(args.answers)
    if args.text:
        return {}
    if not sys.stdin.isatty():
        raise ValueError("no answers: pass --answers or --text for a non-interactive run")
    return questionnaire_flow()


def main(argv: Optional[List[str]] = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.real and args.provider:
        parser.error("--real and --provider are mutually exclusive")
    provider = args.provider or ("merged" if args.real else "synthetic")

    try:
        agent = InvestAgent(provider_name=provider)
    except Exception as exc:  # provider discovery can fail for optional data sources
        print(f"error: cannot create provider '{provider}': {exc}", file=sys.stderr)
        return 2

    non_interactive = bool(args.answers is not None or args.text or args.capital is not None)
    if not args.offline and not non_interactive and agent.available():
        print("已连接 DeepSeek，进入对话模式。")
        chat_mode(agent)
        return 0

    if not args.offline:
        print("未检测到 DEEPSEEK_API_KEY 或使用了非交互参数 -> 使用本地确定性管线。")
    try:
        answers = _offline_answers(args)
        capital = args.capital
        if capital is None:
            if not sys.stdin.isatty():
                raise ValueError("no capital: pass --capital for a non-interactive run")
            capital = _input_float("\n可投资本金(CNY, 回车=100000): ", 100000.0)
        free_text = args.text
        if not free_text and sys.stdin.isatty():
            free_text = input("补充说明风险态度/目标(可回车跳过): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nerror: interactive input ended; use --answers/--capital for automation",
              file=sys.stderr)
        return 2
    except ValueError as exc:
        parser.error(str(exc))

    res = agent.offline_plan(answers or {}, float(capital), free_text=free_text or None)
    plan, profile = res["plan"], res["profile"]
    print("\n=== 结果 ===")
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

    if not args.no_report:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        from .report import save_report
        save_report(res["report"], str(output))
        print(f"完整报告已写入 {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
