from types import SimpleNamespace

import pytest

from invest_agent.data.universe import build_universe
from invest_agent.portfolio import holdings


def test_parse_csv_and_xray():
    rows = holdings.parse_csv(
        "symbol,market_value,currency,fx_to_cny,shares,cost,account\n"
        "510300,150000,CNY,1,30000,4.8,brokerA\n"
        "CASH,50000,CNY,1,,,brokerA\n"
    )
    xray = holdings.parse_holdings(rows)
    assert xray["available"] is True
    assert xray["total_value"] == 200000
    assert xray["class_weights"]["equity_cn"] == 0.75
    assert xray["class_weights"]["cash"] == 0.25
    assert xray["concentration"]["top1"] == 0.75


def test_duplicate_symbols_aggregate():
    rows = holdings.parse_csv(
        "symbol,market_value,currency,fx_to_cny,account\n"
        "510300,100000,CNY,1,a\n"
        "510300,50000,CNY,1,b\n"
        "CASH,50000,CNY,1,a\n"
    )
    xray = holdings.parse_holdings(rows)
    assert xray["available"] is True
    csi = next(h for h in xray["holdings"] if h["asset_id"] == "csi300_etf")
    assert csi["market_value"] == 150000
    assert csi["accounts"] == ["a", "b"]


def test_formatted_numbers_and_currency_symbols():
    xray = holdings.parse_holdings([{
        "symbol": "510300", "market_value": "¥150,000.50", "currency": "CNY",
    }])
    assert xray["available"] is True
    assert xray["total_value"] == 150000.5


def test_unknown_symbol_is_rejected():
    xray = holdings.parse_holdings(
        [{"symbol": "NOT_A_REAL_TICKER", "market_value": "1000"}])
    assert xray["available"] is False
    assert any("无法识别" in e for e in xray["errors"])


def test_missing_value_is_rejected():
    xray = holdings.parse_holdings([{"symbol": "510300", "shares": "100"}])
    assert xray["available"] is False
    assert any("market_value" in e for e in xray["errors"])


def test_non_cny_requires_fx():
    bad = holdings.parse_holdings(
        [{"symbol": "510300", "market_value": "1000", "currency": "USD"}])
    assert bad["available"] is False
    assert any("fx_to_cny" in e for e in bad["errors"])

    good = holdings.parse_holdings(
        [{"symbol": "510300", "market_value": "1000", "currency": "USD",
          "fx_to_cny": "7.2"}])
    assert good["available"] is True
    assert good["total_value"] == 7200


def test_csv_rejects_oversized_upload():
    with pytest.raises(ValueError, match="过大"):
        holdings.parse_csv(b"x" * (holdings.MAX_CSV_BYTES + 1))


def test_csv_rejects_too_many_rows():
    body = "symbol,market_value\n" + "510300,1000\n" * (holdings.MAX_CSV_ROWS + 1)
    with pytest.raises(ValueError, match="行数过多"):
        holdings.parse_csv(body)


def test_csv_accepts_gb18030_export():
    rows = holdings.parse_csv(
        "代码,市值,币种\n510300,100000,人民币\n".encode("gb18030"))
    assert rows[0]["代码"] == "510300"


def test_parse_holdings_rejects_too_many_rows():
    rows = [{"symbol": "510300", "market_value": "100"}
            for _ in range(holdings.MAX_CSV_ROWS + 1)]
    xray = holdings.parse_holdings(rows)
    assert xray["available"] is False
    assert any("行数过多" in e for e in xray["errors"])


def test_fx_out_of_range_is_rejected():
    xray = holdings.parse_holdings(
        [{"symbol": "510300", "market_value": "1000", "currency": "USD",
          "fx_to_cny": "72"}])
    assert xray["available"] is False
    assert any("超出合理范围" in e for e in xray["errors"])


def test_absurd_market_value_is_rejected():
    xray = holdings.parse_holdings(
        [{"symbol": "510300", "market_value": "1e308", "currency": "USD",
          "fx_to_cny": "7.2"}])
    assert xray["available"] is False
    assert any("超出合理范围" in e for e in xray["errors"])


def test_negative_quantity_is_rejected():
    xray = holdings.parse_holdings(
        [{"symbol": "510300", "shares": "-100", "price": "5"}])
    assert xray["available"] is False
    assert any("不能为负数" in e for e in xray["errors"])


def test_symbol_map_handles_missing_symbol_ak():
    asset = SimpleNamespace(id="csi300_etf", name_zh="沪深300ETF",
                            name_en="CSI300 ETF", asset_class="equity_cn",
                            meta={"symbol_ak": None})
    xray = holdings.parse_holdings(
        [{"symbol": "csi300_etf", "market_value": "1000"}], universe=[asset])
    assert xray["available"] is True
    assert xray["holdings"][0]["asset_id"] == "csi300_etf"


def test_drift_and_trade_list():
    assets = build_universe()
    plan = SimpleNamespace(
        assets=assets,
        weights={"csi300_etf": 0.5, "bond_etf": 0.5},
        class_caps={"equity_cn": 0.8, "fixed_income": 0.5, "cash": 0.2},
    )
    rows = holdings.parse_csv(
        "symbol,market_value,currency,fx_to_cny\n"
        "510300,50000,CNY,1\n"
        "CASH,150000,CNY,1\n"
    )
    xray = holdings.parse_holdings(rows)
    drift = holdings.drift_analysis(xray, plan)
    assert drift["available"] is True
    assert drift["total_value"] == 200000
    assert drift["turnover"] > 0
    by_asset = {r["asset_id"]: r for r in drift["rows"]}
    assert by_asset["csi300_etf"]["action"] == "BUY"
    assert by_asset["money_fund"]["action"] == "SELL"
    assert drift["estimated_cost"] > 0
    assert "equity_cn" in {r["class"] for r in drift["class_rows"]}


def test_drift_flags_suitability_violation():
    assets = build_universe()
    plan = SimpleNamespace(assets=assets, weights={"bond_etf": 1.0},
                           class_caps={"fixed_income": 0.4, "cash": 0.2})
    xray = holdings.parse_holdings(holdings.parse_csv(
        "symbol,market_value,currency,fx_to_cny\nCASH,100000,CNY,1\n"))
    drift = holdings.drift_analysis(xray, plan)
    assert drift["violations"]
    assert drift["violations"][0]["class"] == "cash"