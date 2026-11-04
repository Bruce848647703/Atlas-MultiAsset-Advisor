"""Dashboard internationalisation: Simplified Chinese, English, Traditional Chinese.

UI strings are authored as ``(zh_hans, en)`` pairs. Traditional Chinese is
produced from the Simplified text with the OpenCC dictionary shipped by
``zhconv`` — one source of truth, no hand-maintained third copy.

Dynamic research text (news headlines, PDF text, long generated narratives) is
external/source material and is not machine-translated offline; the dashboard
labels it accordingly.
"""

from __future__ import annotations

import warnings
from functools import lru_cache

try:  # optional at import time so the dashboard still runs without it
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import zhconv
except ImportError:  # pragma: no cover - requirements include zhconv
    zhconv = None

LANGS = ["zh", "en", "zh-Hant"]
LANG_LABELS = {"zh": "简体中文", "en": "English", "zh-Hant": "繁體中文"}

# UI dictionary: key -> (简体中文, English)
S = {
    # shell / gate
    "app.tagline": ("多元资产顾问 · 家办配置视角", "Multi-Asset Advisor · Family-Office Allocation"),
    "app.disclaimer": ("量化生成，仅供研究参考，不构成投资建议。",
                       "Quant-generated research only. NOT investment advice."),
    "gate.title": ("Atlas 多元资产投资顾问", "Atlas Multi-Asset Advisor"),
    "gate.token": ("访问口令", "Access token"),
    "gate.enter": ("进入", "Enter"),
    "gate.wrong": ("口令错误", "Wrong token"),
    "language": ("语言", "Language"),
    # global indices
    "indices.title": ("全球市场指数", "Global Market Indices"),
    "indices.refresh": ("刷新指数", "Refresh"),
    "indices.updated": ("更新于 {ts}", "Updated {ts}"),
    "indices.source_ok": ("数据源正常", "Source OK"),
    "indices.source_degraded": ("数据源降级", "Source degraded"),
    "indices.region": ("区域", "Region"),
    "indices.index": ("指数", "Index"),
    "indices.price": ("现价", "Last"),
    "indices.change": ("涨跌%", "Chg %"),
    "indices.status": ("状态", "Status"),
    "indices.trading": ("交易中", "Open"),
    "indices.closed": ("已收盘", "Closed"),
    "indices.unavailable": ("全球指数数据暂不可用", "Global index data unavailable"),
    # geopolitics
    "geo.title": ("全球政治经济局势", "Global Situation"),
    "geo.refresh": ("刷新局势", "Refresh"),
    "geo.spinner": ("聚合实时新闻并研判全球局势...", "Aggregating news and assessing the global situation..."),
    "geo.error": ("局势板块暂不可用：{err}", "Global situation unavailable: {err}"),
    "geo.appetite": ("风险偏好", "Risk appetite"),
    "geo.regime": ("研判", "Regime"),
    "geo.samples": ("新闻样本", "News items"),
    "geo.themes": ("主导议题：{themes}", "Dominant themes: {themes}"),
    "geo.sources": ("数据源：{sources}", "Sources: {sources}"),
    "geo.none": ("无", "none"),
    "geo.watch": ("关注事件", "Watch list"),
    "geo.feed": ("实时新闻流", "News feed"),
    # global basing
    "base.title": ("家办 · 全球资产落位", "Family Office · Global Basing"),
    "base.intro": ("根据适当性等级与资产画像，列出全球适合的落位/通道（境内/跨境/离岸）并打分，"
                   "评估资本管制、税、汇兑、准入与合规摩擦。仅供研究参考。",
                   "Ranks suitable global bases/channels (onshore / cross-border / offshore) by fit "
                   "and friction (capital control, tax, FX, access, compliance). Research only."),
    "base.profile": ("① 资产画像", "① Asset Profile"),
    "base.holdings": ("当前持有的资产类型", "Asset types currently held"),
    "base.overseas_pct": ("现有资产中境外占比 (%)", "Overseas share of current assets (%)"),
    "base.accounts": ("已开立的境外账户", "Overseas accounts opened"),
    "base.liquidity": ("流动性需求", "Liquidity need"),
    "base.liq_low": ("低（长期不动用）", "Low (long-term)"),
    "base.liq_mid": ("中", "Medium"),
    "base.liq_high": ("高（随时可能用）", "High (may need anytime)"),
    "base.capital": ("总资产规模 (CNY)", "Total assets (CNY)"),
    "base.generate": ("生成落位建议", "Generate basing advice"),
    "base.result_title": ("② 全球落位建议（适当性 {tier}）— 按「适配度 × (1 − 摩擦)」打分",
                          "② Global basing advice (suitability {tier}) — fit × (1 − friction)"),
    "base.col_name": ("落位 / Base", "Base"),
    "base.col_category": ("类别", "Category"),
    "base.col_score": ("评分", "Score"),
    "base.col_friction": ("摩擦", "Friction"),
    "base.col_min": ("门槛", "Minimum"),
    "base.col_highlights": ("要点", "Highlights"),
    "base.none": ("无", "None"),
    "base.fallback_reason": ("综合适配", "Overall fit"),
    "base.details": ("各 base 详情与适配分解", "Base details & fit breakdown"),
    "base.fit": ("适配：资本 {capital} · 资产 {asset} · 风险 {risk} · 经验 {experience} · 境外 {overseas}",
                 "Fit: capital {capital} · assets {asset} · risk {risk} · experience {experience} · overseas {overseas}"),
    "base.principle": ("原则：优先低摩擦境内通道打底 → 跨境通道（QDII/港通）拓展 → "
                       "离岸（港/新/美）仅补境内无法覆盖之需求；资金出境务必合规。",
                       "Principle: low-friction onshore first → cross-border channels (QDII/Connect) → "
                       "offshore only for gaps; keep capital flows compliant."),
    # sidebar
    "side.inputs": ("投资者输入", "Investor Inputs"),
    "side.capital": ("可投资本金 (CNY)", "Investable capital (CNY)"),
    "side.free_text": ("风险态度 / 目标补充", "Risk attitude / goal notes"),
    "side.custom_contrib": ("自定义每月定投额", "Custom monthly contribution"),
    "side.monthly": ("每月定投 (CNY)", "Monthly contribution (CNY)"),
    "side.provider": ("数据源", "Data source"),
    "side.provider_help": ("synthetic=离线合成市场；merged=akshare 真实行情 + 合成补齐；"
                           "kairos=Kairos 真实 ETF 面板（离线）",
                           "synthetic=offline simulated market; merged=akshare real data + synthetic fill; "
                           "kairos=Kairos real ETF panel (offline)"),
    "side.strategy": ("策略", "Strategy"),
    "side.auto": ("自动选择（按画像匹配）", "Auto (match profile)"),
    "side.timing": ("主观择时（可选）", "Market timing (optional)"),
    "side.timing_help": ("表达对各类资产的多空观点：-1=强烈看空，0=中性，+1=强烈看多。"
                         "观点只影响今日配置，不改变历史回测。",
                         "Express directional views: -1=strongly bearish, 0=neutral, +1=strongly bullish. "
                         "Applies to today's allocation only; historical backtests stay unchanged."),
    "side.timing_enable": ("启用主观择时", "Enable timing views"),
    "side.timing_text": ("或用一句话描述（优先）", "Or describe in one sentence (takes precedence)"),
    "side.timing_placeholder": ("例：短期看空 A 股，看多加密", "e.g. bearish A-shares short term, bullish crypto"),
    "side.menu": ("策略菜单", "Strategy menu"),
    "side.menu_strategy": ("策略", "Strategy"),
    "side.menu_philosophy": ("哲学", "Philosophy"),
    "side.menu_objective": ("目标", "Objective"),
    "side.menu_cadence": ("调仓", "Cadence"),
    "side.menu_tiers": ("适用", "Tiers"),
    "side.about": ("数据源说明", "About data sources"),
    "side.about_body": (
        "**synthetic（离线）**：固定种子模拟的多资产世界，内置熊市/繁荣/币圈闪崩情景，"
        "完全可复现、无需网络，适合研究与演示。\n\n"
        "**merged（真实 + 补齐）**：通过 akshare 拉取 A 股 ETF 与公募基金的真实月度净值"
        "（首次联网，之后缓存在 `data_cache/`）；加密货币与期货列由合成数据自动补齐。",
        "**synthetic (offline)**: fixed-seed simulated multi-asset world with bear/boom/crypto-crash "
        "regimes; fully reproducible, no network required.\n\n"
        "**merged (real + fill)**: akshare monthly NAV for CN ETFs and mutual funds (network on first "
        "use, then cached in `data_cache/`); crypto and futures columns are filled synthetically.",
    ),
    # questionnaire / generation
    "q.title": ("① 适当性问卷", "① Suitability Questionnaire"),
    "q.prefix": ("Q{n}. {q}", "Q{n}. {q}"),
    "gen.title": ("② 生成方案", "② Generate"),
    "gen.button": ("生成方案", "Generate plan"),
    "gen.note": ("修改上方任意输入后再次点击即可重新生成；结果会保留到下一次生成。",
                 "Change any input and generate again; results persist until the next run."),
    "gen.spinner": ("量化计算中（策略菜单回测 + 组合优化 + 回测）...",
                    "Running quant pipeline (strategy menu, optimization, backtest)..."),
    "gen.error": ("生成失败：{err}\n请调整问卷/策略选择后重试，或在侧边栏改用自动策略。",
                  "Generation failed: {err}\nAdjust the questionnaire/strategy and retry, "
                  "or use Auto strategy in the sidebar."),
    "gen.need_input": ("请先完成问卷并点击「生成方案」。", "Complete the questionnaire and click Generate plan."),
    # results
    "res.title": ("③ 结果：适当性 {tier} {tier_label}（评分 {score:.0f}）· 客群 {segment} · 数据源 {provider}",
                  "③ Result: suitability {tier} {tier_label} (score {score:.0f}) · segment {segment} · source {provider}"),
    "res.exp_return": ("预期年化收益", "Expected annual return"),
    "res.vol": ("年化波动", "Annual volatility"),
    "res.sharpe": ("夏普（事前）", "Sharpe (ex-ante)"),
    "res.mdd": ("回测最大回撤", "Backtest max drawdown"),
    "res.selected": ("所选策略：**{name}** · 目标 `{objective}` · 调仓 `{cadence}`",
                     "Selected strategy: **{name}** · objective `{objective}` · cadence `{cadence}`"),
    "res.timing": ("已注入主观择时：{views}（仅影响今日配置，不改变历史回测）",
                   "Timing views applied: {views} (today only; historical backtests unchanged)"),
    # final advice
    "fa.title": ("④ 最终综合建议", "④ Final Integrated Advice"),
    "fa.intro": ("把量化配置 × 大类观点 × 全球政经局势 × 全球 base 落位有机融合，"
                 "形成符合发展趋势、利益最大化的最终建议（含全球落位与执行清单）。",
                 "Fuses the quant allocation × class views × global regime × global bases into one "
                 "trend-aligned recommendation with a basing map and action list."),
    "fa.generate": ("生成最终建议", "Generate final advice"),
    "fa.spinner": ("融合中：大类观点 + 全球局势 + base 落位 ...", "Fusing class views, global regime and basing..."),
    "fa.thesis": ("**研判主线**：{thesis}", "**Thesis**: {thesis}"),
    "fa.overlays": ("全球局势：{regime}（风险偏好 {appetite:+.2f}）· 议题：{themes}",
                    "Global regime: {regime} (appetite {appetite:+.2f}) · themes: {themes}"),
    "fa.class": ("资产类别", "Asset class"),
    "fa.weight": ("最终权重", "Final weight"),
    "fa.base": ("落位 base", "Base"),
    "fa.base_score": ("base 评分", "Base score"),
    "fa.friction": ("摩擦", "Friction"),
    "fa.council": ("🧑‍💼 智囊团投票（约 30 选 5，相关度加权，已按此微调上方配置）：共识 **{consensus}**{divergence}",
                   "🧑‍💼 Council vote (top 5 of ~30, relevance-weighted; allocation adjusted): consensus **{consensus}**{divergence}"),
    "fa.divergence": (" · 分歧度 {score:.2f}（{level}，影响力已衰减至 {influence:.0f}%）",
                      " · divergence {score:.2f} ({level}, influence damped to {influence:.0f}%)"),
    "fa.net": ("净仓位信号：{signals}", "Net position signals: {signals}"),
    "fa.members": ("成员：{members}", "Members: {members}"),
    "fa.actions": ("执行清单 + 完整叙述", "Action list & full narrative"),
    "fa.error": ("最终建议暂不可用：{err}", "Final advice unavailable: {err}"),
    # council
    "council.title": ("⑤ 金融分析师智囊团", "⑤ Analyst Council"),
    "council.intro": ("从约 30 位投资大师/流派（西蒙斯、巴菲特、达利欧、塔勒布、伍德…）中，"
                      "按当前策略/资产/局势/适当性等级选出方向最匹配的 5 位，各自给出观点。仅供参考。",
                      "Selects the 5 most directionally relevant of ~30 legends/schools (Simons, Buffett, "
                      "Dalio, Taleb, Wood…) for the current strategy/regime/tier. Views are illustrative."),
    "council.generate": ("召集智囊团", "Convene council"),
    "council.spinner": ("匹配分析师并生成观点（含局势 + 大类观点）...",
                        "Matching analysts and generating views (regime + class views)..."),
    "council.consensus": ("共识研判：**{consensus}** · 候选池 {n} 位{dissent}",
                          "Consensus: **{consensus}** · pool of {n}{dissent}"),
    "council.dissent": (" · 异议：{names}", " · dissent: {names}"),
    "council.divergence": ("分歧度", "Divergence"),
    "council.warning": ("⚠ 智囊团分歧显著：建议降低主观观点权重，以量化基础配置与纪律为主。",
                        "⚠ Council disagreement is high: reduce the weight on subjective views and "
                        "stick to the quant baseline."),
    "council.voice": ("话语权 ×{v:.2f}", "Voice ×{v:.2f}"),
    "council.voice_default": ("话语权 ×1.00（未校准）", "Voice ×1.00 (uncalibrated)"),
    "council.meta": ("{name} — {school}｜相关度 {rel:.2f}｜{voice}｜{stance}",
                     "{name} — {school} | relevance {rel:.2f} | {voice} | {stance}"),
    "council.advice": ("🗣 {text}", "🗣 {text}"),
    "council.tilt": ("📊 仓位倾向：`{tilt}` ｜ 原则：“{signature}”",
                     "📊 Position tilt: `{tilt}` | principle: “{signature}”"),
    "council.calibration": ("📈 话语权校准（风格 IC，{ts}）：最高 {top} · 最低 {bottom}",
                            "📈 Voice calibration (style IC, {ts}): top {top} · bottom {bottom}"),
    "council.disclaimer": ("智囊团为不同投资流派视角的模拟观点，仅供多元参考，不构成投资建议。",
                           "The council is a simulation of different schools, for reference only, "
                           "not investment advice."),
    "council.error": ("智囊团暂不可用：{err}", "Analyst council unavailable: {err}"),
    # menu
    "menu.title": ("策略菜单对比（各自回测）", "Strategy menu (walk-forward backtest)"),
    "menu.col_strategy": ("策略", "Strategy"),
    "menu.col_objective": ("目标", "Objective"),
    "menu.col_cadence": ("调仓", "Cadence"),
    "menu.col_return": ("年化", "Return"),
    "menu.col_vol": ("波动", "Vol"),
    "menu.col_sharpe": ("夏普", "Sharpe"),
    "menu.col_mdd": ("最大回撤", "Max DD"),
    # intel
    "intel.title": ("市场情报（最新财经要闻）", "Market Intel (latest headlines)"),
    "intel.fetch": ("拉取最新情报", "Fetch latest"),
    "intel.spinner": ("抓取最新新闻/快讯...", "Fetching latest headlines..."),
    "intel.meta": ("生成时间 {ts} · 状态 {status} · 话题：{topics}",
                   "Generated {ts} · status {status} · topics: {topics}"),
    "intel.source_language": ("新闻标题保留来源语言（外部抓取内容不做离线机器翻译）。",
                              "Headlines are shown in their source language (external content is not "
                              "machine-translated offline)."),
    # allocation / universe
    "alloc.title": ("配置明细", "Allocation"),
    "alloc.asset": ("资产", "Asset"),
    "alloc.weight": ("权重", "Weight"),
    "alloc.exp_return": ("预期年化", "Exp. return"),
    "alloc.vol": ("年化波动", "Vol"),
    "universe.title": ("完整资产池与准入", "Full Universe & Access"),
    "universe.intro": ("权重为 0 不代表不存在：下表列出全部可投候选及其在当前画像下的准入上限。"
                       "加密货币需 C3 及以上，期货仅对富裕/高净值客群且满足门槛开放。",
                       "Zero weight does not mean unavailable: all candidates and their access caps are "
                       "listed. Crypto requires C3+; futures only for affluent/HNW clients above ticket size."),
    "universe.asset": ("资产", "Asset"),
    "universe.class": ("类别", "Class"),
    "universe.access": ("准入", "Access"),
    "universe.current": ("当前权重", "Current weight"),
    "universe.no_segment": ("不对该客群开放", "Not available to this segment"),
    "universe.no_suitability": ("适当性不足", "Below suitability"),
    "universe.no_tier": ("当前等级不可投", "Not available at this tier"),
    "universe.cap": ("上限 {cap:.0%}", "Cap {cap:.0%}"),
    # macro
    "macro.title": ("大类资产配置建议", "Macro Allocation Advice"),
    "macro.intro": ("结合真实动量、估值分位、新闻情绪与宏观研判的大类观点 + 权益内部风格/行业细分。"
                    "需与个人适当性结合，不构成投资建议。",
                    "Class views from real momentum, valuation percentile, news sentiment and macro "
                    "signals, plus equity style/sector splits. Combine with suitability; not advice."),
    "macro.spinner": ("生成大类配置建议（动量 + 估值 + 新闻 + 宏观）...",
                      "Generating macro advice (momentum, valuation, news, macro)..."),
    "macro.stance": ("观点", "View"),
    "macro.class": ("大类", "Class"),
    "macro.score": ("评分", "Score"),
    "macro.reasons": ("依据", "Rationale"),
    "macro.style": ("**行业/风格细分**：{style}", "**Style / sector split**: {style}"),
    "macro.context": ("**宏观背景**", "**Macro context**"),
    "macro.pmi": ("中国制造业：{v}", "China manufacturing: {v}"),
    "macro.pe": ("A 股估值分位：{v}%", "A-share valuation percentile: {v}%"),
    "macro.regime": ("全球局势：{v}", "Global regime: {v}"),
    "macro.narrative": ("综合研判叙述", "Narrative"),
    "macro.error": ("大类配置建议暂不可用：{err}", "Macro advice unavailable: {err}"),
    # factors
    "factor.title": ("因子透镜筛选", "Factor-Lens Screening"),
    "factor.intro": ("收益代理：动量(+)/短期反转(−)/低波动(−)/抗回撤(−)；"
                     "在线真因子（免费接口）：指数 PE 历史分位(−)/成交额流动性(+)/主力净流入(+)。"
                     "无数据的资产自动降权，不编造。",
                     "Return proxies: momentum(+), short reversal(−), low vol(−), drawdown resistance(−); "
                     "live factors: index PE percentile(−), turnover liquidity(+), main net inflow(+). "
                     "Missing data is down-weighted, never fabricated."),
    "factor.spinner": ("拉取在线因子数据（换手/资金流/PE 分位，有缓存）...",
                       "Fetching live factor data (turnover, flows, PE percentile; cached)..."),
    "factor.rank": ("排名", "Rank"),
    "factor.asset": ("资产", "Asset"),
    "factor.class": ("类别", "Class"),
    "factor.score": ("因子分", "Score"),
    "factor.momentum": ("动量", "Momentum"),
    "factor.vol": ("年化波动", "Vol"),
    "factor.pe": ("PE 分位(10y)", "PE pct (10y)"),
    "factor.flow": ("主力净流入", "Net inflow"),
    "factor.n_live": ("在线因子数", "Live factors"),
    "factor.live_yes": ("在线真因子已启用：是", "Live factors: enabled"),
    "factor.live_no": ("在线真因子已启用：否（离线/接口不可用，已回退收益代理）",
                       "Live factors: off (offline/API unavailable; using return proxies)"),
    "factor.skipped": ("仍不可计算的因子族（需日频个股财务/分析师数据）",
                       "Factor families not computable here (need daily stock/fundamental data)"),
    "factor.error": ("因子筛选不可用：{err}", "Factor screening unavailable: {err}"),
    "factor.kb": ("因子库", "Factor Knowledge Base"),
    "factor.kb_stats": ("共 {n} 个因子 · {c} 个类别 · {r} 条记录",
                        "{n} factors · {c} categories · {r} records"),
    "factor.kb_empty": ("因子库未加载（请设置 ATLAS_FACTOR_DIR）", "Factor library not loaded (set ATLAS_FACTOR_DIR)"),
    "factor.evo": ("因子自进化（自主学习）", "Factor Self-Evolution (autonomous)"),
    "factor.evo_stats": ("项目因子库：共 {n} 个因子 · 来源 {sources} · 已测 IC {ic} 个",
                         "Project factor store: {n} factors · sources {sources} · {ic} with IC"),
    "factor.evo_last": ("上次学习：{last} · 累计 {cycles} 轮 · 距今 {gap}",
                        "Last cycle: {last} · {cycles} cycles · {gap} ago"),
    "factor.evo_how": ("自主学习：后台守护进程定期学习（见 scripts/evolution_daemon.py）；"
                       "每次打开 Atlas 若超过阈值未学习会自动后台补一轮。",
                       "Autonomous learning: the daemon runs on a schedule (scripts/evolution_daemon.py); "
                       "opening Atlas after the threshold triggers a background catch-up."),
    "factor.evo_once": ("立即学习一轮（前台）", "Run one cycle (foreground)"),
    "factor.evo_spinner": ("学习中：研报因子采集 + 实证 IC 测量...", "Learning: report mining + empirical IC..."),
    "factor.evo_bg": ("触发后台学习", "Trigger background learning"),
    "factor.evo_bg_ok": ("已触发后台学习", "Background learning triggered"),
    "factor.evo_bg_fail": ("触发失败", "Trigger failed"),
    "factor.evo_error": ("学习失败：{err}", "Learning failed: {err}"),
    "factor.evo_done": ("本轮：{before} → {after} 个因子（知识库 {kb}，研报 {reports}，"
                        "PDF 深解析 {pdf}，在线 {online}）",
                        "This cycle: {before} → {after} factors (KB {kb}, reports {reports}, "
                        "PDF {pdf}, online {online})"),
    "factor.ic_note": ("IC（信息系数）= 因子值与未来收益的秩相关；|IC| 越大预测力越强。",
                       "IC (information coefficient) = rank correlation with forward returns; larger |IC| = stronger signal."),
    "factor.evo_ic_factor": ("因子", "Factor"),
    # Factor Forge
    "ff.title": ("Factor Forge · 研报因子 → 代码", "Factor Forge · report factor → code"),
    "ff.intro": ("粘贴券商研报里的因子简述（自然语言 + 公式），自动解析为结构化因子，"
                 "生成可执行 Python 代码并做样本验证；确认后可写入 Atlas 因子库。",
                 "Paste a broker-report factor brief (prose + formula); it is parsed into a "
                 "structured factor, compiled to Python and validated on sample data. Confirm to "
                 "write it into the Atlas factor store."),
    "ff.brief": ("研报因子简述", "Factor brief"),
    "ff.placeholder": ("例：\\n资本利得突出量\\n行为金融因子-处置效应\\nCGO = (Close - RP) / Close\\n...",
                       "e.g.\\nCapital gains overhang\\nBehavioral factor - disposition effect\\n"
                       "CGO = (Close - RP) / Close\\n..."),
    "ff.source": ("来源（研报/机构/日期）", "Source (report / institution / date)"),
    "ff.name": ("因子代码名（可选）", "Factor code name (optional)"),
    "ff.forge": ("解析并生成代码", "Parse & generate code"),
    "ff.spinner": ("解析因子并验证生成代码...", "Parsing factor and validating generated code..."),
    "ff.import": ("写入 Atlas 因子库", "Import into Atlas factor store"),
    "ff.import_spinner": ("写入因子库...", "Importing into factor store..."),
    "ff.imported": ("已写入因子库：{name}（{source}）", "Imported into factor store: {name} ({source})"),
    "ff.not_available": ("未检测到 factor-forge 兄弟仓库。设置 FACTOR_FORGE_ROOT 或把 factor-forge 放在 Atlas 同级目录。",
                         "No factor-forge sibling checkout detected. Set FACTOR_FORGE_ROOT or place "
                         "factor-forge next to Atlas."),
    "ff.error": ("Factor Forge 失败：{err}", "Factor Forge failed: {err}"),
    "ff.preview": ("结构化因子预览", "Structured factor preview"),
    "ff.code": ("生成的 Python 代码", "Generated Python code"),
    "ff.validation": ("样本验证：{status} — {msg}", "Sample validation: {status} — {msg}"),
    "ff.direction": ("方向", "Direction"),
    "ff.operator": ("算子", "Operator"),
    "ff.category": ("类别", "Category"),
    "ff.fields": ("所需数据字段", "Required data fields"),
    "ff.import_note": ("写入后会出现在因子库/自进化统计中，source=factor_forge。",
                       "Once imported it appears in the factor store/evolution stats with "
                       "source=factor_forge."),
    "ff.pdf": ("上传研报 PDF（可选，需要 PyMuPDF）", "Upload a report PDF (optional, needs PyMuPDF)"),
    "ff.pdf_parse": ("解析 PDF 研报", "Parse PDF"),
    "ff.pdf_spinner": ("解析 PDF 并提取因子简述...", "Parsing PDF and extracting factor briefs..."),
    "ff.pdf_none": ("未在 PDF 中找到可用的因子简述。", "No usable factor brief found in the PDF."),
    "ff.pdf_briefs": ("PDF 候选因子", "PDF factor candidates"),
    "ff.pdf_use": ("使用该候选因子", "Use this candidate"),
    "ff.evaluate": ("在 Atlas 资产池验证 IC", "Validate IC on the Atlas panel"),
    "ff.eval_spinner": ("在 Atlas 月度资产池上计算截面 IC...",
                        "Computing cross-sectional IC on the Atlas monthly panel..."),
    "ff.eval_title": ("Atlas 资产池验证", "Atlas panel validation"),
    "ff.ic": ("平均 RankIC", "Mean RankIC"),
    "ff.icir": ("ICIR", "ICIR"),
    "ff.tstat": ("t 值", "t-stat"),
    "ff.positive": ("IC>0 占比", "IC>0 share"),
    "ff.periods": ("截面期数", "Cross-sections"),
    "ff.direction_match": ("方向一致", "Direction match"),
    "ff.eval_unavailable": ("无法在 Atlas 面板验证：{reason}",
                            "Cannot validate on the Atlas panel: {reason}"),
    # Custom forged-factor composite
    "custom.title": ("自定义因子评分（Factor Forge）", "Custom factor scores (Factor Forge)"),
    "custom.intro": ("把已写入因子库、可通过 Atlas 面板验证的 Factor Forge 因子做成截面 z-score，"
                     "按方向与 |IC| 加权，输出最近几个月的资产综合评分。仅作研究证据，不自动进入优化器。",
                     "Turns forged Factor Forge factors that can be evaluated on the Atlas panel into "
                     "cross-sectional z-scores, signs/weights them by direction and |IC|, and averages "
                     "the latest months into an asset score. Research evidence only; not fed to the optimizer."),
    "custom.run": ("计算 / 刷新自定义因子评分", "Compute / refresh custom scores"),
    "custom.spinner": ("在 Atlas 面板上计算自定义因子 IC 与综合评分...",
                       "Computing forged-factor IC and composite scores on the Atlas panel..."),
    "custom.none": ("因子库中还没有可执行的 Factor Forge 因子。先在 Factor Forge 面板生成并写入。",
                    "No executable Factor Forge factors in the store yet. Forge and import one first."),
    "custom.not_ready": ("暂无可评分结果：{reason}", "No scores yet: {reason}"),
    "custom.meta": ("生成于 {ts} · {n} 个可用因子 · 近期 {months} 个月均值",
                    "Generated {ts} · {n} usable factors · latest {months} months"),
    "custom.col_factor": ("因子", "Factor"),
    "custom.col_ic": ("平均 IC", "Mean IC"),
    "custom.col_icir": ("ICIR", "ICIR"),
    "custom.col_t": ("t 值", "t-stat"),
    "custom.col_weight": ("权重", "Weight"),
    "custom.col_match": ("方向一致", "Direction match"),
    "custom.factors": ("参与评分的因子", "Factors in the composite"),
    "custom.top": ("综合评分最高", "Top assets"),
    "custom.bottom": ("综合评分最低", "Bottom assets"),
    "custom.asset": ("资产", "Asset"),
    "custom.score": ("综合分", "Score"),
    # report
    "report.title": ("完整报告", "Full report"),
    "report.zh_only": ("完整 Markdown 报告目前由中文分析层生成；切换英文时此处不展示，"
                       "上方表格与图表仍提供全部数值。",
                       "The full Markdown report is generated by the Chinese analysis layer; it is hidden "
                       "in English mode. All numbers remain available in the tables and charts above."),
    # misc
    "common.yes": ("是", "Yes"),
    "common.no": ("否", "No"),
    "common.none": ("无", "None"),
    "common.hours": ("{h:.1f} 小时", "{h:.1f} h"),
    "common.never": ("从未", "never"),
    # Kairos ecosystem
    "kairos.title": ("Kairos 生态联动", "Kairos Ecosystem"),
    "kairos.intro": ("Atlas 与同目录的 Kairos 量化套件联动：复用 kairos-data 的真实 ETF 行情、"
                     "kairos-risk 的 VaR/ES 与风险分解、kairos-research 的研究结论。"
                     "未检测到兄弟仓库时自动降级，不影响原有功能。",
                     "Atlas links to the sibling Kairos quant suite: kairos-data real ETF prices, "
                     "kairos-risk VaR/ES and risk decomposition, and kairos-research findings. "
                     "Missing siblings degrade gracefully."),
    "kairos.root": ("Kairos 根目录", "Kairos root"),
    "kairos.packages": ("已检测包", "Detected packages"),
    "kairos.data": ("真实 ETF 数据", "Real ETF data"),
    "kairos.data_line": ("{n} 只 ETF · 目录 {dir}", "{n} ETFs · {dir}"),
    "kairos.mapped": ("可映射 Atlas 资产", "Mapped Atlas assets"),
    "kairos.mapped_line": ("{n} 个：{ids}", "{n}: {ids}"),
    "kairos.research": ("研究结论（kairos-research）", "Research findings (kairos-research)"),
    "kairos.findings": ("关键发现", "Key findings"),
    "kairos.champions": ("稳健策略短名单", "Robust strategy shortlist"),
    "kairos.risk": ("Kairos 风险叠加", "Kairos risk overlay"),
    "kairos.var": ("历史 VaR 95% / 99%", "Historical VaR 95% / 99%"),
    "kairos.es": ("期望损失 ES 95% / 99%", "Expected shortfall 95% / 99%"),
    "kairos.dr": ("分散化比率", "Diversification ratio"),
    "kairos.effn": ("有效资产数", "Effective N"),
    "kairos.class_risk": ("类别风险贡献", "Risk contribution by class"),
    "kairos.not_found": ("未检测到 Kairos 兄弟仓库。设置 KAIROS_ROOT 或把 kairos-* 放在 Atlas 同级目录。",
                         "No Kairos sibling checkout detected. Set KAIROS_ROOT or place kairos-* next to Atlas."),
    "kairos.source": ("来源：{src} · {n} 个月度观测", "Source: {src} · {n} monthly observations"),
    "kairos.col_metric": ("指标", "Metric"),
    "kairos.col_value": ("值", "Value"),
    "kairos.col_unit": ("单位", "Unit"),
    "kairos.col_source": ("来源", "Source"),
    "kairos.col_strategy": ("策略", "Strategy"),
    "kairos.col_score": ("稳健分", "Robustness"),
    "kairos.col_rank": ("排名", "Rank"),
    # Kairos Strategy Lab
    "lab.title": ("Kairos 策略实验室", "Kairos Strategy Lab"),
    "lab.intro": ("把 kairos-strategies 的 106 个原创策略跑在 kairos-data 的真实 ETF 日线面板上，"
                  "按夏普/回撤/换手对比；结果缓存在本地。仅展示 long-only 策略。",
                  "Runs the 106 original kairos-strategies strategies on the real ETF daily panel "
                  "from kairos-data, ranked by Sharpe/drawdown/turnover; cached locally. Long-only only."),
    "lab.run": ("运行 / 刷新策略实验室", "Run / refresh lab"),
    "lab.spinner": ("运行 106 个策略（约 30 秒，结果会缓存）...",
                    "Running 106 strategies (~30s, results are cached)..."),
    "lab.cached": ("已缓存：{ts} · {n} 个 long-only 策略 · 数据 {start} → {end}",
                   "Cached: {ts} · {n} long-only strategies · data {start} → {end}"),
    "lab.no_cache": ("还没有缓存。点击上方按钮运行一次。",
                     "No cache yet. Click the button above to run once."),
    "lab.not_available": ("未检测到 kairos-strategies 或 kairos-data，策略实验室不可用。",
                          "kairos-strategies or kairos-data not detected; lab unavailable."),
    "lab.col_channel": ("渠道", "Channel"),
    "lab.col_cagr": ("年化", "CAGR"),
    "lab.col_vol": ("波动", "Vol"),
    "lab.col_sharpe": ("夏普", "Sharpe"),
    "lab.col_mdd": ("最大回撤", "Max DD"),
    "lab.col_turnover": ("换手", "Turnover"),
    "lab.select": ("选择策略查看净值", "Select a strategy to inspect"),
    "lab.show": ("查看净值曲线", "Show equity curve"),
    "lab.equity": ("净值曲线（{name}）", "Equity curve ({name})"),
    "lab.description": ("思路：{text}", "Idea: {text}"),
    "lab.params": ("参数：{params}", "Params: {params}"),
    "lab.error": ("策略实验室失败：{err}", "Strategy lab failed: {err}"),
    # Satellite overlay
    "sat.title": ("卫星策略叠加", "Satellite strategy overlay"),
    "sat.none": ("不启用", "None"),
    "sat.budget": ("卫星仓位上限 (%)", "Max satellite budget (%)"),
    "sat.help": ("把 Kairos 策略实验室中某个策略的最新权重作为卫星仓位叠加到基础配置；"
                 "实际投资额取决于策略自身的仓位，且始终受适当性类别上限约束。",
                 "Blends the latest weights of a Kairos lab strategy into the base plan as a "
                 "satellite sleeve; actual exposure follows the strategy's own cash level and is "
                 "always clipped to suitability caps."),
    "sat.applied": ("已叠加卫星策略：{name}（{channel}）· 预算上限 {budget:.0%} · "
                    "组合实际仓位 {actual:.1%}（策略自身投资比例 {invested:.0%}）· "
                    "Atlas 覆盖率 {coverage:.0%}",
                    "Satellite overlay applied: {name} ({channel}) · budget cap {budget:.0%} · "
                    "actual portfolio weight {actual:.1%} (strategy invested {invested:.0%}) · "
                    "Atlas coverage {coverage:.0%}"),
    "sat.coverage_low": ("该策略只有 {coverage:.0%} 的权重能映射到 Atlas 资产池，叠加效果有限。",
                         "Only {coverage:.0%} of this strategy maps onto the Atlas universe; "
                         "the overlay has limited effect."),
}


