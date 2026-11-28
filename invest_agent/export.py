"""Standalone report exports and reproducible snapshots.

The dashboard already renders a full Markdown report. This module turns it into
a self-contained HTML file (charts embedded as data URIs), and builds a
JSON snapshot of the plan/profile/modules so a recommendation can be shared or
reproduced later.

No live data is fetched here. The HTML uses a small print-friendly stylesheet
so a browser's "Print to PDF" produces a clean document.
"""

from __future__ import annotations

import dataclasses
import html
import json
import re
import time
from datetime import datetime
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

SNAPSHOT_SCHEMA = "atlas.snapshot.v1"

_CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { margin: 0; background: #f6f7f9; color: #1a1d21;
       font: 15px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
       "Microsoft YaHei", sans-serif; }
main { max-width: 1120px; margin: 28px auto 56px; padding: 36px 44px;
       background: #fff; border: 1px solid #e3e6ea; border-radius: 10px;
       box-shadow: 0 8px 30px rgba(20, 28, 40, .06); }
h1 { font-size: 26px; margin: 0 0 6px; letter-spacing: -.02em; }
h2 { font-size: 21px; margin: 30px 0 12px; padding-bottom: 6px;
     border-bottom: 1px solid #e3e6ea; }
h3 { font-size: 17px; margin: 24px 0 10px; }
p { margin: 8px 0; }
table { width: 100%; border-collapse: collapse; margin: 12px 0 18px;
        font-size: 13.5px; }
th, td { border: 1px solid #e3e6ea; padding: 7px 9px; text-align: right;
         vertical-align: top; }
th { background: #f3f5f8; font-weight: 600; }
th:first-child, td:first-child { text-align: left; }
blockquote { margin: 12px 0; padding: 10px 14px; background: #fafbfc;
             border-left: 3px solid #c9a227; color: #40464f; }
code { background: #f3f5f8; padding: 1px 5px; border-radius: 4px; }
pre { background: #f3f5f8; padding: 12px; overflow-x: auto; border-radius: 6px; }
img { max-width: 100%; height: auto; display: block; margin: 14px auto; }
hr { border: 0; border-top: 1px solid #e3e6ea; margin: 26px 0; }
.meta { color: #6e747d; font-size: 12.5px; margin-bottom: 18px; }
.footer { margin-top: 34px; padding-top: 12px; border-top: 1px solid #e3e6ea;
          color: #7b828c; font-size: 12px; }
@media print {
  body { background: #fff; }
  main { max-width: none; margin: 0; padding: 0; border: 0;
         box-shadow: none; border-radius: 0; }
  h2 { break-after: avoid; }
  table, img, blockquote { break-inside: avoid; }
  a { color: inherit; text-decoration: none; }
}
"""


def _jsonable(value: Any) -> Any:
    """Recursively convert dataclasses / numpy / pandas values to JSON types."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if np.isfinite(value) else None
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return [_jsonable(v) for v in value.tolist()]
    if isinstance(value, pd.Series):
        return [_jsonable(v) for v in value.tolist()]
    if isinstance(value, pd.DataFrame):
        return _jsonable(value.to_dict(orient="split"))
    if dataclasses.is_dataclass(value):
        return _jsonable(dataclasses.asdict(value))
    return str(value)


def snapshot(plan, *, profile=None, final_advice: Optional[Dict] = None,
             analyst_council: Optional[Dict] = None,
             holdings: Optional[Dict] = None,
             monte_carlo: Optional[Dict] = None,
             attribution: Optional[Dict] = None,
             glide_path: Optional[Dict] = None,
             lang: str = "zh", provider: Optional[str] = None) -> Dict[str, Any]:
    """Build a JSON-serialisable recommendation snapshot."""
    profile = profile or plan.profile
    strategy = plan.strategy
    modules = {
        "final_advice": final_advice,
        "analyst_council": analyst_council,
        "holdings": holdings,
        "monte_carlo": monte_carlo,
        "attribution": attribution,
        "glide_path": glide_path,
    }
    modules = {k: _jsonable(v) for k, v in modules.items() if v}
    return {
        "schema": SNAPSHOT_SCHEMA,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "lang": lang,
        "provider": provider or getattr(plan, "provider_name", ""),
        "segment": getattr(plan, "segment", ""),
        "profile": {
            "tier": profile.tier,
            "score": _jsonable(profile.score),
            "capital": _jsonable(profile.capital),
            "horizon_years": profile.horizon_years,
            "base_tier": getattr(profile, "base_tier", ""),
            "base_score": _jsonable(getattr(profile, "base_score", 0.0)),
            "text_tier": getattr(profile, "text_tier", ""),
            "text_adjustment": _jsonable(getattr(profile, "text_adjustment", 0.0)),
            "tier_capped": bool(getattr(profile, "tier_capped", False)),
            "answers": _jsonable(getattr(profile, "answers", {})),
        },
        "strategy": {
            "id": strategy.id,
            "name_zh": strategy.name_zh,
            "name_en": strategy.name_en,
            "objective": strategy.objective,
            "cadence": strategy.cadence,
            "tags": list(strategy.tags),
        },
        "plan": {
            "weights": _jsonable(plan.weights),
            "class_caps": _jsonable(plan.class_caps),
            "expected": _jsonable(plan.expected),
            "backtest": _jsonable(plan.backtest),
            "monthly_contrib": _jsonable(plan.monthly_contrib),
            "n_months": plan.n_months,
            "timing": _jsonable(plan.timing),
            "satellite": _jsonable(plan.satellite),
        },
        "modules": modules,
    }


def snapshot_json(plan, **kwargs) -> str:
    return json.dumps(snapshot(plan, **kwargs), ensure_ascii=False, indent=2)


def _sanitize_html(body: str) -> str:
    """Strip executable/embedded raw HTML from generated Markdown output."""
    body = re.sub(
        r"<\s*(script|iframe|object|embed|style|link|meta)\b[^>]*>.*?"
        r"<\s*/\s*\1\s*>",
        "", body, flags=re.IGNORECASE | re.DOTALL)
    body = re.sub(
        r"<\s*(script|iframe|object|embed|style|link|meta)\b[^>]*/?>",
        "", body, flags=re.IGNORECASE)
    body = re.sub(r"\son\w+\s*=\s*(['\"]).*?\1", "", body,
                  flags=re.IGNORECASE | re.DOTALL)
    body = re.sub(r"javascript:", "", body, flags=re.IGNORECASE)
    return body


def to_html(markdown_text: str, *, title: str = "Atlas Report",
            subtitle: str = "", footer: str = "", lang: str = "zh") -> str:
    """Convert the generated Markdown report to a standalone HTML document."""
    try:
        import markdown  # type: ignore
        body = markdown.markdown(
            markdown_text,
            extensions=["tables", "fenced_code", "sane_lists", "nl2br"],
            output_format="html5",
        )
    except Exception:  # pragma: no cover - dependency is in requirements
        body = f"<pre>{html.escape(markdown_text)}</pre>"
    body = _sanitize_html(body)
    _title = html.escape(title)
    _subtitle = html.escape(subtitle)
    _footer = html.escape(footer)
    _lang = "en" if lang == "en" else ("zh-Hant" if lang == "zh-Hant" else "zh-CN")
    return (
        "<!doctype html>\n"
        f"<html lang=\"{_lang}\"><head><meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"<title>{_title}</title>\n"
        "<meta name=\"generator\" content=\"Atlas Multi-Asset Advisor\">\n"
        f"<style>{_CSS}</style></head><body><main>\n"
        f"<h1>{_title}</h1>\n"
        + (f"<div class=\"meta\">{_subtitle}</div>\n" if _subtitle else "")
        + f"{body}\n"
        + (f"<div class=\"footer\">{_footer}</div>\n" if _footer else "")
        + "</main></body></html>\n"
    )


def timestamped_name(prefix: str = "atlas_report", ext: str = "html",
                     now: Optional[datetime] = None) -> str:
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M")
    return f"{prefix}_{stamp}.{ext}"