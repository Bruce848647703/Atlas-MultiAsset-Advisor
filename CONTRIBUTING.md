# Contributing to Atlas

Thanks for improving Atlas. This is a research/engineering project, not a
licensed advisory service — keep that framing in docs and UI copy.

## Setup

```bash
git clone https://github.com/Bruce848647703/Atlas-MultiAsset-Advisor.git
cd Atlas-MultiAsset-Advisor
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt   # runtime deps + ruff
```

Python 3.10+ is supported; CI also runs on 3.13.

## Before opening a PR

```bash
make lint    # ruff (pyflakes + high-signal pycodestyle)
make test    # 181 tests, fully offline (synthetic provider)
make eval    # suitability caps / disclaimer / requirement-understanding gates
```

For UI work, also smoke-test the dashboard:

```bash
make dashboard                                  # localhost:8501
TOKEN='choose-a-secret' make dashboard-host     # LAN/public, token-gated
```

## Design rules

1. **The quant core stays deterministic and offline-capable.** The LLM is an
   interface, never the source of allocation numbers.
2. **Suitability is a hard constraint.** Any new feature that can raise a class
   weight must still respect `config/risk_profiles.yaml` and the client-segment
   access gates.
3. **No look-ahead in backtests.** Subjective views and council tilts may affect
   the current allocation only; historical evaluation must stay honest.
4. **Network features degrade gracefully.** Always set an HTTP timeout, cache
   where sensible, and fall back to synthetic/cached data instead of blanking
   the page.
5. **Config is portable.** Do not commit absolute home-directory paths, API
   keys, or `data/` runtime artifacts. Use environment variables
   (`DEEPSEEK_API_KEY`, `ATLAS_FACTOR_DIR`, `ATLAS_ACCESS_TOKEN`).

## Commit / PR style

- Small, focused commits with a `type: summary` subject
  (`fix:`, `feat:`, `docs:`, `test:`, `chore:`).
- Describe the user-visible change and the trade-off, not just the diff.
- Add or update tests when behaviour changes.
- Update `README.md` / `DEMO.md` when a command, config key, or count changes.

## Adding a data source

Implement `DataProvider` in `invest_agent/data/`, register it with
`@register_provider`, and add a fixture/unit test using a recorded response.
Never let a provider constructor perform unbounded network I/O.