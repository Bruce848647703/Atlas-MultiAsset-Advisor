"""Streamlit dashboard (visual layer).

Install:  pip install streamlit
Run:      streamlit run dashboard/app.py

Layout: questionnaire and inputs are ALWAYS rendered before the generate
button, so every answer can be customized first; results persist in
session state across re-runs.

Optional access gate for remote hosting:
    ATLAS_ACCESS_TOKEN=*** streamlit run dashboard/app.py \
        --server.address 0.0.0.0 --server.port 8501 --server.headless true
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st  # noqa: E402

from invest_agent.agent import InvestAgent  # noqa: E402
from invest_agent.risk_profiler import QUESTIONS  # noqa: E402
from invest_agent.strategy import STRATEGY_MENU  # noqa: E402

st.set_page_config(page_title="Atlas Multi-Asset Advisor", layout="wide")

# Jane Street-style theme (dark, data-dense, tabular figures, gold accent)
try:
    from style import CSS as _THEME_CSS  # noqa: E402
except Exception:  # noqa: BLE001 - fallback if imported as package
    import os as _os
    import importlib.util as _ilu
    _sp = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "style.py")
    _spec = _ilu.spec_from_file_location("atlas_style", _sp)
    _mod = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    _THEME_CSS = _mod.CSS
st.markdown(_THEME_CSS, unsafe_allow_html=True)

# ----------------------------------------------------------------------
# Optional password gate (only enforced when ATLAS_ACCESS_TOKEN is set)
# ----------------------------------------------------------------------
_TOKEN = os.environ.get("ATLAS_ACCESS_TOKEN", "").strip()
if _TOKEN:
    if st.session_state.get("atlas_authed") is not True:
        st.title("Atlas 多元资产投资顾问")
        pwd = st.text_input("访问口令 Access token", type="password")
        if st.button("进入 Enter"):
            if pwd == _TOKEN:
                st.session_state["atlas_authed"] = True
                st.rerun()
            else:
                st.error("口令错误 / wrong token")
        st.stop()

st.markdown(
    """
    <div style="display:flex;align-items:center;gap:.8rem;margin-bottom:.3rem;">
      <svg width="34" height="38" viewBox="0 0 34 38" style="flex:none;">
        <polygon points="17,1 32,9.5 32,28.5 17,37 2,28.5 2,9.5"
                 fill="none" stroke="#d0001d" stroke-width="2.4"/>
        <polygon points="17,10 24.5,14.2 24.5,23.8 17,28 9.5,23.8 9.5,14.2"
                 fill="#d0001d"/>
      </svg>
      <div>
        <div style="font-size:1.9rem;font-weight:700;letter-spacing:-.02em;color:#1a1a1a;line-height:1;">
          ATLAS</div>
        <div style="font-size:.72rem;font-weight:600;letter-spacing:.16em;text-transform:uppercase;color:#6e7278;margin-top:.25rem;">
          Multi-Asset Advisor · Family-Office Allocation</div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.caption("量化生成，仅供研究参考，不构成投资建议 (research only, NOT investment advice)")

# Startup catch-up: if no factor-learning cycle ran recently, spawn a background
# one so the agent keeps learning even without explicit user action.
try:
    from invest_agent.factors.factor_evolution import maybe_autolearn as _autolearn  # noqa: E402
    _autolearn(threshold_hours=24.0)
except Exception:  # noqa: BLE001 - learning must never break the page
    pass

# ----------------------------------------------------------------------
# 全球市场指数看板 (形象工程, 常驻显示, 双源+缓存+降级)
# ----------------------------------------------------------------------
st.subheader("全球市场指数 · Global Market Indices")
_gi_hdr1, _gi_hdr2 = st.columns([5, 1])
with _gi_hdr2:
    _gi_refresh = st.button("刷新指数", key="gi_refresh")
if _gi_refresh or "atlas_indices" not in st.session_state:
    try:
        from invest_agent.global_indices import fetch_global_indices  # noqa: E402
        st.session_state["atlas_indices"] = fetch_global_indices()
    except Exception as _gie:  # noqa: BLE001
        st.session_state["atlas_indices"] = {"source_ok": False,
                                             "note": str(_gie), "regions": {}}
_gi = st.session_state.get("atlas_indices", {})
_gi_hdr1.caption(f"更新于 {_gi.get('updated_at') or '—'} · "
                 f"数据源 {'正常' if _gi.get('source_ok') else '降级'}"
                 + (f" · {_gi['note']}" if _gi.get('note') else ""))

