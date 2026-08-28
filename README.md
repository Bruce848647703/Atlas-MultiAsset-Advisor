# Atlas · 多元资产投资顾问 Agent (Multi-Asset Investment Advisor)

> 基于 DeepSeek 工具调用 harness 的个人投资 Agent：跨**股票/基金、债券、黄金、加密货币、期货**多资产类别，
> 通过**问卷 + 对话推断**评估投资者适当性（C1～C5），按**适合性约束下的量化权重**给出配置，
> 用**收益曲线、有效前沿、目标投射等图表**直观呈现长期复利，激发理性投资动力。

**English**: An LLM-agent that profiles an investor's risk tolerance (questionnaire + conversational
inference), then runs a deterministic quant core — Ledoit-Wolf shrinkage estimators, mean-variance
allocation under suitability caps, monthly-rebalance backtesting — over a multi-asset universe
(CN/global equity ETFs, bonds, gold, crypto, managed futures), and presents the plan with
motivational-but-honest charts. Built on a DeepSeek tool-calling harness; fully runnable offline.

> **免责声明**: 本项目是量化研究与工程演示，输出不构成投资建议。市场有风险，投资需谨慎。
> This project is research/engineering material, NOT licensed investment advice.

---

## 1. 设计观察：不同阶层的投资者约束不同 (Strata-aware design)

专业性首先体现在**客群分层**：同样的收益率目标，对不同本金规模意味着完全不同的约束。

| 客群 | 可投资本 | 核心约束 | 配置框架 | 产品准入 |
|---|---|---|---|---|
| 大众 (mass) | < 20万 | 试错成本高、流动性约束紧 | 指数定投核心 + 应急金优先 | 基金/ETF/黄金；**禁期货** |
| 富裕 (mass_affluent) | 20万–100万 | 财富积累期，房贷并存 | 核心-卫星-机会三层 | + 管理型期货(限额) |
| 高净值 (hnw) | > 100万 | 跨周期保值、尾部风险 | 机构化多资产+衍生品对冲 | 全资产类别 |

分层与**适当性等级**（C1 保守 → C5 激进，对标国内投资者适当性管理惯例）交叉生效：
任何建议都必须同时通过两道闸门（见 `config/risk_profiles.yaml`），优化器层面硬约束、报告层面双重校验。

## 2. 架构 (Architecture)

```
                        ┌──────────────────────────────────────────┐
  投资者                │              InvestAgent                 │
  (提问/回答)  ◄──────► │  DeepSeek harness (tool-calling loop)    │
                        │  llm.py + harness.py + tools/            │
                        └───────┬──────────────────────────────┬───┘
                    ask_investor │                              │ assess / build / charts / intel
                                ▼                              ▼
                        ┌────────────────┐        ┌────────────────────────┐
                        │ 风险画像        │        │ 量化核心 (确定性、可测)   │
                        │ risk_profiler  │───────►│ personas: 分层准入       │
                        │ 问卷+关键词+LLM │        │ advisor.build_plan()     │
                        └────────────────┘        │  ├ 数据层 (synthetic/akshare)
                                                  │  ├ 策略层 strategy.py ★    │
                                                  │  ├ 收缩估计 (Ledoit-Wolf) │
                                                  │  └ 回测/目标投射          │
                                                  └────────────┬───────────┘
                        ┌────────────────┐                     ▼
                        │ 市场情报        │        report.py + charts.py
                        │ intel.py (新闻/ │        (PNG/Markdown)
                        │ 研报快讯, 话题归类)│
                        └────────────────┘
```

关键原则：**量化核心完全确定性**（无 LLM 也能出方案，便于单测与训练数据生成）；
**LLM 是对话界面**，通过 18 个工具驱动核心：

