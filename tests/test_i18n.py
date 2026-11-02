import re

from dashboard.i18n import (
    S, account_label, asset_type_label, base_category_label, cadence_label,
    class_label, index_label, note_label, objective_label, option_text,
    school_label, source_label, strategy_name, strategy_philosophy, t,
    theme_label,
)
from invest_agent.analysts import REGISTRY
from invest_agent.risk_profiler import QUESTIONS
from invest_agent.strategy import STRATEGY_MENU

CJK = re.compile(r"[\u4e00-\u9fff]")


def test_ui_catalog_is_fully_translated():
    for key, (_zh, en) in S.items():
        assert en, f"missing English for {key}"
        assert not CJK.search(en), f"English still contains Chinese for {key}: {en}"


def test_three_languages_render():
    assert t("indices.title", "zh") == "全球市场指数"
    assert t("indices.title", "en") == "Global Market Indices"
    assert t("indices.title", "zh-Hant") == "全球市場指數"


def test_template_formatting():
    assert t("geo.appetite", "en") == "Risk appetite"
    assert "42" in t("geo.themes", "en", themes="42")


def test_structured_entities_in_english():
    assert class_label("equity_cn", "en") == "China equities"
    assert objective_label("max_sharpe", "en") == "Max Sharpe"
    assert index_label("沪深300", "en") == "CSI 300"
    assert option_text(QUESTIONS[0][3][0], "en") == "Above 60"
    assert strategy_name(STRATEGY_MENU[0], "en") == "Steady Carry"


def test_every_analyst_school_has_english():
    for a in REGISTRY:
        school = school_label(a.school, "en")
        assert school and not CJK.search(school), a.school


def test_other_entity_labels_have_english():
    cases = [
        (class_label, ["cash", "fixed_income", "hybrid", "commodity",
                       "equity_cn", "equity_global", "crypto", "futures"]),
        (objective_label, ["max_sharpe", "mean_variance", "min_vol", "risk_parity"]),
        (cadence_label, ["high", "mid", "low"]),
        (base_category_label, ["onshore", "crossborder", "offshore"]),
        (asset_type_label, ["cash_deposit", "a_share", "cn_fund", "hk_us_stock",
                            "crypto", "gold", "other"]),
        (account_label, ["none", "hk", "us", "sg", "other_offshore"]),
        (source_label, ["东财快讯", "新闻联播", "财经日历"]),
        (index_label, ["上证指数", "沪深300", "恒生指数", "标普500", "德国DAX"]),
        (theme_label, ["地缘冲突", "贸易/关税", "央行/利率", "增长/景气"]),
        (note_label, ["部分国际指数(东财源)暂不可用", "全球指数数据暂不可用"]),
    ]
    for fn, values in cases:
        for value in values:
            out = fn(value, "en")
            assert out and not CJK.search(out), (fn.__name__, value, out)


def test_strategy_philosophy_has_english():
    for s in STRATEGY_MENU:
        out = strategy_philosophy(s, "en")
        assert out and not CJK.search(out), s.id