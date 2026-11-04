"""Factor knowledge base loader.

Parses page-level JSON files (year/page_XXXX.json) produced by the factor
extraction pipeline into a clean catalog:

    factor_name / category / formula / variables / direction / rationale

Direction priors are mined from the rationale text: phrases like
"与未来收益正相关" mark the factor as return-positive, "负相关" as negative.
High-frequency factor families are flagged as not-computable on monthly data
so downstream code only uses what it honestly can.
"""

from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Optional

from ..config import get_config

POSITIVE_PHRASES = ["正相关", "正向预测", "正向影响", "显著为正", "收益更高", "未来收益高"]
NEGATIVE_PHRASES = ["负相关", "负向预测", "负向影响", "显著为负", "反转效应", "收益更低"]


@dataclass
class Factor:
    name: str
    name_cn: str
    category: str
    formula: str = ""
    variables: List[Dict[str, str]] = field(default_factory=list)
    rationale: str = ""
    direction: int = 0          # +1 / -1 / 0 (unknown)
    is_high_freq: bool = False
    n_records: int = 1


@dataclass
class FactorCatalog:
    factors: Dict[str, Factor]
    categories: Dict[str, List[str]]     # category -> factor names
    n_records: int = 0

    def search(self, query: str, limit: int = 8) -> List[Factor]:
        q = query.lower()
        out = []
        for f in self.factors.values():
            hay = f"{f.name} {f.name_cn} {f.category}".lower()
            if q in hay:
                out.append(f)
        out.sort(key=lambda f: -f.n_records)
        return out[:limit]

    def by_category(self, category: str, limit: int = 20) -> List[Factor]:
        names = self.categories.get(category, [])
        return [self.factors[n] for n in names[:limit]]

    def category_summary(self) -> List[Dict[str, object]]:
        return [
            {"category": c, "n_factors": len(names)}
            for c, names in sorted(self.categories.items(), key=lambda kv: -len(kv[1]))
        ]


def _direction_of(text: str) -> int:
    pos = any(p in text for p in POSITIVE_PHRASES)
    neg = any(p in text for p in NEGATIVE_PHRASES)
    if pos and not neg:
        return 1
    if neg and not pos:
        return -1
    return 0


def load_catalog(data_dir: str) -> FactorCatalog:
    factors: Dict[str, Factor] = {}
    categories: Dict[str, List[str]] = {}
    n_records = 0
    if not os.path.isdir(data_dir):
        return FactorCatalog(factors={}, categories={}, n_records=0)

    for fp in sorted(glob.glob(os.path.join(data_dir, "*", "page_*.json"))):
        try:
            with open(fp, "r", encoding="utf-8") as f:
                doc = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        for s in doc.get("signals", []) or []:
            name = (s.get("manual_factor_name") or s.get("signal_name_cn") or "").strip()
            if not name:
                continue
            n_records += 1
            cat = s.get("signal_type_cn", "未分类")
            raw = s.get("raw_text", "") or ""
            if name in factors:
                f0 = factors[name]
                f0.n_records += 1
                if f0.direction == 0:
                    f0.direction = _direction_of(raw)
                if len(raw) > len(f0.rationale):
                    f0.rationale = raw
                continue
            factors[name] = Factor(
                name=name,
                name_cn=s.get("signal_name_cn", name),
                category=cat,
                formula=s.get("formula", "") or "",
                variables=s.get("variables", []) or [],
                rationale=raw,
                direction=_direction_of(raw),
                is_high_freq=cat.startswith("高频"),
            )
            categories.setdefault(cat, []).append(name)

    return FactorCatalog(factors=factors, categories=categories, n_records=n_records)


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BUNDLED_SAMPLE = os.path.join(_PROJECT_ROOT, "examples", "factor_library_sample")


def default_data_dir() -> str:
    """Resolve the configured factor-library directory.

    Empty/unset means the bundled ``examples/factor_library_sample`` so the
    knowledge base works out of the box. Relative paths are resolved against
    the project root, not the current working directory.
    """
    cfg = get_config().get("factors", {}) or {}
    value = str(cfg.get("data_dir", "") or "").strip()
    if not value:
        return _BUNDLED_SAMPLE
    if not os.path.isabs(value):
        value = os.path.join(_PROJECT_ROOT, value)
    return os.path.normpath(value)


def _default_dir() -> str:
    return default_data_dir()


@lru_cache(maxsize=4)
def default_catalog(data_dir: Optional[str] = None) -> FactorCatalog:
    return load_catalog(data_dir or _default_dir())
