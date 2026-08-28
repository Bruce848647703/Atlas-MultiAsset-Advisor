# 训练与完善流程 (Training Pipeline)

目标：让 agent 在**策略选择**与**建议生成**上越来越专业。分两条线：

- **量化核心**不需要"学习"——它是确定性的、可单测的数学。它的"完善"靠**在真实数据上回归验证**（见 `eval/` 与 `build_real_dataset.py`）。
- **LLM 层**需要训练——用真实数据构造的"金牌答案"做 SFT，让蒸馏小模型学会本系统的投资逻辑。

```
┌──────────── 真实数据层 ────────────┐
│ build_real_dataset.py              │
│  1) merged provider 拉真实月度收益   │
│  2) 滚动窗口拟合 shrinkage 估计      │
│  3) 每策略 out-of-sample 回测打标    │
│     → backtest_labels.csv (ground truth)
└──────────────┬─────────────────────┘
               │
┌──────────────▼─────────────────────┐
│ 训练样本构造                         │
│  generate_sft_data.py              │
│  确定性管线当 oracle：               │
│  画像 → 策略选择 → 配置 → 合规话术    │
│  (可升级为读取 backtest_labels 做    │
│   真实数据对齐)                      │
│  → sft_data/train.jsonl            │
└──────────────┬─────────────────────┘
               │
┌──────────────▼─────────────────────┐
│ 微调 (LLaMA-Factory / ms-swift)     │
│  base: deepseek-r1-distill-7b      │
│  方法: LoRA/QLoRA, chat 模板        │
└──────────────┬─────────────────────┘
               │
┌──────────────▼─────────────────────┐
│ 本地部署                            │
│  vLLM serve (OpenAI 兼容)           │
│  config/agent.yaml provider=local   │
│  同一套 harness 无缝切换             │
└──────────────┬─────────────────────┘
               │
┌──────────────▼─────────────────────┐
│ 回归闸门                            │
│  eval/eval_suite.py  合规硬闸门      │
│  真实数据 OOS 夏普对比               │
└────────────────────────────────────┘
```

## 一、用真实数据训练/验证（推荐主路径）

1. **拉真实数据并打标**
   ```bash
   python training/build_real_dataset.py --months 120 --out training/real_data
   ```
   产出 `returns.csv`（真实收益面板）、`features.csv`（滚动 12 月收益/波动/夏普）、
   `backtest_labels.csv`（每个策略在每个滚动窗口的**样本外**真实表现）。

2. **什么是"正确策略"的监督信号**
   `backtest_labels.csv` 的 `fwd_sharpe` 就是 ground truth：给定截至 t 的历史，
   哪个策略在未来 6 个月真实夏普最高，就是那个画像下"应该推荐"的策略。
   这避免了用合成数据自嗨——模型学的是**真实市场里验证过的选择**。

3. **把真实标签注入 SFT**
   `generate_sft_data.py` 目前用合成管线当 oracle。把它升级为：
   - 对每个画像，从 `backtest_labels.csv` 取对应窗口的最优策略作为答案；
   - 对话中的回测数字改用真实 OOS 数字，而非合成数字。
   这样微调后的模型输出与真实市场一致。

## 二、策略层的"训练" = 参数校准（不是神经网络）

策略层的优化目标、调仓频率、筛选阈值都是**可用真实数据网格搜索**的超参：

- 对每个策略，用 `walk_forward_labels` 在真实数据上扫 `risk_aversion`、`cadence`、
  `exclude_tags`，选样本外夏普最稳的一组。
- 这一步产出的是**更好的策略定义**（写回 `strategy.py`），而不是模型权重。

## 三、需求理解（理解投资者在说什么）

"理解需求"被拆成可测的结构化任务：`requirement.parse_requirement` 把自由文本解析为
`{风险倾向, 择时观点, 兴趣资产, 期限}`。`eval/eval_requirement.py` 用 10 条人工标注的
自然语言案例（`requirement_cases.jsonl`）打分，当前确定性基线 **36/36 通过**。