| 工具 | 作用 |
|---|---|
| `ask_investor` | 直接向投资者提问（挂起循环等待回答） |
| `assess_risk_profile` | 问卷答案/原话 → 适当性等级 + 类别上限 |
| `get_market_summary` | 资产池历史表现摘要 |
| `list_strategies` | 列出策略菜单（哲学/目标/调仓频率/适用等级） |
| `build_investment_plan` | 自动选择或指定策略，生成配置方案 |
| `apply_timing_views` | 保存主观择时观点（文本或 {类别: 倾斜度}），注入下一次配置 |
| `get_market_intel` | 拉取最新数日财经新闻/快讯并按话题归类（加密/美股/债券/商品/宏观） |
| `get_macro_advice` | 大类资产配置建议（超配/标配/低配+行业风格细分，融合动量/估值/新闻/宏观） |
| `get_global_situation` | 全球政经局势研判（实时新闻聚合+风险偏好+主导议题） |
| `get_global_indices` | 全球主要指数实时行情看板（中国内地/亚太/欧洲/美洲，双源+缓存+降级） |
| `get_asset_profile_questionnaire` | 资产画像问卷结构（资产类型/境外占比/境外账户/流动性） |
| `recommend_global_bases` | 家办式全球落位建议（境内/跨境/离岸 base 打分+摩擦评估） |
| `get_final_advice` | 最终综合建议（量化×大类×地缘×落位 有机融合 + 执行清单） |
| `evolve_factor_library` | 因子自进化（导入知识库+从真实数据实证学习因子测IC+在线搜集） |
| `get_factor_knowledge` | 从因子库检索因子定义/公式/逻辑/收益方向 |
| `screen_assets_by_factors` | 用因子透镜给资产池打分排序（动量/反转/低波动/抗回撤） |
| `generate_charts` | 4 张图：配置环图、风险-收益地图、净值+回撤、目标投射 |
| `explain_product` | 产品风险教育（先风险后收益） |

### 需求理解 + 主观择时 ★

- **需求理解**（`requirement.py`）：把投资者自由文本解析为结构化需求
  `{风险倾向, 择时观点, 兴趣资产, 期限}`，情绪感知（"加密要暴跌清仓"不会被误读成
  风险偏好高）。基准见 `training/eval/eval_requirement.py`（36 检查）。
- **主观择时**（`timing.py`）：多空观点在两处生效——① 策略选择对齐度
  （"看空股票避险"→旋转到防御策略）② 倾斜注入预期收益再优化。**只影响当前
  配置，历史回测保持诚实**，且受适当性上限约束。页面侧边栏有择时滑块。

### 全球市场指数看板 ★（`global_indices.py`，形象工程·常驻）

页面顶部常驻展示全球主要指数（现价/涨跌/交易状态），按区域分组：
**中国内地**（上证/深成/创业板/沪深300）· **亚太**（恒指/日经/韩KOSPI/印SENSEX/
新海峡时报/澳标普200）· **欧洲**（富时100/DAX/CAC40）· **美洲**（标普500/纳指/道指/加TSX）。

**双源可靠性设计**（形象工程必须常亮）：
- 主源 **腾讯行情**（极稳定，覆盖中美港）+ 扩展源 **东财**（日欧亚太，尽力而为）
- 重试退避 + 5 分钟 TTL 缓存 + 失败降级（旧缓存 > 空），接口抖动不影响展示
- 按当前 UTC 时间推算各区域 **交易中/已收盘** 状态（近似，忽略夏令时）

### 全球政经局势板块 ★（`geopolitics.py`）

独立于投资建议的常显板块：聚合实时新闻（东财快讯/新闻联播/财经日历），
按话题归类（地缘冲突/贸易关税/央行利率/通胀就业/增长景气/资本市场政策），
输出**风险偏好评分、研判（risk-on/观望/risk-off）、主导议题、关注事件**。
规则透明可复现，接口失败优雅降级。

### 大类资产配置建议 ★（`macro_advice.py`）

在具体持仓之外的大类观点层，融合四类信号：真实动量（各大类近12月）、
估值分位（跟踪指数PE近10年）、新闻情绪（全球风险偏好）、宏观研判（中国PMI）。
输出各大类**超配/标配/低配 + 依据**，以及权益内部**风格/行业细分**
（成长vs价值、大盘vs中小盘）。确定性打分，每条结论附驱动信号。

