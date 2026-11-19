# Operations

## Local run

```bash
python -m pip install -r requirements.txt
make dashboard            # local Streamlit dashboard
make demo                 # offline three-strata demo -> examples/demo_outputs/

# non-interactive CLI: deterministic offline plan, no stdin
python -m invest_agent.cli --offline \
  --answers 2,2,2,2,2,2,2,2,2 --capital 200000 --no-report
```

`DEEPSEEK_API_KEY` enables conversational mode. Without it, `InvestAgent` uses
the deterministic offline path.

## Required and optional environment

| Variable | Required | Purpose |
|---|---|---|
| `ATLAS_ACCESS_TOKEN` | Docker/LAN | streamlit access token; container fails closed without it |
| `ATLAS_ALLOW_INSECURE` | local demo only | bypass the token gate |
| `DEEPSEEK_API_KEY` | conversational mode | DeepSeek/OpenAI-compatible API |
| `DEEPSEEK_BASE_URL` | optional | local vLLM or compatible endpoint |
| `ATLAS_FACTOR_DIR` | optional | external full factor library |
| `KAIROS_ROOT` | optional | Kairos sibling checkout root |
| `FACTOR_FORGE_ROOT` | optional | factor-forge sibling checkout |

## Docker

```bash
export ATLAS_ACCESS_TOKEN='long-random-secret'
docker compose up -d --build
curl -fsS http://127.0.0.1:8501/_stcore/health
```

The image runs as non-root, binds to `127.0.0.1:8501` by default and persists
`data/`, `data_cache/` and chart outputs in named volumes. For public access,
put nginx/Caddy in front with HTTPS and authentication; see the README.

## Data and caches

- `data_cache/` holds committed ETF monthly CSVs and generated caches.
- `data/factor_store.json` is the local factor library; writes are guarded by
  `factor_store.json.lock`.
- `data/evolution_state.json` tracks the optional factor-evolution daemon.
- Live data failures degrade to stale cache, then synthetic data; they never
  block the dashboard.

## Scheduled jobs

`deploy/atlas-evolution.service` and `scripts/evolution_daemon.py` provide the
optional factor evolution loop. The dashboard does not require the daemon.

## Rebalancing check

The rebalance monitor is a read-only CLI:

```bash
python scripts/rebalance_check.py --target target.json --current current.json \
  --value 1000000 --threshold 0.05
# or: make rebalance TARGET=target.json CURRENT=current.json VALUE=1000000
```

Exit code `1` means the drift threshold was breached, which is convenient for
cron or CI. No orders are placed.

## Troubleshooting

| Symptom | Check |
|---|---|
| dashboard asks for token | set `ATLAS_ACCESS_TOKEN`, or `ATLAS_ALLOW_INSECURE=1` locally |
| no live quotes | network/proxy, then stale cache; the synthetic fallback keeps the UI alive |
| Kairos panels empty | `KAIROS_ROOT` or sibling checkout; optional integration |
| Factor Forge unavailable | `FACTOR_FORGE_ROOT` or sibling checkout; optional integration |
| LLM errors | API key/base URL, tool budgets in `config/agent.yaml` |
| stale plan | inputs changed after Generate; press Generate again |