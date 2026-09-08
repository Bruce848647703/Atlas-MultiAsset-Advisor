"""Markdown report generation (LLM-friendly and human-readable)."""

from __future__ import annotations

import os
from typing import Dict, Optional

from .advisor import Plan
from .config import get_config
from .personas import describe as describe_persona


def _fmt_pct(x: float, digits: int = 1) -> str:
    return f"{x * 100:.{digits}f}%"


def metrics_table(plan: Plan) -> str:
    m, b = plan.backtest, {} if not plan.bench_backtest else plan.bench_backtest
    rows = [
        ("年化收益 Ann. return", _fmt_pct(m["ann_return"]), _fmt_pct(b.get("ann_return", 0)) if b else "-"),
        ("年化波动 Ann. vol", _fmt_pct(m["ann_vol"]), _fmt_pct(b.get("ann_vol", 0)) if b else "-"),
        ("夏普比率 Sharpe", f"{m['sharpe']:.2f}", f"{b.get('sharpe', 0):.2f}" if b else "-"),
        ("最大回撤 Max DD", _fmt_pct(m["max_drawdown"]), _fmt_pct(b.get("max_drawdown", 0)) if b else "-"),
        ("卡玛比率 Calmar", f"{m['calmar']:.2f}", f"{b.get('calmar', 0):.2f}" if b else "-"),
        ("月度胜率 Win rate", _fmt_pct(m["win_rate"]), _fmt_pct(b.get("win_rate", 0)) if b else "-"),
        ("最差月份 Worst month", _fmt_pct(m["worst_month"]), _fmt_pct(b.get("worst_month", 0)) if b else "-"),
    ]
    lines = ["| 指标 Metric | 组合 Portfolio | 基准 CSI300ETF Benchmark |", "|---|---|---|"]
    lines += [f"| {n} | {p} | {q} |" for n, p, q in rows]
    return "\n".join(lines)


def _render_final_advice(adv: Dict, plan: Plan) -> str:
    """Render the organically-fused final advice (quant × macro × geo × base)."""
    zh_of = {a.id: a.name_zh for a in plan.assets}
    cls_of = {a.id: a.asset_class for a in plan.assets}
    L = ["## ★ 最终综合建议 Final Integrated Advice",
         "> 量化配置 × 大类观点 × 全球政经局势 × 全球落位，四者有机融合、相互校准。\n",
         f"**研判主线**: {adv['thesis']}\n"]

    ov = adv.get("overlays", {})
    L.append(f"- 全球局势: **{ov.get('geo_regime', '—')}**"
             f"（风险偏好 {ov.get('geo_appetite', 0):+.2f}，议题 {ov.get('geo_themes', '—')}）")
    stance = ov.get("macro_stance", {})
    if stance:
        st_txt = "、".join(f"{c}:{s}" for c, s in list(stance.items())[:6])
        L.append(f"- 大类观点: {st_txt}")
    L.append("")

    L.append("### 最终大类配置 + 全球落位")
    L.append("| 资产类别 | 最终权重 | 落位 base | base 评分 | 摩擦 |")
    L.append("|---|---|---|---|---|")
    bm = adv.get("base_map", {})
    for cls, w in adv.get("final_class_weights", {}).items():
        b = bm.get(cls, {})
        L.append(f"| {cls} | **{_fmt_pct(w)}** | {b.get('base', '—')} "
                 f"| {b.get('score', '—')} | {b.get('friction', '—')} |")
    L.append("")

    L.append("### 执行清单（前 8 项）")
    for i, (a_id, w) in enumerate(
            sorted(adv.get("final_asset_weights", {}).items(), key=lambda kv: -kv[1])[:8], 1):
        nm = zh_of.get(a_id, a_id)
        b = bm.get(cls_of.get(a_id, ""), {})
        where = f"（落位: {b['base']}）" if b else ""
        L.append(f"{i}. {nm} — {_fmt_pct(w)} {where}")
    L.append("")
    return "\n".join(L) + "\n"


def _render_council(council: Dict) -> str:
    """Render the analyst council (top-5 direction-matched personas)."""
    L = ["## 🧑‍💼 金融分析师智囊团 Analyst Council",
         f"> {council.get('summary', '')}\n",
         f"共识研判: **{council.get('consensus', '中性')}**"
         + (f" · 异议: {'、'.join(council['dissent'])}" if council.get("dissent") else "")
         + f" · 候选池 {council.get('n_analysts_total', 30)} 位\n"]
    for v in council.get("council", []):
        L.append(f"**{v['name_zh']} · {v['name_en']}**（{v['school']}，相关度 {v['relevance']:.2f}，{v['stance']}）")
        L.append(f"> {v['philosophy']}")
        L.append(f"- 观点: {v['advice']}")
        L.append(f"- 仓位倾向: {v['tilt_text']}")
        L.append(f"- 原则: “{v['signature']}”\n")
    L.append("_智囊团为不同投资流派视角的模拟观点，仅供多元参考，不构成投资建议。_\n")
    return "\n".join(L) + "\n"