### 家办式全球资产落位 ★（`global_base.py`）

家族办公室视角的"降低摩擦"配置层。一个 **base** = 投资者落位/接入全球资产的
地点或通道。内置 12 个全球 base 目录（境内：A股账户/境内公募QDII/银行理财；
跨境通道：沪深港通/债券通/跨境理财通；离岸：港券商/港保险/新家办/美券商/
合规加密交易所/海外不动产），每个 base 标注**摩擦五维**（资本管制/税/汇兑/
准入/合规，0-1）与门槛。

结合**适当性等级 + 资产画像问卷**（现有资产类型/境外占比/境外账户/流动性）打分：
```
score = 100 · (资本适配·资产相关性·风险适配·经验适配) · (1 − λ·摩擦)
```
输出排序的 base 列表（含评分/摩擦/门槛/理由），指导"低摩擦境内打底 → 跨境通道
拓展 → 离岸仅补缺口"，并提示资金合规出境。页面"家办·全球资产落位"板块可视化。

### 最终综合建议 ★（`final_advice.py`，四者有机融合）

前述各层**不是独立的**，由融合层串成一条研判主线，输出最终建议：
```
量化配置(地基) × 大类观点(超配/低配) × 全球政经局势(风险偏好) × 全球落位(摩擦)
        └─ 大类权重倾斜 → 适当性上限约束 → 类内按量化比例再分配 → 每类落最优 base
```
- **地缘 regime 倾斜**：risk-on 加仓风险类/减仓防御类；risk-off 反向并增黄金对冲。
- **大类观点倾斜**：超配×1.22 / 标配×1.0 / 低配×0.68。
- **落位映射**：每类资产落到"支持该类、评分最高"的 base（家办式）。
- 输出：最终大类配置 + 全球落位 + 研判主线叙述 + 执行清单，自动写入报告
  （`build_report(..., final_advice=...)` 的"★ 最终综合建议"章节）。

### 因子自进化 ★（`factors/factor_store.py` + `factor_evolution.py`，**自主学习**）

项目内持久化因子库（`data/factor_store.json`），**无需人工触发、自己成长**：
1. **导入知识库**：外部因子库（1093 因子）批量入库，保留出处；
2. **券商研报采集（标题级）**：拉取研报标题，按因子概念关键词提取因子主题，
   带出处（报告/机构/日期）登记；
3. **研报 PDF 深解析**（`report_pdf_miner.py`）：先跨类型扫描研报接口，
   按关键词（因子/多因子/选股/金融工程/alpha）**定位因子专题研报**，
   下载 PDF→提取全文→挖掘因子概念（估值/股息/景气度/成长/动量/低波/流动性）
   与"XX因子"显式定义，以报告原文论据为证据登记；
4. **实证学习**：从真实数据推导因子信号并测 **IC（信息系数）**，
   数据越多越准（如短期反转 IC≈0.48）。

**自动调度（不用 Atlas 时也在学习）**：
- `make evolve-daemon`：后台守护进程，默认每 6 小时学一轮（`scripts/evolution_daemon.py`）；
- **启动补学**：每次打开页面，若距上次学习 >24h 自动后台补一轮（`maybe_autolearn`）；
- systemd 常驻：`deploy/atlas-evolution.service`；cron 亦可。
学习状态记录在 `data/evolution_state.json`，面板"因子自进化"可见。

### 因子库融合（1000+ 量化因子）★

`invest_agent/factors/` 融合了外部因子库（`signal-name/data/json`，
1837 条记录 / 1093 个因子 / 79 类：动量反转、波动率、流动性、估值、基本面、
行为金融、高频资金流等）：

- **`loader.py` 知识库**: 解析→去重→按类别索引，并从因子说明文本中挖掘
  收益方向先验（"正/负相关"），标记高频因子。
