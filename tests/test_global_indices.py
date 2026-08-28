from invest_agent.global_indices import (_trading_status, _group,
                                         fetch_global_indices)


def test_trading_status_valid():
    for region in ["中国内地", "亚太", "欧洲", "美洲"]:
        assert _trading_status(region) in ("交易中", "已收盘")


def test_group_by_region():
    pack = {"updated_at": "x", "source_ok": True, "indices": [
        {"code": "a", "name": "上证指数", "region": "中国内地", "price": 1.0,
         "chg_pct": 0.1, "prev_close": 0.9, "status": "交易中", "source": "tencent"},
        {"code": "b", "name": "标普500", "region": "美洲", "price": 2.0,
         "chg_pct": -0.2, "prev_close": 2.1, "status": "已收盘", "source": "tencent"},
    ]}
    g = _group(pack)
    assert set(g["regions"]) == {"中国内地", "亚太", "欧洲", "美洲"}
    assert len(g["regions"]["中国内地"]) == 1
    assert len(g["regions"]["美洲"]) == 1
    assert g["regions"]["亚太"] == []


def test_fetch_returns_structure(tmp_path, monkeypatch):
    import invest_agent.global_indices as gi
    monkeypatch.setattr(gi, "_CACHE_PATH", str(tmp_path / "gi.json"))
    monkeypatch.setattr(gi, "_CACHE_DIR", str(tmp_path))
    # force both sources to fail -> should degrade gracefully, not raise
    monkeypatch.setattr(gi, "_fetch_tencent", lambda: (_ for _ in ()).throw(IOError("x")))
    monkeypatch.setattr(gi, "_fetch_em", lambda: (_ for _ in ()).throw(IOError("x")))
    pack = gi.fetch_global_indices(retries=1, backoff=0.0)
    assert set(pack) >= {"updated_at", "source_ok", "note", "regions"}
    assert pack["source_ok"] is False
    assert set(pack["regions"]) == {"中国内地", "亚太", "欧洲", "美洲"}


def test_fetch_with_mocked_sources(tmp_path, monkeypatch):
    import invest_agent.global_indices as gi
    monkeypatch.setattr(gi, "_CACHE_PATH", str(tmp_path / "gi.json"))
    monkeypatch.setattr(gi, "_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(gi, "_fetch_tencent", lambda: [
        {"code": "sh000001", "name": "上证指数", "region": "中国内地",
         "price": 3000.0, "chg_pct": 0.5, "prev_close": 2985.0,
         "status": "交易中", "source": "tencent"}])
    monkeypatch.setattr(gi, "_fetch_em", lambda: [
        {"code": "100.N225", "name": "日经225", "region": "亚太",
         "price": 40000.0, "chg_pct": -0.3, "prev_close": 40120.0,
         "status": "交易中", "source": "eastmoney"}])
    pack = gi.fetch_global_indices(retries=1, backoff=0.0)
    assert pack["source_ok"] is True
    assert len(pack["regions"]["中国内地"]) == 1
    assert len(pack["regions"]["亚太"]) == 1