def t(key: str, lang: str = "zh", **fmt) -> str:
    zh, en = S.get(key, (key, key))
    text = en if lang == "en" else zh
    if fmt:
        try:
            text = text.format(**fmt)
        except (KeyError, ValueError):
            pass
    return to_hant(text) if lang == "zh-Hant" else text


@lru_cache(maxsize=4096)
def to_hant(text: str) -> str:
    if not text or zhconv is None:
        return text
    try:
        return zhconv.convert(text, "zh-hant")
    except Exception:  # noqa: BLE001 - never break rendering over a glyph
        return text


def pick(zh: str, en: str, lang: str) -> str:
    text = en if lang == "en" else zh
    return to_hant(text) if lang == "zh-Hant" else text


def question_text(q, lang: str) -> str:
    return q[2] if lang == "en" else pick(q[1], q[1], lang)


def option_text(opt, lang: str) -> str:
    return opt[1] if lang == "en" else pick(opt[0], opt[0], lang)


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------
_CLASS = {
    "cash": ("现金", "Cash"),
    "fixed_income": ("固定收益", "Fixed income"),
    "hybrid": ("固收+", "Hybrid"),
    "commodity": ("商品", "Commodities"),
    "equity_cn": ("中国股票", "China equities"),
    "equity_global": ("海外股票", "Global equities"),
    "crypto": ("加密货币", "Crypto"),
    "futures": ("期货", "Futures"),
}