_REGION_FLAG = {"中国内地": "🇨🇳", "亚太": "🌏", "欧洲": "🇪🇺", "美洲": "🌎"}
_ORDER = ["中国内地", "亚太", "欧洲", "美洲"]
_rows = []
for _region in _ORDER:
    for _idx in _gi.get("regions", {}).get(_region, []):
        _chg = _idx.get("chg_pct")
        _rows.append({
            "区域": _REGION_FLAG.get(_region, "") + " " + _region,
            "指数": _idx["name"],
            "现价": f"{_idx['price']:,.2f}" if _idx.get("price") is not None else "—",
            "涨跌%": _chg,
            "状态": _idx.get("status", "—"),
        })
if _rows:
    import pandas as _pd  # noqa: E402
    _df = _pd.DataFrame(_rows)
    _styled = (
        _df.style
        .applymap(lambda v: "color:#16a34a;font-weight:600;"
                  if isinstance(v, (int, float)) and v > 0
                  else ("color:#d0001d;font-weight:600;"
                        if isinstance(v, (int, float)) and v < 0 else ""),
                  subset=["涨跌%"])
        .format({"涨跌%": lambda v: (f"{v:+.2f}" if isinstance(v, (int, float)) else "—")})
        .set_properties(**{"text-align": "right"})
        .hide(axis="index")
    )
    st.dataframe(_styled, use_container_width=True, height=30 + 36 * len(_rows))
else:
    st.info("全球指数数据暂不可用")
st.divider()

# ----------------------------------------------------------------------
# 全球政治经济局势板块 (独立于投资建议, 实时新闻 + 宏观趋势研判)
# ----------------------------------------------------------------------
st.subheader("全球政治经济局势 · Global Situation")
_geo_col_btn, _geo_col_info = st.columns([1, 4])
with _geo_col_btn:
    _geo_refresh = st.button("刷新局势", key="geo_refresh")
if _geo_refresh or "atlas_geo" not in st.session_state:
    with st.spinner("聚合实时新闻并研判全球局势..."):
        try:
            from invest_agent.geopolitics import (assess_global_situation,  # noqa: E402
                                                  fetch_global_news, situation_digest)
            _gpack = fetch_global_news(max_items=40)
            _gsitu = assess_global_situation(_gpack)
            _gsitu["news_sample"] = [it["title"] for it in _gpack["items"][:8]]
            st.session_state["atlas_geo"] = _gsitu
        except Exception as _ge:  # noqa: BLE001
            st.session_state["atlas_geo"] = {"error": str(_ge)}
_g = st.session_state.get("atlas_geo", {})
if _g.get("error"):
    st.warning(f"局势板块暂不可用: {_g['error']}")
else:
    _gc1, _gc2, _gc3 = st.columns(3)
    _gc1.metric("风险偏好", f"{_g['risk_appetite']:+.2f}")
    _gc2.metric("研判", _g["regime"])
    _gc3.metric("新闻样本", _g["n_items"])
    _themes = "、".join(t["theme"] for t in _g.get("themes", [])) or "—"
    st.caption(f"主导议题: {_themes} · 数据源: {', '.join(_g.get('sources_ok', [])) or '无'}")
    with st.expander("关注事件 Watch list"):
        for _w in _g.get("watch_items", []):
            st.text(f"• {_w[:60]}")
    with st.expander("实时新闻流 News feed"):
        for _n in _g.get("news_sample", []):
            st.text(f"• {_n[:70]}")
st.divider()

# ----------------------------------------------------------------------
# 家办式全球资产落位 Global Basing (资产画像问卷 + base 打分)
# ----------------------------------------------------------------------
st.subheader("家办 · 全球资产落位 · Global Basing")
st.caption("根据您的适当性等级与资产画像，列出全球适合的落位/通道(境内/跨境/离岸)并打分，"
           "评估摩擦(资本管制/税/汇兑/准入/合规)。仅供研究参考。")
with st.expander("① 资产画像 Asset Profile", expanded=True):
    from invest_agent.global_base import (ASSET_TYPE_OPTIONS,  # noqa: E402
                                          OVERSEAS_ACCOUNT_OPTIONS)
    _ap_c1, _ap_c2 = st.columns(2)
    with _ap_c1:
        _ap_types = st.multiselect(
            "当前持有的资产类型", [o[1] for o in ASSET_TYPE_OPTIONS],
            default=["现金/存款/货基", "境内公募基金"])
        _ap_overseas_pct = st.slider("现有资产中境外占比 (%)", 0, 100, 0, 5)
    with _ap_c2:
        _ap_accts = st.multiselect(
            "已开立的境外账户", [o[1] for o in OVERSEAS_ACCOUNT_OPTIONS],
            default=["暂无境外账户"])
        _ap_liq = st.selectbox("流动性需求", ["低(长期不动用)", "中", "高(随时可能用)"], index=1)
    _ap_capital = st.number_input("总资产规模 (CNY)", min_value=10_000, value=500_000,
                                  step=50_000)
    _ap_gen = st.button("生成落位建议", key="gen_bases")
