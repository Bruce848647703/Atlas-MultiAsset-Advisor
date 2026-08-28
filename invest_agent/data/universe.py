"""Asset universe helpers built from config/assets.yaml."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from ..config import asset_universe


@dataclass
class Asset:
    id: str
    name_zh: str
    name_en: str
    asset_class: str
    fee: float = 0.0005
    currency: str = "CNY"
    meta: Dict[str, object] = field(default_factory=dict)


def build_universe(include_classes: List[str] = None) -> List[Asset]:
    out = []
    for row in asset_universe():
        if include_classes and row["class"] not in include_classes:
            continue
        out.append(
            Asset(
                id=row["id"],
                name_zh=row.get("name_zh", row["id"]),
                name_en=row.get("name_en", row["id"]),
                asset_class=row["class"],
                fee=float(row.get("fee", 0.0005)),
                currency=row.get("currency", "CNY"),
                meta={k: v for k, v in row.items() if k not in ("id", "name_zh", "name_en", "class", "fee", "currency")},
            )
        )
    return out


def asset_classes(assets: List[Asset]) -> List[str]:
    return [a.asset_class for a in assets]


def asset_ids(assets: List[Asset]) -> List[str]:
    return [a.id for a in assets]
