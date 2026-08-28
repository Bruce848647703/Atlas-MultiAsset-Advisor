"""Charts that sell the plan — professionally and honestly.

English labels by default (font safety on headless servers); every chart is
saved as PNG and referenced from the Markdown/HTML report.
"""

from __future__ import annotations

import os
from typing import Dict, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from .advisor import Plan  # noqa: E402

plt.rcParams.update({
    "figure.dpi": 110,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "font.size": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
})

CLASS_COLORS = {
    "cash": "#9AA5B1", "fixed_income": "#4C9AFF", "hybrid": "#7B8CDE",
    "commodity": "#F5A623", "equity_cn": "#E4572E", "equity_global": "#7B61FF",
    "crypto": "#17BEBB", "futures": "#2E7D32",
}


def _fig(out_dir: str, name: str, fig) -> str:
    path = os.path.join(out_dir, f"{name}.png")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def chart_allocation(plan: Plan, out_dir: str) -> str:
    ids = [k for k, v in plan.weights.items() if v > 1e-4]
    vals = [plan.weights[k] for k in ids]
    name_of = {a.id: a.name_en for a in plan.assets}
    class_of = {a.id: a.asset_class for a in plan.assets}
    colors = [CLASS_COLORS[class_of[i]] for i in ids]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.4))
    wedges, _ = ax1.pie(vals, colors=colors, startangle=90, counterclock=False,
                        wedgeprops=dict(width=0.42, edgecolor="white"))
    ax1.text(0, 0.06, f"{plan.profile.tier}", ha="center", fontsize=20, fontweight="bold")
    ax1.text(0, -0.16, plan.profile.tier_info["label_en"], ha="center", fontsize=9)
    ax1.legend(wedges, [f"{name_of[i]} {plan.weights[i]:.1%}" for i in ids],
               loc="center left", bbox_to_anchor=(0.98, 0.5), frameon=False, fontsize=8)
    ax1.set_title("Recommended Allocation", loc="left", fontweight="bold")

    expo: Dict[str, float] = {}
    for i in ids:
        expo[class_of[i]] = expo.get(class_of[i], 0.0) + plan.weights[i]
    ks = sorted(expo, key=lambda k: -expo[k])
    ax2.barh(ks[::-1], [expo[k] for k in ks[::-1]], color=[CLASS_COLORS[k] for k in ks[::-1]])
    for y, k in enumerate(ks[::-1]):
        cap = plan.class_caps.get(k)
        if cap is not None and cap < 1.0:
            ax2.plot([cap, cap], [y - 0.35, y + 0.35], "k--", lw=1)
    ax2.set_xlim(0, 1.0)
    ax2.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax2.set_xticklabels(["0%", "25%", "50%", "75%", "100%"])
    ax2.set_title("Class Exposure vs Suitability Caps (dashed)", loc="left", fontweight="bold")
    return _fig(out_dir, "allocation", fig)


def chart_frontier(plan: Plan, out_dir: str) -> str:
    if not plan.frontier:
        return ""
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    vols = [p["vol"] for p in plan.frontier]
    rets = [p["ret"] for p in plan.frontier]
    ax.plot(vols, rets, "-", color="#4C9AFF", lw=2, label="Efficient frontier")
    for a in plan.assets:
        ax.scatter(plan.vol_ann[a.id], plan.mu_ann[a.id], s=26, zorder=3,
                   color=CLASS_COLORS[a.asset_class], edgecolors="black", linewidths=0.4)
        ax.annotate(a.id, (plan.vol_ann[a.id], plan.mu_ann[a.id]), fontsize=6.5,
                    xytext=(4, 3), textcoords="offset points")
    px, py = plan.expected["ann_vol"], plan.expected["ann_return"]
    ax.scatter([px], [py], s=160, marker="*", color="#E4572E", edgecolors="black", zorder=5,
               label=f"Recommended (ret {py:.1%}, vol {px:.1%})")
    ax.set_xlabel("Annualized volatility")
    ax.set_ylabel("Annualized return (shrinkage estimator)")
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.set_title("Risk–Return Map & Efficient Frontier", loc="left", fontweight="bold")
    ax.legend(loc="upper left", frameon=False, fontsize=8)
    return _fig(out_dir, "frontier", fig)


def chart_equity(plan: Plan, out_dir: str, bench_label: str = "CSI300 ETF") -> str:
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 5.4), sharex=True,
                                   gridspec_kw={"height_ratios": [3, 1]})
    wealth = plan.equity_curve
    xlabels = [str(p) for p in wealth.index]
    ax1.plot(xlabels, wealth.values, lw=2, color="#2E7D32", label="Portfolio")
    if bench_label:
        ax1.axhline(1.0, color="grey", lw=0.8)
    ax1.set_ylabel("Growth of ¥1")
    ax1.legend(frameon=False, fontsize=8)
    ax1.set_title(f"Backtest: {plan.n_months} months, monthly rebalance "
                  f"(ann. {plan.backtest['ann_return']:.1%}, Sharpe {plan.backtest['sharpe']:.2f}, "
                  f"MaxDD {plan.backtest['max_drawdown']:.1%})", loc="left", fontweight="bold")

    dd = wealth / wealth.cummax() - 1.0
    ax2.fill_between(xlabels, dd.values, 0, color="#E4572E", alpha=0.55)
    ax2.set_ylabel("Drawdown")
    ax2.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    xticks = np.linspace(0, len(wealth) - 1, 6).astype(int)
    ax2.set_xticks(xticks)
    ax2.set_xticklabels([xlabels[i][:7] for i in xticks], rotation=0)
    return _fig(out_dir, "equity_curve", fig)


def chart_projection(plan: Plan, out_dir: str) -> str:
    rows = plan.projection
    if not rows:
        return ""
    years = [r["year"] for r in rows]
    values = [r["value"] for r in rows]
    principal = [r["principal_in"] for r in rows]
    gain = [g for g in values]

    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    ax.bar(years, principal, label="Principal contributed", color="#9AA5B1")
    ax.bar(years, [v - p for v, p in zip(values, principal)], bottom=principal,
           label="Investment gain", color="#17BEBB")
    for x, v in zip(years, gain):
        ax.annotate(f"¥{v/1e4:.1f}w", (x, v), textcoords="offset points", xytext=(0, 3),
                    ha="center", fontsize=8, fontweight="bold")
    ax.set_xlabel("Years")
    ax.set_ylabel("Portfolio value (CNY, w = 10,000)")
    ax.set_title(f"Goal Projection  (start ¥{plan.profile.capital:,.0f}, "
                 f"+¥{plan.monthly_contrib:,.0f}/mo, "
                 f"{plan.expected['ann_return']:.1%}/yr expected)", loc="left", fontweight="bold")
    ax.legend(frameon=False, fontsize=8)
    return _fig(out_dir, "projection", fig)


def render_all(plan: Plan, out_dir: str) -> Dict[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    return {
        "allocation": chart_allocation(plan, out_dir),
        "frontier": chart_frontier(plan, out_dir),
        "equity": chart_equity(plan, out_dir),
        "projection": chart_projection(plan, out_dir),
    }