_OBJECTIVE = {
    "max_sharpe": ("最大夏普", "Max Sharpe"),
    "mean_variance": ("均值方差", "Mean-variance"),
    "min_vol": ("最小波动", "Min volatility"),
    "risk_parity": ("风险平价", "Risk parity"),
    "equal": ("等权", "Equal weight"),
}

_CADENCE = {
    "high": ("高频（月度）", "High (monthly)"),
    "mid": ("中频（季度）", "Mid (quarterly)"),
    "low": ("低频（年度）", "Low (annual)"),
}

_STANCE = {
    "超配": ("超配", "Overweight"),
    "标配": ("标配", "Neutral"),
    "低配": ("低配", "Underweight"),
    "偏进攻": ("偏进攻", "Offensive"),
    "中性": ("中性", "Neutral"),
    "偏防御": ("偏防御", "Defensive"),
}

_DIVERGENCE = {
    "高度共识": ("高度共识", "Strong consensus"),
    "中度分歧": ("中度分歧", "Moderate disagreement"),
    "高度分歧": ("高度分歧", "High disagreement"),
}

_REGIME = {
    "风险偏好回升 (risk-on)": ("风险偏好回升 (risk-on)", "Risk-on"),
    "避险情绪主导 (risk-off)": ("避险情绪主导 (risk-off)", "Risk-off"),
    "中性/观望": ("中性/观望", "Neutral / wait-and-see"),
    "数据不可用": ("数据不可用", "Data unavailable"),
    "未知": ("未知", "Unknown"),
}

