"""Persistent factor library for the project.

A single JSON store (`data/factor_store.json`) holding ALL factors the system
knows — both imported from the external knowledge base and learned/collected
over time. Each factor carries provenance (source, added date) and, for learned
factors, a measured information coefficient (IC).

This is the memory substrate of the self-evolution loop: evolution adds new
factors here; the advisor/lens read from here.

Concurrency: the dashboard, the evolution daemon, and tool calls can write
concurrently. We therefore serialise read-modify-write cycles with an advisory
file lock (`<store>.lock`) and replace the JSON atomically (temp file + rename),
so readers never observe a half-written store. Locking is POSIX (Linux/macOS);
on other platforms it degrades to an in-process lock.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import threading
import time
from datetime import datetime
from typing import Dict, Iterator, List, Optional

try:  # POSIX advisory locks; Windows falls back to an in-process lock
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX
    fcntl = None

_STORE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data", "factor_store.json")

# Seconds to wait for another writer before giving up. Kept generous enough to
# cover a bulk knowledge-base import.
_LOCK_TIMEOUT = float(os.environ.get("ATLAS_STORE_LOCK_TIMEOUT", "30"))
_thread_lock = threading.Lock()


def _ensure_dir():
    directory = os.path.dirname(_STORE_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)


@contextlib.contextmanager
def _store_lock() -> Iterator[None]:
    """Serialise writers across threads and processes."""
    _ensure_dir()
    if fcntl is None:
        with _thread_lock:
            yield
        return

    lock_path = _STORE_PATH + ".lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        deadline = time.monotonic() + _LOCK_TIMEOUT
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"factor store is locked by another writer: {lock_path}")
                time.sleep(0.05)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _quarantine_corrupt_store() -> Optional[str]:
    """Move an unreadable store aside so it is never silently overwritten."""
    backup = f"{_STORE_PATH}.corrupt-{datetime.now():%Y%m%d-%H%M%S-%f}"
    try:
        os.replace(_STORE_PATH, backup)
        return backup
    except OSError:
        return None


def _read_store() -> List[Dict]:
    if not os.path.exists(_STORE_PATH):
        return []
    try:
        with open(_STORE_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        _quarantine_corrupt_store()
        return []
    if not isinstance(data, list):
        _quarantine_corrupt_store()
        return []
    return data


def _write_store(factors: List[Dict]) -> None:
    """Atomic write: a crash can leave a stale temp file, never a torn store."""
    _ensure_dir()
    directory = os.path.dirname(_STORE_PATH) or "."
    fd, tmp = tempfile.mkstemp(prefix=".factor_store.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(factors, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, _STORE_PATH)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load_store() -> List[Dict]:
    return _read_store()


def save_store(factors: List[Dict]) -> None:
    with _store_lock():
        _write_store(factors)


def _upsert(factors: List[Dict], name: str, category: str, source: str, *,
            name_cn: str = "", formula: str = "", direction: int = 0,
            ic: Optional[float] = None, rationale: str = "",
            code: str = "", meta: Optional[Dict] = None,
            overwrite: bool = False) -> Dict:
    idx = next((i for i, f in enumerate(factors) if f.get("name") == name), None)
    rec = {
        "name": name,
        "name_cn": name_cn or name,
        "category": category,
        "formula": formula,
        "direction": int(direction),          # +1 / -1 / 0(unknown)
        "source": source,                     # e.g. knowledge_base | empirical | online
        "added_date": datetime.now().strftime("%Y-%m-%d"),
        "ic": ic,
        "rationale": rationale,
        "code": code,                         # optional executable implementation
        "meta": meta or {},                   # operator / variables / validation
    }
    if idx is not None:
        if overwrite:
            rec["added_date"] = factors[idx].get("added_date", rec["added_date"])
            rec["ic"] = ic if ic is not None else factors[idx].get("ic")
            factors[idx] = rec
        else:
            # keep existing, just refresh IC/code if provided
            if ic is not None:
                factors[idx]["ic"] = ic
            if code:
                factors[idx]["code"] = code
            rec = factors[idx]
    else:
        factors.append(rec)
    return rec


def add_factor(name: str, category: str, source: str, *,
               name_cn: str = "", formula: str = "", direction: int = 0,
               ic: Optional[float] = None, rationale: str = "",
               code: str = "", meta: Optional[Dict] = None,
               overwrite: bool = False) -> Dict:
    """Add (or update) one factor; dedupes by name. Returns the record."""
    with _store_lock():
        factors = _read_store()
        rec = _upsert(factors, name, category, source,
                      name_cn=name_cn, formula=formula, direction=direction,
                      ic=ic, rationale=rationale, code=code, meta=meta,
                      overwrite=overwrite)
        _write_store(factors)
        return rec


def import_knowledge_base(data_dir: str, limit: Optional[int] = None) -> int:
    """Bulk-import the external JSON factor knowledge base (provenance kept).

    Performs a single locked read-modify-write instead of one write per factor,
    which matters for the ~1k-factor library.
    """
    from .loader import load_catalog
    cat = load_catalog(data_dir)
    with _store_lock():
        factors = _read_store()
        n = 0
        for name, f in cat.factors.items():
            _upsert(factors, name, f.category, source="knowledge_base",
                    name_cn=f.name_cn, formula=f.formula, direction=f.direction,
                    rationale=(f.rationale or "")[:200], overwrite=False)
            n += 1
            if limit and n >= limit:
                break
        _write_store(factors)
    return n


def stats() -> Dict:
    factors = load_store()
    by_src: Dict[str, int] = {}
    with_ic = 0
    for f in factors:
        by_src[f.get("source", "?")] = by_src.get(f.get("source", "?"), 0) + 1
        if f.get("ic") is not None:
            with_ic += 1
    return {"total": len(factors), "by_source": by_src, "with_ic": with_ic}