if _ap_gen:
    from invest_agent.global_base import AssetProfile, recommend_bases  # noqa: E402
    _type_id = {o[1]: o[0] for o in ASSET_TYPE_OPTIONS}
    _acct_id = {o[1]: o[0] for o in OVERSEAS_ACCOUNT_OPTIONS}
    _liq_map = {"低(长期不动用)": "low", "中": "medium", "高(随时可能用)": "high"}
    _ap = AssetProfile(
        asset_types=[_type_id[t] for t in _ap_types if t in _type_id],
        overseas_pct=float(_ap_overseas_pct),
        overseas_accounts=[_acct_id[a] for a in _ap_accts if a in _acct_id] or ["none"],
        total_capital=float(_ap_capital),
        crypto_held=("加密货币" in _ap_types),
        liquidity_need=_liq_map.get(_ap_liq, "medium"),
    )
    # risk tier: from the last generated plan (session), else C3 default
    _tier = "C3"
    if st.session_state.get("atlas_result"):
        try:
            _tier = st.session_state["atlas_result"]["profile"].tier
        except Exception:  # noqa: BLE001
            pass
    st.session_state["atlas_asset_profile"] = _ap     # reuse in final advice
    st.session_state["atlas_bases"] = {"tier": _tier,
                                       "ranked": recommend_bases(_tier, _ap)}
if st.session_state.get("atlas_bases"):
    _b = st.session_state["atlas_bases"]
    st.markdown(f"**② 全球落位建议（适当性 {_b['tier']}）— 按「适配度×(1−摩擦)」打分**")
    _cat_label = {"onshore": "境内", "crossborder": "跨境通道", "offshore": "离岸"}
    _brows = []
    for i, r in enumerate(_b["ranked"], 1):
        _brows.append({
            "#": i, "Base": r["name_zh"], "类别": _cat_label.get(r["category"], r["category"]),
            "评分": r["score"], "摩擦": r["friction"],
            "门槛": (f"¥{r['min_capital']:,.0f}" if r["min_capital"] else "无"),
            "要点": "; ".join(r["reasons"][:2]) or "综合适配",
        })
    st.dataframe(_brows, hide_index=True, use_container_width=True)
    with st.expander("各 base 详情与适配分解"):
        for r in _b["ranked"]:
            fb = r["fit_breakdown"]
            st.markdown(f"**{r['name_zh']}** ({_cat_label.get(r['category'],'')}) · "
                        f"评分 {r['score']} · 摩擦 {r['friction']}")
            st.caption(f"适配: 资本{fb['capital']} · 资产{fb['asset']} · "
                       f"风险{fb['risk']} · 经验{fb['experience']} · "
                       f"境外{fb.get('overseas','—')} | {r['desc']} {r['notes']}")
    st.caption("原则: 优先低摩擦境内通道打底 → 跨境通道(QDII/港通)拓展 → "
               "离岸(港/新/美)仅补境内无法覆盖之需求; 资金出境务必合规。")
st.divider()

