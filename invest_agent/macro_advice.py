"""Macro asset-allocation advice (broad class + sector tilt).

Produces a qualitative, explainable overlay on top of the numeric optimizer:
for each asset class it issues overweight / neutral / underweight with reasons,
plus a sector/style tilt within equities. Signals fused:

  * real trailing momentum per class (merged provider)
  * equity valuation (tracking-index PE percentile, low = cheap = attractive)
  * global news risk appetite & themes (geopolitics.assess_global_situation)
  * macro trend (China PMI direction)

Deterministic and transparent — every stance lists the signals that drove it.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from .data.base import get_provider
from .data.universe import build_universe, asset_ids

STANCE_OVER = "超配"
STANCE_NEUTRAL = "标配"
STANCE_UNDER = "低配"

# classes we give advice on
_ADVICE_CLASSES = ["equity_cn", "equity_global", "fixed_income",
                   "commodity", "crypto", "cash"]


def _class_momentum(returns, assets) -> Dict[str, float]:
    """Trailing 12m return per class (mean of class assets)."""
    mom: Dict[str, List[float]] = {}
    for a in assets:
        if a.id not in returns.columns:
            continue
        r = returns[a.id].dropna().values
        if len(r) >= 13:
            mom.setdefault(a.asset_class, []).append(float(np.prod(1 + r[-13:-1]) - 1))
    return {c: float(np.mean(v)) for c, v in mom.items() if v}


def _equity_pe_percentile(assets) -> Optional[float]:
    """Average tracking-index PE percentile for the equity classes (None if NA)."""
    try:
        from .factors.enrich import enrich_universe
        enr = enrich_universe(assets)
        if enr.empty or "pe_percentile" not in enr.columns:
            return None
        vals = enr["pe_percentile"].dropna()
        return float(vals.mean()) if len(vals) else None
    except Exception:  # noqa: BLE001
        return None


def _china_pmi_trend() -> Optional[str]:
    try:
        import akshare as ak
        df = ak.macro_china_pmi()
        col = "制造业-指数"
        s = df[col].astype(float).dropna()
        if len(s) < 4:
            return None
        recent = float(s.iloc[-1])
        prior3 = float(s.iloc[-4:-1].mean())
        if recent >= 50 and recent > prior3:
            return f"扩张且改善(制造业PMI {recent:.1f})"
        if recent >= 50:
            return f"扩张但走弱(制造业PMI {recent:.1f})"
        return f"收缩(制造业PMI {recent:.1f})"
    except Exception:  # noqa: BLE001
        return None


def _stance(score: float) -> str:
    if score >= 0.6:
        return STANCE_OVER
    if score <= -0.6:
        return STANCE_UNDER
    return STANCE_NEUTRAL


def generate_macro_advice(provider_name: str = "merged",
                          months: int = 60) -> Dict[str, object]:
    """Build the macro allocation advice pack."""
    assets = build_universe()
    ids = asset_ids(assets)
    try:
        prov = get_provider(provider_name)
        returns = prov.get_monthly_returns(ids, months)[ids]
    except Exception:  # noqa: BLE001
        returns = get_provider("synthetic").get_monthly_returns(ids, months)[ids]

    momentum = _class_momentum(returns, assets)
    pe_pct = _equity_pe_percentile(assets)
    pmi = _china_pmi_trend()

    # global news regime
    try:
        from .geopolitics import assess_global_situation, fetch_global_news
        situ = assess_global_situation(fetch_global_news(max_items=40))
    except Exception:  # noqa: BLE001
        situ = {"regime": "数据不可用", "risk_appetite": 0.0, "themes": []}
    appetite = float(situ.get("risk_appetite", 0.0))

    advice: List[Dict[str, object]] = []

    def add(cls, name, score, reasons):
        advice.append({"class": cls, "name": name, "stance": _stance(score),
                       "score": round(float(score), 2), "reasons": reasons})

    # --- equity_cn ---
    m = momentum.get("equity_cn", 0.0)
    reasons = [f"近12月动量 {m:+.1%}"]
    score = np.clip(m * 4, -1, 1)
    if pe_pct is not None:
        reasons.append(f"估值PE分位 {pe_pct:.0f}%")
        score += np.clip((50 - pe_pct) / 60, -0.5, 0.5)  # cheap -> boost
    score += appetite * 0.4
    reasons.append(f"全球风险偏好 {appetite:+.2f}")
    add("equity_cn", "A股权益", score, reasons)

    # --- equity_global ---
    mg = momentum.get("equity_global", 0.0)
    rg = [f"近12月动量 {mg:+.1%}"]
    sg = np.clip(mg * 4, -1, 1) + appetite * 0.4
    rg.append(f"全球风险偏好 {appetite:+.2f}")
    add("equity_global", "海外权益", sg, rg)

    # --- fixed_income ---
    mf = momentum.get("fixed_income", 0.0)
    rf_ = [f"近12月动量 {mf:+.1%}"]
    sf = np.clip(mf * 6, -0.6, 0.6) - appetite * 0.5   # risk-off -> bonds up
    rf_.append("避险情绪上升时债券受益" if appetite < 0 else "风险偏好回升削弱债券吸引力")
    add("fixed_income", "债券/固收", sf, rf_)

    # --- commodity (gold) ---
    mc = momentum.get("commodity", 0.0)
    rc = [f"近12月动量 {mc:+.1%}"]
    sc = np.clip(mc * 3, -0.8, 0.8)
    if appetite < -0.1:
        sc += 0.4
        rc.append("避险需求利好黄金")
    add("commodity", "商品/黄金", sc, rc)

    # --- crypto ---
    mk = momentum.get("crypto", 0.0)
    rk = [f"近12月动量 {mk:+.1%}", "高波动高风险, 仅适合高风险等级小仓位"]
    sk = np.clip(mk * 1.5, -1, 1) + appetite * 0.3
    add("crypto", "加密货币", sk, rk)

    # --- cash ---
    rcash = ["流动性储备, 任何等级都应保留应急金"]
    scash = -appetite * 0.3   # risk-off -> hold more cash
    add("cash", "现金/货基", scash, rcash)

    # --- equity style/sector tilt ---
    sector = _sector_tilt(returns, assets, pe_pct)

    return {
        "advice": advice,
        "sector_tilt": sector,
        "macro_context": {
            "china_pmi": pmi,
            "equity_pe_percentile": round(pe_pct, 1) if pe_pct is not None else None,
            "global_regime": situ.get("regime"),
            "risk_appetite": appetite,
            "themes": [t["theme"] for t in situ.get("themes", [])][:4],
        },
        "narrative": _narrative(advice, situ, pmi, pe_pct),
    }


def _sector_tilt(returns, assets, pe_pct) -> Dict[str, object]:
    """Within-equity style recommendation (growth vs value/dividend, big vs small)."""
    def mom(aid):
        if aid not in returns.columns:
            return None
        r = returns[aid].dropna().values
        return float(np.prod(1 + r[-13:-1]) - 1) if len(r) >= 13 else None

    growth = [m for m in (mom("gem_etf"), mom("star50_etf"), mom("nasdaq_etf")) if m is not None]
    value = [m for m in (mom("dividend_etf"), mom("csi300_etf")) if m is not None]
    small = mom("csi500_etf")
    g = float(np.mean(growth)) if growth else 0.0
    v = float(np.mean(value)) if value else 0.0

    notes = []
    if g > v + 0.03:
        style = "偏成长/科技"
        notes.append(f"成长风格动量({g:+.1%})强于价值({v:+.1%})")
    elif v > g + 0.03:
        style = "偏红利/价值"
        notes.append(f"价值/红利动量({v:+.1%})强于成长({g:+.1%})")
    else:
        style = "风格均衡"
        notes.append("成长与价值动量接近")
    if pe_pct is not None:
        if pe_pct > 70:
            notes.append(f"估值偏高(分位{pe_pct:.0f}%)，建议控制仓位或偏向低估值方向")
        elif pe_pct < 30:
            notes.append(f"估值偏低(分位{pe_pct:.0f}%)，具备配置吸引力")
    if small is not None and small > g + 0.02:
        notes.append("中小盘动量占优, 可关注中证500方向")
    return {"style": style, "notes": notes}


def _narrative(advice, situ, pmi, pe_pct) -> str:
    over = [a["name"] for a in advice if a["stance"] == STANCE_OVER]
    under = [a["name"] for a in advice if a["stance"] == STANCE_UNDER]
    parts = [f"全球局势研判为「{situ.get('regime', '未知')}」。"]
    if pmi:
        parts.append(f"国内宏观: {pmi}。")
    if pe_pct is not None:
        parts.append(f"A股估值处于近10年 {pe_pct:.0f}% 分位。")
    if over:
        parts.append(f"建议超配: {'、'.join(over)}。")
    if under:
        parts.append(f"建议低配: {'、'.join(under)}。")
    parts.append("以上为基于量化信号与新闻情绪的大类观点，需与个人适当性等级结合，"
                 "不构成投资建议。")
    return "".join(parts)
