from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import invest_agent.factors.factor_store as fs


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "_STORE_PATH", str(tmp_path / "store.json"))


def test_concurrent_add_factor_keeps_every_record(tmp_path, monkeypatch):
    """Dashboard sessions + the evolution daemon can write at the same time."""
    _isolate(tmp_path, monkeypatch)
    n = 30

    def add(i):
        fs.add_factor(f"factor_{i}", "test", "empirical", ic=i / 100)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(add, range(n)))

    names = {f["name"] for f in fs.load_store()}
    assert names == {f"factor_{i}" for i in range(n)}


def test_corrupt_store_is_quarantined_not_overwritten(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    store = tmp_path / "store.json"
    store.write_text("{not valid json", encoding="utf-8")

    assert fs.load_store() == []
    assert not store.exists()
    backups = list(tmp_path.glob("store.json.corrupt-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "{not valid json"

    # A fresh store can be written after quarantine.
    fs.add_factor("new", "test", "empirical")
    assert [f["name"] for f in fs.load_store()] == ["new"]


def test_non_list_payload_is_quarantined(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    (tmp_path / "store.json").write_text('{"oops": true}', encoding="utf-8")

    assert fs.load_store() == []
    assert list(tmp_path.glob("store.json.corrupt-*"))


def test_bulk_import_uses_a_single_write(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    writes = []
    original = fs._write_store
    monkeypatch.setattr(fs, "_write_store", lambda factors: (writes.append(1), original(factors)))

    root = Path(__file__).resolve().parents[1]
    n = fs.import_knowledge_base(str(root / "examples" / "factor_library_sample"))

    assert n > 0
    assert len(writes) == 1
    assert len(fs.load_store()) == n


def test_atomic_write_leaves_no_temp_files(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    fs.add_factor("x", "test", "empirical")
    assert not list(tmp_path.glob(".factor_store.*.tmp"))