# ----------------------------------------------------------------------
# Sidebar: investor inputs
# ----------------------------------------------------------------------
with st.sidebar:
    st.header("投资者输入 Investor Inputs")
    capital = st.number_input("可投资本金 (CNY)", min_value=10_000, value=300_000, step=10_000)
    free_text = st.text_input("风险态度 / 目标补充",
                              value="能接受短期波动，但不想亏掉本金")
    use_contrib = st.checkbox("自定义每月定投额", value=False)
    monthly_contrib = st.number_input(
        "每月定投 (CNY)", min_value=0, value=3000, step=500,
        disabled=not use_contrib)
    provider = st.radio(
        "数据源 Data source",
        ["synthetic", "merged"],
        help="synthetic=离线合成市场；merged=akshare真实行情+合成补齐",
    )
    strategy_choice = st.selectbox(
        "策略 Strategy",
        ["auto"] + [s.id for s in STRATEGY_MENU],
        format_func=lambda x: "自动选择 (按画像匹配)" if x == "auto" else next(
            f"{s.name_zh} ({s.cadence_label})" for s in STRATEGY_MENU if s.id == x),
    )
    with st.expander("主观择时 Market Timing (可选)"):
        st.caption("表达你对各类资产的多空观点：-1=强烈看空, 0=中性, +1=强烈看多。"
                   "观点将注入预期收益，仅影响今日配置，不改变历史回测。")
        use_timing = st.checkbox("启用主观择时", value=False)
        _t_sliders = {}
        for _cls, _lbl in [("equity_cn", "A股"), ("equity_global", "海外股票"),
                           ("crypto", "加密货币"), ("commodity", "商品/黄金"),
                           ("fixed_income", "债券"), ("hybrid", "固收+(二级债基)")]:
            _t_sliders[_cls] = st.slider(_lbl, -1.0, 1.0, 0.0, 0.25,
                                         disabled=not use_timing, key=f"t_{_cls}")
        _timing_free = st.text_input("或用一句话描述(优先)", "",
                                     placeholder="例: 短期看空A股，看多加密",
                                     disabled=not use_timing)
    with st.expander("策略菜单 Strategy menu"):
        st.dataframe(
            [{"策略": f"{s.name_zh}", "哲学": s.philosophy, "目标": s.objective,
              "调仓": s.cadence_label, "适用": f"{s.min_tier}-{s.max_tier}"}
             for s in STRATEGY_MENU],
            hide_index=True,
        )
    with st.expander("数据源说明 About data sources"):
        st.markdown(
            "**synthetic（离线）**: 固定种子模拟的多资产世界，内置熊市/繁荣/"
            "币圈闪崩情景，完全可复现、无需网络，适合研究与演示。\n\n"
            "**merged（真实+补齐）**: 通过 akshare 拉取 A股ETF 与公募基金的"
            "真实月度净值（首次联网，之后缓存在 data_cache/）；加密货币与期货"
            "列由合成数据自动补齐。"
        )

# ----------------------------------------------------------------------
# Questionnaire: ALWAYS rendered, before the generate button
# ----------------------------------------------------------------------
st.subheader("① 适当性问卷 Suitability Questionnaire")
answers = {}
cols = st.columns(3)
for i, (_w, q_zh, _q_en, opts) in enumerate(QUESTIONS):
    with cols[i % 3]:
        answers[i] = st.selectbox(
            f"Q{i}. {q_zh}",
            range(len(opts)),
            index=2,
            format_func=lambda j, o=opts: o[j][0],
            key=f"atlas_q{i}",
        )

# ----------------------------------------------------------------------
# Generate
# ----------------------------------------------------------------------
st.subheader("② 生成方案 Generate")
c_btn, c_note = st.columns([1, 3])
with c_btn:
    run = st.button("生成方案 Generate Plan", type="primary", use_container_width=True)
with c_note:
    st.caption("修改上方任意输入后再次点击即可重新生成；结果会保留到下一次生成。")

if run:
    agent = InvestAgent(provider_name=provider, output_dir="examples/demo_outputs")
    # assemble timing view: free text wins, else slider dict
    _timing_arg = None
    if use_timing:
        if _timing_free.strip():
            _timing_arg = _timing_free.strip()
        else:
            _nz = {c: v for c, v in _t_sliders.items() if abs(v) > 1e-9}
            _timing_arg = _nz or None
    try:
        with st.spinner("量化计算中 (策略菜单回测 + 组合优化 + 回测)..."):
            res = agent.offline_plan(
                answers,
                capital=float(capital),
                free_text=free_text or "",
                monthly_contrib=float(monthly_contrib) if use_contrib else None,
                strategy_id=None if strategy_choice == "auto" else strategy_choice,
                timing=_timing_arg,
            )
        st.session_state["atlas_result"] = res
    except Exception as e:  # noqa: BLE001 - friendly error instead of traceback
        st.error(f"生成失败: {type(e).__name__}: {e}\n请调整问卷/策略选择后重试，"
                 f"或在侧边栏改用 auto 策略。")

# ----------------------------------------------------------------------
# Results (persisted across re-runs)
# ----------------------------------------------------------------------
res = st.session_state.get("atlas_result")
if res is None:
    st.info("请先完成问卷并点击「生成方案」。")
    st.stop()

plan, profile = res["plan"], res["profile"]
st.subheader(f"③ 结果: 适当性 {profile.tier} {profile.tier_info['label_zh']} "
             f"(评分 {profile.score:.0f}) · 客群 {plan.segment} · 数据源 {provider}")

