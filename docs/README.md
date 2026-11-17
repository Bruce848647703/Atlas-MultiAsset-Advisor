# Atlas documentation

Start with the main [README](../README.md) for the product view. This directory
holds the engineering details that do not belong in the front page.

- [PORTFOLIO.md](PORTFOLIO.md): optimizer, metrics, walk-forward backtest and
  the rebalance/drift monitor.
- [OPERATIONS.md](OPERATIONS.md): local runs, Docker, tokens, data caches and
  scheduled jobs.
- [TESTING.md](TESTING.md): offline test suite, compliance gates and CI jobs.

## Design invariants

1. **The quant core is deterministic.** Plans, backtests, risk profiles and
   rebalance reports run without an LLM or network access.
2. **Suitability is a hard constraint.** Tier class caps are applied before the
   report is rendered and checked again at the report layer.
3. **Untrusted text stays data.** News, PDFs and user text are sanitized before
   entering prompts; tool arguments and results have explicit size budgets.
4. **Optional integrations degrade gracefully.** Kairos and Factor Forge are
   discovered at runtime; missing checkouts return empty results rather than
   failing a plan.
5. **Research is not execution.** Atlas never places orders and has no trading
   credentials; every output carries the research-only disclaimer.