```bash
python training/eval/eval_requirement.py
```

这套基准同时是**微调 LLM 的考卷**：让模型对同一批句子输出结构化 JSON，与标注比对，
即可量化"模型是否真的理解需求"。关键设计（也是易错点）：
- **情绪感知**："加密要暴跌了，清仓币圈"里提到币≠风险偏好高，退出词会抑制资产提及的风险加分；
- **风险画像（稳定）与择时（战术）分离**：减仓/避险是择时信号，不改动适当性等级。

## 四、主观择时（让观点进入配置）

`timing.py` + `requirement.py`：投资者的多空观点（文本或 `{类别: 倾斜度[-1,1]}`）被
解析为 `TimingView`，在**两处**生效：
1. **策略选择**：观点与策略袖珍结构对齐度计入选择分（"看空股票避险"→旋转到防御策略）；
2. **权重优化**：倾斜注入预期收益再优化（±1 ≈ ±2 个月波动率 × 确信度）。

原则：**只影响当前配置，历史走查回测保持干净**；且受适当性上限约束（择时不能让
C4 变成全现金）。页面侧边栏有择时滑块 + 一句话输入；工具侧 `apply_timing_views`。

## 五、评估（每次改动后必跑）

```bash
make eval                                   # 合规硬闸门：权重合法/适当性/客群/免责声明
make test                                   # 66 项数值正确性
python training/eval/eval_requirement.py    # 需求理解基准 (36 检查)
python training/build_real_dataset.py       # 真实数据 OOS 各策略夏普排名
```

## 六、微调落地（LLaMA-Factory）

```bash
python training/generate_sft_data.py --n 800 --timing_ratio 0.3   # 生成含择时样例
llamafactory-cli train training/finetune/lora_sft_deepseek.yaml   # LoRA SFT
# 合并后经 vLLM 起 OpenAI 兼容服务, config/agent.yaml provider=local
```
数据集注册见 `finetune/dataset_info.json`，SFT 参数见 `finetune/lora_sft_deepseek.yaml`。

## 六-2、因子自进化（自主学习，无需人工触发）

因子库会**自己成长**，四条增长线 + 自动调度：

- **知识库导入**：外部因子库（1093 因子）入库，保留出处。
- **券商研报采集（标题级）**：拉取研报标题，按因子概念关键词提取因子主题。
- **研报 PDF 深解析**：先扫描研报接口按关键词(因子/多因子/选股/金融工程/alpha)
  定位**因子专题研报**，下载 PDF→提全文→挖因子概念与显式因子定义，
  以报告原文论据为证据登记（`report_pdf_miner.py`，需 `pip install pypdf`）。
- **实证学习**：从真实数据推导因子信号并测 **IC**，数据越多估计越准。

**自动运行方式**（不用 Atlas 时也在学习）：

```bash
make evolve-daemon        # 启动后台守护进程, 默认每6小时学一轮
make evolve-daemon-stop   # 停止
make evolve               # 手动跑一轮(前台)
```
- 守护进程: `scripts/evolution_daemon.py --interval-hours 6`，日志在 `data/evolution_daemon.log`。
- **启动补学**: 每次打开 Atlas 页面，若距上次学习 >24h 会自动后台补一轮
  （`maybe_autolearn`），即使没装守护进程也能周期性学习。
- **systemd 常驻**: `sudo cp deploy/atlas-evolution.service /etc/systemd/system/ && sudo systemctl enable --now atlas-evolution`。
- **cron 替代**: `0 */6 * * * cd /path/to/invest-agent && python3 scripts/evolution_daemon.py --once`。
- 学习状态: `data/evolution_state.json`（last_run/轮数/历史），面板"因子自进化"可见。

## 七、情报能力的评估

`get_market_intel` 拉真实新闻。训练时可把"结合情报调整建议"也写进 SFT：
给模型 (画像 + 配置 + 当日情报) → 期望输出包含对情报的引用与风险提示。