k1, k2, k3, k4 = st.columns(4)
k1.metric("预期年化收益", f"{plan.expected['ann_return']:.1%}")
k2.metric("年化波动", f"{plan.expected['ann_vol']:.1%}")
k3.metric("夏普 (事前)", f"{plan.expected['sharpe_hint']:.2f}")
k4.metric("回测最大回撤", f"{plan.backtest['max_drawdown']:.1%}")

_st = plan.strategy
st.success(f"所选策略: **{_st.name_zh} ({_st.name_en})** · 目标 `{_st.objective}` · "
           f"调仓 `{_st.cadence_label}`")
st.caption(_st.philosophy)
if plan.timing:
    _tl = "、".join(f"{c} {'看多' if v>0 else '看空'}{abs(v):.2f}" for c, v in plan.timing.items())
    st.info(f"已注入主观择时: {_tl}（仅影响今日配置，不改变历史回测）")

# ---- ④ 最终综合建议 (量化×大类×地缘×落位 有机融合) ----
st.subheader("④ 最终综合建议 Final Integrated Advice")
st.caption("把量化配置 × 大类观点 × 全球政经局势 × 全球base落位 有机融合，"
           "形成符合发展趋势、利益最大化的最终建议（含全球落位与执行清单）。")
_fa_col1, _fa_col2 = st.columns([1, 3])
with _fa_col1:
    _gen_fa = st.button("生成最终建议", key="gen_final_advice", type="primary")
if _gen_fa:
    from invest_agent.final_advice import build_final_advice  # noqa: E402
    from invest_agent.global_base import AssetProfile  # noqa: E402
    # reuse asset profile from the Global Basing section if provided
    _ap_fa = AssetProfile(asset_types=["cash_deposit", "cn_fund"],
                          total_capital=float(capital))
    if st.session_state.get("atlas_asset_profile"):
        _ap_fa = st.session_state["atlas_asset_profile"]
    with st.spinner("融合中: 大类观点 + 全球局势 + base落位 ..."):
        try:
            _fa = build_final_advice(plan, profile, _ap_fa, provider_name=provider)
            st.session_state["atlas_final_advice"] = _fa
        except Exception as _fae:  # noqa: BLE001
            st.session_state["atlas_final_advice"] = {"error": str(_fae)}
_fa = st.session_state.get("atlas_final_advice")
if _fa and not _fa.get("error"):
    st.markdown(f"**研判主线**: {_fa['thesis']}")
    _ov = _fa.get("overlays", {})
    st.caption(f"全球局势: {_ov.get('geo_regime','—')} (风险偏好 {_ov.get('geo_appetite',0):+.2f})"
               f" · 议题: {_ov.get('geo_themes','—')}")
    _fa_rows = []
    _bm = _fa.get("base_map", {})
    for _c, _w in _fa.get("final_class_weights", {}).items():
        _b = _bm.get(_c, {})
        _fa_rows.append({"资产类别": _c, "最终权重": f"{_w:.1%}",
                         "落位base": _b.get("base", "—"), "base评分": _b.get("score", "—"),
                         "摩擦": _b.get("friction", "—")})
    st.dataframe(_fa_rows, hide_index=True, use_container_width=True)
    _fa_council = _fa.get("council")
    if _fa_council:
        st.markdown(f"**🧑‍💼 智囊团投票**（约30选5，相关度加权，已按此微调上方配置）："
                    f"共识 **{_fa_council.get('consensus','—')}**")
        _net = _fa_council.get("net_tilt", {})
        if _net:
            _nt = "、".join(f"{c} {v:+.2f}" for c, v in
                           sorted(_net.items(), key=lambda kv: -kv[1]) if abs(v) > 0.05)
            st.caption(f"净仓位信号: {_nt}")
        _mem = "、".join(f"{m['name_zh']}({m['stance']})" for m in _fa_council.get("members", []))
        st.caption(f"成员: {_mem}")
    with st.expander("执行清单 + 完整叙述"):
        for _i, _a in enumerate(_fa.get("actions", []), 1):
            st.text(f"{_i}. {_a}")
        st.write(_fa.get("digest", ""))
elif _fa and _fa.get("error"):
    st.warning(f"最终建议暂不可用: {_fa['error']}")

# ---- ⑤ 金融分析师智囊团 (约30选5, 方向匹配) ----
st.subheader("⑤ 金融分析师智囊团 Analyst Council")
st.caption("从约30位投资大师/流派(西蒙斯·巴菲特·达利欧·塔勒布·伍德…)中，按当前"
           "策略/资产/局势/适当性等级选出方向最匹配的5位，各自给出观点。仅供参考。")