_THEME = {
    "地缘冲突": ("地缘冲突", "Geopolitical conflict"),
    "贸易/关税": ("贸易/关税", "Trade & tariffs"),
    "央行/利率": ("央行/利率", "Central banks & rates"),
    "通胀/就业": ("通胀/就业", "Inflation & jobs"),
    "增长/景气": ("增长/景气", "Growth"),
    "资本市场政策": ("资本市场政策", "Capital-market policy"),
}

_BASE_CATEGORY = {
    "onshore": ("境内", "Onshore"),
    "crossborder": ("跨境通道", "Cross-border"),
    "offshore": ("离岸", "Offshore"),
}

_SEGMENT = {
    "mass": ("大众客群", "Mass retail"),
    "mass_affluent": ("富裕客群", "Mass affluent"),
    "hnw": ("高净值客群", "High net worth"),
}

_NOTE = {
    "部分国际指数(东财源)暂不可用": ("部分国际指数(东财源)暂不可用",
                          "Some international indices unavailable (Eastmoney)"),
    "实时接口暂不可用，展示缓存数据": ("实时接口暂不可用，展示缓存数据",
                          "Live source unavailable; showing cached data"),
    "全球指数数据暂不可用": ("全球指数数据暂不可用", "Global index data unavailable"),
}

