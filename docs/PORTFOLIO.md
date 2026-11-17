# Portfolio pipeline

## From data to a plan

```text
provider (synthetic / akshare / kairos)
  -> monthly returns panel
  -> shrunk expected returns + covariance
  -> strategy weight builder
  -> suitability class caps
  -> allocation + projection + charts
```

`invest_agent/advisor.py` owns the pipeline. `Plan` stores the target weights,
expected metrics, backtest, equity curve, frontier, projection, optional timing
tilts and the optional Kairos risk overlay.

## Estimators

`invest_agent/portfolio/optimizer.py` implements:

- `expected_returns_shrinkage`: sample means shrunk toward class priors.
- `cov_shrinkage`: Ledoit-Wolf-style constant-correlation target, with the
  analytical oracle intensity.
- `optimize_mean_variance`: SLSQP mean-variance with class caps.
- `risk_parity`: equal risk contribution fallback.
- `efficient_frontier`: long-only frontier scanner.
- `_clip_to_class_caps`: water-filling cap enforcement used after overlays.

All estimators are long-only and suitability caps are applied after the
optimizer, so a timing view or satellite overlay cannot escape the tier.

## Metrics and backtest

`invest_agent/portfolio/metrics.py` provides annualized return/volatility,
Sharpe, max drawdown, Calmar, win rate and best/worst month. It also includes
probabilistic and deflated Sharpe ratios for multiple-testing-aware strategy
selection.

`invest_agent/portfolio/backtest.py` runs the walk-forward backtest used by the
strategy menu. The report shows both the strategy and its benchmark; historical
metrics are not modified by current subjective timing views.

## Rebalance and drift monitor

`invest_agent/portfolio/rebalance.py` compares a target plan with the current
portfolio and turns drift into explicit trades:

```python
from invest_agent.portfolio.rebalance import analyze_drift, weights_from_positions

current, total_value = weights_from_positions(
    {"csi300_etf": 6000, "gold_etf": 300, "bond_etf": 2000},
    {"csi300_etf": 100.0, "gold_etf": 500.0, "bond_etf": 100.0},
    cash=50_000,
)
report = analyze_drift(
    {"csi300_etf": 0.5, "gold_etf": 0.2, "bond_etf": 0.2},
    current,
    total_value=total_value,
    threshold=0.05,
)
print(report.breached, report.max_drift, report.turnover)
for line in report.trades:
    print(line.asset_id, line.trade_weight, line.trade_amount)
```

Rules:

- Cash is the residual `1 - sum(asset weights)`.
- `drift = current - target`; a positive drift is overweight.
- `trade_weight = target - current`; positive means buy.
- A breach is `max(|drift|) > threshold`.
- Trades smaller than `min_trade_weight` are suppressed but still count toward
  drift and breach detection.
- Turnover is half the sum of absolute trade weights.
- Missing prices, negative positions, non-finite weights and target sums above
  1.0 are rejected.

CLI:

```bash
python scripts/rebalance_check.py \
  --target target.json --current current.json \
  --value 1000000 --threshold 0.05
```

The JSON files may be an Atlas plan (`{"weights": ...}`) or a direct
`asset -> weight` mapping. Exit codes: `0` no breach, `1` breach, `2` invalid
input. Add `--json` for machine-readable output.

## Limitations

- The monitor is weight-based; it does not model lot sizes, fees or taxes.
- Rebalancing is advisory only; it does not place orders.
- The optimizer is long-only and does not model transaction costs.
- Backtests use monthly bars and a deterministic synthetic provider by default.