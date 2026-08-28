"""Persistent factor library for the project.

A single JSON store (`data/factor_store.json`) holding ALL factors the system
knows — both imported from the external knowledge base and learned/collected
over time. Each factor carries provenance (source, added date) and, for learned
factors, a measured information coefficient (IC).

This is the memory substrate of the self-evolution loop: evolution adds new
factors here; the advisor/lens read from here.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Dict, List, Optional

_STORE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data", "factor_store.json")


def _ensure_dir():
    os.makedirs(os.path.dirname(_STORE_PATH), exist_ok=True)


def load_store() -> List[Dict]:
    if not os.path.exists(_STORE_PATH):
        return []
    try:
        with open(_STORE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return []


def save_store(factors: List[Dict]) -> None:
    _ensure_dir()
    with open(_STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(factors, f, ensure_ascii=False, indent=1)


def add_factor(name: str, category: str, source: str, *,
               name_cn: str = "", formula: str = "", direction: int = 0,
               ic: Optional[float] = None, rationale: str = "",
               overwrite: bool = False) -> Dict:
    """Add (or update) one factor; dedupes by name. Returns the record."""
    factors = load_store()
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
    }
    if idx is not None:
        if overwrite:
            rec["added_date"] = factors[idx].get("added_date", rec["added_date"])
            rec["ic"] = ic if ic is not None else factors[idx].get("ic")
            factors[idx] = rec
        else:
            # keep existing, just refresh IC if provided
            if ic is not None:
                factors[idx]["ic"] = ic
            rec = factors[idx]
    else:
        factors.append(rec)
    save_store(factors)
    return rec


def import_knowledge_base(data_dir: str, limit: Optional[int] = None) -> int:
    """Bulk-import the external JSON factor knowledge base (provenance kept)."""
    from .loader import load_catalog
    cat = load_catalog(data_dir)
    n = 0
    for name, f in cat.factors.items():
        add_factor(name, f.category, source="knowledge_base",
                   name_cn=f.name_cn, formula=f.formula, direction=f.direction,
                   rationale=(f.rationale or "")[:200], overwrite=False)
        n += 1
        if limit and n >= limit:
            break
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