_SOURCE = {
    "东财快讯": ("东财快讯", "Eastmoney flash"),
    "新闻联播": ("新闻联播", "CCTV News"),
    "财经日历": ("财经日历", "Econ calendar"),
    "东方财富-全球财经快讯": ("东方财富-全球财经快讯", "Eastmoney global flash"),
}

_INDEX = {
    "上证指数": ("上证指数", "Shanghai Composite"),
    "深证成指": ("深证成指", "Shenzhen Component"),
    "创业板指": ("创业板指", "ChiNext"),
    "沪深300": ("沪深300", "CSI 300"),
    "恒生指数": ("恒生指数", "Hang Seng"),
    "标普500": ("标普500", "S&P 500"),
    "纳斯达克": ("纳斯达克", "Nasdaq"),
    "道琼斯": ("道琼斯", "Dow Jones"),
    "日经225": ("日经225", "Nikkei 225"),
    "韩国KOSPI": ("韩国KOSPI", "KOSPI"),
    "印度SENSEX": ("印度SENSEX", "SENSEX"),
    "新加坡海峡时报": ("新加坡海峡时报", "STI"),
    "澳洲标普200": ("澳洲标普200", "ASX 200"),
    "英国富时100": ("英国富时100", "FTSE 100"),
    "德国DAX": ("德国DAX", "DAX"),
    "法国CAC40": ("法国CAC40", "CAC 40"),
    "加拿大TSX": ("加拿大TSX", "TSX"),
}