_c_col1, _c_col2 = st.columns([1, 3])
with _c_col1:
    _gen_council = st.button("召集智囊团", key="gen_council")
if _gen_council:
    with st.spinner("匹配分析师并生成观点(含局势+大类观点)..."):
        try:
            from invest_agent.tools import AdvisorContext, build_tools  # noqa: E402
            _actx = AdvisorContext(provider_name=provider)
            _actx.plan = plan
            _actx.profile = profile
            _tools = {t.name: t for t in build_tools(_actx)}
            st.session_state["atlas_council"] = _tools["get_analyst_council"].handler({"n": 5})
        except Exception as _ce:  # noqa: BLE001
            st.session_state["atlas_council"] = {"error": str(_ce)}
_cc = st.session_state.get("atlas_council")
if _cc and not _cc.get("error"):
    st.success(f"共识研判: **{_cc['consensus']}** · 候选池 {_cc['n_analysts_total']} 位"
               + (f" · 异议: {'、'.join(_cc['dissent'])}" if _cc.get("dissent") else ""))
    st.caption(_cc["summary"])
    for _v in _cc["council"]:
        with st.container():
            st.markdown(f"**{_v['name_zh']} · {_v['name_en']}** — {_v['school']} "
                        f"｜相关度 {_v['relevance']:.2f}｜{_v['stance']}")
            st.markdown(f"&nbsp;&nbsp;🗣 {_v['advice']}")
            st.markdown(f"&nbsp;&nbsp;📊 仓位倾向: `{_v['tilt_text']}` ｜ 原则: “{_v['signature']}”")
    st.caption("_智囊团为不同投资流派视角的模拟观点，仅供多元参考，不构成投资建议。_")
elif _cc and _cc.get("error"):
    st.warning(f"智囊团暂不可用: {_cc['error']}")

if plan.menu:
    with st.expander("策略菜单对比 Strategy menu (各自回测)"):
        _rows = []
        for r in plan.menu:
            _rows.append({
                "策略": ("✅ " if r["id"] == _st.id else "") + r["name_zh"],
                "目标": r["objective"], "调仓": r["cadence_label"],
                "年化": f"{r['ann_return']:.1%}", "波动": f"{r['ann_vol']:.1%}",
                "夏普": f"{r['sharpe']:.2f}", "最大回撤": f"{r['max_drawdown']:.1%}",
            })
        st.dataframe(_rows, hide_index=True, use_container_width=True)

with st.expander("市场情报 Market Intel (最新财经要闻)"):
    if st.button("拉取最新情报 Fetch latest"):
        from invest_agent.intel import fetch_market_intel, summarize_for_prompt  # noqa: E402
        with st.spinner("抓取最新新闻/快讯..."):
            _pack = fetch_market_intel(max_items=20)
        st.session_state["atlas_intel"] = _pack
    _pack = st.session_state.get("atlas_intel")
    if _pack:
        st.caption(f"生成时间 {_pack['generated_at']} · 状态 {_pack['source_status']} · "
                   f"话题: {', '.join(_pack['topics_covered'])}")
        for it in _pack["items"]:
            st.text(f"[{','.join(it['topics'][:2])}] {it['title']}")

c1, c2 = st.columns(2)
with c1:
    st.image(res["charts"]["allocation"])
with c2:
    st.image(res["charts"]["frontier"])
c3, c4 = st.columns(2)
with c3:
    st.image(res["charts"]["equity"])
with c4:
    st.image(res["charts"]["projection"])

st.subheader("配置明细 Allocation")
name_of = {a.id: a.name_zh for a in plan.assets}
st.dataframe(
    [
        {"资产": name_of[k], "权重": f"{v:.2%}",
         "预期年化": f"{plan.mu_ann[k]:.1%}", "年化波动": f"{plan.vol_ann[k]:.1%}"}
        for k, v in sorted(plan.weights.items(), key=lambda kv: -kv[1])
    ],
    hide_index=True, use_container_width=True,
)

st.subheader("完整资产池与准入 Full Universe & Access")
st.caption("权重为 0 不代表不存在：下表列出全部可投候选及其在当前画像下的准入上限。"
           "加密货币需 C3 及以上，期货仅对富裕/高净值客群且满足门槛开放。")
from invest_agent.config import client_segments  # noqa: E402
from invest_agent.data.universe import build_universe  # noqa: E402
from invest_agent.personas import accessible_classes  # noqa: E402

