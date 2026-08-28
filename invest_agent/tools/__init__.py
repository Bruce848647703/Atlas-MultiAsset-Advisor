"""Tools exposed to the DeepSeek harness.

Every tool is a plain function over a shared :class:`AdvisorContext`,
wrapped with an OpenAI-style JSON schema. The ``ask_investor`` tool
pauses the loop and returns its question to the human — the agent's
direct-questioning capability.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..advisor import Plan, build_plan
from ..charts import render_all
from ..config import class_priors, get_config
from ..data.base import get_provider
from ..data.universe import build_universe
from ..factors import default_catalog, screen_universe
from ..harness import Tool
from ..intel import fetch_market_intel, summarize_for_prompt
from ..personas import accessible_classes, describe, segment_for_capital, segment_insight
from ..portfolio.metrics import performance_metrics
from ..risk_profiler import profile_from_answers, QUESTIONS
from ..strategy import STRATEGY_MENU, menu_for_tier
from ..timing import views_from_args, extract_timing_views
from ..macro_advice import generate_macro_advice
from ..geopolitics import assess_global_situation, fetch_global_news, situation_digest
from ..global_base import (AssetProfile, recommend_bases, base_digest,
                           ASSET_TYPE_OPTIONS, OVERSEAS_ACCOUNT_OPTIONS,
                           ASSET_PROFILE_QUESTIONS)
from ..final_advice import build_final_advice, synthesize_final_advice, final_digest
from ..global_indices import fetch_global_indices

PRODUCT_RISK_NOTES = {
    "cash": "R1 低风险: 货币基金/存款，流动性储备，几乎无回撤。",
    "fixed_income": "R2 中低风险: 利率与信用风险并存，回撤通常 <3%。",
    "hybrid": "R3 中风险: 固收+（二级债基等），含少量权益/转债敞口，回撤可达 5-8%。",
    "commodity": "R3 中风险: 黄金/原油等实物资产，对冲通胀与尾部风险。",
    "equity_cn": "R4 中高风险: A股宽基/行业，波动高但长期分享经济增长。",
    "equity_global": "R4 中高风险: 美股/港股/日股宽基，注意汇率与QDII溢价。",
    "crypto": "R5 高风险: BTC/ETH/SOL等，7×24 交易、极端波动、监管与托管风险，仓位必须受限。",
    "futures": "R5 高风险: 保证金杠杆机制，仅限合格投资者与管理型策略。",
}


class AdvisorContext:
    """Mutable state shared across tool calls within a conversation."""

    def __init__(self, provider_name: str = "synthetic", output_dir: str = "examples/demo_outputs"):
        self.provider_name = provider_name
        self.output_dir = output_dir
        self.profile = None
        self.plan: Optional[Plan] = None
        self.timing_view = None      # subjective market-timing view

    # convenience ---------------------------------------------------------
    def get_provider(self):
        return get_provider(self.provider_name)


def T(name, desc, props, required, handler):
    return Tool(
        name=name, description=desc,
        parameters={"type": "object", "properties": props, "required": required},
        handler=handler,
    )


def _profile_summary(ctx: AdvisorContext) -> Dict[str, Any]:
    p = ctx.profile
    return {
        "tier": p.tier, "tier_label": p.tier_info["label_zh"],
        "score": p.score, "capital": p.capital,
        "horizon_years": p.horizon_years,
        "segment": segment_for_capital(p.capital),
        "class_caps": accessible_classes(p),
        "notes": p.notes,
    }


def build_tools(ctx: AdvisorContext) -> List[Tool]:

    def ask_investor(args: Dict[str, Any]) -> Dict[str, Any]:
        q = str(args.get("question", "")).strip()
        if not q:
            return {"error": "question is required"}
        return {"__ask_user__": q}

    def assess_risk_profile(args: Dict[str, Any]) -> Dict[str, Any]:
        answers = args.get("answers") or {}
        answers = {int(k): int(v) for k, v in answers.items()}
        capital = float(args.get("capital", ctx.profile.capital if ctx.profile else 0.0))
        free_text = str(args.get("free_text", "") or "")
        horizon = args.get("horizon_years")
        if not answers and not free_text:
            return {"error": "需要问卷答案(answers) 或 投资者原话(free_text)；可先用 ask_investor 收集。"}
        ctx.profile = profile_from_answers(answers, capital=capital, free_text=free_text,
                                           horizon_years=int(horizon) if horizon else None)
        # auto-extract a subjective timing view from the investor's words
        if free_text:
            v = extract_timing_views(free_text)
            if not v.is_empty():
                ctx.timing_view = v
        summary = _profile_summary(ctx)
        summary["persona"] = describe(ctx.profile, lang="zh")
        summary["questionnaire"] = {str(i): q[1] for i, q in enumerate(QUESTIONS)}
        if ctx.timing_view is not None:
            summary["timing_view"] = {
                "tilts": ctx.timing_view.tilts,
                "conviction": ctx.timing_view.conviction,
                "notes": ctx.timing_view.notes[:6],
            }
        return summary

    def get_market_summary(args: Dict[str, Any]) -> Dict[str, Any]:
        n_months = int(args.get("n_months", 120))
        provider = ctx.get_provider()
        if ctx.profile is not None:
            caps = accessible_classes(ctx.profile)
            universe = build_universe(include_classes=[c for c, v in caps.items() if v > 0])
        else:
            universe = build_universe()
        ids = [a.id for a in universe]
        R = provider.get_monthly_returns(ids, n_months)
        out = {}
        for a in universe:
            m = performance_metrics(R[a.id].values)
            out[a.id] = {
                "name_zh": a.name_zh, "class": a.asset_class,
                "ann_return": round(m["ann_return"], 4), "ann_vol": round(m["ann_vol"], 4),
                "sharpe": round(m["sharpe"], 2), "max_drawdown": round(m["max_drawdown"], 4),
            }
        return {"n_months": n_months, "provider": provider.name, "assets": out}

    def build_investment_plan(args: Dict[str, Any]) -> Dict[str, Any]:
        if ctx.profile is None:
            return {"error": "必须先完成风险评估 (assess_risk_profile)。"}
        if args.get("capital") is not None:
            ctx.profile.capital = float(args["capital"])
        provider = ctx.get_provider()
        # allow an explicit timing override in this call, else use the stored view
        call_view = views_from_args(args.get("timing")) or ctx.timing_view
        plan = build_plan(
            ctx.profile, provider,
            monthly_contrib=float(args["monthly_contrib"]) if args.get("monthly_contrib") else None,
            strategy_id=args.get("strategy_id"),
            timing_view=call_view,
        )
        ctx.plan = plan
        return {
            "strategy": {
                "id": plan.strategy.id, "name_zh": plan.strategy.name_zh,
                "philosophy": plan.strategy.philosophy,
                "objective": plan.strategy.objective,
                "cadence": plan.strategy.cadence_label,
            },
            "timing_applied": plan.timing,
            "segment": plan.segment,
            "segment_insight": segment_insight(ctx.profile),
            "weights": {k: round(v, 4) for k, v in plan.weights.items()},
            "class_caps": plan.class_caps,
            "expected": {k: round(v, 4) for k, v in plan.expected.items()},
            "backtest": {k: round(v, 4) for k, v in plan.backtest.items()},
            "benchmark": {k: round(v, 4) for k, v in (plan.bench_backtest or {}).items()},
            "projection_final": plan.projection[-1] if plan.projection else None,
            "monthly_contrib": plan.monthly_contrib,
            "notes": plan.notes,
        }

    def list_strategies(args: Dict[str, Any]) -> Dict[str, Any]:
        tier = args.get("tier") or (ctx.profile.tier if ctx.profile else None)
        menu = menu_for_tier(tier) if tier else STRATEGY_MENU
        return {
            "tier": tier,
            "strategies": [
                {"id": s.id, "name_zh": s.name_zh, "philosophy": s.philosophy,
                 "objective": s.objective, "cadence": s.cadence_label,
                 "tier_range": f"{s.min_tier}-{s.max_tier}"}
                for s in menu
            ],
        }

    def get_market_intel(args: Dict[str, Any]) -> Dict[str, Any]:
        pack = fetch_market_intel(max_items=int(args.get("max_items", 12)))
        return {
            "source_status": pack["source_status"],
            "generated_at": pack["generated_at"],
            "topics_covered": pack["topics_covered"],
            "brief": summarize_for_prompt(pack, max_items=int(args.get("max_items", 12))),
            "items": pack["items"][: int(args.get("max_items", 12))],
        }

    def apply_timing_views(args: Dict[str, Any]) -> Dict[str, Any]:
        """Store a subjective market-timing view on the context. Accepts either
        free text ("看空A股，看多加密") or a dict {class: tilt in [-1,1]}.
        The view is applied to the next build_investment_plan."""
        view = views_from_args(args.get("views") if "views" in args else args.get("text"))
        if view is None or view.is_empty():
            return {"error": "未能解析出择时观点；请给出方向(看多/看空)与标的类别，"
                             "或形如 {\"equity_cn\": -0.5, \"crypto\": 0.8} 的字典。"}
        if args.get("conviction") is not None:
            view.conviction = float(args["conviction"])
        ctx.timing_view = view
        return {
            "stored": True,
            "tilts": view.tilts,
            "conviction": view.conviction,
            "source": view.source,
            "notes": view.notes[:6],
            "hint": "观点已保存，将在下一次 build_investment_plan 注入预期收益。",
        }

    def get_macro_advice(args: Dict[str, Any]) -> Dict[str, Any]:
        """大类资产配置建议(结合真实动量/估值/新闻情绪/宏观研判) + 行业风格细分。"""
        try:
            adv = generate_macro_advice(
                provider_name=ctx.provider_name,
                months=int(args.get("months", 60)))
            return adv
        except Exception as e:  # noqa: BLE001
            return {"error": f"macro advice unavailable: {e}"}

    def get_global_situation(args: Dict[str, Any]) -> Dict[str, Any]:
        """全球政治经济局势研判: 实时新闻聚合 + 风险偏好 + 主导议题 + 关注事件。"""
        try:
            pack = fetch_global_news(max_items=int(args.get("max_items", 40)))
            situ = assess_global_situation(pack)
            situ["digest"] = situation_digest(situ)
            situ["news_sample"] = [it["title"] for it in pack["items"][:10]]
            return situ
        except Exception as e:  # noqa: BLE001
            return {"error": f"global situation unavailable: {e}"}

    def get_global_indices(args: Dict[str, Any]) -> Dict[str, Any]:
        """全球主要指数实时行情(形象看板): 中国内地/亚太/欧洲/美洲，含现价、涨跌、交易状态。
        双源(腾讯核心+东财扩展)，带缓存与降级。"""
        try:
            pack = fetch_global_indices()
            return pack
        except Exception as e:  # noqa: BLE001
            return {"error": f"global indices unavailable: {e}"}

    def recommend_global_bases(args: Dict[str, Any]) -> Dict[str, Any]:
        """家办式全球资产落位建议: 根据适当性等级+资产画像(现有资产类型/境外占比/
        境外账户/规模)，列出全球适合的 base(境内/跨境通道/离岸)并打分排序，
        每类 base 标注摩擦(资本管制/税/汇兑/准入/合规)与理由。"""
        try:
            tier = args.get("tier") or (ctx.profile.tier if ctx.profile else "C3")
            ap = AssetProfile(
                asset_types=list(args.get("asset_types", []) or []),
                overseas_pct=float(args.get("overseas_pct", 0.0)),
                overseas_accounts=list(args.get("overseas_accounts", ["none"]) or ["none"]),
                total_capital=float(args.get("capital",
                                             ctx.profile.capital if ctx.profile else 0.0)),
                crypto_held=bool(args.get("crypto_held", False)),
                liquidity_need=str(args.get("liquidity_need", "medium")),
            )
            ranked = recommend_bases(tier, ap)
            return {"tier": tier, "total_capital": ap.total_capital,
                    "ranked": ranked, "digest": base_digest(ranked, top_n=6)}
        except Exception as e:  # noqa: BLE001
            return {"error": f"global base advice unavailable: {e}"}

    def get_asset_profile_questionnaire(args: Dict[str, Any]) -> Dict[str, Any]:
        """返回资产画像问卷结构(资产类型/境外占比/境外账户/流动性)，供前端渲染或提问。"""
        return {"questions": ASSET_PROFILE_QUESTIONS,
                "asset_type_options": ASSET_TYPE_OPTIONS,
                "overseas_account_options": OVERSEAS_ACCOUNT_OPTIONS}

    def get_final_advice(args: Dict[str, Any]) -> Dict[str, Any]:
        """最终综合建议: 把量化配置方案 × 大类观点 × 全球政经局势 × 全球base落位
        有机融合成一个符合发展趋势、利益最大化的最终建议。需先生成方案。"""
        if ctx.plan is None:
            return {"error": "请先生成配置方案 (build_investment_plan)。"}
        try:
            ap = AssetProfile(
                asset_types=list(args.get("asset_types", ["cash_deposit", "cn_fund"]) or []),
                overseas_pct=float(args.get("overseas_pct", 0.0)),
                overseas_accounts=list(args.get("overseas_accounts", ["none"]) or ["none"]),
                total_capital=float(args.get("capital",
                                             ctx.profile.capital if ctx.profile else 0.0)),
                crypto_held=bool(args.get("crypto_held", False)),
                liquidity_need=str(args.get("liquidity_need", "medium")),
            )
            adv = build_final_advice(ctx.plan, ctx.profile, ap,
                                     provider_name=ctx.provider_name)
            return adv
        except Exception as e:  # noqa: BLE001
            return {"error": f"final advice unavailable: {e}"}

    def evolve_factor_library(args: Dict[str, Any]) -> Dict[str, Any]:
        """因子自进化(自主学习): 导入知识库 + 券商研报因子采集 + 从真实数据实证学习(测IC)
        + 在线搜集, 持久化到项目因子库并记录学习状态。后台守护进程会定期自动运行本循环。"""
        try:
            from ..factors.factor_evolution import (read_state, run_cycle,
                                                    hours_since_last_run)
            from ..factors.factor_store import stats
            if args.get("dry_run"):
                st = read_state()
                return {"store_stats": stats(), "state": st,
                        "hours_since_last": hours_since_last_run(),
                        "hint": "dry_run; pass run=true to evolve"}
            rep = run_cycle(provider_name=ctx.provider_name,
                            months=int(args.get("months", 96)),
                            ic_threshold=float(args.get("ic_threshold", 0.0)),
                            import_kb=bool(args.get("import_kb", True)),
                            collect_reports=bool(args.get("collect_reports", True)),
                            mine_pdfs=bool(args.get("mine_pdfs", True)))
            rep["state"] = read_state()
            return rep
        except Exception as e:  # noqa: BLE001
            return {"error": f"factor evolution failed: {e}"}

    def get_factor_knowledge(args: Dict[str, Any]) -> Dict[str, Any]:
        cat = default_catalog()
        if not cat.factors:
            return {"error": "factor library not loaded (data_dir missing/empty)"}
        query = str(args.get("query", "")).strip()
        category = str(args.get("category", "")).strip()
        limit = int(args.get("limit", 6))
        if category:
            hits = cat.by_category(category, limit)
        elif query:
            hits = cat.search(query, limit)
        else:
            return {
                "n_factors": len(cat.factors),
                "n_records": cat.n_records,
                "categories": cat.category_summary()[:15],
                "hint": "pass query=... or category=... to fetch factor details",
            }
        return {
            "matched": [
                {
                    "name": f.name, "name_cn": f.name_cn, "category": f.category,
                    "direction": {1: "与未来收益正相关", -1: "与未来收益负相关", 0: "方向未明"}[f.direction],
                    "is_high_freq": f.is_high_freq,
                    "rationale": (f.rationale or "")[:400],
                }
                for f in hits
            ],
            "note": "高频因子/估值/财务类因子需要日频个股数据，不能直接用于本资产池。",
        }

    def screen_assets_by_factors(args: Dict[str, Any]) -> Dict[str, Any]:
        provider = ctx.get_provider()
        universe = build_universe()
        ids = [a.id for a in universe]
        R = provider.get_monthly_returns(ids, int(args.get("n_months", 96)))
        try:
            from ..factors import enrich_universe
            enrichment = enrich_universe(universe)
        except Exception:  # noqa: BLE001 - live layer optional
            enrichment = None
        res = screen_universe(R[ids], universe, default_catalog(), enrichment=enrichment)
        topn = int(args.get("top", 10))
        return {
            "top": res["ranked"][:topn],
            "bottom": res["ranked"][-3:],
            "factors": res["factors"],
            "live_data_used": res["live_data_used"],
            "skipped_families": res["skipped_families"],
            "method": "收益代理(动量/反转/低波/回撤) + 在线真因子(PE分位/流动性/主力资金流)，缺失自动降权",
        }

    def generate_charts(args: Dict[str, Any]) -> Dict[str, Any]:
        if ctx.plan is None:
            return {"error": "请先生成方案 (build_investment_plan)。"}
        out_dir = str(args.get("out_dir", ctx.output_dir))
        paths = render_all(ctx.plan, out_dir)
        ctx.output_dir = out_dir
        return {"charts": {k: v for k, v in paths.items() if v}}

    def explain_product(args: Dict[str, Any]) -> Dict[str, Any]:
        asset_id = str(args.get("asset_id", ""))
        universe = build_universe()
        asset = next((a for a in universe if a.id == asset_id), None)
        if asset is None:
            return {"error": f"unknown asset '{asset_id}'",
                    "available": [a.id for a in universe]}
        prior = class_priors()[asset.asset_class]
        tags = asset.meta.get("tags", [])
        return {
            "id": asset.id, "name_zh": asset.name_zh, "name_en": asset.name_en,
            "class": asset.asset_class,
            "risk_note": PRODUCT_RISK_NOTES.get(asset.asset_class, ""),
            "long_run_prior": {"ann_return": prior["ann_ret"], "ann_vol": prior["ann_vol"]},
            "tags": tags,
            "fee": asset.fee,
        }

    return [
        T("ask_investor",
          "向投资者直接提问(一次只问关键问题，最多3个)。返回的问题会转达给投资者。",
          {"question": {"type": "string", "description": "要向投资者提出的问题(中文)"}},
          ["question"], ask_investor),
        T("assess_risk_profile",
          "根据问卷答案(0-8题,各题选项0-3)和/或投资者原话评估适当性等级并确定各类资产上限。",
          {"answers": {"type": "object", "description": "题号->选项序号, 如 {\"0\":2}"},
           "capital": {"type": "number", "description": "可投资本金(CNY)"},
           "free_text": {"type": "string", "description": "投资者关于风险态度的原话"},
           "horizon_years": {"type": "integer"}},
          [], assess_risk_profile),
        T("get_market_summary",
          "获取可投资产池的历史表现摘要(年化收益/波动/夏普/回撤)。",
          {"n_months": {"type": "integer"}}, [], get_market_summary),
        T("build_investment_plan",
          "基于当前风险画像生成量化配置方案: 自动选择(或指定)策略，返回权重、预期收益、回测指标与目标投射。"
          "可通过 timing 参数注入主观择时观点(文本或 {类别: 倾斜度[-1,1]})。",
          {"capital": {"type": "number"}, "monthly_contrib": {"type": "number"},
           "strategy_id": {"type": "string", "description": "可选; 指定策略(见 list_strategies)"},
           "timing": {"description": "可选; 主观择时观点(文本或 {class: tilt})"}},
          [], build_investment_plan),
        T("apply_timing_views",
          "保存投资者的主观择时观点(看多/看空某类资产)，注入下一次配置。"
          "接受自由文本(如\"短期看空A股，看多加密\")或 {类别: 倾斜度} 字典(如 {\"equity_cn\":-0.5,\"crypto\":0.8})。"
          "倾斜度 -1=强烈看空, +1=强烈看多。",
          {"views": {"description": "择时观点: 文本或 {class: tilt in [-1,1]}"},
           "conviction": {"type": "number", "description": "确信度 0-1, 默认0.5"}},
          [], apply_timing_views),
        T("get_macro_advice",
          "获取大类资产配置建议: 结合真实动量/估值分位/新闻情绪/宏观研判，"
          "输出各类超配/标配/低配及理由，含权益内部风格/行业细分建议。",
          {"months": {"type": "integer"}}, [], get_macro_advice),
        T("get_global_situation",
          "全球政治经济局势研判: 聚合实时新闻(东财/央视/财经日历)，输出风险偏好、主导议题与关注事件。",
          {"max_items": {"type": "integer"}}, [], get_global_situation),
        T("get_global_indices",
          "全球主要指数实时行情(形象看板): 中国内地/亚太/欧洲/美洲，现价/涨跌/交易状态，双源+缓存+降级。",
          {}, [], get_global_indices),
        T("recommend_global_bases",
          "家办式全球资产落位建议: 按适当性等级+资产画像，列出全球适合的 base(境内/跨境/离岸)并打分排序，"
          "标注摩擦(资本管制/税/汇兑/准入/合规)。",
          {"asset_types": {"type": "array"}, "overseas_pct": {"type": "number"},
           "overseas_accounts": {"type": "array"}, "capital": {"type": "number"},
           "crypto_held": {"type": "boolean"}, "liquidity_need": {"type": "string"},
           "tier": {"type": "string"}},
          [], recommend_global_bases),
        T("get_asset_profile_questionnaire",
          "返回资产画像问卷结构(资产类型/境外占比/境外账户/流动性)，用于向投资者采集资产情况。",
          {}, [], get_asset_profile_questionnaire),
        T("get_final_advice",
          "最终综合建议: 把量化配置方案×大类观点×全球政经局势×全球base落位有机融合，"
          "输出符合发展趋势、利益最大化的最终建议+执行清单。需先 build_investment_plan。",
          {"asset_types": {"type": "array"}, "overseas_pct": {"type": "number"},
           "overseas_accounts": {"type": "array"}, "capital": {"type": "number"},
           "crypto_held": {"type": "boolean"}, "liquidity_need": {"type": "string"}},
          [], get_final_advice),
        T("evolve_factor_library",
          "因子自进化: 导入知识库+从真实数据实证学习因子(测IC)+在线搜集，持久化到项目因子库。",
          {"months": {"type": "integer"}, "ic_threshold": {"type": "number"},
           "dry_run": {"type": "boolean"}}, [], evolve_factor_library),
        T("list_strategies",
          "列出可用投资策略(含投资哲学/优化目标/调仓频率/适用等级)，可按当前画像过滤。",
          {"tier": {"type": "string", "description": "可选, 如 C3"}},
          [], list_strategies),
        T("get_market_intel",
          "获取最新数日的重要财经新闻/快讯并按话题归类(加密/美股/债券/商品/宏观等)，用于结合时效信息做判断。",
          {"max_items": {"type": "integer"}}, [], get_market_intel),
        T("get_factor_knowledge",
          "从因子库(1000+量化因子)检索因子的定义/公式/逻辑与收益方向，用于解释选股逻辑或辅助判断。"
          "可按 query(如 动量/反转/波动率) 或 category 检索。",
          {"query": {"type": "string"}, "category": {"type": "string"},
           "limit": {"type": "integer"}}, [], get_factor_knowledge),
        T("screen_assets_by_factors",
          "用因子透镜对当前资产池打分排序(动量/短期反转/低波动/抗回撤)，返回最优与最差标的及所用因子。",
          {"n_months": {"type": "integer"}, "top": {"type": "integer"}},
          [], screen_assets_by_factors),
        T("generate_charts",
          "为当前方案生成图表(配置环图/风险收益地图/净值曲线/目标投射)，返回文件路径。",
          {"out_dir": {"type": "string"}}, [], generate_charts),
        T("explain_product",
          "解释某类资产/产品的风险特征(先风险后收益)。",
          {"asset_id": {"type": "string"}}, ["asset_id"], explain_product),
    ]