_REGION = {
    "中国内地": ("中国内地", "Mainland China"),
    "亚太": ("亚太", "Asia-Pacific"),
    "欧洲": ("欧洲", "Europe"),
    "美洲": ("美洲", "Americas"),
}

_ASSET_TYPE = {
    "cash_deposit": ("现金/存款/货基", "Cash / deposits / MMF"),
    "a_share": ("A股/境内股票", "A-shares / onshore stocks"),
    "cn_fund": ("境内公募基金", "Onshore mutual funds"),
    "bank_wm": ("银行理财/信托", "Bank WM / trusts"),
    "bond": ("债券/债基", "Bonds / bond funds"),
    "realestate": ("房产", "Real estate"),
    "insurance": ("保险(储蓄型)", "Savings insurance"),
    "hk_us_stock": ("港股/美股", "HK / US stocks"),
    "overseas_fund": ("境外基金", "Offshore funds"),
    "crypto": ("加密货币", "Crypto"),
    "gold": ("黄金/贵金属", "Gold / precious metals"),
    "other": ("其他", "Other"),
}

_ACCOUNT = {
    "none": ("暂无境外账户", "No overseas account"),
    "hk": ("香港券商/银行", "HK broker / bank"),
    "us": ("美国券商", "US broker"),
    "sg": ("新加坡", "Singapore"),
    "other_offshore": ("其他离岸", "Other offshore"),
}

