# Testing

## Local offline suite

The default suite is fully offline and uses the deterministic synthetic provider:

```bash
python -m pytest tests -q
ruff check .
```

Expected shape on the reference machine: ~210 tests in under a minute.

## What is covered

- Risk profiling, questionnaire normalization and suitability gates.
- Optimizer shrinkage, caps, risk parity and efficient frontier.
- Strategy menu, weight builders and timing-tilt constraints.
- Walk-forward backtests, metrics and deflated Sharpe.
- Rebalance/drift monitor: position conversion, breach detection, cash
  residuals, trade suppression, validation and amounts.
- Tool harness schemas, argument/result budgets and prompt-injection hygiene.
- Global indices, macro/geopolitical advice and final advice fusion.
- Factor store/evolution, custom factors and Factor Forge integration.
- Kairos integration with absent and present checkouts.
- Dashboard i18n/state helpers and deployment checks.

## Compliance gates

```bash
python training/eval/eval_suite.py
python training/eval/eval_requirement.py
```

These check disclaimers, suitability language and the requirement-understanding
benchmark. CI runs them separately from unit tests.

## CI

`.github/workflows/ci.yml` runs:

1. Ruff lint.
2. Pytest on Python 3.10, 3.12 and 3.13.
3. Docker compose validation, image build, token-gate refusal and health check.
4. Compliance gates.

The suite must stay network-free. Tests that need live data or optional sibling
packages should skip or use the synthetic provider.