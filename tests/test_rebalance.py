import pytest

from invest_agent.portfolio.rebalance import analyze_drift, weights_from_positions


def test_weights_from_positions_include_cash():
    weights, total = weights_from_positions(
        {"A": 10, "B": 5, "Z": 0}, {"A": 100, "B": 200}, cash=500
    )
    assert total == pytest.approx(2500)
    assert weights["A"] == pytest.approx(0.4)
    assert weights["B"] == pytest.approx(0.4)
    assert "Z" not in weights


def test_weights_from_positions_rejects_stale_or_invalid_inputs():
    with pytest.raises(ValueError, match="missing price"):
        weights_from_positions({"A": 1}, {})
    with pytest.raises(ValueError, match="non-negative"):
        weights_from_positions({"A": -1}, {"A": 100})
    with pytest.raises(ValueError, match="positive"):
        weights_from_positions({"A": 1}, {"A": 0})
    with pytest.raises(ValueError, match="cash"):
        weights_from_positions({}, {}, cash=-1)
    with pytest.raises(ValueError, match="positive"):
        weights_from_positions({}, {}, cash=0)


def test_no_drift_produces_no_trades():
    report = analyze_drift(
        {"A": 0.5, "B": 0.3}, {"A": 0.5, "B": 0.3}, total_value=1_000
    )
    assert not report.breached
    assert report.trades == ()
    assert report.max_drift == pytest.approx(0.0)
    assert report.turnover == pytest.approx(0.0)
    assert report.target_cash_weight == pytest.approx(0.2)
    assert report.current_cash_weight == pytest.approx(0.2)


def test_breach_reports_trade_weights_and_amounts():
    report = analyze_drift(
        {"A": 0.6, "B": 0.2},
        {"A": 0.5, "B": 0.3},
        total_value=10_000,
        threshold=0.05,
    )
    assert report.breached
    assert report.max_drift == pytest.approx(0.1)
    assert report.trade_count == 2
    assert report.turnover == pytest.approx(0.1)
    by_id = {line.asset_id: line for line in report.trades}
    assert by_id["A"].trade_weight == pytest.approx(0.1)
    assert by_id["A"].trade_amount == pytest.approx(1_000)
    assert by_id["B"].trade_weight == pytest.approx(-0.1)
    assert by_id["B"].trade_amount == pytest.approx(-1_000)
    assert "cash" not in by_id


def test_cash_residual_is_rebalanced():
    report = analyze_drift(
        {"A": 0.5}, {"A": 0.9}, total_value=1_000, threshold=0.01
    )
    by_id = {line.asset_id: line for line in report.trades}
    assert report.target_cash_weight == pytest.approx(0.5)
    assert report.current_cash_weight == pytest.approx(0.1)
    assert by_id["A"].trade_weight == pytest.approx(-0.4)
    assert by_id["cash"].trade_weight == pytest.approx(0.4)
    assert report.turnover == pytest.approx(0.4)


def test_small_trades_are_suppressed_but_still_count_for_drift():
    report = analyze_drift(
        {"A": 0.500}, {"A": 0.501}, total_value=10_000,
        threshold=0.01, min_trade_weight=0.005,
    )
    assert report.trades == ()
    assert report.max_drift == pytest.approx(0.001)
    assert not report.breached


def test_missing_target_asset_is_a_sell():
    report = analyze_drift(
        {"A": 1.0}, {"A": 0.6, "B": 0.4}, total_value=100, threshold=0.0
    )
    by_id = {line.asset_id: line for line in report.trades}
    assert by_id["A"].trade_weight == pytest.approx(0.4)
    assert by_id["B"].trade_weight == pytest.approx(-0.4)


def test_report_validates_weights_and_settings():
    with pytest.raises(ValueError, match="above 1.0"):
        analyze_drift({"A": 0.7, "B": 0.4}, {"A": 1.0})
    with pytest.raises(ValueError, match="non-negative"):
        analyze_drift({"A": -0.1}, {"A": 0.1})
    with pytest.raises(ValueError, match="threshold"):
        analyze_drift({"A": 1.0}, {"A": 1.0}, threshold=1.1)
    with pytest.raises(ValueError, match="min_trade_weight"):
        analyze_drift({"A": 1.0}, {"A": 1.0}, min_trade_weight=-0.1)
    with pytest.raises(ValueError, match="total_value"):
        analyze_drift({"A": 1.0}, {"A": 1.0}, total_value=0)

def test_rebalance_cli_json_and_exit_codes(tmp_path):
    import json
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    target = tmp_path / "target.json"
    target.write_text(json.dumps({"weights": {"A": 0.6, "B": 0.4}}), encoding="utf-8")

    current = tmp_path / "current.json"
    current.write_text(json.dumps({"weights": {"A": 0.6, "B": 0.4}}), encoding="utf-8")
    command = [
        sys.executable, str(root / "scripts" / "rebalance_check.py"),
        "--target", str(target), "--current", str(current),
        "--value", "100000", "--json",
    ]
    ok = subprocess.run(command, capture_output=True, text=True, check=False)
    assert ok.returncode == 0
    payload = json.loads(ok.stdout)
    assert payload["breached"] is False
    assert payload["trades"] == []

    current.write_text(json.dumps({"weights": {"A": 0.9, "B": 0.1}}), encoding="utf-8")
    breached = subprocess.run(command, capture_output=True, text=True, check=False)
    assert breached.returncode == 1
    assert json.loads(breached.stdout)["breached"] is True