_LIQUIDITY = {
    "low": ("低（长期不动用）", "Low (long-term)"),
    "medium": ("中", "Medium"),
    "high": ("高（随时可能用）", "High (may need anytime)"),
}

_STRATEGY_PHILOSOPHY = {
    "steady_carry": (
        "放大固收的确定性现金流，几乎不承担权益波动；用货基+纯债+短久期构建，目标是低回撤的稳定增值。",
        "Amplify the certainty of fixed-income cash flow with minimal equity risk; MMF + pure bonds + "
        "short duration, targeting steady growth with low drawdown.",
    ),
    "balanced_core": (
        "股债商均衡的核心仓位，用最大夏普在低相关资产间分散，牺牲少量收益换取显著更平滑的净值。",
        "A balanced equity/bond/commodity core using max-Sharpe diversification across low-correlation "
        "assets: give up some return for a materially smoother path.",
    ),
    "global_equity_momentum": (
        "放大权益资产的长期增长溢价，集中在高夏普的宽基与科技指数，用季度调仓捕捉动量、控制换手。",
        "Amplify the long-run equity premium in high-Sharpe broad/tech indices; quarterly rebalancing "
        "captures momentum while controlling turnover.",
    ),
    "all_weather_risk_parity": (
        "不预测方向，让每类资产对组合风险的贡献相等；放大分散化优势，在任何宏观环境下都不被单一资产绑架。",
        "No directional bets: equal risk contribution across classes, so no single asset dominates in "
        "any macro regime.",
    ),
    "aggressive_frontier": (
        "放大高成长资产(纳指/科创/加密)的弹性，用均值方差在高波动资产里找最优风险补偿；高频调仓及时止盈止损。",
        "Amplify high-growth assets (Nasdaq/STAR/crypto) via mean-variance optimization; frequent "
        "rebalancing to take profit and cut risk.",
    ),
    "crypto_barbell": (
        "哑铃结构：一端极安全(货基/短债)保流动性，一端高弹性(主流币)博非对称收益，规避中间地带；只适合明确能承受归零风险的资金。",
        "Barbell: ultra-safe cash/short bonds for liquidity plus high-beta major crypto for asymmetric "
        "upside; only for capital that can tolerate a total loss.",
    ),
}

