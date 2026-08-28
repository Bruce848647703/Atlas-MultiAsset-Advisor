import json

from invest_agent.harness import AgentHarness
from invest_agent.tools import AdvisorContext, build_tools


class ScriptedClient:
    """Deterministic stand-in for the DeepSeek endpoint."""

    def __init__(self, steps):
        self.steps = list(steps)

    def chat(self, messages, tools=None, model=None):
        return self.steps.pop(0)


def _tool_call(name, args, tc_id="call_1"):
    return {"id": tc_id, "name": name, "arguments": args}


def test_full_tool_loop():
    ctx = AdvisorContext()
    client = ScriptedClient([
        {"content": "", "tool_calls": [
            _tool_call("assess_risk_profile",
                       {"answers": {str(i): 2 for i in range(9)}, "capital": 300000,
                        "free_text": "能接受短期波动，但不想亏掉本金"}, "call_a")]},
        {"content": "", "tool_calls": [
            _tool_call("build_investment_plan", {}, "call_b")]},
        {"content": "方案已生成：核心为宽基+债券，符合稳健偏好。免责声明: ..."},
    ])
    harness = AgentHarness(client, build_tools(ctx), "sys", max_steps=6)
    res = harness.run("我有30万想投资")
    assert "方案已生成" in res.final_text
    assert ctx.profile is not None and ctx.plan is not None
    assert [t["tool"] for t in res.trace] == ["assess_risk_profile", "build_investment_plan"]
    roles = [m["role"] for m in res.history]
    assert roles.count("tool") == 2


def test_ask_investor_pauses_loop():
    ctx = AdvisorContext()
    client = ScriptedClient([
        {"content": "", "tool_calls": [
            _tool_call("ask_investor", {"question": "您的投资期限是多久？"}, "call_a")]},
        {"content": "不该到这里"},
    ])
    harness = AgentHarness(client, build_tools(ctx), "sys")
    res = harness.run("帮我做配置")
    assert res.needs_user_input
    assert "投资期限" in res.pending_question
    # paused before any final answer
    assert res.final_text == ""


def test_unknown_tool_error_fed_back():
    ctx = AdvisorContext()
    client = ScriptedClient([
        {"content": "", "tool_calls": [_tool_call("no_such_tool", {}, "call_a")]},
        {"content": "收到错误并恢复。"},
    ])
    harness = AgentHarness(client, build_tools(ctx), "sys")
    res = harness.run("hi")
    assert "收到错误并恢复" in res.final_text
    assert "error" in res.trace[0]["result"]


def test_max_steps_guard():
    ctx = AdvisorContext()
    infinite = [{"content": "", "tool_calls": [
        _tool_call("ask_investor", {"question": "q"}, f"call_{i}")]} for i in range(10)]
    client = ScriptedClient(infinite)
    harness = AgentHarness(client, build_tools(ctx), "sys", max_steps=1)
    # ask_investor pauses immediately even within budget
    res = harness.run("hi")
    assert res.needs_user_input


def test_tool_results_are_json_serializable():
    ctx = AdvisorContext()
    tools = {t.name: t for t in build_tools(ctx)}
    out = tools["get_market_summary"].handler({"n_months": 36})
    json.dumps(out, ensure_ascii=False)
    assert out["provider"] == "synthetic"
