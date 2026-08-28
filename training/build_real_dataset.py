#!/usr/bin/env python3
"""Build a REAL-data dataset for training & evaluating the advisor.

Pulls genuine monthly returns through the merged provider (akshare real
quotes for ETFs/funds, synthetic fill for crypto/futures), then produces:

  1. real_data/returns.csv        — the return panel (date x asset)
  2. real_data/features.parquet   — rolling features per asset (for models)
  3. real_data/backtest_labels.csv— walk-forward realized outcomes per
                                    strategy, usable as supervision signal
                                    or as the eval benchmark.

The key idea for "training on real data": instead of trusting the seeded
synthetic world, we (a) fit estimators on actual history and (b) score each
strategy by its OUT-OF-SAMPLE realized Sharpe over rolling windows, which is
the ground truth the agent should learn to reproduce.

Usage:
    python training/build_real_dataset.py --months 120 --out training/real_data
"""

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from invest_agent.config import class_priors                     # noqa: E402
from invest_agent.data.base import get_provider                  # noqa: E402
from invest_agent.data.universe import build_universe, asset_ids, asset_classes  # noqa: E402
from invest_agent.portfolio.metrics import performance_metrics   # noqa: E402
from invest_agent.portfolio.optimizer import cov_shrinkage, expected_returns_shrinkage  # noqa: E402
from invest_agent.strategy import STRATEGY_MENU, build_strategy_weights  # noqa: E402


def fetch_panel(months: int) -> pd.DataFrame:
    prov = get_provider("merged")
    ids = asset_ids(build_universe())
    df = prov.get_monthly_returns(ids, months)
    return df


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Rolling 12m return / vol / Sharpe per asset (long format)."""
    rows = []
    for col in df.columns:
        r = df[col]
        ret12 = r.rolling(12).sum()
        vol12 = r.rolling(12).std() * np.sqrt(12)
        sharpe12 = (ret12 - 0.02) / vol12.replace(0, np.nan)
        tmp = pd.DataFrame({
            "date": df.index.astype(str), "asset": col,
            "ret12": ret12, "vol12": vol12, "sharpe12": sharpe12,
        })
        rows.append(tmp)
    return pd.concat(rows, ignore_index=True)


def walk_forward_labels(df: pd.DataFrame, train: int = 48, step: int = 6) -> pd.DataFrame:
    """For each window, fit on [0:t), allocate each strategy, then score by
    realized performance over [t:t+step). Produces ground-truth labels."""
    classes = asset_classes(build_universe())
    priors = class_priors()
    universe = build_universe()
    records = []
    T = len(df)
    cols = list(df.columns)
    cls_of_col = {a.id: a.asset_class for a in universe}
    col_classes = [cls_of_col[c] for c in cols]
    full_caps = {c: 1.0 for c in set(col_classes)}

    for t in range(train, T - step, step):
        hist = df.iloc[:t].values
        fwd = df.iloc[t:t + step]
        prior_m = np.array([priors[c]["ann_ret"] / 12 for c in col_classes])
        mu = expected_returns_shrinkage(hist, prior_m, 0.6)
        cov, _ = cov_shrinkage(hist)
        for s in STRATEGY_MENU:
            try:
                w = build_strategy_weights(s, mu, cov, col_classes, full_caps,
                                           assets=universe)
            except ValueError:
                continue
            port_fwd = fwd.values @ w
            m = performance_metrics(port_fwd)
            records.append({
                "as_of": str(df.index[t]), "strategy": s.id,
                "fwd_months": step,
                "fwd_ann_return": m["ann_return"], "fwd_ann_vol": m["ann_vol"],
                "fwd_sharpe": m["sharpe"], "fwd_max_dd": m["max_drawdown"],
            })
    return pd.DataFrame(records)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=120)
    ap.add_argument("--out", default="training/real_data")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    df = fetch_panel(args.months)
    df.to_csv(os.path.join(args.out, "returns.csv"))
    print(f"returns panel: {df.shape} -> returns.csv")

    feats = build_features(df)
    fpath = os.path.join(args.out, "features.parquet")
    try:
        feats.to_parquet(fpath)
    except Exception:  # pyarrow optional
        feats.to_csv(os.path.join(args.out, "features.csv"), index=False)
        fpath = "features.csv"
    print(f"features: {feats.shape} -> {fpath}")

    labels = walk_forward_labels(df)
    labels.to_csv(os.path.join(args.out, "backtest_labels.csv"), index=False)
    print(f"walk-forward labels: {labels.shape} -> backtest_labels.csv")

    # quick summary: which strategy had the best median OOS sharpe
    if len(labels):
        summ = labels.groupby("strategy")["fwd_sharpe"].median().sort_values(ascending=False)
        print("\n[real-data OOS median Sharpe by strategy]")
        print(summ.round(2).to_string())


if __name__ == "__main__":
    main()
