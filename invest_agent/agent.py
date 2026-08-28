"""High-level agent facade: DeepSeek harness + advisory tools."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .config import get_config
from .harness import AgentHarness, AgentResult
from .llm import LLMClient, LLMConfig, LLMUnavailable, SYSTEM_PROMPT
from .tools import AdvisorContext, build_tools


class InvestAgent:
    """Conversational investment advisor.

    ``chat()`` requires a reachable DeepSeek(-compatible) endpoint.
    ``offline_plan()`` runs the same deterministic pipeline without any LLM,
    which is also how local training data is generated.
    """

    def __init__(self, provider_name: str = "synthetic", llm_provider: Optional[str] = None,
                 output_dir: str = "examples/demo_outputs"):
        self.ctx = AdvisorContext(provider_name=provider_name, output_dir=output_dir)
        self.tools = build_tools(self.ctx)
        max_steps = int(get_config()["agent"]["max_tool_steps"])
        self.system_prompt = SYSTEM_PROMPT
        self._llm_provider = llm_provider
        self._client: Optional[LLMClient] = None
        self._max_steps = max_steps

    # ------------------------------------------------------------------
    @property
    def client(self) -> LLMClient:
        if self._client is None:
            self._client = LLMClient(LLMConfig.from_config(self._llm_provider))
        return self._client

    def available(self) -> bool:
        try:
            self.client._ensure()
            return True
        except LLMUnavailable:
            return False

    def chat(self, user_message: str, history: Optional[List[Dict[str, Any]]] = None) -> AgentResult:
        harness = AgentHarness(self.client, self.tools, self.system_prompt, max_steps=self._max_steps)
        return harness.run(user_message, history)

    # ------------------------------------------------------------------
    def offline_plan(self, answers: Dict[int, int], capital: float,
                     free_text: str = "", monthly_contrib: Optional[float] = None,
                     horizon_years: Optional[int] = None,
                     strategy_id: Optional[str] = None,
                     timing=None):
        """Deterministic end-to-end plan without the LLM.

        `timing` accepts either a free-text view ("看空A股，看多加密") or a
        dict {class: tilt in [-1,1]} for subjective market timing.
        """
        from .advisor import build_plan
        from .personas import segment_insight
        from .risk_profiler import profile_from_answers
        from .charts import render_all
        from .report import build_report
        from .timing import views_from_args

        profile = profile_from_answers(answers, capital=capital, free_text=free_text,
                                       horizon_years=horizon_years)
        self.ctx.profile = profile
        view = views_from_args(timing)
        plan = build_plan(profile, self.ctx.get_provider(),
                          monthly_contrib=monthly_contrib, strategy_id=strategy_id,
                          timing_view=view)
        self.ctx.plan = plan
        charts = render_all(plan, self.ctx.output_dir)
        report = build_report(plan, charts)
        return {
            "profile": profile, "plan": plan, "charts": charts, "report": report,
            "segment_insight": segment_insight(profile),
        }
