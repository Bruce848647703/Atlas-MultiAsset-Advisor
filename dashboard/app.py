"""Streamlit dashboard (visual layer).

Install:  pip install streamlit
Run:      streamlit run dashboard/app.py

Layout: questionnaire and inputs are ALWAYS rendered before the generate
button, so every answer can be customized first; results persist in
session state across re-runs.

Optional access gate for remote hosting:
    ATLAS_ACCESS_TOKEN='<your-token>' streamlit run dashboard/app.py \
        --server.address 0.0.0.0 --server.port 8501 --server.headless true
"""

import hmac
import json
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st  # noqa: E402

from i18n import (  # noqa: E402
    LANG_LABELS, LANGS, account_label, analyst_name, analyst_name_by_id,
    analyst_name_from_zh, asset_name, asset_type_label, base_category_label,
    cadence_label, class_label, divergence_label, index_label, liquidity_label,
    note_label, objective_label, option_text, pick, question_text, regime_label, region_label,
    school_label, segment_label, source_label, stance_label, strategy_name,
    strategy_philosophy, t, theme_label, tier_label, to_hant,
)
from invest_agent.agent import InvestAgent  # noqa: E402
from invest_agent.factors import custom as custom_factors  # noqa: E402
from invest_agent.integrations import factor_forge as forge_bridge  # noqa: E402
from invest_agent.integrations import kairos as kairos_bridge  # noqa: E402
from invest_agent.integrations import kairos_strategies as kairos_lab  # noqa: E402
from invest_agent.risk_profiler import QUESTIONS, profile_from_answers  # noqa: E402
from invest_agent.strategy import STRATEGY_MENU, menu_for_tier  # noqa: E402

st.set_page_config(page_title="Atlas · Multi-Asset Advisor", layout="wide")

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
_lang0 = st.session_state.get("atlas_lang", "zh")
if _TOKEN:
    if st.session_state.get("atlas_authed") is not True:
        st.title(t("gate.title", _lang0))
        pwd = st.text_input(t("gate.token", _lang0), type="password")
        if st.button(t("gate.enter", _lang0)):
            if hmac.compare_digest(pwd, _TOKEN):
                st.session_state["atlas_authed"] = True
                st.rerun()
            else:
                st.error(t("gate.wrong", _lang0))
        st.stop()