_caps = accessible_classes(profile)
_seg = client_segments()[plan.segment]
_pool_rows = []
for a in build_universe():
    cap = _caps.get(a.asset_class, 0.0)
    if a.asset_class == "futures" and not _seg.get("allow_futures", False):
        status = "不对该客群开放"
    elif a.asset_class == "futures" and cap <= 0:
        status = "适当性不足"
    elif cap <= 0:
        status = "当前等级不可投"
    else:
        status = f"上限 {cap:.0%}"
    wgt = plan.weights.get(a.id)
    _pool_rows.append({
        "资产": f"{a.name_zh} ({a.name_en})",
        "类别": a.asset_class,
        "准入": status,
        "当前权重": f"{wgt:.2%}" if wgt else "—",
    })
st.dataframe(_pool_rows, hide_index=True, use_container_width=True)

st.subheader("大类资产配置建议 Macro Allocation Advice")
st.caption("结合真实动量、估值分位、新闻情绪与宏观研判的大类观点 + 权益内部风格/行业细分。"
           "需与个人适当性结合，不构成投资建议。")
try:
    from invest_agent.macro_advice import generate_macro_advice  # noqa: E402
    with st.spinner("生成大类配置建议(动量+估值+新闻+宏观)..."):
        _madv = generate_macro_advice(provider_name=provider, months=60)
    _stance_icon = {"超配": "🟢", "标配": "⚪", "低配": "🔴"}
    _mrows = []
    for a in _madv["advice"]:
        _mrows.append({
            "观点": _stance_icon.get(a["stance"], "") + " " + a["stance"],
            "大类": a["name"],
            "评分": f"{a['score']:+.2f}",
            "依据": "; ".join(a["reasons"]),
        })
    st.dataframe(_mrows, hide_index=True, use_container_width=True)
    _mc1, _mc2 = st.columns(2)
    with _mc1:
        st.markdown(f"**行业/风格细分**: {_madv['sector_tilt']['style']}")
        for _n in _madv["sector_tilt"]["notes"]:
            st.caption(f"• {_n}")
    with _mc2:
        _ctx = _madv["macro_context"]
        st.markdown("**宏观背景**")
        st.caption(f"• 中国制造业: {_ctx.get('china_pmi', '—')}")
        st.caption(f"• A股估值分位: {_ctx.get('equity_pe_percentile', '—')}%")
        st.caption(f"• 全球局势: {_ctx.get('global_regime', '—')}")
    with st.expander("综合研判叙述 Narrative"):
        st.write(_madv["narrative"])
except Exception as _me:  # noqa: E401
    st.warning(f"大类配置建议暂不可用: {_me}")

st.subheader("因子透镜筛选 Factor-Lens Screening")
st.caption("收益代理: 动量(+)/短期反转(−)/低波动(−)/抗回撤(−)；"
           "在线真因子(免费接口): 指数PE历史分位(−)/成交额流动性(+)/主力净流入(+)。"
           "无数据的资产自动降权，不编造。")
try:
    from invest_agent.factors import default_catalog, enrich_universe, screen_universe  # noqa: E402
    _prov = InvestAgent(provider_name=provider).ctx.get_provider()
    _uni = build_universe()
    _ids = [a.id for a in _uni]
    _R = _prov.get_monthly_returns(_ids, 96)
    with st.spinner("拉取在线因子数据(换手/资金流/PE分位, 有缓存)..."):
        _enrich = enrich_universe(_uni)
    _screen = screen_universe(_R[_ids], _uni, default_catalog(), enrichment=_enrich)
    _rows = []
    for i, r in enumerate(_screen["ranked"]):
        _rows.append({
            "排名": i + 1, "资产": r["name_zh"], "类别": r["class"],
            "因子分": f"{r['score']:+.2f}",
            "动量": f"{r['momentum']:+.1%}",
            "年化波动": f"{r['low_vol']:.1%}",
            "PE分位(10y)": f"{r['pe_percentile']:.0f}%" if "pe_percentile" in r else "—",
            "主力净流入": f"{r['money_flow']:+.2f}%" if "money_flow" in r else "—",
            "在线因子数": r["n_live_factors"],
        })
    st.dataframe(_rows, hide_index=True, use_container_width=True)
    st.caption(f"在线真因子已启用: {'是' if _screen['live_data_used'] else '否(离线/接口不可用, 已回退收益代理)'}")
    with st.expander("仍不可计算的因子族(需日频个股财务/分析师数据)"):
        st.write("、".join(_screen["skipped_families"]) or "无")
