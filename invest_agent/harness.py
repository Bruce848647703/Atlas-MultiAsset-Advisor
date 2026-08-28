"""DeepSeek tool-calling harness.

The loop:  user message -> model -> (tool_calls? execute & feed back)* ->
final answer. Two special behaviors:

* a tool may return ``{"__ask_user__": "<question>"}`` to pause the loop and
  relay the question to the human (this is how the agent *asks the
  investor*);
* ``max_steps`` guards against runaway loops.

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


class AgentHarness:
    def __init__(self, client, tools: List[Tool], system_prompt: str,
                 max_steps: int = 8, model: Optional[str] = None):
        self.client = client
        self.tools = {t.name: t for t in tools}
        self.system_prompt = system_prompt
        self.max_steps = max_steps
        self.model = model

    # --------------------------------------------------------------------
    def _execute_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        tool = self.tools.get(name)
        if tool is None:
            return {"error": f"unknown tool: {name}"}
        try:
            result = tool.handler(arguments or {})
        except Exception as e:  # noqa: BLE001 - report, don't crash the loop
            result = {"error": f"{type(e).__name__}: {e}"}
        if not isinstance(result, dict):
            result = {"result": result}
        return result

    # --------------------------------------------------------------------
    def run(self, user_message: str, history: Optional[List[Dict[str, Any]]] = None) -> AgentResult:
        history = list(history or [])
        if not history or history[0].get("role") != "system":
            history.insert(0, {"role": "system", "content": self.system_prompt})
        history.append({"role": "user", "content": user_message})

        trace: List[Dict[str, Any]] = []
        tool_schemas = [t.to_openai_schema() for t in self.tools.values()] or None

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

            for tc in tool_calls:
                result = self._execute_tool(tc["name"], tc["arguments"])
                trace.append({"tool": tc["name"], "arguments": tc["arguments"], "result": result})
                if "__ask_user__" in result:
                    history.append({"role": "tool", "tool_call_id": tc["id"],
                                    "content": json.dumps(result, ensure_ascii=False)})
                    return AgentResult(
                        final_text="", pending_question=result["__ask_user__"],
                        history=history, trace=trace,
                    )
                history.append({"role": "tool", "tool_call_id": tc["id"],
                                "content": json.dumps(result, ensure_ascii=False)})

        final = "（已达到最大推理步数，请简化问题或拆分任务。）"
        history.append({"role": "assistant", "content": final})
        return AgentResult(final_text=final, history=history, trace=trace)