# Language switch: top-right of the page, "Language: [selector]".
_top_l, _top_r = st.columns([7, 3], vertical_alignment="bottom")
with _top_r:
    _lang_label_col, _lang_select_col = st.columns([1, 2], vertical_alignment="bottom")
    with _lang_label_col:
        st.markdown(
            "<div style='text-align:right;font-weight:600;padding-bottom:.35rem;'>Language:</div>",
            unsafe_allow_html=True,
        )
    with _lang_select_col:
        lang = st.selectbox(
            "Language",
            LANGS,
            index=LANGS.index(_lang0),
            format_func=lambda x: LANG_LABELS[x],
            key="atlas_lang",
            label_visibility="collapsed",
        )

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
          {tagline}</div>
      </div>
    </div>
    """.replace("{tagline}", t("app.tagline", lang)),
    unsafe_allow_html=True,
)
st.caption(t("app.disclaimer", lang))

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
st.subheader(t("indices.title", lang))
_gi_hdr1, _gi_hdr2 = st.columns([5, 1])
with _gi_hdr2:
    _gi_refresh = st.button(t("indices.refresh", lang), key="gi_refresh")
if _gi_refresh or "atlas_indices" not in st.session_state:
    try:
        from invest_agent.global_indices import fetch_global_indices  # noqa: E402
        st.session_state["atlas_indices"] = fetch_global_indices()
    except Exception as _gie:  # noqa: BLE001
        st.session_state["atlas_indices"] = {"source_ok": False,
                                             "note": str(_gie), "regions": {}}
_gi = st.session_state.get("atlas_indices", {})
_gi_src = t("indices.source_ok" if _gi.get("source_ok") else "indices.source_degraded", lang)
_gi_hdr1.caption(t("indices.updated", lang, ts=_gi.get("updated_at") or "—")
                 + " · " + _gi_src
                 + (f" · {note_label(_gi['note'], lang)}" if _gi.get("note") else ""))

_REGION_FLAG = {"中国内地": "🇨🇳", "亚太": "🌏", "欧洲": "🇪🇺", "美洲": "🌎"}
_ORDER = ["中国内地", "亚太", "欧洲", "美洲"]
_chg_col = t("indices.change", lang)
_rows = []
for _region in _ORDER:
    for _idx in _gi.get("regions", {}).get(_region, []):
        _chg = _idx.get("chg_pct")
        _st_status = _idx.get("status", "")
        _rows.append({
            t("indices.region", lang): _REGION_FLAG.get(_region, "") + " " + region_label(_region, lang),
            t("indices.index", lang): index_label(_idx["name"], lang),
            t("indices.price", lang): f"{_idx['price']:,.2f}" if _idx.get("price") is not None else "—",
            _chg_col: _chg,
            t("indices.status", lang): t("indices.trading" if _st_status == "交易中" else "indices.closed", lang)
            if _st_status else "—",
        })
if _rows:
    import pandas as _pd  # noqa: E402
    _df = _pd.DataFrame(_rows)
    # Styler.map replaced applymap in pandas 2.1; keep a shim for older versions.
    _style = _df.style
    _map = getattr(_style, "map", None) or getattr(_style, "applymap")
    _styled = (
        _map(lambda v: "color:#16a34a;font-weight:600;"
             if isinstance(v, (int, float)) and v > 0
             else ("color:#d0001d;font-weight:600;"
                   if isinstance(v, (int, float)) and v < 0 else ""),
             subset=[_chg_col])
        .format({_chg_col: lambda v: (f"{v:+.2f}" if isinstance(v, (int, float)) else "—")})
        .set_properties(**{"text-align": "right"})
        .hide(axis="index")
    )
    st.dataframe(_styled, use_container_width=True, height=30 + 36 * len(_rows))
else:
    st.info(t("indices.unavailable", lang))
st.divider()

# ----------------------------------------------------------------------
# 全球政治经济局势板块 (独立于投资建议, 实时新闻 + 宏观趋势研判)
# ----------------------------------------------------------------------
st.subheader(t("geo.title", lang))
_geo_col_btn, _geo_col_info = st.columns([1, 4])
with _geo_col_btn:
    _geo_refresh = st.button(t("geo.refresh", lang), key="geo_refresh")
if _geo_refresh or "atlas_geo" not in st.session_state:
    with st.spinner(t("geo.spinner", lang)):
        try:
            from invest_agent.geopolitics import (assess_global_situation,  # noqa: E402
                                                  fetch_global_news)
            _gpack = fetch_global_news(max_items=40)
            _gsitu = assess_global_situation(_gpack)
            _gsitu["news_sample"] = [it["title"] for it in _gpack["items"][:8]]
            st.session_state["atlas_geo"] = _gsitu
        except Exception as _ge:  # noqa: BLE001
            st.session_state["atlas_geo"] = {"error": str(_ge)}
_g = st.session_state.get("atlas_geo", {})
_ext = lambda s: to_hant(str(s)) if lang == "zh-Hant" else str(s)  # noqa: E731
if _g.get("error"):
    st.warning(t("geo.error", lang, err=_g["error"]))
else:
    _gc1, _gc2, _gc3 = st.columns(3)
    _gc1.metric(t("geo.appetite", lang), f"{_g['risk_appetite']:+.2f}")
    _gc2.metric(t("geo.regime", lang), regime_label(_g["regime"], lang))
    _gc3.metric(t("geo.samples", lang), _g["n_items"])
    _sep = ", " if lang == "en" else "、"
    _themes = _sep.join(theme_label(x["theme"], lang) for x in _g.get("themes", [])) or "—"
    _sources = _sep.join(source_label(x, lang) for x in _g.get("sources_ok", [])) \
        or t("geo.none", lang)
    st.caption(t("geo.themes", lang, themes=_themes) + " · " + t("geo.sources", lang, sources=_sources))
    with st.expander(t("geo.watch", lang)):
        for _w in _g.get("watch_items", []):
            st.text(f"• {_ext(_w)[:60]}")
    with st.expander(t("geo.feed", lang)):
        if lang == "en":
            st.caption(t("intel.source_language", lang))
        for _n in _g.get("news_sample", []):
            st.text(f"• {_ext(_n)[:70]}")
st.divider()

# ----------------------------------------------------------------------
# 家办式全球资产落位 Global Basing (资产画像问卷 + base 打分)
# ----------------------------------------------------------------------
st.subheader(t("base.title", lang))
st.caption(t("base.intro", lang))
with st.expander(t("base.profile", lang), expanded=True):
    from invest_agent.global_base import (ASSET_TYPE_OPTIONS,  # noqa: E402
                                          OVERSEAS_ACCOUNT_OPTIONS)
    _ap_type_labels = {o[0]: asset_type_label(o[0], lang) for o in ASSET_TYPE_OPTIONS}
    _ap_acct_labels = {o[0]: account_label(o[0], lang) for o in OVERSEAS_ACCOUNT_OPTIONS}
    # Widget values are stable IDs (not translated labels), so switching the
    # page language never invalidates the current selection.
    _ap_c1, _ap_c2 = st.columns(2)
    _saved_types = [x for x in st.session_state.get(
        "ap_types_persist", ["cash_deposit", "cn_fund"]) if x in _ap_type_labels]
    _saved_accts = [x for x in st.session_state.get(
        "ap_accts_persist", ["none"]) if x in _ap_acct_labels]
    _saved_liq = st.session_state.get("ap_liq_persist", "medium")
    if _saved_liq not in ("low", "medium", "high"):
        _saved_liq = "medium"
    with _ap_c1:
        _ap_types = st.multiselect(
            t("base.holdings", lang), list(_ap_type_labels),
            default=_saved_types,
            format_func=lambda x: _ap_type_labels.get(x, x),
            key="ap_types")
        _ap_overseas_pct = st.slider(
            t("base.overseas_pct", lang), 0, 100,
            int(st.session_state.get("ap_overseas_pct_persist", 0)), 5,
            key="ap_overseas_pct")
    with _ap_c2:
        _ap_accts = st.multiselect(
            t("base.accounts", lang), list(_ap_acct_labels),
            default=_saved_accts, format_func=lambda x: _ap_acct_labels.get(x, x),
            key="ap_accts")
        _ap_liq = st.selectbox(
            t("base.liquidity", lang), ["low", "medium", "high"],
            index=["low", "medium", "high"].index(_saved_liq),
            format_func=lambda x: liquidity_label(x, lang), key="ap_liq")
    _ap_capital = st.number_input(
        t("base.capital", lang), min_value=10_000,
        value=int(st.session_state.get("ap_capital_persist", 500_000)),
        step=50_000, key="ap_capital")
    st.session_state["ap_types_persist"] = list(_ap_types)
    st.session_state["ap_accts_persist"] = list(_ap_accts)
    st.session_state["ap_liq_persist"] = _ap_liq
    st.session_state["ap_overseas_pct_persist"] = int(_ap_overseas_pct)
    st.session_state["ap_capital_persist"] = _ap_capital
    _ap_gen = st.button(t("base.generate", lang), key="gen_bases")
if _ap_gen:
    from invest_agent.global_base import AssetProfile, recommend_bases  # noqa: E402
    _ap_type_ids = [x for x in _ap_types if x in _ap_type_labels]
    _ap = AssetProfile(
        asset_types=_ap_type_ids,
        overseas_pct=float(_ap_overseas_pct),
        overseas_accounts=[a for a in _ap_accts if a in _ap_acct_labels] or ["none"],
        total_capital=float(_ap_capital),
        crypto_held=("crypto" in _ap_type_ids),
        liquidity_need=_ap_liq,
    )
    # Risk tier: follow the current questionnaire answers, not a stale plan.
    _tier = "C3"
    try:
        _ans_now = {
            i: st.session_state.get(
                f"atlas_q{i}",
                st.session_state.get("atlas_answers_persist", {}).get(i, 2))
            for i in range(len(QUESTIONS))
        }
        _tier = profile_from_answers(
            _ans_now,
            capital=float(st.session_state.get("capital_persist", 300_000)),
            free_text=st.session_state.get("free_text_persist", ""),
        ).tier
    except Exception:  # noqa: BLE001
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
    st.markdown(t("base.result_title", lang, tier=_b["tier"]))
    _brows = []
    for i, r in enumerate(_b["ranked"], 1):
        _b_reasons = ("; ".join(r["reasons"][:2]) or t("base.fallback_reason", lang)) \
            if lang != "en" else t("base.fallback_reason", lang)
        if lang == "zh-Hant":
            _b_reasons = to_hant(_b_reasons)
        _brows.append({
            "#": i,
            t("base.col_name", lang): r["name_en"] if lang == "en" else
            pick(r["name_zh"], r["name_en"], lang),
            t("base.col_category", lang): base_category_label(r["category"], lang),
            t("base.col_score", lang): r["score"], t("base.col_friction", lang): r["friction"],
            t("base.col_min", lang): (f"¥{r['min_capital']:,.0f}" if r["min_capital"]
                                      else t("base.none", lang)),
            t("base.col_highlights", lang): _b_reasons,
        })
    st.dataframe(_brows, hide_index=True, use_container_width=True)
    with st.expander(t("base.details", lang)):
        for r in _b["ranked"]:
            fb = r["fit_breakdown"]
            _bname = r["name_en"] if lang == "en" else pick(r["name_zh"], r["name_en"], lang)
            st.markdown(f"**{_bname}** ({base_category_label(r['category'], lang)}) · "
                        f"{t('base.col_score', lang)} {r['score']} · "
                        f"{t('base.col_friction', lang)} {r['friction']}")
            _fit = (f"Fit: capital {fb['capital']} · assets {fb['asset']} · "
                    f"risk {fb['risk']} · experience {fb['experience']} · "
                    f"overseas {fb.get('overseas','—')}") if lang == "en" else \
                (f"适配: 资本{fb['capital']} · 资产{fb['asset']} · "
                 f"风险{fb['risk']} · 经验{fb['experience']} · "
                 f"境外{fb.get('overseas','—')}")
            if lang == "zh-Hant":
                _fit = to_hant(_fit)
            _desc = "" if lang == "en" else to_hant(f"{r['desc']} {r['notes']}") \
                if lang == "zh-Hant" else f"{r['desc']} {r['notes']}"
            st.caption(_fit + (f" | {_desc}" if _desc else ""))
    st.caption(t("base.principle", lang))
st.divider()

# ----------------------------------------------------------------------
# Sidebar: investor inputs
# ----------------------------------------------------------------------
with st.sidebar:
    st.header(t("side.inputs", lang))
    # Shadow state: Streamlit resets a keyed widget when its label changes
    # (e.g. switching the page language). Persisting the value and feeding it
    # back as the default/index keeps the user's choices stable.
    capital = st.number_input(
        t("side.capital", lang), min_value=10_000,
        value=int(st.session_state.get("capital_persist", 300_000)),
        step=10_000, key="capital")
    st.session_state["capital_persist"] = capital
    free_text = st.text_input(
        t("side.free_text", lang),
        value=st.session_state.get(
            "free_text_persist",
            pick("能接受短期波动，但不想亏掉本金",
                 "Can tolerate short-term swings, but not losing principal", lang)),
        key="free_text")
    st.session_state["free_text_persist"] = free_text
    use_contrib = st.checkbox(
        t("side.custom_contrib", lang),
        value=bool(st.session_state.get("use_contrib_persist", False)),
        key="use_contrib")
    st.session_state["use_contrib_persist"] = use_contrib
    monthly_contrib = st.number_input(
        t("side.monthly", lang), min_value=0,
        value=int(st.session_state.get("monthly_contrib_persist", 3000)),
        step=500, disabled=not use_contrib, key="monthly_contrib")
    st.session_state["monthly_contrib_persist"] = monthly_contrib
    _provider_options = ["synthetic", "merged"]
    if kairos_bridge.etf_dir() is not None:
        _provider_options.append("kairos")
    _saved_provider = st.session_state.get("provider_persist", "synthetic")
    if _saved_provider not in _provider_options:
        _saved_provider = _provider_options[0]
    provider = st.radio(
        t("side.provider", lang),
        _provider_options,
        index=_provider_options.index(_saved_provider),
        help=t("side.provider_help", lang),
        key="provider",
    )
    st.session_state["provider_persist"] = provider
    # Strategy options follow the current questionnaire tier, so a C1 profile
    # can never stay on a C5-only strategy after the questionnaire changes.
    _saved_q = st.session_state.get("atlas_answers_persist", {})
    # Prefer the live widget state (updated by the frontend before this run) so
    # the strategy list reacts in the same rerun as a questionnaire change.
    _preview_answers = {i: st.session_state.get(f"atlas_q{i}", _saved_q.get(i, 2))
                        for i in range(len(QUESTIONS))}
    try:
        _preview_profile = profile_from_answers(
            _preview_answers, capital=float(capital), free_text=free_text or "")
        _tier_ok = menu_for_tier(_preview_profile.tier)
    except Exception:  # noqa: BLE001 - keep the UI usable
        _preview_profile = None
        _tier_ok = list(STRATEGY_MENU)
    _strategy_ids = ["auto"] + [s.id for s in _tier_ok]
    _saved_strategy = st.session_state.get("strategy_persist", "auto")
    if _saved_strategy not in _strategy_ids:
        _saved_strategy = "auto"
    strategy_choice = st.selectbox(
        t("side.strategy", lang),
        _strategy_ids,
        index=_strategy_ids.index(_saved_strategy),
        format_func=lambda x: t("side.auto", lang) if x == "auto" else next(
            (f"{strategy_name(s, lang)} ({cadence_label(s.cadence, lang)})"
             for s in STRATEGY_MENU if s.id == x), x),
        key="strategy_choice",
    )
    st.session_state["strategy_persist"] = strategy_choice
    if _preview_profile is not None:
        st.caption(t("side.strategy_tier_hint", lang,
                     tier=f"{_preview_profile.tier} "
                          f"{tier_label(_preview_profile.tier_info, lang)}"))
    _lab_cache = kairos_lab.load_cached()
    _lab_names = [r["name"] for r in (_lab_cache or {}).get("strategies", [])[:20]]
    satellite_choice = "none"
    satellite_budget = 0.0
    if _lab_names:
        with st.expander(t("sat.title", lang)):
            st.caption(t("sat.help", lang))
            _sat_options = ["none"] + _lab_names
            _saved_sat = st.session_state.get("satellite_persist", "none")
            if _saved_sat not in _sat_options:
                _saved_sat = "none"
            satellite_choice = st.selectbox(
                t("sat.title", lang), _sat_options,
                index=_sat_options.index(_saved_sat),
                format_func=lambda x: t("sat.none", lang) if x == "none" else x,
                key="satellite_choice",
            )
            st.session_state["satellite_persist"] = satellite_choice
            satellite_budget = st.slider(
                t("sat.budget", lang), 0, 20,
                int(st.session_state.get("satellite_budget_persist", 10)), 5,
                disabled=(satellite_choice == "none"),
                key="satellite_budget",
            ) / 100.0
            st.session_state["satellite_budget_persist"] = int(satellite_budget * 100)
    with st.expander(t("side.timing", lang)):
        st.caption(t("side.timing_help", lang))
        use_timing = st.checkbox(
            t("side.timing_enable", lang),
            value=bool(st.session_state.get("use_timing_persist", False)),
            key="use_timing")
        st.session_state["use_timing_persist"] = use_timing
        _t_sliders = {}
        _t_saved = st.session_state.get("timing_sliders_persist", {})
        for _cls in ("equity_cn", "equity_global", "crypto", "commodity",
                     "fixed_income", "hybrid"):
            _t_sliders[_cls] = st.slider(
                class_label(_cls, lang), -1.0, 1.0,
                float(_t_saved.get(_cls, 0.0)), 0.25,
                disabled=not use_timing, key=f"t_{_cls}")
        st.session_state["timing_sliders_persist"] = dict(_t_sliders)
        _timing_free = st.text_input(
            t("side.timing_text", lang),
            st.session_state.get("timing_free_persist", ""),
            placeholder=t("side.timing_placeholder", lang),
            disabled=not use_timing, key="timing_free")
        st.session_state["timing_free_persist"] = _timing_free
    with st.expander(t("side.menu", lang)):
        st.dataframe(
            [{t("side.menu_strategy", lang): strategy_name(s, lang),
              t("side.menu_philosophy", lang): strategy_philosophy(s, lang),
              t("side.menu_objective", lang): objective_label(s.objective, lang),
              t("side.menu_cadence", lang): cadence_label(s.cadence, lang),
              t("side.menu_tiers", lang): f"{s.min_tier}-{s.max_tier}"}
             for s in STRATEGY_MENU],
            hide_index=True,
        )
    with st.expander(t("side.about", lang)):
        st.markdown(t("side.about_body", lang))

# ----------------------------------------------------------------------
# Questionnaire: ALWAYS rendered, before the generate button
# ----------------------------------------------------------------------
st.subheader(t("q.title", lang))
answers = {}
_saved_answers = st.session_state.get("atlas_answers_persist", {})
cols = st.columns(3)
for i, (_w, _q_zh, _q_en, opts) in enumerate(QUESTIONS):
    with cols[i % 3]:
        _q_default = int(_saved_answers.get(i, 2))
        _q_default = max(0, min(_q_default, len(opts) - 1))
        answers[i] = st.selectbox(
            t("q.prefix", lang, n=i, q=question_text((_w, _q_zh, _q_en, opts), lang)),
            range(len(opts)),
            index=_q_default,
            format_func=lambda j, o=opts: option_text(o[j], lang),
            key=f"atlas_q{i}",
        )
st.session_state["atlas_answers_persist"] = {i: int(v) for i, v in answers.items()}

# ----------------------------------------------------------------------
# Generate
# ----------------------------------------------------------------------
st.subheader(t("gen.title", lang))
c_btn, c_note = st.columns([1, 3])
with c_btn:
    run = st.button(t("gen.button", lang), type="primary", use_container_width=True)
with c_note:
    st.caption(t("gen.note", lang))

def _input_signature() -> str:
    """Stable fingerprint of every input that changes a generated plan."""
    return json.dumps({
        "answers": {str(i): int(v) for i, v in answers.items()},
        "capital": float(capital),
        "free_text": free_text,
        "provider": provider,
        "strategy": strategy_choice,
        "use_contrib": bool(use_contrib),
        "monthly_contrib": float(monthly_contrib),
        "timing": {
            "enabled": bool(use_timing),
            "text": _timing_free,
            "sliders": {k: float(v) for k, v in _t_sliders.items()},
        },
        "satellite": [satellite_choice, float(satellite_budget)],
    }, sort_keys=True, ensure_ascii=False)


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
        with st.spinner(t("gen.spinner", lang)):
            res = agent.offline_plan(
                answers,
                capital=float(capital),
                free_text=free_text or "",
                monthly_contrib=float(monthly_contrib) if use_contrib else None,
                strategy_id=None if strategy_choice == "auto" else strategy_choice,
                timing=_timing_arg,
                satellite_strategy=None if satellite_choice == "none" else satellite_choice,
                satellite_budget=satellite_budget,
            )
        res["_signature"] = _input_signature()
        st.session_state["atlas_result"] = res
    except Exception as e:  # noqa: BLE001 - friendly error instead of traceback
        st.error(t("gen.error", lang, err=f"{type(e).__name__}: {e}"))

# ----------------------------------------------------------------------
# Results (persisted across re-runs)
# ----------------------------------------------------------------------
res = st.session_state.get("atlas_result")
if res is None:
    st.info(t("gen.need_input", lang))
    st.stop()

plan, profile = res["plan"], res["profile"]
if res.get("_signature") and res["_signature"] != _input_signature():
    st.warning(t("gen.stale", lang))
st.subheader(t("res.title", lang, tier=profile.tier,
               tier_label=tier_label(profile.tier_info, lang),
               score=profile.score, segment=segment_label(plan.segment, lang),
               provider=provider))

k1, k2, k3, k4 = st.columns(4)
k1.metric(t("res.exp_return", lang), f"{plan.expected['ann_return']:.1%}")
k2.metric(t("res.vol", lang), f"{plan.expected['ann_vol']:.1%}")
k3.metric(t("res.sharpe", lang), f"{plan.expected['sharpe_hint']:.2f}")
k4.metric(t("res.mdd", lang), f"{plan.backtest['max_drawdown']:.1%}")

if plan.kairos_risk:
    _kr = plan.kairos_risk
    st.markdown(f"**{t('kairos.risk', lang)}**")
    _kc1, _kc2, _kc3, _kc4 = st.columns(4)
    _kc1.metric(t("kairos.var", lang),
                f"{_kr.get('var_95', 0):.2%} / {_kr.get('var_99', 0):.2%}")
    _kc2.metric(t("kairos.es", lang),
                f"{_kr.get('es_95', 0):.2%} / {_kr.get('es_99', 0):.2%}")
    _kc3.metric(t("kairos.dr", lang), f"{_kr.get('diversification_ratio', 0):.2f}")
    _kc4.metric(t("kairos.effn", lang), f"{_kr.get('effective_n', 0):.2f}")
    st.caption(t("kairos.source", lang, src=_kr.get("source", "kairos-risk"),
                 n=_kr.get("observations", 0)))

_st = plan.strategy
st.success(t("res.selected", lang, name=strategy_name(_st, lang),
             objective=objective_label(_st.objective, lang),
             cadence=cadence_label(_st.cadence, lang)))
st.caption(strategy_philosophy(_st, lang))
if plan.satellite:
    _sat = plan.satellite
    st.info(t("sat.applied", lang, name=_sat.get("name", "—"),
              channel=_sat.get("channel", "—"),
              budget=_sat.get("requested_budget", 0),
              actual=_sat.get("portfolio_weight", 0),
              invested=_sat.get("invested", 0),
              coverage=_sat.get("coverage", 0)))
    if float(_sat.get("coverage", 0)) < 0.5:
        st.warning(t("sat.coverage_low", lang, coverage=_sat.get("coverage", 0)))
if plan.timing:
    _sep = "、 " if lang != "en" else ", "
    _tl = _sep.join(
        f"{class_label(c, lang)} {'看多' if v > 0 else '看空'}{abs(v):.2f}"
        if lang != "en" else
        f"{class_label(c, lang)} {'bullish' if v > 0 else 'bearish'} {abs(v):.2f}"
        for c, v in plan.timing.items())
    st.info(t("res.timing", lang, views=_tl))

# ---- ④ 最终综合建议 (量化×大类×地缘×落位 有机融合) ----
st.subheader(t("fa.title", lang))
st.caption(t("fa.intro", lang))
_fa_col1, _fa_col2 = st.columns([1, 3])
with _fa_col1:
    _gen_fa = st.button(t("fa.generate", lang), key="gen_final_advice", type="primary")
if _gen_fa:
    from invest_agent.final_advice import build_final_advice  # noqa: E402
    from invest_agent.global_base import AssetProfile  # noqa: E402
    # reuse asset profile from the Global Basing section if provided
    _ap_fa = AssetProfile(asset_types=["cash_deposit", "cn_fund"],
                          total_capital=float(capital))
    if st.session_state.get("atlas_asset_profile"):
        _ap_fa = st.session_state["atlas_asset_profile"]
    with st.spinner(t("fa.spinner", lang)):
        try:
            _fa = build_final_advice(plan, profile, _ap_fa, provider_name=provider)
            st.session_state["atlas_final_advice"] = _fa
        except Exception as _fae:  # noqa: BLE001
            st.session_state["atlas_final_advice"] = {"error": str(_fae)}
_fa = st.session_state.get("atlas_final_advice")
if _fa and not _fa.get("error"):
    from invest_agent.global_base import GLOBAL_BASES  # noqa: E402
    _base_en = {b.name_zh: b.name_en for b in GLOBAL_BASES}
    _sep = ", " if lang == "en" else "、"

    def _localized_base(name_zh: str) -> str:
        if not name_zh or name_zh == "—":
            return "—"
        return _base_en.get(name_zh, name_zh) if lang == "en" \
            else pick(name_zh, _base_en.get(name_zh, name_zh), lang)

    _ov = _fa.get("overlays", {})
    _macro_stance = _ov.get("macro_stance", {})
    _over_names = [class_label(c, lang) for c, s in _macro_stance.items() if s == "超配"]
    _under_names = [class_label(c, lang) for c, s in _macro_stance.items() if s == "低配"]
    _themes_raw = str(_ov.get("geo_themes", "—"))
    _themes = "—" if _themes_raw in ("", "—") else _sep.join(
        theme_label(x, lang) for x in _themes_raw.split("、"))
    if lang == "en":
        _thesis = (f"Regime: {regime_label(_ov.get('geo_regime', '未知'), lang)} "
                   f"(risk appetite {_ov.get('geo_appetite', 0):+.2f}); themes: {_themes}. ")
        if _over_names:
            _thesis += f"Macro overweight: {', '.join(_over_names)}. "
        if _under_names:
            _thesis += f"Underweight: {', '.join(_under_names)}. "
        _thesis += (f"The baseline strategy ({strategy_name(plan.strategy, lang)}) was tilted within "
                    f"suitability caps and mapped to the lowest-friction global bases.")
    else:
        _thesis = to_hant(_fa["thesis"]) if lang == "zh-Hant" else _fa["thesis"]
    st.markdown(t("fa.thesis", lang, thesis=_thesis))
    st.caption(t("fa.overlays", lang,
                 regime=regime_label(_ov.get("geo_regime", "未知"), lang),
                 appetite=_ov.get("geo_appetite", 0), themes=_themes))
    _fa_rows = []
    _bm = _fa.get("base_map", {})
    for _c, _w in _fa.get("final_class_weights", {}).items():
        _b = _bm.get(_c, {})
        _fa_rows.append({
            t("fa.class", lang): class_label(_c, lang),
            t("fa.weight", lang): f"{_w:.1%}",
            t("fa.base", lang): _localized_base(_b.get("base", "—")),
            t("fa.base_score", lang): _b.get("score", "—"),
            t("fa.friction", lang): _b.get("friction", "—"),
        })
    st.dataframe(_fa_rows, hide_index=True, use_container_width=True)
    _fa_council = _fa.get("council")
    if _fa_council:
        _dv = _fa_council.get("divergence") or {}
        _dv_txt = ""
        if _dv:
            _dv_txt = t("fa.divergence", lang, score=_dv.get("score", 0),
                        level=divergence_label(_dv.get("level", "—"), lang),
                        influence=100 * (1 - _dv.get("score", 0)))
        st.markdown(t("fa.council", lang,
                      consensus=stance_label(_fa_council.get("consensus", "—"), lang),
                      divergence=_dv_txt))
        _net = _fa_council.get("net_tilt", {})
        if _net:
            _nt = _sep.join(f"{class_label(c, lang)} {v:+.2f}" for c, v in
                            sorted(_net.items(), key=lambda kv: -kv[1]) if abs(v) > 0.05)
            st.caption(t("fa.net", lang, signals=_nt))
        _mem = _sep.join(
            f"{analyst_name_from_zh(m['name_zh'], lang)} "
            f"({stance_label(m['stance'], lang)})"
            for m in _fa_council.get("members", []))
        st.caption(t("fa.members", lang, members=_mem))
    with st.expander(t("fa.actions", lang)):
        if lang == "en":
            _name_en = {a.id: a.name_en for a in plan.assets}
            _cls_of = {a.id: a.asset_class for a in plan.assets}
            _top = sorted(_fa.get("final_asset_weights", {}).items(), key=lambda kv: -kv[1])[:5]
            for _i, (_aid, _w) in enumerate(_top, 1):
                _bb = _bm.get(_cls_of.get(_aid, ""), {}).get("base")
                _where = f" (base: {_localized_base(_bb)})" if _bb else ""
                st.text(f"{_i}. {_name_en.get(_aid, _aid)} — {_w:.1%}{_where}")
            st.write("Research synthesis of quant allocation, class views, global regime and "
                     "basing. Not investment advice; markets carry risk.")
        else:
            _actions = _fa.get("actions", [])
            if lang == "zh-Hant":
                _actions = [to_hant(x) for x in _actions]
            for _i, _a in enumerate(_actions, 1):
                st.text(f"{_i}. {_a}")
            _digest = _fa.get("digest", "")
            st.write(to_hant(_digest) if lang == "zh-Hant" else _digest)
elif _fa and _fa.get("error"):
    st.warning(t("fa.error", lang, err=_fa["error"]))

# ---- ⑤ 金融分析师智囊团 (约30选5, 方向匹配) ----
st.subheader(t("council.title", lang))
st.caption(t("council.intro", lang))
_c_col1, _c_col2 = st.columns([1, 3])
with _c_col1:
    _gen_council = st.button(t("council.generate", lang), key="gen_council")
if _gen_council:
    with st.spinner(t("council.spinner", lang)):
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
    _sep = ", " if lang == "en" else "、"
    _dv = _cc.get("divergence") or {}
    _dv_metric = f"{_dv.get('score', 0):.2f}" if _dv else "—"
    _dv_level = divergence_label(_dv.get("level", "—"), lang) if _dv else "—"
    _dc1, _dc2 = st.columns([3, 1])
    with _dc1:
        _dissent = _sep.join(analyst_name_from_zh(x, lang) for x in _cc.get("dissent", []))
        st.success(t("council.consensus", lang,
                     consensus=stance_label(_cc["consensus"], lang),
                     n=_cc["n_analysts_total"],
                     dissent=t("council.dissent", lang, names=_dissent) if _dissent else ""))
    with _dc2:
        st.metric(t("council.divergence", lang), _dv_metric, _dv_level,
                  delta_color="inverse")
    if _dv.get("score", 0) >= 0.45:
        st.warning(t("council.warning", lang))
    if lang != "en":
        st.caption(to_hant(_cc["summary"]) if lang == "zh-Hant" else _cc["summary"])
    else:
        _members_en = _sep.join(analyst_name(v, lang) for v in _cc.get("council", []))
        st.caption(f"Selected {len(_cc.get('council', []))} of {_cc['n_analysts_total']} "
                   f"analysts by directional match: {_members_en}. Views are illustrative, "
                   f"not investment advice.")
    for _v, _vote in zip(_cc["council"], _cc.get("votes", [])):
        with st.container():
            _voice = _vote.get("voice", 1.0)
            _voice_txt = t("council.voice", lang, v=_voice) if abs(_voice - 1.0) > 0.01 \
                else t("council.voice_default", lang)
            st.markdown(t("council.meta", lang,
                          name=analyst_name(_v, lang),
                          school=school_label(_v["school"], lang),
                          rel=_v["relevance"], voice=_voice_txt,
                          stance=stance_label(_v["stance"], lang)))
            if lang == "en":
                _focus = ", ".join(class_label(c, lang) for c in str(_v.get("focus", "")).split("、") if c)
                _tilt_keys = ", ".join(class_label(c, lang) for c in _v.get("tilt", {}))
                st.markdown(f"&nbsp;&nbsp;🗣 From a {school_label(_v['school'], lang)} lens, "
                            f"current stance: {stance_label(_v['stance'], lang)}. "
                            f"Focus: {_focus or '—'}.")
                st.markdown(f"&nbsp;&nbsp;📊 Position tilt: `{_tilt_keys or '—'}`")
            else:
                _advice = to_hant(_v["advice"]) if lang == "zh-Hant" else _v["advice"]
                _tilt = to_hant(_v["tilt_text"]) if lang == "zh-Hant" else _v["tilt_text"]
                _sig = to_hant(_v["signature"]) if lang == "zh-Hant" else _v["signature"]
                st.markdown(t("council.advice", lang, text=_advice))
                st.markdown(t("council.tilt", lang, tilt=_tilt, signature=_sig))
    _cal = _cc.get("calibration") or {}
    if _cal.get("calibrated"):
        _top = _sep.join(
            f"{analyst_name_by_id(x['id'], lang)}({x['multiplier']:.2f})"
            for x in _cal.get("top", [])[:3])
        _bot = _sep.join(
            f"{analyst_name_by_id(x['id'], lang)}({x['multiplier']:.2f})"
            for x in _cal.get("bottom", [])[:3])
        st.caption(t("council.calibration", lang,
                     ts=_cal.get("meta", {}).get("calibrated_at", "—"),
                     top=_top, bottom=_bot))
    st.caption(t("council.disclaimer", lang))
elif _cc and _cc.get("error"):
    st.warning(t("council.error", lang, err=_cc["error"]))

if plan.menu:
    with st.expander(t("menu.title", lang)):
        _rows = []
        for r in plan.menu:
            _srow = next((s for s in STRATEGY_MENU if s.id == r["id"]), None)
            _rows.append({
                t("menu.col_strategy", lang): ("✅ " if r["id"] == _st.id else "")
                + (strategy_name(_srow, lang) if _srow else r["id"]),
                t("menu.col_objective", lang): objective_label(r["objective"], lang),
                t("menu.col_cadence", lang): cadence_label(r["cadence"], lang),
                t("menu.col_return", lang): f"{r['ann_return']:.1%}",
                t("menu.col_vol", lang): f"{r['ann_vol']:.1%}",
                t("menu.col_sharpe", lang): f"{r['sharpe']:.2f}",
                "DSR": f"{r.get('dsr', 0):.2f}",
                t("menu.col_mdd", lang): f"{r['max_drawdown']:.1%}",
            })
        st.dataframe(_rows, hide_index=True, use_container_width=True)

with st.expander(t("intel.title", lang)):
    if st.button(t("intel.fetch", lang)):
        from invest_agent.intel import fetch_market_intel  # noqa: E402
        with st.spinner(t("intel.spinner", lang)):
            _pack = fetch_market_intel(max_items=20)
        st.session_state["atlas_intel"] = _pack
    _pack = st.session_state.get("atlas_intel")
    if _pack:
        st.caption(t("intel.meta", lang, ts=_pack["generated_at"], status=_pack["source_status"],
                     topics=", ".join(_pack["topics_covered"])))
        if lang == "en":
            st.caption(t("intel.source_language", lang))
        for it in _pack["items"]:
            _title = to_hant(it["title"]) if lang == "zh-Hant" else it["title"]
            st.text(f"[{','.join(it['topics'][:2])}] {_title}")

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

st.subheader(t("alloc.title", lang))
name_of = {a.id: asset_name(a, lang) for a in plan.assets}
st.dataframe(
    [
        {t("alloc.asset", lang): name_of[k], t("alloc.weight", lang): f"{v:.2%}",
         t("alloc.exp_return", lang): f"{plan.mu_ann[k]:.1%}",
         t("alloc.vol", lang): f"{plan.vol_ann[k]:.1%}"}
        for k, v in sorted(plan.weights.items(), key=lambda kv: -kv[1])
    ],
    hide_index=True, use_container_width=True,
)

st.subheader(t("universe.title", lang))
st.caption(t("universe.intro", lang))
from invest_agent.config import client_segments  # noqa: E402
from invest_agent.data.universe import build_universe  # noqa: E402
from invest_agent.personas import accessible_classes  # noqa: E402

_caps = accessible_classes(profile)
_seg = client_segments()[plan.segment]
_pool_rows = []
for a in build_universe():
    cap = _caps.get(a.asset_class, 0.0)
    if a.asset_class == "futures" and not _seg.get("allow_futures", False):
        status = t("universe.no_segment", lang)
    elif a.asset_class == "futures" and cap <= 0:
        status = t("universe.no_suitability", lang)
    elif cap <= 0:
        status = t("universe.no_tier", lang)
    else:
        status = t("universe.cap", lang, cap=cap)
    wgt = plan.weights.get(a.id)
    _pool_rows.append({
        t("universe.asset", lang): f"{asset_name(a, lang)}",
        t("universe.class", lang): class_label(a.asset_class, lang),
        t("universe.access", lang): status,
        t("universe.current", lang): f"{wgt:.2%}" if wgt else "—",
    })
st.dataframe(_pool_rows, hide_index=True, use_container_width=True)

st.subheader(t("macro.title", lang))
st.caption(t("macro.intro", lang))
try:
    from invest_agent.macro_advice import generate_macro_advice  # noqa: E402
    with st.spinner(t("macro.spinner", lang)):
        _madv = generate_macro_advice(provider_name=provider, months=60)
    _stance_icon = {"超配": "🟢", "标配": "⚪", "低配": "🔴"}
    _mrows = []
    for a in _madv["advice"]:
        _reasons = "; ".join(a["reasons"]) if lang != "en" else ""
        if lang == "zh-Hant":
            _reasons = to_hant(_reasons)
        _mrows.append({
            t("macro.stance", lang): _stance_icon.get(a["stance"], "") + " "
            + stance_label(a["stance"], lang),
            t("macro.class", lang): class_label(a["class"], lang),
            t("macro.score", lang): f"{a['score']:+.2f}",
            t("macro.reasons", lang): _reasons or "—",
        })
    st.dataframe(_mrows, hide_index=True, use_container_width=True)
    _mc1, _mc2 = st.columns(2)
    with _mc1:
        if lang != "en":
            _style = to_hant(_madv["sector_tilt"]["style"]) if lang == "zh-Hant" \
                else _madv["sector_tilt"]["style"]
            st.markdown(t("macro.style", lang, style=_style))
            for _n in _madv["sector_tilt"]["notes"]:
                st.caption(f"• {to_hant(_n) if lang == 'zh-Hant' else _n}")
    with _mc2:
        _ctx = _madv["macro_context"]
        st.markdown(t("macro.context", lang))
        if lang != "en" and _ctx.get("china_pmi"):
            st.caption(f"• {t('macro.pmi', lang, v=_ctx.get('china_pmi'))}")
        if _ctx.get("equity_pe_percentile") is not None:
            st.caption(f"• {t('macro.pe', lang, v=_ctx.get('equity_pe_percentile'))}")
        st.caption(f"• {t('macro.regime', lang, v=regime_label(_ctx.get('global_regime', '—'), lang))}")
    if lang != "en":
        with st.expander(t("macro.narrative", lang)):
            st.write(to_hant(_madv["narrative"]) if lang == "zh-Hant" else _madv["narrative"])
except Exception as _me:  # noqa: BLE001
    st.warning(t("macro.error", lang, err=_me))

st.subheader(t("factor.title", lang))
st.caption(t("factor.intro", lang))
try:
    from invest_agent.factors import default_catalog, enrich_universe, screen_universe  # noqa: E402
    _prov = InvestAgent(provider_name=provider).ctx.get_provider()
    _uni = build_universe()
    _ids = [a.id for a in _uni]
    _cn_to_en = {a.name_zh: a.name_en for a in _uni}
    _R = _prov.get_monthly_returns(_ids, 96)
    with st.spinner(t("factor.spinner", lang)):
        _enrich = enrich_universe(_uni)
    _screen = screen_universe(_R[_ids], _uni, default_catalog(), enrichment=_enrich)
    _rows = []
    for i, r in enumerate(_screen["ranked"]):
        _aname = _cn_to_en.get(r["name_zh"], r["name_zh"]) if lang == "en" \
            else pick(r["name_zh"], _cn_to_en.get(r["name_zh"], r["name_zh"]), lang)
        _rows.append({
            t("factor.rank", lang): i + 1, t("factor.asset", lang): _aname,
            t("factor.class", lang): class_label(r["class"], lang),
            t("factor.score", lang): f"{r['score']:+.2f}",
            t("factor.momentum", lang): f"{r['momentum']:+.1%}",
            t("factor.vol", lang): f"{r['low_vol']:.1%}",
            t("factor.pe", lang): f"{r['pe_percentile']:.0f}%" if "pe_percentile" in r else "—",
            t("factor.flow", lang): f"{r['money_flow']:+.2f}%" if "money_flow" in r else "—",
            t("factor.n_live", lang): r["n_live_factors"],
        })
    st.dataframe(_rows, hide_index=True, use_container_width=True)
    st.caption(t("factor.live_yes" if _screen["live_data_used"] else "factor.live_no", lang))
    if lang != "en":
        with st.expander(t("factor.skipped", lang)):
            _sk = "、".join(_screen["skipped_families"]) or t("common.none", lang)
            st.write(to_hant(_sk) if lang == "zh-Hant" else _sk)
except Exception as _e:  # noqa: BLE001
    st.warning(t("factor.error", lang, err=_e))

with st.expander(t("factor.kb", lang)):
    _cat = default_catalog()
    if _cat.factors:
        st.caption(t("factor.kb_stats", lang, n=len(_cat.factors),
                     c=len(_cat.categories), r=_cat.n_records))
        if lang != "en":
            _cs = _cat.category_summary()[:30]
            if lang == "zh-Hant":
                _cs = [{"category": to_hant(x["category"]), "n_factors": x["n_factors"]}
                       for x in _cs]
            st.dataframe(_cs, hide_index=True)
    else:
        st.info(t("factor.kb_empty", lang))

with st.expander(t("ff.title", lang)):
    st.caption(t("ff.intro", lang))
    if not forge_bridge.available():
        st.info(t("ff.not_available", lang))
    else:
        _ff_text = st.text_area(
            t("ff.brief", lang),
            st.session_state.get("ff_text_persist", ""), height=180,
            placeholder=t("ff.placeholder", lang), key="ff_text")
        st.session_state["ff_text_persist"] = _ff_text
        _ff_c1, _ff_c2 = st.columns(2)
        with _ff_c1:
            _ff_source = st.text_input(
                t("ff.source", lang),
                st.session_state.get("ff_source_persist", ""), key="ff_source")
            st.session_state["ff_source_persist"] = _ff_source
        with _ff_c2:
            _ff_name = st.text_input(
                t("ff.name", lang),
                st.session_state.get("ff_name_persist", ""), key="ff_name")
            st.session_state["ff_name_persist"] = _ff_name

        _ff_pdf = st.file_uploader(t("ff.pdf", lang), type=["pdf"], key="ff_pdf")
        if _ff_pdf is not None and st.button(t("ff.pdf_parse", lang), key="ff_pdf_btn"):
            with st.spinner(t("ff.pdf_spinner", lang)):
                _pdf_path = None
                try:
                    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as _tmp:
                        _tmp.write(_ff_pdf.getvalue())
                        _pdf_path = _tmp.name
                    st.session_state["atlas_forge_pdf"] = forge_bridge.forge_pdf(
                        _pdf_path, source=_ff_source or _ff_pdf.name, max_briefs=3)
                except Exception as _pfe:  # noqa: BLE001
                    st.session_state["atlas_forge_pdf"] = {"available": False,
                                                           "reason": str(_pfe)}
                finally:
                    if _pdf_path and os.path.exists(_pdf_path):
                        os.unlink(_pdf_path)
        _pdfres = st.session_state.get("atlas_forge_pdf")
        if _pdfres:
            if not _pdfres.get("available"):
                st.warning(t("ff.error", lang, err=_pdfres.get("reason", "—")))
            else:
                _briefs = _pdfres.get("briefs") or []
                if not _briefs:
                    st.info(t("ff.pdf_none", lang))
                else:
                    st.markdown(f"**{t('ff.pdf_briefs', lang)}**")
                    _brows = [{
                        "name": b["factor"].get("name", ""),
                        t("ff.operator", lang): b["factor"].get("operator", ""),
                        "score": b.get("score", 0),
                        "anchor": b.get("anchor", ""),
                    } for b in _briefs]
                    st.dataframe(_brows, hide_index=True, use_container_width=True)
                    _bidx = st.selectbox(
                        t("ff.pdf_use", lang), range(len(_briefs)),
                        format_func=lambda i: f"{_briefs[i]['factor'].get('name', '')} "
                                              f"({_briefs[i].get('score', 0)})",
                        key="ff_pdf_pick")
                    if st.button(t("ff.pdf_use", lang), key="ff_pdf_use_btn"):
                        st.session_state["atlas_forge"] = _briefs[_bidx]

        if st.button(t("ff.forge", lang), key="ff_forge_btn"):
            with st.spinner(t("ff.spinner", lang)):
                try:
                    st.session_state["atlas_forge"] = forge_bridge.forge(
                        _ff_text, source=_ff_source, name=_ff_name, validate=True)
                except Exception as _ffe:  # noqa: BLE001
                    st.session_state["atlas_forge"] = {"available": False,
                                                       "reason": str(_ffe)}
        _ff = st.session_state.get("atlas_forge")
        if _ff and not _ff.get("available"):
            st.warning(t("ff.error", lang, err=_ff.get("reason", "—")))
        elif _ff and _ff.get("available"):
            _fac = _ff["factor"]
            st.markdown(f"**{t('ff.preview', lang)}**")
            _fields = [v.get("data_field") for v in _fac.get("variables", [])
                       if v.get("data_field")]
            _prow = [
                {"name": _fac.get("name", ""),
                 t("ff.operator", lang): _fac.get("operator", ""),
                 t("ff.direction", lang): _fac.get("direction", 0),
                 t("ff.fields", lang): ", ".join(dict.fromkeys(_fields)) or "—"},
            ]
            if lang != "en":
                _prow[0][t("ff.category", lang)] = to_hant(_fac.get("category", "")) \
                    if lang == "zh-Hant" else _fac.get("category", "")
            st.dataframe(_prow, hide_index=True, use_container_width=True)
            _val = _ff.get("validation") or {}
            if _val:
                _status = "PASS" if _val.get("ok") else "WARN"
                st.caption(t("ff.validation", lang, status=_status,
                             msg=_val.get("message", "")))
            if st.button(t("ff.evaluate", lang), key="ff_eval_btn"):
                with st.spinner(t("ff.eval_spinner", lang)):
                    st.session_state["atlas_forge_eval"] = forge_bridge.evaluate_on_atlas(
                        _fac, _ff.get("code", ""), provider_name=provider)
            _ev = st.session_state.get("atlas_forge_eval")
            if _ev:
                if not _ev.get("available"):
                    st.caption(t("ff.eval_unavailable", lang,
                                 reason=_ev.get("reason", "—")))
                else:
                    st.markdown(f"**{t('ff.eval_title', lang)}**")
                    st.dataframe([{
                        t("ff.ic", lang): f"{_ev['mean_ic']:+.3f}",
                        t("ff.icir", lang): f"{_ev['icir']:+.2f}",
                        t("ff.tstat", lang): f"{_ev['t_stat']:+.2f}",
                        t("ff.positive", lang): f"{_ev['positive_rate']:.1%}",
                        t("ff.periods", lang): _ev["n_periods"],
                        t("ff.direction_match", lang):
                            "—" if _ev.get("direction_match") is None
                            else ("✅" if _ev["direction_match"] else "❌"),
                    }], hide_index=True, use_container_width=True)
            if lang != "en":
                _json_txt = json.dumps(_fac, ensure_ascii=False, indent=1)
                if lang == "zh-Hant":
                    _json_txt = to_hant(_json_txt)
                st.code(_json_txt, language="json")
                _code_txt = _ff.get("code", "")
                if lang == "zh-Hant":
                    _code_txt = to_hant(_code_txt)
                st.markdown(f"**{t('ff.code', lang)}**")
                st.code(_code_txt, language="python")
            if st.button(t("ff.import", lang), key="ff_import_btn"):
                with st.spinner(t("ff.import_spinner", lang)):
                    try:
                        _rec = forge_bridge.import_factor(
                            _fac, _ff.get("code", ""), source=_ff_source,
                            overwrite=True)
                        st.success(t("ff.imported", lang,
                                     name=_rec.get("name", "—"), source="factor_forge"))
                        st.caption(t("ff.import_note", lang))
                    except Exception as _ffe:  # noqa: BLE001
                        st.warning(t("ff.error", lang, err=_ffe))

with st.expander(t("custom.title", lang)):
    st.caption(t("custom.intro", lang))
    if not custom_factors.forged_records():
        st.info(t("custom.none", lang))
    else:
        _cp = st.session_state.get("atlas_custom_factors") or custom_factors.load_cached()
        if st.button(t("custom.run", lang), key="custom_factor_btn"):
            with st.spinner(t("custom.spinner", lang)):
                try:
                    _cp = custom_factors.compute(provider_name=provider, force=True)
                    st.session_state["atlas_custom_factors"] = _cp
                except Exception as _ce:  # noqa: BLE001
                    st.warning(t("ff.error", lang, err=_ce))
                    _cp = None
        if _cp and _cp.get("available"):
            st.caption(t("custom.meta", lang, ts=_cp.get("generated_at", "—"),
                         n=_cp.get("n_factors", 0),
                         months=_cp.get("recent_months", 6)))
            _frows = []
            for _f in _cp.get("factors", []):
                if not _f.get("available"):
                    continue
                _frows.append({
                    t("custom.col_factor", lang): _f.get("name", ""),
                    t("custom.col_ic", lang): f"{_f['mean_ic']:+.3f}",
                    t("custom.col_icir", lang): f"{_f['icir']:+.2f}",
                    t("custom.col_t", lang): f"{_f['t_stat']:+.2f}",
                    t("custom.col_weight", lang): f"{_f['weight']:.3f}",
                    t("custom.col_match", lang):
                        "—" if _f.get("direction_match") is None
                        else ("✅" if _f["direction_match"] else "❌"),
                })
            if _frows:
                st.markdown(f"**{t('custom.factors', lang)}**")
                st.dataframe(_frows, hide_index=True, use_container_width=True)
            from invest_agent.data.universe import build_universe as _bu  # noqa: E402
            _names = {a.id: asset_name(a, lang) for a in _bu()}
            _top = _cp.get("ranked", [])[:8]
            _bottom = list(reversed(_cp.get("ranked", [])[-8:]))
            _c1, _c2 = st.columns(2)
            with _c1:
                st.markdown(f"**{t('custom.top', lang)}**")
                st.dataframe([{t("custom.asset", lang): _names.get(r["asset"], r["asset"]),
                              t("custom.score", lang): f"{r['score']:+.3f}"}
                             for r in _top], hide_index=True, use_container_width=True)
            with _c2:
                st.markdown(f"**{t('custom.bottom', lang)}**")
                st.dataframe([{t("custom.asset", lang): _names.get(r["asset"], r["asset"]),
                              t("custom.score", lang): f"{r['score']:+.3f}"}
                             for r in _bottom], hide_index=True, use_container_width=True)
        elif _cp:
            st.caption(t("custom.not_ready", lang, reason=_cp.get("reason", "—")))

with st.expander(t("factor.evo", lang), expanded=False):
    from invest_agent.factors.factor_evolution import (  # noqa: E402
        hours_since_last_run, maybe_autolearn, read_state)
    from invest_agent.factors.factor_store import stats as _fstats  # noqa: E402
    _fs = _fstats()
    _st_state = read_state()
    _gap = hours_since_last_run()
    st.caption(t("factor.evo_stats", lang, n=_fs["total"], sources=_fs["by_source"],
                 ic=_fs["with_ic"]))
    _last = _st_state.get("last_run") or t("common.never", lang)
    _gap_txt = t("common.hours", lang, h=_gap) if _gap is not None else "—"
    st.caption(t("factor.evo_last", lang, last=_last,
                 cycles=_st_state.get("cycles", 0), gap=_gap_txt))
    st.caption(t("factor.evo_how", lang))
    _ac1, _ac2 = st.columns(2)
    with _ac1:
        if st.button(t("factor.evo_once", lang), key="evolve_btn"):
            with st.spinner(t("factor.evo_spinner", lang)):
                try:
                    from invest_agent.factors.factor_evolution import run_cycle  # noqa: E402
                    st.session_state["atlas_evolve"] = run_cycle(provider_name=provider,
                                                                 months=96)
                except Exception as _ee:  # noqa: BLE001
                    st.session_state["atlas_evolve"] = {"error": str(_ee)}
    with _ac2:
        if st.button(t("factor.evo_bg", lang), key="evolve_bg_btn"):
            _tr = maybe_autolearn(threshold_hours=-1, provider_name=provider)
            st.toast(t("factor.evo_bg_ok" if _tr.get("triggered") else "factor.evo_bg_fail", lang))
    _ev = st.session_state.get("atlas_evolve")
    if _ev:
        if _ev.get("error"):
            st.warning(t("factor.evo_error", lang, err=_ev["error"]))
        else:
            st.success(t("factor.evo_done", lang,
                         before=_ev["factors_before"], after=_ev["factors_after"],
                         kb=_ev["knowledge_base_imported"],
                         reports=_ev["broker_report_factors"],
                         pdf=_ev.get("pdf_factors_registered", 0),
                         online=_ev["collected_online"]))
            if _ev.get("learned_empirical"):
                st.dataframe([{t("factor.evo_ic_factor", lang): f["name"], "IC": f.get("ic")}
                              for f in _ev["learned_empirical"]], hide_index=True)
                st.caption(t("factor.ic_note", lang))

with st.expander(t("kairos.title", lang)):
    st.caption(t("kairos.intro", lang))
    _ks = kairos_bridge.context(plan)
    if not _ks.get("root"):
        st.info(t("kairos.not_found", lang))
    else:
        st.caption(f"{t('kairos.root', lang)}: `{_ks['root']}`")
        _pkgs = {k: v for k, v in (_ks.get("packages") or {}).items() if v}
        if _pkgs:
            st.markdown(f"**{t('kairos.packages', lang)}**: " + ", ".join(
                f"`{k}` {v}" for k, v in sorted(_pkgs.items())))
        if _ks.get("etf_count"):
            st.caption(t("kairos.data_line", lang, n=_ks["etf_count"],
                         dir=_ks.get("etf_dir") or "—"))
            st.caption(t("kairos.mapped_line", lang, n=_ks.get("n_mapped_assets", 0),
                         ids=", ".join(_ks.get("mapped_assets") or [])))
        _res = _ks.get("research") or {}
        if _res:
            _champs = _res.get("champions") or []
            if _champs:
                st.markdown(f"**{t('kairos.champions', lang)}**")
                _crow = [{
                    t("kairos.col_strategy", lang): r.get("strategy", ""),
                    "channel": r.get("channel", ""),
                    "Sharpe": r.get("real_sharpe", ""),
                    t("kairos.col_score", lang): r.get("robustness_score", ""),
                    t("kairos.col_rank", lang): r.get("rank", ""),
                } for r in _champs[:5]]
                st.dataframe(_crow, hide_index=True, use_container_width=True)
            _find = _res.get("findings") or []
            if _find:
                if lang == "en":
                    st.caption(f"{len(_find)} key findings are available in the Chinese "
                               f"kairos-research report (not machine-translated offline).")
                else:
                    st.markdown(f"**{t('kairos.findings', lang)}**")
                    _frow = []
                    for r in _find[:4]:
                        _frow.append({
                            t("kairos.col_metric", lang): pick(r.get("指标", ""), "", lang),
                            t("kairos.col_value", lang): pick(str(r.get("值", "")), "", lang),
                            t("kairos.col_unit", lang): pick(r.get("单位", ""), "", lang),
                            t("kairos.col_source", lang): pick(r.get("来源仓库", ""), "", lang),
                        })
                    st.dataframe(_frow, hide_index=True, use_container_width=True)
        if plan.kairos_risk:
            _crisk = plan.kairos_risk.get("class_risk") or {}
            if _crisk:
                st.markdown(f"**{t('kairos.class_risk', lang)}**")
                st.dataframe(
                    [{t("fa.class", lang): class_label(c, lang),
                      t("fa.weight", lang): f"{v:.1%}"}
                     for c, v in sorted(_crisk.items(), key=lambda kv: -kv[1])],
                    hide_index=True, use_container_width=True,
                )

with st.expander(t("lab.title", lang)):
    st.caption(t("lab.intro", lang))
    if not kairos_lab.available():
        st.info(t("lab.not_available", lang))
    else:
        _lab = st.session_state.get("atlas_lab") or kairos_lab.load_cached()
        if st.button(t("lab.run", lang), key="run_strategy_lab"):
            with st.spinner(t("lab.spinner", lang)):
                try:
                    _lab = kairos_lab.run_lab(force=True)
                    st.session_state["atlas_lab"] = _lab
                    st.rerun()
                except Exception as _le:  # noqa: BLE001
                    st.warning(t("lab.error", lang, err=_le))
                    _lab = None
        if _lab and _lab.get("available"):
            _u = _lab.get("universe", {})
            st.caption(t("lab.cached", lang, ts=_lab.get("generated_at", "—"),
                         n=_lab.get("n_strategies", 0),
                         start=_u.get("start", "—"), end=_u.get("end", "—")))
            _rows = []
            for _r in _lab.get("strategies", [])[:20]:
                _rows.append({
                    t("kairos.col_strategy", lang): _r["name"],
                    t("lab.col_channel", lang): _r["channel"],
                    t("lab.col_cagr", lang): f"{_r['cagr']:.1%}",
                    t("lab.col_vol", lang): f"{_r['volatility']:.1%}",
                    t("lab.col_sharpe", lang): f"{_r['sharpe']:.2f}",
                    t("lab.col_mdd", lang): f"{_r['max_drawdown']:.1%}",
                    t("lab.col_turnover", lang): f"{_r['avg_turnover']:.3f}",
                })
            st.dataframe(_rows, hide_index=True, use_container_width=True)
            _names = [r["name"] for r in _lab.get("strategies", [])[:20]]
            if _names:
                _saved_lab = st.session_state.get("lab_strategy_persist", _names[0])
                if _saved_lab not in _names:
                    _saved_lab = _names[0]
                _sel = st.selectbox(t("lab.select", lang), _names,
                                    index=_names.index(_saved_lab),
                                    key="lab_strategy_pick")
                st.session_state["lab_strategy_persist"] = _sel
                if st.button(t("lab.show", lang), key="lab_show_btn"):
                    _detail = kairos_lab.run_strategy(_sel)
                    if not _detail.get("available"):
                        st.warning(_detail.get("reason", "—"))
                    else:
                        if lang != "en":
                            _desc = _detail.get("description", "")
                            st.markdown(t("lab.description", lang,
                                          text=to_hant(_desc) if lang == "zh-Hant" else _desc))
                        st.caption(t("lab.params", lang, params=_detail.get("params", {})))
                        import pandas as _pd  # noqa: E402
                        _eqdf = _pd.DataFrame(_detail["equity"])
                        _eqdf["date"] = _pd.to_datetime(_eqdf["date"])
                        _eqdf = _eqdf.set_index("date")["value"]
                        st.caption(t("lab.equity", lang, name=_sel))
                        st.line_chart(_eqdf, height=260)
        elif _lab is None:
            st.caption(t("lab.no_cache", lang))

with st.expander(t("report.title", lang)):
    if lang == "en":
        st.info(t("report.zh_only", lang))
        st.stop()
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
    st.markdown(to_hant(_report_text) if lang == "zh-Hant" else _report_text)
