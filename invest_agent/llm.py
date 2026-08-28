"""LLM client wrapper.

OpenAI-compatible, so the harness runs against:
  * DeepSeek API            (https://api.deepseek.com)          -- provider=api
  * any local server that speaks OpenAI protocol (vLLM / Ollama
    serving DeepSeek-R1-Distill models)                          -- provider=local

The rest of the codebase only sees :class:`LLMClient`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .config import get_config


class LLMUnavailable(RuntimeError):
    pass


@dataclass
class LLMConfig:
    provider: str
    api_base: str
    api_key: str
    model_chat: str
    model_reasoner: str
    temperature: float
    max_tokens: int

    @classmethod
    def from_config(cls, provider: Optional[str] = None) -> "LLMConfig":
        cfg = get_config()["llm"]
        provider = provider or cfg.get("provider", "api")
        if provider == "local":
            sec = cfg.get("local", {})
            base = sec.get("api_base", "http://127.0.0.1:8000/v1")
            key = os.environ.get(sec.get("api_key_env", "LOCAL_LLM_API_KEY"), "EMPTY")
            model_chat = sec.get("model_chat", "deepseek-r1-distill-7b")
            model_reasoner = sec.get("model_reasoner", model_chat)
        else:
            base = cfg.get("api_base", "https://api.deepseek.com")
            key = os.environ.get(cfg.get("api_key_env", "DEEPSEEK_API_KEY"), "")
            model_chat = cfg.get("model_chat", "deepseek-chat")
            model_reasoner = cfg.get("model_reasoner", "deepseek-reasoner")
        return cls(
            provider=provider, api_base=base.rstrip("/"), api_key=key,
            model_chat=model_chat, model_reasoner=model_reasoner,
            temperature=float(cfg.get("temperature", 0.3)),
            max_tokens=int(cfg.get("max_tokens", 2048)),
        )


class LLMClient:
    """Thin wrapper over the OpenAI SDK pointed at a DeepSeek-compatible endpoint."""

    def __init__(self, cfg: Optional[LLMConfig] = None):
        self.cfg = cfg or LLMConfig.from_config()
        self._client = None

    def _ensure(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as e:
                raise LLMUnavailable("openai package not installed") from e
            if not self.cfg.api_key and self.cfg.provider == "api":
                raise LLMUnavailable(
                    "DEEPSEEK_API_KEY not set; run `export DEEPSEEK_API_KEY=*** or use provider=local"
                )
            self._client = OpenAI(api_key=self.cfg.api_key or "EMPTY", base_url=self.cfg.api_base)
        return self._client

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        use_reasoner: bool = False,
    ) -> Dict[str, Any]:
        client = self._ensure()
        kwargs = dict(
            model=model or (self.cfg.model_reasoner if use_reasoner else self.cfg.model_chat),
            messages=messages,
            temperature=self.cfg.temperature,
            max_tokens=self.cfg.max_tokens,
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        resp = client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        out: Dict[str, Any] = {"content": msg.content or "", "tool_calls": []}
        for tc in getattr(msg, "tool_calls", None) or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"__raw__": tc.function.arguments}
            out["tool_calls"].append({"id": tc.id, "name": tc.function.name, "arguments": args})
        return out


SYSTEM_PROMPT = """你是 Atlas 多元资产投资顾问 (Atlas Multi-Asset Advisor)，一名面向个人投资者的专业助手。

能力与职责:
1. 通过提问与推理评估投资者的适当性等级 (C1保守 ~ C5激进)，评估必须基于证据，不得凭空假设。
2. 依据客群分层(大众/富裕/高净值)与适当性等级，先用 list_strategies 了解策略菜单，
   再调用 build_investment_plan。策略各有投资哲学(放大优势/控制劣势)、优化目标与调仓频率，
   选择要与投资者的风险偏好和期限匹配，而不是把所有资产堆进一个组合。
3. 给出配置前，调用 get_market_intel 获取最新数日的财经新闻/研报要点，
   结合时效信息评估方案的现实风险(如行业政策、宏观事件)，并在回答中引用关键情报。
4. 解释资产选择时，可调用 get_factor_knowledge / screen_assets_by_factors，
   基于因子库(动量/反转/低波动等)说明筛选逻辑；引用因子须注明其与未来收益的方向。
5. 提供大类视角时，调用 get_macro_advice 获取大类配置建议(超配/标配/低配+行业风格细分)，
   调用 get_global_situation 获取全球政经局势研判(风险偏好/主导议题)，
   把宏观与大类观点落到具体配置上。
6. 家办视角: 用 get_asset_profile_questionnaire 采集资产画像(现有资产类型/境外占比/
   境外账户)，再用 recommend_global_bases 给出全球资产落位(境内/跨境通道/离岸)打分建议，
   帮投资者在满足适当性的前提下降低资本管制/税收/汇兑等摩擦。
7. 用数字(年化收益、波动率、夏普、最大回撤)与图表清晰展示方案，强调长期复利与纪律，
   激发理性的投资动力，而不是追逐短期暴利。
8. 解释任何产品时先讲风险，再讲收益。

硬性规则:
- 信息不足时，先用 ask_investor 工具向投资者提问，一次最多问3个问题。
- 任何配置必须满足适当性上限: 不得超配工具返回的 class_caps。
- 每次给出配置建议时，必须在末尾附上免责声明。
- 使用投资者的语言(默认简体中文)回答。
- evolve_factor_library 用于因子库自进化(导入知识库+从真实数据实证学习因子测IC)，
  通常在用户要求"学习新因子/更新因子库"时调用，勿在每次对话中自动触发。

免责声明: 以上内容由量化模型生成，仅供研究参考，不构成投资建议；市场有风险，投资需谨慎。
"""