- **`lens.py` 因子透镜**: 双层因子合成一个综合分，缺失自动降权、不编造：
  - *收益代理*（全资产可算）: 动量(+) / 短期反转(−) / 低波动(−) / 抗回撤(−)
  - *在线真因子*（`enrich.py` 走免费 akshare 接口，仅交易所 ETF 有）:
    **估值**=跟踪指数滚动PE近10年分位(−，`stock_index_pe_lg`)；
    **流动性**=log成交额(+)；**资金流**=主力净流入净占比(+)；另有换手率/
    量比/折溢价/市值原始字段（`fund_etf_spot_em`）。
  - 加密/期货代理/场外基金无交易所数据 → 仅用收益代理，权重自动归一。
  - 带 TTL 缓存（盘中快照 4h、估值 24h）；接口不可用时优雅回退。
- **三处落地**: ① 卫星仓（加密袖珍）选币偏好混入因子分；② LLM 工具可检索
  因子知识、解释筛选逻辑；③ SFT 训练样本注入因子筛选理由，让微调后的
  模型学会"用因子说话"。
- 配置: `config/agent.yaml` → `factors.data_dir`（置空则禁用，优雅降级）。

### 策略层（放大优势，而非堆砌资产）★

不是把 26 只资产塞进一个组合，而是 6 个各有哲学的策略，各自：

- **筛选**：类别袖珍上限 + 资产级标签排除（如激进策略剔除红利防御类，稳健策略剔除高贝塔/行业/迷因币）
- **目标**：`max_sharpe` / `mean_variance` / `min_vol` / `risk_parity`
- **调仓频率**：高频(月度) / 中频(季度) / 低频(年度)

| 策略 | 哲学 | 目标 | 调仓 | 适用 |
|---|---|---|---|---|
| 稳健票息 | 放大固收确定性现金流 | min_vol | 低频 | C1-C3 |
| 均衡核心 | 低相关资产最大夏普分散 | max_sharpe | 中频 | C2-C4 |
| 全球权益动量 | 放大权益增长溢价 | max_sharpe | 中频 | C3-C5 |
| 全天候风险平价 | 风险贡献均等，不预测方向 | risk_parity | 低频 | C2-C5 |
| 进取前沿 | 放大高成长弹性 | mean_variance | 高频 | C4-C5 |
| 加密哑铃 | 极安全+高弹性两端 | mean_variance | 高频 | C5 |

画像→策略自动选择：`score = 夏普 − 1.5×波动超界 − 1.2×目标收益缺口`（文本信号按等级门控加成）。
策略菜单会在同一数据上各自回测，页面/报告中展示对比表。


## 3. 快速开始 (Quickstart)

```bash
pip install -r requirements.txt          # numpy/pandas/scipy/matplotlib/openai/pyyaml/akshare

make demo        # 离线 demo: 大众/富裕/高净值三客群 → examples/demo_outputs/
make test        # 36 项单元+集成测试
make eval        # 合规闸门评估(权重合法/上限/免责声明/客群准入)
make sft         # 生成 400 条 SFT 对话 → training/sft_data/train.jsonl

# 交互模式（需要 DeepSeek key 进入对话，否则自动降级为问卷+离线管线）
export DEEPSEEK_API_KEY=***
make chat
```

Streamlit 可视化面板（可选）：`pip install streamlit && make dashboard`

### 输出示例

```
[02_mass_affluent_C3] 富裕客群 · 平衡型 · 家庭支柱，有房贷，想要跑赢通胀
   tier=C3 score=56 E[ret]=8.5% vol=10.6% Sharpe=0.61
   配置: sp500_etf=39.2%, bond_fund=28.1%, csi300_etf=17.7%, gold_etf=15.0%
```
![样例](examples/sample/02_mass_affluent_C3/allocation.png)

## 4. 量化方法 (Quant core)

- **期望收益**: 样本均值向类别先验收缩（δ=0.6），抑制均值估计噪声（Black-Litterman 思想）。
- **协方差**: Ledoit & Wolf (2003) 常数相关目标，解析 oracle 收缩强度（`cov_shrinkage`）。
- **组合优化**: 多目标可选——`mean_variance`(最大化 `w'μ−(λ/2)w'Σw`)、`max_sharpe`(直接最大化
  夏普，多起点)、`min_vol`、`risk_parity`。约束统一为：**类别上限（适当性∩策略袖珍）**、
  单资产 ≤65%（集中度纪律）、无卖空。失败时回退风险平价。