except Exception as _e:  # noqa: BLE001
    st.warning(f"因子筛选不可用: {_e}")

with st.expander("因子库 Factor Knowledge Base"):
    _cat = default_catalog()
    if _cat.factors:
        st.caption(f"共 {len(_cat.factors)} 个因子 · {len(_cat.categories)} 个类别 · "
                   f"{_cat.n_records} 条记录")
        st.dataframe(_cat.category_summary()[:30], hide_index=True)
    else:
        st.info("因子库未加载（请在 config/agent.yaml 配置 factors.data_dir）")

with st.expander("因子自进化 Factor Self-Evolution (自主学习)", expanded=False):
    from invest_agent.factors.factor_evolution import (  # noqa: E402
        hours_since_last_run, maybe_autolearn, read_state)
    from invest_agent.factors.factor_store import stats as _fstats  # noqa: E402
    _fs = _fstats()
    _st_state = read_state()
    _gap = hours_since_last_run()
    st.caption(f"项目因子库: 共 {_fs['total']} 个因子 · 来源 {_fs['by_source']} · "
               f"已测IC {_fs['with_ic']} 个")
    st.caption(f"上次学习: {_st_state.get('last_run') or '从未'} · "
               f"累计 {_st_state.get('cycles', 0)} 轮 · "
               f"距今 {('%.1f 小时' % _gap) if _gap is not None else '—'}")
    st.caption("自主学习: 后台守护进程定期学习(见 scripts/evolution_daemon.py)；"
               "且每次打开 Atlas 若超过阈值未学习会自动后台补一轮。")
    _ac1, _ac2 = st.columns(2)
    with _ac1:
        if st.button("立即学习一轮 (前台)", key="evolve_btn"):
            with st.spinner("学习中: 研报因子采集 + 实证IC测量..."):
                try:
                    from invest_agent.factors.factor_evolution import run_cycle  # noqa: E402
                    st.session_state["atlas_evolve"] = run_cycle(provider_name=provider,
                                                                 months=96)
                except Exception as _ee:  # noqa: BLE001
                    st.session_state["atlas_evolve"] = {"error": str(_ee)}
    with _ac2:
        if st.button("触发后台学习", key="evolve_bg_btn"):
            _tr = maybe_autolearn(threshold_hours=-1, provider_name=provider)
            st.toast("已触发后台学习" if _tr.get("triggered") else "触发失败")
    _ev = st.session_state.get("atlas_evolve")
    if _ev:
        if _ev.get("error"):
            st.warning(f"学习失败: {_ev['error']}")
        else:
            st.success(f"本轮: {_ev['factors_before']} → {_ev['factors_after']} 个因子 "
                       f"(知识库 {_ev['knowledge_base_imported']}, "
                       f"研报 {_ev['broker_report_factors']}, "
                       f"PDF深解析 {_ev.get('pdf_factors_registered', 0)}, "
                       f"在线 {_ev['collected_online']})")
            if _ev.get("learned_empirical"):
                st.dataframe([{"因子": f["name"], "IC": f.get("ic")}
                              for f in _ev["learned_empirical"]], hide_index=True)
                st.caption("IC(信息系数)=因子值与未来收益的秩相关；|IC|越大预测力越强。")

with st.expander("完整报告 Full report"):
    import base64 as _b64
    import os as _os
    import re as _re

    def _embed(m):
        alt, fname = m.group(1), m.group(2)
        # resolve against the rendered chart paths
        path = next((p for p in res["charts"].values()
                     if p and _os.path.basename(p) == fname), None)
        if path and _os.path.exists(path):
            with open(path, "rb") as fh:
                b64 = _b64.b64encode(fh.read()).decode()
            return f"![{alt}](data:image/png;base64,{b64})"
        return ""  # drop unresolvable refs

    # rebuild the report to include fused final advice + analyst council
    _fa_rep = st.session_state.get("atlas_final_advice")
    _cc_rep = st.session_state.get("atlas_council")
    _cc_rep = _cc_rep if (_cc_rep and not _cc_rep.get("error")) else None
    if (_fa_rep and not _fa_rep.get("error")) or _cc_rep:
        from invest_agent.report import build_report as _br  # noqa: E402
        _rep_src = _br(plan, res["charts"],
                       final_advice=(_fa_rep if _fa_rep and not _fa_rep.get("error") else None),
                       analyst_council=_cc_rep)
    else:
        _rep_src = res["report"]
    _report_text = _re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", _embed, _rep_src)
    st.markdown(_report_text)