def build_report(plan: Plan, chart_paths: Optional[Dict[str, str]] = None,
                 lang: str = "zh", final_advice: Optional[Dict] = None,
                 analyst_council: Optional[Dict] = None) -> str:
    cfg = get_config()
    disclaimer = cfg["agent"]["disclaimer"].strip()
    name_of = {a.id: a.name_en for a in plan.assets}
    zh_of = {a.id: a.name_zh for a in plan.assets}
    chart_paths = chart_paths or {}

    L = []
    L.append(f"# Atlas 多元资产配置方案 | Multi-Asset Plan ({plan.profile.tier} {plan.profile.tier_info['label_en']})\n")
    L.append(describe_persona(plan.profile, lang="zh" if lang == "zh" else "en") + "\n")

    # ---- 最终综合建议 (量化×大类×地缘×落位 有机融合) ----
    if final_advice:
        L.append(_render_final_advice(final_advice, plan))

    # ---- 分析师智囊团 (约30选5, 方向匹配) ----
    if analyst_council:
        L.append(_render_council(analyst_council))

    st = plan.strategy
    L.append("## 0. 所选策略 Strategy\n")
    L.append(f"**{st.name_zh} ({st.name_en})** · 目标 `{st.objective}` · 调仓 `{st.cadence_label}`\n")
    L.append(f"> {st.philosophy}\n")
    if plan.menu:
        L.append("策略菜单对比（同数据、各自调仓频率回测）：\n")
        L.append("| 策略 | 目标 | 调仓 | 年化 | 波动 | 夏普 | 最大回撤 | 年化换手 |")
        L.append("|---|---|---|---|---|---|---|---|")
        for row in plan.menu:
            mark = " ✅" if row["id"] == st.id else ""
            L.append(f"| {row['name_zh']}{mark} | {row['objective']} | {row['cadence_label']} "
                     f"| {_fmt_pct(row['ann_return'])} | {_fmt_pct(row['ann_vol'])} "
                     f"| {row['sharpe']:.2f} | {_fmt_pct(row['max_drawdown'])} "
                     f"| {row.get('turnover_annual', 0):.2f} |")
        L.append("")

    L.append("## 1. 建议配置 Recommended Allocation\n")
    L.append("| 资产 Asset | 类别 Class | 权重 Weight | 预期年化 E[ret] | 年化波动 Vol |")
    L.append("|---|---|---|---|---|")
    for a_id in sorted(plan.weights, key=lambda k: -plan.weights[k]):
        L.append(f"| {zh_of[a_id]} {name_of[a_id]} | {next(a.asset_class for a in plan.assets if a.id==a_id)} "
                 f"| **{_fmt_pct(plan.weights[a_id])}** | {_fmt_pct(plan.mu_ann[a_id])} | {_fmt_pct(plan.vol_ann[a_id])} |")
    L.append("")
    L.append(f"事前组合预期: 年化 **{_fmt_pct(plan.expected['ann_return'])}**, "
             f"波动 **{_fmt_pct(plan.expected['ann_vol'])}**, "
             f"夏普≈ **{plan.expected['sharpe_hint']:.2f}**\n")

    from .data.universe import build_universe as _bu
    zero = [(a.name_zh, a.asset_class, plan.class_caps.get(a.asset_class, 0.0))
            for a in _bu()
            if a.id not in plan.weights and plan.class_caps.get(a.asset_class, 0.0) > 0]
    if zero:
        L.append("可投但本次未配置的资产（可及上限）: " +
                 "; ".join(f"{n}({c}≤{_fmt_pct(cap, 0)})" for n, c, cap in zero) + "\n")

    L.append("## 2. 历史回测 Backtest（样本外走查·无未来函数，按策略调仓频率）\n")
    L.append(metrics_table(plan) + "\n")

    L.append("## 3. 目标投射 Goal Projection\n")
    last = plan.projection[-1] if plan.projection else None
    if last:
        L.append(f"期初 ¥{plan.profile.capital:,.0f}，每月定投 ¥{plan.monthly_contrib:,.0f}，"
                 f"按预期年化 {_fmt_pct(plan.expected['ann_return'])} 估算：\n"
                 f"> **{int(last['year'])}年后组合价值 ≈ ¥{last['value']:,.0f}**"
                 f"（其中收益 ¥{last['gain']:,.0f}，投入本金 ¥{last['principal_in']:,.0f}）\n")

    L.append("## 4. 图表 Charts\n")
    labels = {"allocation": "配置结构", "frontier": "风险-收益地图与有效前沿",
              "equity": "净值曲线与回撤", "projection": "目标投射"}
    for k, p in chart_paths.items():
        if p:
            L.append(f"![{labels.get(k, k)}]({os.path.basename(p)})\n")

    L.append("## 5. 纪律与再平衡 Discipline\n")
    L.append("- 每季度检查一次偏离度，类别权重偏离上限的 80% 时触发再平衡；")
    L.append("- 加密与期货仓位只使用闲余资金，禁止借贷加杠杆；")
    L.append("- 市场极端波动时优先降低单资产集中度，而非清仓离场。\n")

    L.append("---")
    L.append(f"> **免责声明**: {disclaimer}\n")
    return "\n".join(L)


def save_report(text: str, path: str) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path
