"""DeepSeek tool-calling harness.

The loop:  user message -> model -> (tool_calls? execute & feed back)* ->
final answer. Two special behaviors:

* a tool may return ``{"__ask_user__": "<question>"}`` to pause the loop and
  relay the question to the human (this is how the agent *asks the
  investor*);
* ``max_steps`` guards against runaway loops.

Safety boundaries (the model is untrusted output, not a trusted caller):

* tool arguments are validated against each tool's JSON schema before the
  handler runs (required keys, primitive types, enum/bounds, size caps);
* the number of tool calls per conversation is bounded;
* oversized tool results are truncated with an explicit marker.

The harness is model-agnostic: any client exposing ``.chat(messages, tools)``
works, including the scripted mock used in tests and offline demos.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


class Tool:
    def __init__(self, name: str, description: str, parameters: Dict[str, Any], handler: Callable[[Dict[str, Any]], Any]):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.handler = handler

    def to_openai_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class AgentResult:
    final_text: str
    pending_question: Optional[str] = None
    history: List[Dict[str, Any]] = field(default_factory=list)
    trace: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def needs_user_input(self) -> bool:
        return self.pending_question is not None


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True


def validate_arguments(tool: Tool, arguments: Dict[str, Any],
                       max_chars: int = 16_000) -> Optional[str]:
    """Return an error string when arguments violate the tool's schema."""
    if not isinstance(arguments, dict):
        return "arguments must be a JSON object"

    params = tool.parameters or {}
    for key in params.get("required", []) or []:
        if key not in arguments:
            return f"missing required argument: {key}"

    per_string_limit = max(1000, max_chars // 2)
    for key, spec in (params.get("properties") or {}).items():
        if key not in arguments:
            continue
        value = arguments[key]
        expected = spec.get("type")
        if expected and not _matches_type(value, expected):
            return f"argument '{key}' must be {expected}"
        if "enum" in spec and value not in spec["enum"]:
            return f"argument '{key}' must be one of {spec['enum']}"
        if expected in ("integer", "number"):
            if "minimum" in spec and value < spec["minimum"]:
                return f"argument '{key}' must be >= {spec['minimum']}"
            if "maximum" in spec and value > spec["maximum"]:
                return f"argument '{key}' must be <= {spec['maximum']}"
        if isinstance(value, str) and len(value) > per_string_limit:
            return f"argument '{key}' is too long (>{per_string_limit} chars)"

    try:
        size = len(json.dumps(arguments, ensure_ascii=False))
    except (TypeError, ValueError):
        return "arguments are not JSON-serializable"
    if size > max_chars:
        return f"arguments too large ({size} > {max_chars} chars)"
    return None


class AgentHarness:
    def __init__(self, client, tools: List[Tool], system_prompt: str,
                 max_steps: int = 8, model: Optional[str] = None,
                 max_tool_calls: int = 24,
                 max_tool_argument_chars: int = 16_000,
                 max_tool_result_chars: int = 12_000):
        self.client = client
        self.tools = {t.name: t for t in tools}
        self.system_prompt = system_prompt
        self.max_steps = max_steps
        self.model = model
        self.max_tool_calls = max(int(max_tool_calls), 0)
        self.max_tool_argument_chars = max(int(max_tool_argument_chars), 1000)
        self.max_tool_result_chars = max(int(max_tool_result_chars), 1000)

    # --------------------------------------------------------------------
    def _execute_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        tool = self.tools.get(name)
        if tool is None:
            return {"error": f"unknown tool: {name}"}
        error = validate_arguments(tool, arguments or {}, self.max_tool_argument_chars)
        if error:
            return {"error": f"invalid arguments for tool '{name}': {error}"}
        try:
            result = tool.handler(arguments or {})
        except Exception as e:  # noqa: BLE001 - report, don't crash the loop
            result = {"error": f"{type(e).__name__}: {e}"}
        if not isinstance(result, dict):
            result = {"result": result}
        return result

    def _tool_content(self, result: Dict[str, Any]) -> str:
        try:
            content = json.dumps(result, ensure_ascii=False)
        except (TypeError, ValueError):
            content = json.dumps({"error": "tool result is not JSON-serializable"})
        if len(content) > self.max_tool_result_chars:
            content = json.dumps({
                "_truncated": True,
                "original_chars": len(content),
                "preview": content[: self.max_tool_result_chars],
            }, ensure_ascii=False)
        return content

    # --------------------------------------------------------------------
    def run(self, user_message: str, history: Optional[List[Dict[str, Any]]] = None) -> AgentResult:
        history = list(history or [])
        if not history or history[0].get("role") != "system":
            history.insert(0, {"role": "system", "content": self.system_prompt})
        history.append({"role": "user", "content": user_message})

        trace: List[Dict[str, Any]] = []
        tool_schemas = [t.to_openai_schema() for t in self.tools.values()] or None
        calls_used = 0

        for _ in range(self.max_steps):
            response = self.client.chat(history, tools=tool_schemas, model=self.model)
            tool_calls = response.get("tool_calls") or []

            if not tool_calls:
                final = response.get("content", "") or ""
                history.append({"role": "assistant", "content": final})
                return AgentResult(final_text=final, history=history, trace=trace)

            # record assistant message with its tool calls
            history.append({
                "role": "assistant",
                "content": response.get("content") or "",
                "tool_calls": [
                    {"id": tc["id"], "type": "function",
                     "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"], ensure_ascii=False)}}
                    for tc in tool_calls
                ],
            })

            budget_hit = False
            for tc in tool_calls:
                if calls_used >= self.max_tool_calls:
                    result = {"error": "tool call budget exhausted for this conversation"}
                    budget_hit = True
                else:
                    calls_used += 1
                    result = self._execute_tool(tc["name"], tc["arguments"])
                trace.append({"tool": tc["name"], "arguments": tc["arguments"], "result": result})
                history.append({"role": "tool", "tool_call_id": tc["id"],
                                "content": self._tool_content(result)})
                if "__ask_user__" in result and not budget_hit:
                    return AgentResult(
                        final_text="", pending_question=result["__ask_user__"],
                        history=history, trace=trace,
                    )

            if budget_hit:
                final = ("（本次会话的工具调用次数已达上限，请总结已有信息或开启新会话继续。）")
                history.append({"role": "assistant", "content": final})
                return AgentResult(final_text=final, history=history, trace=trace)

        final = "（已达到最大推理步数，请简化问题或拆分任务。）"
        history.append({"role": "assistant", "content": final})
        return AgentResult(final_text=final, history=history, trace=trace)