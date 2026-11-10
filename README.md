# Atlas · Multi-Asset Investment Advisor Agent

[![CI](https://github.com/Bruce848647703/Atlas-MultiAsset-Advisor/actions/workflows/ci.yml/badge.svg)](https://github.com/Bruce848647703/Atlas-MultiAsset-Advisor/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-green.svg)](LICENSE)

> A DeepSeek tool-calling agent for personal investing across **equities/funds,
> bonds, gold, crypto, and futures**. It profiles investor suitability (C1–C5)
> via **questionnaire + conversational inference**, allocates under **suitability
> constraints**, fuses **macro / geopolitical / factor intelligence**, and presents
> plans with honest, motivational charts.

> **Disclaimer**: This project is research/engineering material. Outputs do NOT
> constitute licensed investment advice. Markets carry risk; invest with care.

---

## 1. Strata-Aware Design

Professionalism starts with **client segmentation**: the same return target means
very different constraints at different capital scales.

| Segment | Investable Capital | Core Constraint | Allocation Framework | Product Access |
|---|---|---|---|---|
| Mass | < ¥200k | High cost of mistakes; tight liquidity | Index-DCA core + emergency fund first | Funds/ETFs/gold; **no futures** |
| Mass Affluent | ¥200k–1M | Wealth accumulation; mortgage coexists | Core–satellite–opportunity layers | + managed futures (capped) |
| HNW | > ¥1M | Cross-cycle preservation; tail risk | Institutional multi-asset + derivatives hedging | All asset classes |

Segmentation intersects with the **suitability tier** (C1 conservative → C5
aggressive, following CN investor-suitability convention). Every recommendation
must pass **both gates** (`config/risk_profiles.yaml`) — hard constraints at the
optimizer level, double-checked at the report level.

## 2. Architecture

```
                        ┌──────────────────────────────────────────┐
  Investor              │              InvestAgent                 │
  (Q&A)      ◄────────► │  DeepSeek harness (tool-calling loop)    │
                        │  llm.py + harness.py + tools/            │
                        └───────┬──────────────────────────────┬───┘
                    ask_investor │                              │ assess / build / charts / intel
                                ▼                              ▼
                        ┌────────────────┐        ┌────────────────────────┐
                        │ Risk Profile   │        │ Quant core (deterministic)
                        │ risk_profiler  │───────►│ personas: access gates │
                        │ survey+kw+LLM  │        │ advisor.build_plan()   │
                        └────────────────┘        │  ├ data (synth/akshare)│
                                                  │  ├ strategy.py ★       │
                                                  │  ├ shrinkage (L-W)     │
                                                  │  └ backtest/projection │
                                                  └────────────┬───────────┘
                        ┌────────────────┐                     ▼
                        │ Market Intel   │        report.py + charts.py
                        │ intel.py (news/│        (PNG / Markdown)
                        │ topic tagging) │
                        └────────────────┘
```

Key principle: **the quant core is fully deterministic** (plans work with no LLM —
easy to unit-test and generate training data). **The LLM is the conversational
interface**, driving the core through **22 tools**:

| Tool | Purpose |
|---|---|
| `ask_investor` | Ask the investor directly (pauses the loop for the answer) |
| `assess_risk_profile` | Survey answers / verbatim → suitability tier + class caps |
| `get_market_summary` | Historical performance summary of the asset pool |
| `list_strategies` | Strategy menu (philosophy / objective / cadence / tiers) |
| `build_investment_plan` | Auto-select or specify a strategy; produce the plan |
| `apply_timing_views` | Save subjective timing views (text or {class: tilt}); injected into the next plan |
| `get_market_intel` | Latest financial news/flashes, topic-tagged (crypto/US/bonds/commodities/macro) |
| `get_macro_advice` | Asset-class advice (over/neutral/under + style split; momentum/valuation/news/macro) |
| `get_global_situation` | Global political-economic situation (real-time news + risk appetite + themes) |
| `get_global_indices` | Real-time global index board (CN/APAC/Europe/Americas; dual-source + cache + fallback) |
| `get_asset_profile_questionnaire` | Asset-profile questionnaire structure (types / overseas % / accounts / liquidity) |
| `recommend_global_bases` | Family-office global basing (onshore/cross-border/offshore scoring + friction) |
| `get_final_advice` | Final integrated advice (quant × macro × geo × basing, organically fused + action list) |
| `get_analyst_council` | Analyst council: pick the 5 best-matched of ~30 legends and render their views |
| `evolve_factor_library` | Factor self-evolution (KB import + empirical IC learning + online collection) |
| `get_factor_knowledge` | Retrieve factor definitions / formulas / logic / direction from the factor library |
| `screen_assets_by_factors` | Score/rank the asset pool via the factor lens (momentum/reversal/low-vol/drawdown) |
| `generate_charts` | 4 charts: allocation donut, risk–return map, equity+drawdown, goal projection |
| `get_kairos_context` | Optional Kairos ecosystem context: sibling package status, real ETF coverage, VaR/ES risk overlay, research findings |
| `factor_forge_from_text` | Report brief → structured factor + executable code + sample validation; optionally write into the Atlas factor store |
| `screen_assets_by_custom_factors` | Cross-sectional composite score from forged close-based factors (IC/direction weighted) |
| `explain_product` | Product risk education (risk first, return second) |

### Kairos Ecosystem Integration ★ (`integrations/kairos.py`)

Atlas optionally plugs into the sibling **Kairos quant suite** (`../kairos-data`,
`../kairos-risk`, `../kairos-research`, ...). Nothing is hard-coded or required:
if the checkouts are absent, every bridge returns empty and Atlas behaves exactly
as before.

- **Discovery**: `KAIROS_ROOT`, an explicit `integrations.kairos.root`, or a
  sibling checkout is detected automatically; packages are imported lazily.
- **Real data**: the `kairos` data provider maps 11 overlapping Atlas assets to
  the clean, committed ETF CSVs in `kairos-data/data/etf/` (CSI300, CSI500,
  ChiNext, dividend, S&P500, Nasdaq, HK, bonds, gold, MMF) and fills uncovered
  assets from the deterministic synthetic world. Fully offline.
- **Risk overlay**: `kairos-risk` adds VaR 95/99, ES 95/99, Euler risk
  decomposition by asset class, diversification ratio and effective-N to every
  plan (`Plan.kairos_risk`), surfaced in the report and dashboard.
- **Research**: the dashboard panel and the `get_kairos_context` LLM tool read
  the committed `kairos-research` key findings and robust strategy shortlist, so
  advisory output can be aligned with the suite's real-data conclusions.
- **Strategy Lab** (`integrations/kairos_strategies.py`): runs the 106 original
  `kairos-strategies` long-only strategies on the 14-ETF daily panel, ranks them
  by Sharpe/CAGR/drawdown/turnover, and exposes a cached leaderboard plus
  per-strategy equity curves in the dashboard. Run it from the CLI with
  `make kairos-lab` / `python scripts/kairos_strategy_lab.py`; results are cached
  in `data_cache/kairos_strategy_lab.json` (~30s first run).
- **Satellite overlay**: once the lab has a cache, the sidebar exposes a
  **Satellite strategy overlay** control (0–20% budget). Atlas maps the chosen
  strategy's latest weights to its asset ids, preserves the strategy's own cash
  level, blends at `budget × invested`, and re-clips to suitability class caps.
  The plan/report show budget cap, actual portfolio weight and Atlas coverage.
  Disabled by default; it is an explicit research overlay, not an automatic bet.
- **Config** (`config/agent.yaml`):

```yaml
integrations:
  kairos:
    enabled: true
    root: ""        # empty = auto-detect; or set KAIROS_ROOT
```

Run Atlas and the Kairos repos side-by-side (as in `~/Documents/Github`) and the
dashboard exposes **Kairos Ecosystem** + **Kairos Strategy Lab** panels; choose
data source `kairos` in the sidebar for the offline real-ETF provider.

```bash
make kairos-lab                                  # 106-strategy leaderboard
python scripts/kairos_strategy_lab.py --strategy low_beta_timing
python scripts/kairos_strategy_lab.py --channel trend --top 30
```

### Factor Forge Integration ★ (`integrations/factor_forge.py`)

The sibling **factor-forge** project turns a broker-report factor brief
(natural language + formula) into structured JSON, compiles executable Python,
and validates it on sample data. Atlas wraps the pipeline end to end:

- **Dashboard panel**: paste a brief (or upload a PDF with PyMuPDF) → preview
  the structured factor, required data fields, generated code and validation →
  import into the Atlas factor store with `source=factor_forge`.
- **Atlas panel validation**: for `close`-based factors (momentum/reversal/
  volatility), run cross-sectional RankIC / ICIR / t-stat / IC>0 share on the
  monthly multi-asset panel; factors needing daily `turnover/vwap` report a
  clear "not available" reason.
- **LLM tool**: `factor_forge_from_text` (21st tool).
- **CLI**:
  ```bash
  python scripts/factor_forge_import.py --file brief.txt --source "某券商 2026"
  python scripts/factor_forge_import.py --file brief.txt --import --evaluate
  python scripts/factor_forge_import.py --pdf report.pdf --index 0 --import
  ```
- Stored records keep `formula`, `direction`, `rationale`, generated `code` and
  `meta` (operator/variables); `get_factor_knowledge` searches the store as well
  as the external catalog.
- **Custom factor composite**: the dashboard's *Custom factor scores* panel
  evaluates every forged close-based factor on the Atlas panel, converts each to
  a cross-sectional z-score, signs it by declared direction (or measured IC),
  weights by |IC|, and averages the latest months into a per-asset score. The
  LLM can read the same pack via `screen_assets_by_custom_factors` (22nd tool).
  Research evidence only; not fed to the optimizer.
- Auto-detects `../factor-forge` or `FACTOR_FORGE_ROOT`; absent → graceful
  "not available".

### Dashboard State & Consistency

- Language switching preserves every input/questionnaire answer via shadow
  state (Streamlit recreates keyed widgets when their translated labels change).
- Basing widgets use stable option IDs, not translated labels, so switching
  language never clears selected asset types/accounts.
- The strategy list is filtered by the **current questionnaire tier**; if the
  tier changes, an out-of-tier selection falls back to Auto. The API also
  rejects an explicit strategy outside the investor's tier.
- If questionnaire/inputs change after generating a plan, the result panel warns
  that it still shows the previous run until Generate is clicked again.
- **Input validation happens before the quant core**: finite/non-negative
  capital, 0–3 questionnaire options, 1–50y horizon, 12–600 month lookbacks,
  0–0.30 satellite budget, text-length caps (profile/forge/timing) and valid
  asset-class timing keys. API/tool callers get a readable error instead of a
  deep numpy/optimizer exception.

### LLM Safety Boundary ★ (`harness.py` + `safety.py`)

Tool traffic is treated as untrusted in both directions:

- **Argument validation**: every tool call is checked against its JSON schema
  (required keys, primitive types, enum/bounds) before the handler runs; argument
  payloads are capped (`max_tool_argument_chars`, default 16k).
- **Budgets**: at most `max_tool_calls` (24) tool executions per conversation and
  `max_tool_steps` (8) model turns; oversized tool results are truncated with an
  explicit `_truncated` marker (`max_tool_result_chars`, 12k).
- **Prompt-injection hygiene**: news flashes, geopolitical feeds and report-PDF
  text are flattened, length-capped, stripped of common "ignore previous
  instructions" patterns, and labelled `untrusted` with a data-only notice before
  reaching the model. The system prompt explicitly forbids executing embedded
  instructions or revealing prompts/keys/paths.
- Config lives under `agent:` in `config/agent.yaml`.

### Requirement Understanding + Subjective Timing ★

- **Requirement understanding** (`requirement.py`): parses free text into a
  structured requirement `{risk tilt, timing views, asset interests, horizon}`,
  sentiment-aware ("crypto is crashing, sell everything" is NOT misread as high
  risk appetite). Benchmark: `training/eval/eval_requirement.py` (36 checks).
- **Subjective timing** (`timing.py`): bullish/bearish views act in two places —
  ① strategy-selection alignment ("bearish equities, seek safety" → rotates to a
  defensive strategy); ② tilt injected into expected returns before optimization.
  **Only affects the current allocation; historical backtests stay honest**; always
  bounded by suitability caps. Timing sliders live in the sidebar.

### Global Market Indices Board ★ (`global_indices.py`, always-on flagship)

A persistent top-of-page board of global indices (price / change / trading status):
**Mainland China** (SSE/SZSE/ChiNext/CSI300) · **APAC** (HSI/Nikkei/KOSPI/SENSEX/
STI/ASX200) · **Europe** (FTSE100/DAX/CAC40) · **Americas** (S&P500/Nasdaq/Dow/TSX).

**Dual-source reliability** (the flagship must stay lit):
- Primary **Tencent quotes** (very stable; CN/US/HK) + extended **eastmoney**
  (Japan/Europe/APAC; best-effort)
- Retry with backoff + 5-min TTL cache + graceful degradation (stale cache > empty);
  API flakiness never blanks the board
- Per-region **open/closed** status inferred from current UTC (approximate, DST ignored)

### Global Political-Economic Situation ★ (`geopolitics.py`)

A standalone, always-visible board: aggregates real-time news (eastmoney flashes /
CCTV / economic calendar), topic-tags it (geopolitical conflict / trade & tariffs /
central banks & rates / inflation & jobs / growth / capital-market policy), and emits
a **risk-appetite score, regime call (risk-on / neutral / risk-off), dominant themes,
and watch items**. Transparent, reproducible rules; graceful degradation on failure.

### Macro Asset-Class Advice ★ (`macro_advice.py`)

A class-level view layer on top of specific holdings, fusing four signals: real
momentum (trailing 12m per class), valuation percentile (tracking-index PE, 10y),
news sentiment (global risk appetite), macro read (China PMI). Outputs
**over/neutral/underweight + rationale** per class, plus **style/sector splits**
within equities (growth vs value, large vs small cap). Deterministic scoring; every
conclusion cites its driving signals.

### Family-Office Global Basing ★ (`global_base.py`)

A "friction-reduction" layer from a family-office perspective. A **base** = where an
investor domiciles/accesses global assets. Ships with a catalog of 12 global bases
(onshore: A-share account / onshore QDII funds / bank WM; cross-border: Stock Connect
/ Bond Connect / GBM Wealth Connect; offshore: HK brokerage / HK insurance / SG family
office / US brokerage / regulated crypto exchange / overseas real estate), each with a
**five-dimensional friction model** (capital control / tax / FX / access / compliance,
0–1) and thresholds.

Scored against **suitability tier + asset profile** (held asset types / overseas % /
overseas accounts / liquidity):
```
score = 100 · (capital_fit · asset_relevance · risk_fit · experience_fit) · (1 − λ·friction)
```
Outputs a ranked base list (score / friction / threshold / reasons), guiding
"low-friction onshore base → cross-border expansion → offshore only to fill gaps",
with compliant capital-outflow notes. Visualized in the "Global Basing" panel.

### Final Integrated Advice ★ (`final_advice.py`, organic fusion)

The layers above are **not independent** — a fusion layer threads them into one
recommendation spine:
```
quant allocation × class views × global situation × global basing
   └─ tilt class weights → suitability caps → redistribute within class → map each class to its best base
```
- **Geo-regime tilt**: risk-on → up risk classes / down defensive; risk-off → reverse + gold hedge.
- **Class-view tilt**: over ×1.22 / neutral ×1.0 / under ×0.68.
- **Basing map**: each asset class lands on the highest-scoring base that supports it.
- Output: final class allocation + global basing + thesis narrative + action list,
  auto-written into the report (`build_report(..., final_advice=...)`).

### Analyst Council ★ (`analysts.py`, ~30 legends → top-5 by direction)

A virtual panel of ~30 investment legends / schools (Jim Simons, Buffett, Munger,
Graham, Lynch, Soros, Dalio, Howard Marks, Templeton, Taleb, Swensen, Bogle,
Cathie Wood, O'Neil, Livermore, Asness, Thorp, ...). For each plan the council:

1. **Scores every analyst for directional match** against the current context
   (plan class weights, geo regime, strategy tags, suitability tier, crypto presence);
2. **Selects the top-5** most relevant lenses;
3. **Renders each persona's view** — a *personalized* stance derived from the
   analyst's own numeric posture (so contrarians genuinely dissent from momentum
   analysts even in the same regime), advice tied to the current allocation +
   macro view, class tilts, and their signature principle;
4. **Aggregates a consensus + dissent** and a one-paragraph summary;
5. **Weighted vote → net tilt**: each analyst casts a relevance-weighted numeric
   ballot per asset class; the aggregated net tilt (in [-1,1]) **feeds back into the
   final allocation** (`final_advice._apply_council_tilt`) as a bounded overlay —
   the council refines, it does not override the quant+macro+geo fusion;
6. **Divergence indicator** (`council_divergence`): `0.7·tilt-std + 0.3·stance-split`,
   scored 0–1 and leveled (高度共识 <0.20 / 中度分歧 <0.45 / 高度分歧). **The council's
   influence on the allocation is automatically damped by divergence**
   (`effective_strength = strength × (1 − divergence)`) and a caution is printed —
   a split panel should make you *less* confident, not more.
7. **Learnable voice weights** (`analyst_calibration.py`): each analyst's structural
   style tilt is backtested against forward asset-class returns on real data →
   style IC → `voice_multiplier = clip(1 + 5·IC, 0.5, 1.5)`. Vote weight =
   relevance × voice. Persisted in `data/analyst_weights.json` and **re-calibrated
   by the evolution daemon** — styles that keep working gain influence; styles
   that stop working get muted (e.g. measured: Bogle ×1.45, Cathie Wood ×0.87).

Example: a C5 crypto-heavy risk-on plan selects Wood / Andreessen / Simons / Asness /
Lynch; their weighted vote pushes equity+crypto up and bonds down, and the final
allocation reflects it (crypto capped at its suitability limit). A C1 bond-heavy
risk-off plan selects Klarman / Graham / Dalio / Druckenmiller / Fink. Output is clearly
attributed and labeled as reference views, written into the report's "Analyst Council".

### Factor Self-Evolution ★ (`factors/factor_store.py` + `factor_evolution.py`, autonomous)

A persistent in-project factor library (`data/factor_store.json`) that **grows on its
own, no manual trigger needed**:
1. **Knowledge-base import**: bulk-import the external factor library (1093 factors), keeping provenance.
2. **Broker-report collection (title-level)**: pull report titles, extract factor themes by concept keywords, register with provenance (report / institution / date).
3. **Report-PDF deep mining** (`report_pdf_miner.py`): scan the report API, locate
   factor-focused reports by keyword (factor / multi-factor / stock selection /
   financial engineering / alpha), download the PDF → extract full text → mine factor
   concepts (valuation / dividend / growth / momentum / low-vol / liquidity) and
   explicit "XX factor" definitions, registered with the report's own reasoning as evidence.
4. **Empirical learning**: derive factor signals from real data and measure **IC
   (information coefficient)**; more data → better estimates (e.g. short-term reversal IC≈0.48).

**Autonomous scheduling (learns even when you're not using Atlas)**:
- `make evolve-daemon`: background daemon, one learning cycle every 6h (`scripts/evolution_daemon.py`);
- **Startup catch-up**: on every page load, if >24h since last learning, auto-run a background cycle (`maybe_autolearn`);
- systemd: `deploy/atlas-evolution.service`; cron also works.
State logged in `data/evolution_state.json`; visible in the "Factor Self-Evolution" panel.

**Concurrency-safe store**: dashboard sessions and daemon cycles can write at
the same time. Writers take an advisory file lock (`data/factor_store.json.lock`)
and replace the JSON atomically (temp file + rename); a corrupt store is
quarantined instead of being silently overwritten.

### Factor Library Fusion (1000+ quant factors) ★

`invest_agent/factors/` fuses a factor library. **A 17-factor / 12-category
sample ships in `examples/factor_library_sample` and loads by default**, so the
knowledge base and factor lens work immediately after checkout. The full
`signal-name/data/json` library is:
1837 records / 1093 factors / 79 categories — momentum/reversal, volatility, liquidity,
valuation, fundamentals, behavioral finance, HF money-flow, etc.):

- **`loader.py` knowledge base**: parse → dedup → category index; mine return-direction
  priors ("positive/negative correlation") from rationale text; flag HF factors.
- **`lens.py` factor lens**: two-layer composite score; auto-downweights missing data, never fabricates:
  - *Return proxies* (computable for all assets): momentum(+) / short reversal(−) / low-vol(−) / drawdown-resistance(−)
  - *Live real factors* (`enrich.py` via free akshare, exchange ETFs only):
    **valuation** = tracking-index rolling-PE 10y percentile (−); **liquidity** = log turnover(+);
    **money-flow** = main net-inflow %(+); plus turnover/volume-ratio/premium/mcap fields.
  - Crypto / futures proxies / OTC funds lack exchange data → return proxies only, weights renormalized.
  - TTL cache (intraday 4h, valuation 24h); graceful fallback when APIs fail.
- **Three landing points**: ① satellite-sleeve coin selection blends the factor score;
  ② LLM tools retrieve factor knowledge to explain screening; ③ SFT samples inject
  factor-screening rationale so the fine-tuned model "speaks in factors".
- Config: `config/agent.yaml` → `factors.data_dir` (defaults to the bundled
  `examples/factor_library_sample`, so the knowledge base works out of the box;
  set `ATLAS_FACTOR_DIR` for the full 1000+ library).

### Strategy Layer (amplify strengths, don't pile assets) ★

Rather than cramming 26 assets into one portfolio, six philosophy-driven strategies, each with:

- **Screening**: class sleeve caps + asset-level tag exclusion (e.g. aggressive drops defensive/dividend; conservative drops high-beta/sector/meme)
- **Objective**: `max_sharpe` / `mean_variance` / `min_vol` / `risk_parity`
- **Cadence**: high (monthly) / mid (quarterly) / low (annual)

| Strategy | Philosophy | Objective | Cadence | Tiers |
|---|---|---|---|---|
| Steady Carry | Amplify fixed-income cash-flow certainty | min_vol | low | C1-C3 |
| Balanced Core | Max-Sharpe diversification across low-corr assets | max_sharpe | mid | C2-C4 |
| Global Equity Momentum | Amplify equity growth premium | max_sharpe | mid | C3-C5 |
| All-Weather Risk Parity | Equal risk contribution, no direction bets | risk_parity | low | C2-C5 |
| Aggressive Frontier | Amplify high-growth elasticity | mean_variance | high | C4-C5 |
| Crypto Barbell | Ultra-safe + high-elasticity extremes | mean_variance | high | C5 |

Profile→strategy auto-selection: `score = Sharpe − 1.5×vol-overrun − 1.2×return-shortfall
+ 0.8×(DSR − 0.5)` (text signals add tier-gated boosts). **DSR** is the Deflated
Sharpe Ratio — the probability that the strategy's edge survives deflation for the
number of trials (menu size) plus skew/kurtosis, so the best raw Sharpe does not
automatically win. The menu is backtested per-strategy on the same data; Sharpe,
DSR, drawdown and turnover appear in the page/report.

## 3. Quickstart

```bash
pip install -r requirements.txt          # numpy/pandas/scipy/matplotlib/openai/pyyaml/akshare

make demo        # offline demo: mass / affluent / HNW → examples/demo_outputs/
make lint        # ruff static checks (pip install -r requirements-dev.txt)
make test        # unit + integration tests (201)
make eval        # compliance gate (weight legality / caps / disclaimer / segment access)
make sft         # generate 400 SFT conversations → training/sft_data/train.jsonl

# Interactive mode (needs DeepSeek key; else falls back to survey + offline pipeline)
export DEEPSEEK_API_KEY='<your-key>'
make chat
```

Streamlit dashboard (optional): `pip install streamlit jinja2 && make dashboard`
— binds to `127.0.0.1:8501` by default; use `make dashboard-host TOKEN=...`
(or Docker) for LAN/public access.

### Sample output

```
[02_mass_affluent_C3] Mass Affluent · Balanced · family breadwinner, mortgage, beat inflation
   tier=C3 score=56 E[ret]=8.5% vol=10.6% Sharpe=0.61
   alloc: sp500_etf=39.2%, bond_fund=28.1%, csi300_etf=17.7%, gold_etf=15.0%
```
![sample](examples/sample/02_mass_affluent_C3/allocation.png)

## 4. Quant Core

- **Expected returns**: sample means shrunk toward class priors (δ=0.6) to suppress
  mean-estimation noise (Black-Litterman spirit).
- **Covariance**: Ledoit & Wolf (2003) constant-correlation target with analytic
  oracle intensity (`cov_shrinkage`).
- **Optimization**: multi-objective — `mean_variance` (maximize `w'μ−(λ/2)w'Σw`),
  `max_sharpe` (direct, multi-start), `min_vol`, `risk_parity`. Unified constraints:
  **class caps (suitability ∩ strategy sleeve)**, single asset ≤65% (concentration
  discipline), no shorting. Falls back to risk parity on failure.
- **Strategy selection**: each menu strategy backtested at its own cadence; matched to
  the profile by `Sharpe − vol-overrun − return-shortfall`; overridable manually.
- **Backtest**: per-strategy rebalance (monthly/quarterly/annual) with realistic
  frictions — base fee + 2bps slippage on turnover, optional sell tax (default 0:
  the bundled universe is ETF-based and CN ETFs are stamp-duty exempt), and a 2%
  **no-trade band** that skips meaningless small rebalances. Metrics = ann. return /
  vol / Sharpe / max drawdown / Calmar / turnover / annual cost drag.
- **Intel**: `intel.py` pulls latest financial flashes, topic-tags them, caches 6h.
- **Data**: `SyntheticProvider` (fixed seed, bear/boom/crypto-crash regimes, offline
  reproducible); `AkshareProvider` + `MergedProvider` (real CN/overseas ETFs, funds,
  crude NAV; crypto & futures columns filled synthetically); `KairosProvider`
  (offline real ETF panel from sibling `kairos-data`, synthetic fill for gaps).

## 5. Local Training Loop

1. **Data**: `training/generate_sft_data.py` uses the deterministic pipeline as the
   "gold advisor" to synthesize multi-turn dialogues (system + question + answer +
   compliant plan) in OpenAI chat JSONL.
2. **Fine-tune**: fine-tune `deepseek-r1-distill` (e.g. 7B) with
   [LLaMA-Factory](https://github.com/hiyouga/LLaMA-Factory) / ms-swift; config in `config/agent.yaml`.
3. **Local inference**: serve via vLLM (OpenAI-compatible), set `provider: local` in
   `config/agent.yaml` — same harness, seamless switch.
4. **Evaluation**: `training/eval/eval_suite.py` is the hard-gate regression (weight
   legality, suitability caps, segment access, disclaimer) — run after every config/model
   change; `make test` covers quant-core numerics.

```
   ┌─────────────┐  generate  ┌──────────────┐  finetune  ┌──────────────────┐
   │ Deterministic│ ─────────►│ SFT JSONL    │ ─────────►│ local DeepSeek   │
   │ pipeline     │           │ 400+ dialogues│           │ distill (vLLM)   │
   │ (oracle)     │           └──────────────┘           └────────┬─────────┘
   └─────────────┘                                                 │
          ▲                                                        │
          └────────── eval_suite hard-gate regression ◄────────────┘
```

## 6. Layout

```
invest_agent/
  harness.py      # DeepSeek tool-calling loop + schema validation/budgets
  llm.py          # OpenAI-compatible client (official API / local vLLM)
  agent.py        # InvestAgent facade (chat + offline_plan)
  risk_profiler.py# 9-question survey + keyword inference + sentiment + LLM prompt
  personas.py     # client segmentation & access gates
  strategy.py     # ★ strategy layer: 6 strategies / screening / objective / cadence
  timing.py       # ★ subjective timing: text extraction / tilt injection / focus mode
  requirement.py  # ★ requirement understanding: risk+timing+interests+horizon
  geopolitics.py  # ★ global situation: real-time news + risk appetite + trend call
  macro_advice.py # ★ asset-class advice: momentum+valuation+news+macro
  global_base.py  # ★ family-office basing: 12-base catalog + friction model + scoring
  final_advice.py # ★ final integrated advice: quant × macro × geo × basing fusion
  analysts.py     # ★ analyst council: ~30 legends, top-5 by directional match
  analyst_calibration.py # ★ learnable voice weights (style IC -> multiplier)
  global_indices.py # ★ global index board: dual-source (Tencent+EM) + cache + fallback
  intel.py        # ★ market intel: news fetching + topic tagging + cache
  safety.py       # ★ untrusted-text hygiene / injection-pattern neutralisation
  integrations/   # ★ kairos.py / kairos_strategies.py / factor_forge.py
  factors/        # ★ loader / lens / enrich(live factors) / factor_store /
                  #   factor_evolution / report_pdf_miner
  advisor.py      # strategy-driven allocation pipeline
  portfolio/      # metrics / optimizer(MV+maxSharpe+minVol+riskParity) /
                  #   backtest(walk-forward) / tactical(momentum+trend gate)
  data/           # base / synthetic / akshare / kairos / universe (26 assets)
  tools/          # 22 tools exposed to the LLM
  charts.py, report.py, cli.py
config/           # assets.yaml, risk_profiles.yaml, agent.yaml
integrations/kairos_strategies.py  # ★ 106-strategy lab / cached leaderboard
scripts/run_demo.py         dashboard/app.py (streamlit)
scripts/kairos_strategy_lab.py     # CLI: strategy leaderboard / single curve
scripts/factor_forge_import.py     # CLI: report brief -> Factor JSON/code -> store
training/         # README / generate_sft_data.py / build_real_dataset.py /
                  # eval/(compliance + requirement benchmark) / finetune/
examples/factor_library_sample/  # factor-library sample (full lib: ATLAS_FACTOR_DIR)
tests/            # 201 tests (offline, synthetic provider)
.streamlit/config.toml + dashboard/style.py  # Jane Street-style light theme
dashboard/i18n.py  # zh-Hans / en / zh-Hant UI catalog + entity labels
.github/workflows/ci.yml  # GitHub Actions: lint + tests (3.10/3.12/3.13) + gates
.gitlab-ci.yml + DEMO.md  # optional GitLab mirror CI & live-demo script
Dockerfile / docker-compose.yml  # non-root runtime image + token-gated compose
CONTRIBUTING.md / SECURITY.md  # dev workflow & deployment security notes
```

## 6.5 Front-End Style (Jane Street)

Modeled on janestreet.com's **bright, minimal, academic** aesthetic: white background +
near-black text + signature red accent (`#d0001d`) + geometric sans-serif (Inter,
approximating Alright Sans) + uppercase letter-spaced section labels + thin rules +
hexagon motifs.
- `.streamlit/config.toml`: Streamlit light theme (white / red primary / near-black text)
- `dashboard/style.py`: injected CSS — metric cards, quote table, buttons, sidebar,
  dividers, top red rule, red hexagon section markers, thin scrollbars
- Header: black ATLAS + red hexagon SVG (the JS signature hex)
- Global index board is one dense quote table, green/red change coloring (pandas Styler, needs `jinja2>=3.1.2`)
- **Three-language UI** (`dashboard/i18n.py`): a top-right `Language:` selector switches 简体中文 /
  English / 繁體中文. UI labels, questionnaire, strategies, assets, basing, council,
  tables and captions all follow the selected language; Traditional Chinese is
  generated from the Simplified source via OpenCC (`zhconv`). External news/PDF
  headlines stay in their source language (not machine-translated offline).
  The full Markdown report has native Chinese and English templates (Traditional
  is converted from Chinese), including final advice/council tables where
  available.

## 7. Deployment: Expose the Dashboard

Docker (recommended for a reproducible deployment):

```bash
export ATLAS_ACCESS_TOKEN='choose-a-long-random-secret'
# optional: export DEEPSEEK_API_KEY='...' for conversational mode
docker compose up -d --build
# open http://127.0.0.1:8501
```

- Runs as **non-root** (`uid 10001`) with a built-in healthcheck on
  `/_stcore/health`.
- **Fails closed**: the container exits unless `ATLAS_ACCESS_TOKEN` is set
  (override only for a local demo with `ATLAS_ALLOW_INSECURE=1`).
- Binds to `127.0.0.1:8501` by default; named volumes persist `data/`,
  `data_cache/` and chart outputs.
- Single container: `make docker-build` + `make docker-run TOKEN='...'`.

LAN access without Docker:

```bash
pip install streamlit
make dashboard-host TOKEN='choose-a-long-random-secret'   # 0.0.0.0:8501, token-gated
# open  http://<server-ip>:8501
```

Recommended public setup (nginx reverse proxy + HTTPS + BasicAuth):

```
browser ──HTTPS(443)──► nginx (cert / auth / rate-limit) ──► 127.0.0.1:8501 (streamlit)
```

```nginx
server {
    listen 443 ssl;
    server_name atlas.example.com;
    # certbot-generated certs ...
    auth_basic "Atlas";  auth_basic_user_file /etc/nginx/.htpasswd;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;      # websocket, required by streamlit
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

No public IP / restrictive firewall? Use a tunnel: `frp` or `ngrok http 8501`.

Security checklist: ① enable `ATLAS_ACCESS_TOKEN` or nginx auth (Streamlit has none);
② expose only necessary ports; ③ never attach real trading credentials in a public
deployment — this project is read-only market data, keep it that way.

## 8. Contributing & Security

- **Experience feedback**: [structured issue form](https://github.com/Bruce848647703/Atlas-MultiAsset-Advisor/issues/new?template=experience_feedback.yml)
  · [feedback thread](https://github.com/Bruce848647703/Atlas-MultiAsset-Advisor/discussions/26)
  · [Discussions](https://github.com/Bruce848647703/Atlas-MultiAsset-Advisor/discussions)
  · guidance in [`FEEDBACK.md`](FEEDBACK.md). Real-use friction is more valuable than a feature wishlist.
- Development workflow, design rules, and PR checklist: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Deployment hardening and vulnerability reporting: [`SECURITY.md`](SECURITY.md)
- CI: every push/PR runs the full offline test suite on Python 3.10/3.12/3.13 plus
  the compliance gates (`.github/workflows/ci.yml`); a GitLab mirror can keep using
  `.gitlab-ci.yml`.
- Machine-specific paths stay out of the repo: set `ATLAS_FACTOR_DIR` for the external
  factor library, `DEEPSEEK_API_KEY` for the LLM, and `ATLAS_ACCESS_TOKEN` for the UI.

## 9. Roadmap

- [ ] Real crypto/futures data sources (ccxt / CTP quotes)
- [ ] Black-Litterman view injection (LLM report reading → view vector)
- [ ] Rebalance alerts & drift monitoring (scheduled jobs)
- [ ] Monte-Carlo stress tests & scenario charts
- [ ] Multilingual reports; mobile layout

## References

1. Markowitz, H. (1952). *Portfolio Selection*. Journal of Finance.
2. Ledoit, O., & Wolf, M. (2003). *Honey, I Shrunk the Sample Covariance Matrix*.
3. Maillard, S., Roncalli, T., & Teïletche, J. (2010). *The Properties of Equally Weighted Risk Contribution Portfolios*.
4. Bailey, D. H., & López de Prado, M. (2014). *The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and Non-Normality*. Journal of Portfolio Management.
5. *Measures for the Administration of the Suitability of Securities and Futures Investors* (C1–C5 tiering convention).