- **策略选择**: 菜单内各策略按其调仓频率独立回测，按
  `夏普 − 波动超界惩罚 − 收益缺口惩罚` 自动匹配画像；可手动指定。
- **回测**: 各策略按自身调仓频率(月/季/年)再平衡，换手×单边费率，指标含
  年化收益/波动/夏普/最大回撤/卡玛/年化换手。
- **情报**: `intel.py` 拉取最新财经快讯并按话题(加密/美股/债券/商品/宏观)归类，缓存 6h。
- **数据**: `SyntheticProvider`（固定种子、含熊市/繁荣期/加密闪崩情景，离线可复现）；
  `AkshareProvider` + `MergedProvider`（真实 A股/海外 ETF、基金、原油净值，加密与期货列由合成补齐）。

## 5. 本地训练与完善 (Local training loop)

1. **数据**: `training/generate_sft_data.py` 用确定性管线当"金牌顾问"，批量合成
   多轮对话（系统提示 + 提问 + 回答 + 合规方案），OpenAI chat JSONL 格式。
2. **微调**: 用 [LLaMA-Factory](https://github.com/hiyouga/LLaMA-Factory) / ms-swift
   微调 `deepseek-r1-distill`（如 7B）模型；配置见 `config/agent.yaml`。
3. **本地推理**: vLLM 起 OpenAI 兼容服务后，`config/agent.yaml` 设 `provider: local` 即可，
   同一套 harness 无缝切换。
4. **评估**: `training/eval/eval_suite.py` 是硬闸门回归测试（权重合法性、适当性上限、
   客群准入、免责声明），每次改配置/模型后必跑；`make test` 覆盖量化核心数值正确性。

```
   ┌─────────────┐   生成    ┌──────────────┐  微调   ┌──────────────────┐
   │ 确定性管线   │ ───────► │ SFT JSONL    │ ─────► │ 本地 DeepSeek 蒸馏 │
   │ (oracle)    │          │ 400+ 对话    │        │ (vLLM/Ollama)     │
   └─────────────┘          └──────────────┘        └────────┬─────────┘
          ▲                                                   │
          └──────────── eval_suite 硬闸门回归 ◄───────────────┘
```

## 6. 项目结构 (Layout)

```
invest_agent/
  harness.py      # DeepSeek 工具调用循环(支持 ask_investor 挂起)
  llm.py          # OpenAI 兼容客户端(官方 API / 本地 vLLM)
  agent.py        # InvestAgent 门面(chat + offline_plan)
  risk_profiler.py# 9 题问卷 + 关键词推断 + 情绪感知 + LLM 画像 prompt
  personas.py     # 客群分层与准入闸门
  strategy.py     # ★ 策略层: 6策略/筛选标准/目标/调仓频率/自动选择
  timing.py       # ★ 主观择时: 文本抽取/收益倾斜注入/策略对齐/聚焦模式
  requirement.py  # ★ 需求理解: 风险+择时+兴趣+期限 结构化解析
  geopolitics.py  # ★ 全球政经局势: 实时新闻聚合+风险偏好+趋势研判
  macro_advice.py # ★ 大类资产配置建议: 动量+估值+新闻+宏观
  global_base.py  # ★ 家办全球落位: 12个base目录+摩擦五维+打分排序
  final_advice.py # ★ 最终综合建议: 量化×大类×地缘×落位 有机融合
  global_indices.py # ★ 全球指数看板: 双源(腾讯+东财)+缓存+降级
  intel.py        # ★ 市场情报: 新闻快讯拉取+话题归类+缓存
  factors/        # ★ 因子: loader / lens / enrich(在线真因子) /
                  #   factor_store(持久化库) / factor_evolution(自进化) /
                  #   report_pdf_miner(研报PDF深解析)
  advisor.py      # 策略驱动的配置管线
  portfolio/      # metrics / optimizer(MV+maxSharpe+minVol+风险平价) /
                  #   backtest(含样本外走查) / tactical(动量+趋势门控)
  data/           # base / synthetic / akshare / universe (26 资产)
  tools/          # 暴露给 LLM 的 18 个工具
  charts.py, report.py, cli.py
config/           # assets.yaml, risk_profiles.yaml, agent.yaml
scripts/run_demo.py         dashboard/app.py (streamlit)
training/         # README(训练流程) / generate_sft_data.py(含择时样例) /
                  # build_real_dataset.py / eval/(合规+需求理解基准) /
                  # finetune/(LLaMA-Factory 数据集注册+LoRA配置)
examples/factor_library_sample/  # 因子库样例(完整库见 factors.data_dir)
tests/            # 108 项测试
.streamlit/config.toml + dashboard/style.py  # Jane Street 风格暗色主题
```

## 6.5 前端风格（Jane Street 式）

对标 janestreet.com 的**明亮极简学术风**：白底 + 近黑字 + 标志性红色点缀
（`#d0001d`）+ 几何无衬线字体（Inter，近似其 Alright Sans）+ 大写字距小节标签 +
细线分隔 + 六边形元素。
- `.streamlit/config.toml`：Streamlit 亮色主题（白底/红主色/近黑字）
- `dashboard/style.py`：注入式 CSS——指标卡、行情表、按钮、侧栏、分隔线、
  顶部红色饰条、小节标签前的红色六边形符号、细滚动条
- 页头：黑色 ATLAS + 红色六边形 SVG（JS 标志性 hex）
- 全球指数看板为单张密集行情表，涨绿/跌红着色（pandas Styler，需 `jinja2>=3.1.2`）

## 7. 部署：让外部机器访问 Dashboard (Deployment)

本机局域网内访问（最直接）：

```bash
pip install streamlit "numpy<1.23"     # 注意: 老环境 scipy 与 numpy2 不兼容, 需钉住
make dashboard-host                     # 0.0.0.0:8501, 带口令门
# 浏览器打开  http://<服务器IP>:8501
```

公网安全部署的推荐结构（nginx 反代 + HTTPS + BasicAuth）：

```
用户浏览器 ──HTTPS(443)──► nginx (证书/认证/限流) ──► 127.0.0.1:8501 (streamlit)
```

```nginx
server {
    listen 443 ssl;
    server_name atlas.example.com;
    # certbot 生成的证书 ...
    auth_basic "Atlas";  auth_basic_user_file /etc/nginx/.htpasswd;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;      # websocket, streamlit 必需
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 1800;
    }
    location ^~ /static/ { proxy_pass http://127.0.0.1:8501; }
    location /_stcore/stream { proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1; proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade"; proxy_read_timeout 1800; }
    location /healthz { proxy_pass http://127.0.0.1:8501; }
}
```

无公网 IP / 防火墙受限时，可用内网穿透：`frp` 或 `ngrok http 8501`。

安全清单：① 务必开启 `ATLAS_ACCESS_TOKEN` 或 nginx 认证（Streamlit 本身无鉴权）；
② 只暴露必要端口；③ 公网环境不要挂真实交易凭据——本项目只读行情，保持现状即可。

## 8. 路线图 (Roadmap)

- [ ] 真实加密/期货数据源接入（ccxt / CTP 行情）
- [ ] Black-Litterman 观点注入（LLM 研报解读 → 观点向量）
- [ ] 再平衡提醒与偏离度监控（定时任务）
- [ ] 蒙特卡洛压力测试与情景分析图
- [ ] 多语言报告；移动端展示

## 参考文献

1. Markowitz, H. (1952). *Portfolio Selection*. Journal of Finance.
2. Ledoit, O., & Wolf, M. (2003). *Honey, I Shrunk the Sample Covariance Matrix*.
3. Maillard, S., Roncalli, T., & Teïletche, J. (2010). *The Properties of Equally Weighted Risk Contribution Portfolios*.
4. 《证券期货投资者适当性管理办法》及配套指引（C1–C5 分级惯例）。
