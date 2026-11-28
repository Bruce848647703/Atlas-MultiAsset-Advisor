import json
from datetime import datetime

import pytest

from invest_agent import export
from invest_agent.agent import InvestAgent
from invest_agent.portfolio import glide_path
from invest_agent.report import build_report


@pytest.fixture(scope="module")
def plan():
    return InvestAgent(output_dir="examples/demo_outputs/_export_test").offline_plan(
        {i: 2 for i in range(9)}, capital=600_000)["plan"]


def test_snapshot_is_json_serialisable_and_reproducible(plan):
    gp = glide_path.build(plan, target_value=1_000_000, years=5,
                          monthly_contrib=3_000)
    snap = export.snapshot(plan, glide_path=gp, lang="en", provider="synthetic")
    assert snap["schema"] == export.SNAPSHOT_SCHEMA
    assert snap["provider"] == "synthetic"
    assert snap["profile"]["tier"] == plan.profile.tier
    assert abs(sum(snap["plan"]["weights"].values()) - 1.0) < 1e-6
    assert "glide_path" in snap["modules"]
    raw = export.snapshot_json(plan, glide_path=gp, lang="en")
    loaded = json.loads(raw)
    assert loaded["schema"] == export.SNAPSHOT_SCHEMA
    assert loaded["modules"]["glide_path"]["available"] is True


def test_html_report_embeds_markdown_and_metadata(plan):
    gp = glide_path.build(plan, years=3, monthly_contrib=1_000)
    md = build_report(plan, {}, lang="en", glide_path=gp)
    html = export.to_html(md, title="Atlas <Report>", subtitle="Generated now",
                          footer="Research only", lang="en")
    assert html.startswith("<!doctype html>")
    assert '<html lang="en">' in html
    assert "Atlas &lt;Report&gt;" in html
    assert "Atlas <Report>" not in html
    assert "<table>" in html
    assert "Goal Plan &amp; Glide Path" in html or "Goal Plan & Glide Path" in html
    assert "<script" not in html.lower()


def test_html_language_and_timestamp(plan):
    zh = export.to_html("# 标题\n\n| A | B |\n|---|---|\n| 1 | 2 |", lang="zh")
    hant = export.to_html("# 標題", lang="zh-Hant")
    assert '<html lang="zh-CN">' in zh
    assert '<html lang="zh-Hant">' in hant
    name = export.timestamped_name("atlas_report", "html",
                                   now=datetime(2026, 11, 28, 9, 5))
    assert name == "atlas_report_20261128_0905.html"


def test_html_strips_raw_script_and_event_handlers():
    html = export.to_html(
        "# Safe\n\n<script>alert(1)</script>\n\n"
        "<img src=x onerror=\"alert(2)\">")
    lowered = html.lower()
    assert "<script" not in lowered
    assert "onerror" not in lowered
    assert "javascript:" not in lowered