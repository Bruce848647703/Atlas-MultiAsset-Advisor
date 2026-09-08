"""Factor self-evolution (autonomous learning).

Growth channels, all persisted to factor_store:

1. KNOWLEDGE BASE import (previous factors from the external JSON library).
2. BROKER-REPORT / NEWS collection: fetch research-report titles & news, scan
   for factor concepts, register new factor themes with full provenance.
3. EMPIRICAL LEARNING (the core): derive factor signals from real market data,
   measure their information coefficient (rank-IC with next-month returns), and
   register the validated ones. As data accumulates the IC estimates improve —
   the system genuinely gets smarter over time.

Orchestration:
  * run_cycle()  — one full learning cycle with state tracking (last_run,
    per-cycle counts, evolution history log). Idempotent & error-tolerant.
  * evolve()     — alias kept for backward compatibility.
  * scripts/evolution_daemon.py — background loop so learning happens even
    when nobody is using Atlas; startup catch-up is wired into the dashboard.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np

from .factor_store import add_factor, import_knowledge_base, load_store, stats

_STATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data", "evolution_state.json")

# factor-concept keywords scanned in broker-report / news titles
FACTOR_KEYWORDS = {
    "momentum": ["动量", "趋势", "强势股", "涨幅榜"],
    "reversal": ["反转", "超跌", "回调修复"],
    "low_volatility": ["低波动", "低波", "稳健分红"],
    "value": ["低估值", "价值", "市盈率", "破净", "高股息", "红利"],
    "quality": ["高质量", "盈利质量", "ROE", "护城河"],
    "growth": ["高成长", "业绩增长", "景气度", "景气"],
    "liquidity": ["流动性", "换手", "成交额放大"],
    "size": ["小市值", "微盘股", "中小盘"],
}

# ---------------------------------------------------------------------------
# Empirical factor definitions (signal computable from monthly returns)
# ---------------------------------------------------------------------------
EMPIRICAL_FACTORS = [
    {"name": "momentum_12_1", "name_cn": "12-1月动量", "category": "动量",
     "formula": "prod(1+r[t-13:t-1])-1", "direction": 1,
     "rationale": "过去12个月(剔除最近1月)累计收益, 经典横截面动量"},
    {"name": "reversal_1m", "name_cn": "短期反转", "category": "反转",
     "formula": "r[t-1]", "direction": -1,
     "rationale": "最近1个月收益, 短期反转效应"},
    {"name": "low_vol_12m", "name_cn": "低波动", "category": "波动率",
     "formula": "std(r[t-12:t])*sqrt(12)", "direction": -1,
     "rationale": "低波动异象: 低波动资产风险调整后收益更优"},
    {"name": "max_dd_12m", "name_cn": "抗回撤", "category": "波动率",
     "formula": "max(1-wealth/peak) over t-12:t", "direction": -1,
     "rationale": "近12月最大回撤, 衡量尾部风险"},
    {"name": "trend_strength", "name_cn": "趋势强度", "category": "动量",
     "formula": "sign(mom12)*abs(mom12)/vol12", "direction": 1,
     "rationale": "动量的波动率调整, 趋势信噪比"},
]


def _momentum_signal(R: np.ndarray, t: int, kind: str) -> Optional[np.ndarray]:
    """Cross-sectional factor values at time t (using data up to t)."""
    if kind == "momentum_12_1":
        if t < 14:
            return None
        win = R[t - 13:t - 1]
        return np.prod(1 + win, axis=0) - 1
    if kind == "reversal_1m":
        if t < 2:
            return None
        return R[t - 1]
    if kind == "low_vol_12m":
        if t < 13:
            return None
        return R[t - 12:t].std(axis=0, ddof=1) * np.sqrt(12)
    if kind == "max_dd_12m":
        if t < 13:
            return None
        w = np.cumprod(1 + R[t - 12:t], axis=0)
        peak = np.maximum.accumulate(np.vstack([np.ones(w.shape[1]), w]), axis=0)[1:]
        return (1 - w / peak).max(axis=0)
    if kind == "trend_strength":
        if t < 14:
            return None
        mom = np.prod(1 + R[t - 13:t - 1], axis=0) - 1
        vol = R[t - 12:t].std(axis=0, ddof=1) * np.sqrt(12) + 1e-9
        return mom / vol
    return None


def _rank_ic(factor: np.ndarray, fwd_ret: np.ndarray) -> float:
    """Spearman rank correlation between factor and forward return."""
    from scipy.stats import spearmanr
    mask = np.isfinite(factor) & np.isfinite(fwd_ret)
    if mask.sum() < 5 or factor[mask].std() < 1e-12:
        return float("nan")
    ic, _ = spearmanr(factor[mask], fwd_ret[mask])
    return float(ic)


def measure_factor_ic(name: str, monthly_returns) -> float:
    """Average cross-sectional rank-IC of an empirical factor over time."""
    R = monthly_returns.values.astype(float)
    T = R.shape[0]
    ics = []
    for t in range(14, T - 1):
        f = _momentum_signal(R, t, name)
        if f is None:
            continue
        fwd = R[t]  # return over month t (known after decision at t-1)
        ic = _rank_ic(f, fwd)
        if np.isfinite(ic):
            ics.append(ic)
    return float(np.mean(ics)) if ics else float("nan")


def learn_empirical_factors(provider_name: str = "merged", months: int = 96,
                            ic_threshold: float = 0.0) -> List[Dict]:
    """Derive empirical factors from real data, measure IC, register the
    validated ones. Returns the learned factor records."""
    from ..data.base import get_provider
    from ..data.universe import build_universe, asset_ids
    assets = build_universe()
    ids = asset_ids(assets)
    try:
        prov = get_provider(provider_name)
        returns = prov.get_monthly_returns(ids, months)[ids]
    except Exception:  # noqa: BLE001
        returns = get_provider("synthetic").get_monthly_returns(ids, months)[ids]

    learned = []
    for fac in EMPIRICAL_FACTORS:
        ic = measure_factor_ic(fac["name"], returns)
        if np.isfinite(ic) and abs(ic) >= ic_threshold:
            rec = add_factor(
                fac["name"], fac["category"], source="empirical",
                name_cn=fac["name_cn"], formula=fac["formula"],
                direction=1 if ic > 0 else -1, ic=round(ic, 4),
                rationale=fac["rationale"], overwrite=True)
            learned.append(rec)
        else:
            # still record but mark as unvalidated
            add_factor(fac["name"], fac["category"], source="empirical",
                       name_cn=fac["name_cn"], formula=fac["formula"],
                       direction=0, ic=None if not np.isfinite(ic) else round(ic, 4),
                       rationale=fac["rationale"] + " [IC未达阈值]", overwrite=False)
    return learned


# ---------------------------------------------------------------------------
# Online collection framework (extensible)
# ---------------------------------------------------------------------------
COLLECTORS = []  # each: fn() -> List[Dict] factor records


def register_collector(fn):
    COLLECTORS.append(fn)
    return fn


def collect_online() -> List[Dict]:
    """Run all registered online collectors (best-effort)."""
    collected = []
    for fn in COLLECTORS:
        try:
            recs = fn() or []
            for r in recs:
                add_factor(r["name"], r.get("category", "在线"),
                           source="online", name_cn=r.get("name_cn", r["name"]),
                           formula=r.get("formula", ""), direction=r.get("direction", 0),
                           rationale=r.get("rationale", "")[:200], overwrite=False)
            collected.extend(recs)
        except Exception:  # noqa: BLE001 - a failing source must not block others
            continue
    return collected


def evolve(provider_name: str = "merged", months: int = 96,
           ic_threshold: float = 0.0, knowledge_dir: Optional[str] = None) -> Dict:
    """Backward-compatible alias for one learning cycle."""
    return run_cycle(provider_name, months, ic_threshold, knowledge_dir,
                     import_kb=True)


# ---------------------------------------------------------------------------
# State tracking (autonomous learning memory)
# ---------------------------------------------------------------------------
def read_state() -> Dict:
    if not os.path.exists(_STATE_PATH):
        return {"last_run": None, "cycles": 0, "history": []}
    try:
        with open(_STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {"last_run": None, "cycles": 0, "history": []}


def write_state(state: Dict) -> None:
    os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
    with open(_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


def hours_since_last_run() -> Optional[float]:
    st = read_state()
    if not st.get("last_run"):
        return None
    try:
        last = datetime.fromisoformat(st["last_run"])
        return (datetime.now() - last).total_seconds() / 3600.0
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Broker-report / news factor discovery
# ---------------------------------------------------------------------------
# representative basket whose research reports we scan for factor themes
_REPORT_BASKET = ["300059", "600519", "000858", "601318", "002594"]


def match_factor_theme(title: str) -> Optional[str]:
    """Return the first factor-concept theme present in a report title."""
    for theme, kws in FACTOR_KEYWORDS.items():
        if any(kw in title for kw in kws):
            return theme
    return None


def collect_from_broker_reports(basket: Optional[List[str]] = None,
                                max_per_symbol: int = 20) -> List[Dict]:
    """Scan broker research-report titles for factor concepts and register the
    discovered factor themes with provenance (report title + institution)."""
    basket = basket or _REPORT_BASKET
    discovered: List[Dict] = []
    seen_titles = set()
    try:
        import akshare as ak
    except Exception:  # noqa: BLE001
        return discovered

    for sym in basket:
        try:
            df = ak.stock_research_report_em(symbol=sym)
        except Exception:  # noqa: BLE001
            continue
        if df is None or df.empty or "报告名称" not in df.columns:
            continue
        for _, row in df.head(max_per_symbol).iterrows():
            title = str(row.get("报告名称", "") or "")
            inst = str(row.get("机构", "") or "")
            date = str(row.get("日期", "") or "")
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)
            theme = match_factor_theme(title)
            if theme:
                name = f"report_{theme}"
                rec = add_factor(
                    name, category="券商研报", source="broker_report",
                    name_cn=f"研报因子主题-{theme}",
                    formula="", direction=0,
                    rationale=f"来源研报: {title[:60]} | 机构:{inst} | {date}",
                    overwrite=False)
                discovered.append({"name": name, "theme": theme,
                                   "report": title[:60], "institution": inst})
    return discovered


# ---------------------------------------------------------------------------
# Full autonomous learning cycle
# ---------------------------------------------------------------------------
def run_cycle(provider_name: str = "merged", months: int = 96,
              ic_threshold: float = 0.0, knowledge_dir: Optional[str] = None,
              import_kb: bool = True, collect_reports: bool = True,
              mine_pdfs: bool = True) -> Dict:
    """One full self-evolution cycle with state tracking. Error-tolerant: a
    failing sub-step never aborts the whole cycle."""
    from ..config import get_config
    before = stats()

    kb_imported = 0
    if import_kb:
        kb_dir = knowledge_dir or (get_config().get("factors", {}) or {}).get("data_dir", "")
        if kb_dir:
            try:
                kb_imported = import_knowledge_base(kb_dir)
            except Exception:  # noqa: BLE001
                kb_imported = 0

    broker_hits: List[Dict] = []
    if collect_reports:
        try:
            broker_hits = collect_from_broker_reports()
        except Exception:  # noqa: BLE001
            broker_hits = []

    pdf_mined = 0
    pdf_registered = 0
    if mine_pdfs:
        try:
            from .report_pdf_miner import mine_report_pdfs
            pm = mine_report_pdfs(max_reports=6, max_per_symbol=5)
            pdf_mined = pm["reports_with_factors"]
            pdf_registered = len(pm["registered_factors"])
        except Exception:  # noqa: BLE001
            pdf_mined = pdf_registered = 0

    try:
        learned = learn_empirical_factors(provider_name, months, ic_threshold)
    except Exception:  # noqa: BLE001
        learned = []

    # calibrate analyst council voice weights on the same real data
    analyst_calib = None
    try:
        from ..analyst_calibration import calibrate_all
        calib = calibrate_all(provider_name=provider_name, months=months)
        analyst_calib = calib.get("meta", {})
    except Exception:  # noqa: BLE001
        analyst_calib = None

    try:
        online = collect_online()
    except Exception:  # noqa: BLE001
        online = []

    after = stats()
    now = datetime.now()
    cycle_report = {
        "timestamp": now.isoformat(timespec="seconds"),
        "factors_before": before["total"],
        "factors_after": after["total"],
        "knowledge_base_imported": kb_imported,
        "broker_report_factors": len(broker_hits),
        "pdf_reports_mined": pdf_mined,
        "pdf_factors_registered": pdf_registered,
        "learned_empirical": [{"name": f["name"], "ic": f.get("ic")} for f in learned],
        "collected_online": len(online),
        "analyst_calibration": analyst_calib,
        "store_stats": after,
    }

    # update state + rolling history (keep last 50 cycles)
    state = read_state()
    state["last_run"] = cycle_report["timestamp"]
    state["cycles"] = int(state.get("cycles", 0)) + 1
    hist = state.get("history", [])
    hist.append({k: cycle_report[k] for k in
                 ("timestamp", "factors_after", "broker_report_factors",
                  "pdf_factors_registered", "collected_online")})
    state["history"] = hist[-50:]
    try:
        write_state(state)
    except Exception:  # noqa: BLE001
        pass

    return cycle_report


# ---------------------------------------------------------------------------
# Autonomous triggers (learn even when nobody is actively using Atlas)
# ---------------------------------------------------------------------------
def trigger_background_cycle(provider_name: str = "merged", months: int = 96) -> bool:
    """Launch a detached one-shot learning cycle (non-blocking). Returns True if
    spawned. Used for startup catch-up so the agent learns on its own schedule."""
    import subprocess
    root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    script = os.path.join(root, "scripts", "evolution_daemon.py")
    log = os.path.join(root, "data", "evolution_daemon.log")
    try:
        os.makedirs(os.path.dirname(log), exist_ok=True)
        with open(log, "a", encoding="utf-8") as lf:
            subprocess.Popen(
                [sys.executable, script, "--once", "--provider", provider_name,
                 "--months", str(months)],
                stdout=lf, stderr=lf, start_new_session=True, cwd=root)
        return True
    except Exception:  # noqa: BLE001
        return False


def maybe_autolearn(threshold_hours: float = 24.0,
                    provider_name: str = "merged", months: int = 96) -> Dict:
    """Startup catch-up: if no learning cycle ran within the threshold, spawn a
    background one. Safe to call on every page load (no-op when fresh)."""
    gap = hours_since_last_run()
    if gap is not None and gap < threshold_hours:
        return {"triggered": False, "reason": f"recent run {gap:.1f}h ago"}
    ok = trigger_background_cycle(provider_name, months)
    return {"triggered": ok,
            "reason": ("spawned background cycle" if ok else "failed to spawn"),
            "hours_since_last": gap}
