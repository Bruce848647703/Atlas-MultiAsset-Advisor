"""Holdings import, portfolio X-ray and target drift / rebalance analysis.

The advisor normally starts from an empty portfolio. This module lets a user
import a broker/Excel CSV so Atlas can answer:

* what do I actually own (weights, classes, currencies, concentration)?
* how far is it from the recommended target?
* what should I buy/sell, and what does it cost?
* does the current portfolio violate suitability caps?

CSV is deliberately simple and local-only::

    symbol,market_value,currency,fx_to_cny,shares,cost,account
    510300,150000,CNY,1,30000,4.8,brokerA
    CASH,50000,CNY,1,,,brokerA

`symbol` may be an Atlas asset id, a 6-digit ETF code, a name, or CASH.
`market_value` is in the row currency; non-CNY rows need `fx_to_cny`.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

CASH_ALIASES = {"cash", "cny", "cash_cny", "现金", "现金/存款/货基"}
MAX_CSV_BYTES = 5 * 1024 * 1024      # 5 MB is far beyond a retail holdings file
MAX_CSV_ROWS = 2000                 # avoids pathological uploads freezing the UI
MIN_FX_TO_CNY = 0.001               # JPY/CNY is ~0.05; allow tiny but sane
MAX_FX_TO_CNY = 50.0                # covers KWD/BHD; a fat-fingered 72 is caught
MAX_MARKET_VALUE_CNY = 1e15         # 1 quadrillion CNY: far beyond any retail book
_ALIASES = {
    "symbol": {"symbol", "ticker", "asset", "asset_id", "code", "代码", "标的"},
    "market_value": {"market_value", "value", "amount", "市值", "金额"},
    "shares": {"shares", "quantity", "qty", "数量", "份额"},
    "price": {"price", "last", "close", "现价", "价格"},
    "cost": {"cost", "avg_cost", "成本", "成本价"},
    "currency": {"currency", "ccy", "币种"},
    "fx_to_cny": {"fx_to_cny", "fx", "汇率", "汇率cny"},
    "account": {"account", "账户", "账号"},
}
_REQUIRED_TEMPLATE = (
    "symbol,market_value,currency,fx_to_cny,shares,cost,account\n"
    "510300,150000,CNY,1,30000,4.8,brokerA\n"
    "CASH,50000,CNY,1,,,brokerA\n"
)


def csv_template() -> str:
    return _REQUIRED_TEMPLATE


def _key(row: Dict[str, Any], name: str) -> Any:
    for alias in _ALIASES[name]:
        if alias in row:
            return row[alias]
    return None


def _num(value: Any, field: str, errors: List[str], row_no: int) -> Optional[float]:
    if value in (None, "", "—"):
        return None
    cleaned = str(value).replace(",", "").replace("，", "")
    cleaned = cleaned.replace("¥", "").replace("￥", "").replace("$", "").strip()
    try:
        number = float(cleaned)
    except (TypeError, ValueError):
        errors.append(f"row {row_no}: {field} 不是数字 ({value!r})")
        return None
    if number != number or number in (float("inf"), float("-inf")):
        errors.append(f"row {row_no}: {field} 必须是有限数字")
        return None
    return number


def _symbol_map(universe: Sequence) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for asset in universe:
        symbol_ak = str(asset.meta.get("symbol_ak") or "").lower()
        candidates = {
            str(asset.id).lower(),
            str(asset.name_zh).lower(),
            str(asset.name_en).lower(),
            symbol_ak,
        }
        for raw in list(candidates):
            if not raw:
                continue
            out[raw] = asset
            cleaned = raw.replace(".sh", "").replace(".sz", "")
            cleaned = re.sub(r"^(sh|sz)", "", cleaned)
            out.setdefault(cleaned, asset)
    return out


def _normalise_symbol(symbol: str) -> str:
    raw = str(symbol or "").strip().lower()
    raw = raw.replace(".sh", "").replace(".sz", "")
    return re.sub(r"^(sh|sz)", "", raw)


def parse_csv(content: bytes | str) -> List[Dict[str, Any]]:
    if isinstance(content, bytes):
        if len(content) > MAX_CSV_BYTES:
            raise ValueError(
                f"CSV 文件过大（>{MAX_CSV_BYTES // (1024 * 1024)} MB），"
                "请只保留持仓明细")
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            # Excel on a Chinese Windows machine often exports GBK/GB18030.
            try:
                text = content.decode("gb18030")
            except UnicodeDecodeError as exc:
                raise ValueError("CSV 编码无法识别，请另存为 UTF-8 后重试") from exc
    else:
        text = str(content)
    # tolerate Excel exports with a title row before the header
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []
    header_idx = 0
    for i, line in enumerate(lines[:5]):
        if any(alias in line.lower() for alias in ("symbol", "代码", "标的")):
            header_idx = i
            break
    reader = csv.DictReader(io.StringIO("\n".join(lines[header_idx:])))
    rows = []
    for row in reader:
        cleaned = {(k or "").strip().lower(): v for k, v in row.items()}
        rows.append(cleaned)
        if len(rows) > MAX_CSV_ROWS:
            raise ValueError(
                f"CSV 行数过多（>{MAX_CSV_ROWS} 行），请只保留持仓明细")
    return rows


def parse_holdings(rows: Iterable[Dict[str, Any]],
                   universe: Sequence = None) -> Dict[str, Any]:
    """Validate rows and compute a CNY portfolio X-ray."""
    if universe is None:
        from ..data.universe import build_universe
        universe = build_universe()
    by_symbol = _symbol_map(universe)
    errors: List[str] = []
    warnings: List[str] = []
    holdings: Dict[str, Dict[str, Any]] = {}

    for row_no, row in enumerate(rows, 1):
        if row_no > MAX_CSV_ROWS:
            errors.append(f"持仓行数过多（>{MAX_CSV_ROWS} 行），请只保留持仓明细")
            break
        symbol = _key(row, "symbol")
        if symbol in (None, ""):
            errors.append(f"row {row_no}: symbol 不能为空")
            continue
        raw_symbol = str(symbol).strip()
        asset = None
        if raw_symbol.lower() in CASH_ALIASES:
            asset = next((a for a in universe if a.id == "money_fund"), None)
        else:
            asset = by_symbol.get(raw_symbol.lower()) or by_symbol.get(_normalise_symbol(raw_symbol))
        if asset is None:
            errors.append(f"row {row_no}: 无法识别标的 {raw_symbol!r} "
                          f"（可用 asset_id / 6位代码 / 名称 / CASH）")
            continue

        shares = _num(_key(row, "shares"), "shares", errors, row_no)
        price = _num(_key(row, "price"), "price", errors, row_no)
        cost = _num(_key(row, "cost"), "cost", errors, row_no)
        market_value = _num(_key(row, "market_value"), "market_value", errors, row_no)
        for _label, _value in (("shares", shares), ("price", price),
                               ("cost", cost)):
            if _value is not None and _value < 0:
                errors.append(f"row {row_no}: {_label} 不能为负数")
                continue
        if any(v is not None and v < 0 for v in (shares, price, cost)):
            continue
        if market_value is None:
            if shares is not None and price is not None:
                market_value = shares * price
            else:
                errors.append(f"row {row_no}: 需要 market_value，或 shares + price")
                continue
        if market_value <= 0:
            errors.append(f"row {row_no}: market_value 必须大于 0（不支持做空）")
            continue

        currency = str(_key(row, "currency") or "CNY").strip().upper()
        fx = _num(_key(row, "fx_to_cny"), "fx_to_cny", errors, row_no)
        if currency == "CNY":
            fx = 1.0
        elif fx is None or fx <= 0:
            errors.append(f"row {row_no}: 非 CNY 币种需要正数 fx_to_cny")
            continue
        elif not (MIN_FX_TO_CNY <= fx <= MAX_FX_TO_CNY):
            errors.append(
                f"row {row_no}: fx_to_cny={fx:g} 超出合理范围 "
                f"({MIN_FX_TO_CNY:g}-{MAX_FX_TO_CNY:g})，请检查汇率")
            continue
        market_value_cny = market_value * fx
        if not (0 < market_value_cny <= MAX_MARKET_VALUE_CNY):
            errors.append(
                f"row {row_no}: 市值换算后超出合理范围，请检查市值/汇率/份额")
            continue

        existing = holdings.get(asset.id)
        if existing:
            existing["market_value"] += market_value_cny
            existing["native_value"] += market_value
            existing["accounts"].add(str(_key(row, "account") or ""))
            if shares is not None:
                existing["shares"] = (existing.get("shares") or 0.0) + shares
            if cost is not None:
                existing["cost"] = cost
            if price is not None:
                existing["price"] = price
        else:
            holdings[asset.id] = {
                "asset_id": asset.id,
                "symbol": raw_symbol,
                "name_zh": asset.name_zh,
                "name_en": asset.name_en,
                "class": asset.asset_class,
                "currency": currency,
                "market_value": market_value_cny,
                "native_value": market_value,
                "shares": shares,
                "price": price,
                "cost": cost,
                "accounts": {str(_key(row, "account") or "")},
            }

    total = sum(h["market_value"] for h in holdings.values())
    if total <= 0:
        errors.append("组合总市值必须大于 0")
    for h in holdings.values():
        h["weight"] = h["market_value"] / total if total > 0 else 0.0
        h["accounts"] = sorted(a for a in h["accounts"] if a)
        if h.get("cost") and h.get("price"):
            h["pnl_pct"] = h["price"] / h["cost"] - 1.0
        else:
            h["pnl_pct"] = None
            warnings.append(f"{h['asset_id']}: 缺少 cost/price，无法计算盈亏")

    class_weights: Dict[str, float] = {}
    currency_exposure: Dict[str, float] = {}
    for h in holdings.values():
        class_weights[h["class"]] = class_weights.get(h["class"], 0.0) + h["weight"]
        currency_exposure[h["currency"]] = currency_exposure.get(h["currency"], 0.0) + h["weight"]

    weights = sorted((h["weight"] for h in holdings.values()), reverse=True)
    hhi = sum(w * w for w in weights)
    return {
        "available": bool(holdings) and total > 0 and not errors,
        "total_value": round(total, 2),
        "holdings": sorted(holdings.values(), key=lambda h: -h["market_value"]),
        "class_weights": {k: round(v, 4) for k, v in
                          sorted(class_weights.items(), key=lambda kv: -kv[1])},
        "currency_exposure": {k: round(v, 4) for k, v in
                              sorted(currency_exposure.items(), key=lambda kv: -kv[1])},
        "concentration": {
            "top1": round(weights[0], 4) if weights else 0.0,
            "top3": round(sum(weights[:3]), 4),
            "hhi": round(hhi, 4),
            "effective_n": round(1.0 / hhi, 2) if hhi > 0 else 0.0,
        },
        "errors": errors,
        "warnings": warnings,
    }


def drift_analysis(xray: Dict[str, Any], plan, *,
                   asset_threshold: float = 0.02,
                   class_threshold: float = 0.05,
                   min_trade_value: float = 1000.0) -> Dict[str, Any]:
    """Compare current weights with the plan and produce a rebalance sheet."""
    if not xray.get("available"):
        return {"available": False, "reason": "holdings unavailable"}
    from ..config import get_config
    from ..data.universe import build_universe

    all_assets = {a.id: a for a in build_universe()}
    current = {h["asset_id"]: h for h in xray.get("holdings", [])}
    total = float(xray.get("total_value", 0.0))
    target = dict(plan.weights)
    slippage = float(get_config()["backtest"].get("slippage", 0.0))
    caps = plan.class_caps

    ids = sorted(set(current) | set(target))
    rows = []
    for aid in ids:
        asset = all_assets.get(aid)
        if asset is None:
            continue
        cur = current.get(aid, {})
        cur_w = float(cur.get("weight", 0.0))
        tgt_w = float(target.get(aid, 0.0))
        diff = tgt_w - cur_w
        cur_val = float(cur.get("market_value", 0.0))
        tgt_val = total * tgt_w
        trade = tgt_val - cur_val
        action = "BUY" if trade > min_trade_value else ("SELL" if trade < -min_trade_value else "HOLD")
        rows.append({
            "asset_id": aid,
            "name_zh": asset.name_zh,
            "name_en": asset.name_en,
            "class": asset.asset_class,
            "current_weight": round(cur_w, 4),
            "target_weight": round(tgt_w, 4),
            "drift": round(diff, 4),
            "current_value": round(cur_val, 2),
            "target_value": round(tgt_val, 2),
            "trade_value": round(trade, 2),
            "action": action,
            "estimated_cost": round(abs(trade) * (asset.fee + slippage), 2),
        })

    class_current: Dict[str, float] = {}
    class_target: Dict[str, float] = {}
    for aid, h in current.items():
        class_current[h["class"]] = class_current.get(h["class"], 0.0) + h["weight"]
    for aid, w in target.items():
        cls = all_assets[aid].asset_class if aid in all_assets else "unknown"
        class_target[cls] = class_target.get(cls, 0.0) + w

    class_rows = []
    for cls in sorted(set(class_current) | set(class_target)):
        cw = class_current.get(cls, 0.0)
        tw = class_target.get(cls, 0.0)
        class_rows.append({
            "class": cls, "current_weight": round(cw, 4),
            "target_weight": round(tw, 4), "drift": round(tw - cw, 4),
            "cap": caps.get(cls, 0.0),
            "violates_cap": cw > caps.get(cls, 0.0) + 1e-6,
        })

    asset_alerts = [r for r in rows if abs(r["drift"]) >= asset_threshold]
    class_alerts = [r for r in class_rows if abs(r["drift"]) >= class_threshold]
    violations = [r for r in class_rows if r["violates_cap"]]
    turnover = 0.5 * sum(abs(r["drift"]) for r in rows)
    est_cost = sum(r["estimated_cost"] for r in rows if r["action"] != "HOLD")
    return {
        "available": True,
        "total_value": round(total, 2),
        "rows": rows,
        "class_rows": class_rows,
        "asset_alerts": asset_alerts,
        "class_alerts": class_alerts,
        "violations": violations,
        "turnover": round(turnover, 4),
        "estimated_cost": round(est_cost, 2),
        "trade_count": sum(1 for r in rows if r["action"] != "HOLD"),
        "params": {"asset_threshold": asset_threshold,
                   "class_threshold": class_threshold,
                   "min_trade_value": min_trade_value},
    }