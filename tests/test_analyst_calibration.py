import numpy as np
import pandas as pd
import pytest

from invest_agent.analyst_calibration import (
    calibrate_analyst_ic, class_returns_panel, multiplier_from_ic,
    voice_multiplier,
)


def _panel(n=60):
    idx = pd.period_range("2019-01", periods=n, freq="M")
    rng = np.random.default_rng(5)
    return pd.DataFrame({
        "equity_cn": rng.normal(0.008, 0.05, n),
        "fixed_income": rng.normal(0.003, 0.01, n),
        "cash": np.full(n, 0.002),
        "commodity": rng.normal(0.004, 0.03, n),
    }, index=idx)


def test_class_returns_panel_aggregates():
    from invest_agent.data.universe import build_universe
    assets = build_universe()
    idx = pd.period_range("2020-01", periods=12, freq="M")
    df = pd.DataFrame({a.id: np.full(12, 0.01) for a in assets}, index=idx)
    panel = class_returns_panel(df, assets)
    assert "equity_cn" in panel.columns and "cash" in panel.columns
    assert np.allclose(panel.values, 0.01)


def test_ic_positive_when_tilt_matches_returns():
    panel = _panel()
    # tilt perfectly aligned with a persistent return ordering
    panel.iloc[:] = np.nan
    for t in range(len(panel)):
        panel.iloc[t] = [0.02, 0.01, 0.005, 0.008]   # equity > fi > commodity > cash
    tilt = {"equity_cn": 0.8, "fixed_income": 0.4, "cash": -0.2, "commodity": 0.0}
    ic = calibrate_analyst_ic(tilt, panel)
    assert ic > 0.9        # monotone alignment -> rank IC ≈ 1


def test_ic_negative_when_tilt_anti_matches():
    panel = _panel()
    panel.iloc[:] = np.nan
    for t in range(len(panel)):
        panel.iloc[t] = [0.02, 0.01, 0.005, 0.008]
    tilt = {"equity_cn": -0.8, "fixed_income": -0.4, "cash": 0.2, "commodity": 0.0}
    ic = calibrate_analyst_ic(tilt, panel)
    assert ic < -0.9


def test_multiplier_bounds_and_direction():
    assert multiplier_from_ic(0.0) == 1.0
    assert multiplier_from_ic(0.5) == 1.5     # capped
    assert multiplier_from_ic(-0.5) == 0.5    # floored
    assert multiplier_from_ic(0.02) == pytest.approx(1.1)
    assert multiplier_from_ic(-0.02) == pytest.approx(0.9)


def test_voice_multiplier_default_one(tmp_path, monkeypatch):
    import invest_agent.analyst_calibration as ac
    monkeypatch.setattr(ac, "_WEIGHTS_PATH", str(tmp_path / "missing.json"))
    assert voice_multiplier("buffett") == 1.0


def test_voice_multiplier_roundtrip(tmp_path, monkeypatch):
    import json
    import invest_agent.analyst_calibration as ac
    p = tmp_path / "w.json"
    monkeypatch.setattr(ac, "_WEIGHTS_PATH", str(p))
    p.write_text(json.dumps({"meta": {}, "weights": {
        "buffett": {"ic": 0.05, "multiplier": 1.25, "name_zh": "巴菲特", "school": "价值"}}}))
    assert voice_multiplier("buffett") == 1.25
    assert voice_multiplier("unknown_id") == 1.0


def test_council_vote_uses_voice(tmp_path, monkeypatch):
    """Calibrated voice changes aggregated vote weights."""
    import json
    import invest_agent.analyst_calibration as ac
    p = tmp_path / "w.json"
    monkeypatch.setattr(ac, "_WEIGHTS_PATH", str(p))
    from invest_agent.analysts import REGISTRY, council_vote
    ctx = {"regime": "risk-on",
           "plan_classes": {"equity_global": 0.6, "crypto": 0.1},
           "tier": "C5", "strategy_tags": ["momentum"], "has_crypto": True,
           "macro_stance": {}}
    base = council_vote(ctx, n=5)
    # boost every picked analyst to 1.5 and mute the rest
    ids = {v["name_zh"] for v in base["votes"]}
    name_to_id = {a.name_zh: a.id for a in REGISTRY}
    weights = {aid: {"ic": 0.1, "multiplier": (1.5 if nm in ids else 1.0),
                     "name_zh": nm, "school": ""}
               for nm, aid in name_to_id.items()}
    p.write_text(json.dumps({"meta": {}, "weights": weights}))
    boosted = council_vote(ctx, n=5)
    for v in boosted["votes"]:
        assert v["voice"] == 1.5
        assert v["weight"] > v["relevance"]      # weight = relevance * voice