_SCHOOL = {
    "GARP 成长": ("GARP 成长", "GARP growth"),
    "事件驱动": ("事件驱动", "Event-driven"),
    "价值+科技逆向": ("价值+科技逆向", "Value + contrarian tech"),
    "价值/护城河": ("价值/护城河", "Value / moat"),
    "债券之王": ("债券之王", "Bond king"),
    "全天候/风险平价": ("全天候/风险平价", "All-weather / risk parity"),
    "全球逆向": ("全球逆向", "Global contrarian"),
    "反脆弱/尾部对冲": ("反脆弱/尾部对冲", "Antifragile / tail hedge"),
    "周期/第二层思维": ("周期/第二层思维", "Cycles / second-level thinking"),
    "因子投资": ("因子投资", "Factor investing"),
    "均值回归/估值": ("均值回归/估值", "Mean reversion / valuation"),
    "宏观/反身性": ("宏观/反身性", "Macro / reflexivity"),
    "宏观集中": ("宏观集中", "Concentrated macro"),
    "宏观风控": ("宏观风控", "Macro risk control"),
    "成长动量 CANSLIM": ("成长动量 CANSLIM", "Growth momentum / CANSLIM"),
    "成长调研": ("成长调研", "Growth research"),
    "指数/低成本": ("指数/低成本", "Index / low cost"),
    "机构/风险配置": ("机构/风险配置", "Institutional / risk allocation"),
    "海龟趋势跟踪": ("海龟趋势跟踪", "Turtle trend following"),
    "深度价值": ("深度价值", "Deep value"),
    "激进逆向价值": ("激进逆向价值", "Aggressive contrarian value"),
    "科技/风险成长": ("科技/风险成长", "Tech / venture growth"),
    "绝对价值/现金": ("绝对价值/现金", "Absolute value / cash"),
    "耶鲁捐赠模型": ("耶鲁捐赠模型", "Yale endowment model"),
    "质量/多元思维": ("质量/多元思维", "Quality / mental models"),
    "趋势交易": ("趋势交易", "Trend trading"),
    "逆向深度价值": ("逆向深度价值", "Contrarian deep value"),
    "量化/凯利公式": ("量化/凯利公式", "Quant / Kelly"),
    "量化统计套利": ("量化统计套利", "Quant statistical arbitrage"),
    "颠覆式创新": ("颠覆式创新", "Disruptive innovation"),
}


def class_label(cls: str, lang: str) -> str:
    return pick(*_CLASS.get(cls, (cls, cls)), lang)


def objective_label(obj: str, lang: str) -> str:
    return pick(*_OBJECTIVE.get(obj, (obj, obj)), lang)


def cadence_label(cadence: str, lang: str) -> str:
    return pick(*_CADENCE.get(cadence, (cadence, cadence)), lang)


def stance_label(stance: str, lang: str) -> str:
    return pick(*_STANCE.get(stance, (stance, stance)), lang)


def divergence_label(level: str, lang: str) -> str:
    return pick(*_DIVERGENCE.get(level, (level, level)), lang)


def regime_label(regime: str, lang: str) -> str:
    return pick(*_REGIME.get(regime, (regime, regime)), lang)


def theme_label(theme: str, lang: str) -> str:
    return pick(*_THEME.get(theme, (theme, theme)), lang)


def base_category_label(cat: str, lang: str) -> str:
    return pick(*_BASE_CATEGORY.get(cat, (cat, cat)), lang)


def segment_label(segment: str, lang: str) -> str:
    return pick(*_SEGMENT.get(segment, (segment, segment)), lang)


def note_label(note: str, lang: str) -> str:
    return pick(*_NOTE.get(note, (note, note)), lang)


def source_label(source: str, lang: str) -> str:
    return pick(*_SOURCE.get(source, (source, source)), lang)


def index_label(name: str, lang: str) -> str:
    return pick(*_INDEX.get(name, (name, name)), lang)


def region_label(region: str, lang: str) -> str:
    return pick(*_REGION.get(region, (region, region)), lang)


def asset_type_label(asset_id: str, lang: str) -> str:
    return pick(*_ASSET_TYPE.get(asset_id, (asset_id, asset_id)), lang)


def account_label(account_id: str, lang: str) -> str:
    return pick(*_ACCOUNT.get(account_id, (account_id, account_id)), lang)


def liquidity_label(key: str, lang: str) -> str:
    return pick(*_LIQUIDITY.get(key, (key, key)), lang)


def strategy_name(strategy, lang: str) -> str:
    return strategy.name_en if lang == "en" else pick(strategy.name_zh, strategy.name_zh, lang)


def strategy_philosophy(strategy, lang: str) -> str:
    zh, en = _STRATEGY_PHILOSOPHY.get(strategy.id, (strategy.philosophy, strategy.philosophy))
    return pick(zh, en, lang)


def school_label(school: str, lang: str) -> str:
    return pick(*_SCHOOL.get(school, (school, school)), lang)


def tier_label(tier_info: dict, lang: str) -> str:
    return tier_info.get("label_en", tier_info.get("label_zh", "")) if lang == "en" \
        else pick(tier_info.get("label_zh", ""), "", lang)


def asset_name(asset, lang: str) -> str:
    return asset.name_en if lang == "en" else pick(asset.name_zh, asset.name_zh, lang)


def analyst_name(view: dict, lang: str) -> str:
    return view.get("name_en", view.get("name_zh", "")) if lang == "en" \
        else pick(view.get("name_zh", ""), "", lang)


def analyst_name_by_id(analyst_id: str, lang: str) -> str:
    from invest_agent.analysts import REGISTRY
    a = next((x for x in REGISTRY if x.id == analyst_id), None)
    if a is None:
        return analyst_id
    return a.name_en if lang == "en" else pick(a.name_zh, "", lang)


def analyst_name_from_zh(name_zh: str, lang: str) -> str:
    if lang != "en":
        return pick(name_zh, "", lang)
    from invest_agent.analysts import REGISTRY
    a = next((x for x in REGISTRY if x.name_zh == name_zh), None)
    return a.name_en if a else name_zh