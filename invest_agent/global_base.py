"""Global asset-basing advisory (family-office style).

A "base" is WHERE an investor domiciles / accesses a slice of their global
portfolio — an onshore account, a cross-border channel, or an offshore
structure. Each base carries friction (capital control, tax, FX, access
barrier, compliance). Given an investor's risk profile + asset profile, this
module ranks the world's suitable bases and scores them, family-office style.

score = 100 * ( fit − λ·friction )
  fit      = capital_fit·asset_fit·risk_fit·experience_fit   (0..1 each)
  friction = weighted sum of capital_control/tax/fx/access/compliance (0..1)

Everything is deterministic and explainable — every score ships with reasons.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Asset profile (enriched questionnaire: what the investor actually holds)
# ---------------------------------------------------------------------------
ASSET_TYPE_OPTIONS = [
    ("cash_deposit", "现金/存款/货基"),
    ("a_share", "A股/境内股票"),
    ("cn_fund", "境内公募基金"),
    ("bank_wm", "银行理财/信托"),
    ("bond", "债券/债基"),
    ("realestate", "房产"),
    ("insurance", "保险(储蓄型)"),
    ("hk_us_stock", "港股/美股"),
    ("overseas_fund", "境外基金"),
    ("crypto", "加密货币"),
    ("gold", "黄金/贵金属"),
    ("other", "其他"),
]

OVERSEAS_ACCOUNT_OPTIONS = [
    ("none", "暂无境外账户"),
    ("hk", "香港券商/银行"),
    ("us", "美国券商"),
    ("sg", "新加坡"),
    ("other_offshore", "其他离岸"),
]

# structured asset-profile questionnaire (rendered by the dashboard)
ASSET_PROFILE_QUESTIONS = [
    {"id": "asset_types", "label": "您当前持有的资产类型（多选）",
     "type": "multiselect", "options": ASSET_TYPE_OPTIONS},
    {"id": "overseas_pct", "label": "现有资产中境外部分的大致占比",
     "type": "slider", "min": 0, "max": 100, "step": 5},
    {"id": "overseas_accounts", "label": "已开立的境外账户（多选）",
     "type": "multiselect", "options": OVERSEAS_ACCOUNT_OPTIONS},
    {"id": "liquidity_need", "label": "流动性需求",
     "type": "select", "options": [("low", "低(长期不动用)"), ("medium", "中"), ("high", "高(随时可能用)")]},
]


@dataclass
class AssetProfile:
    """The investor's current asset situation (from enriched questionnaire)."""
    asset_types: List[str] = field(default_factory=list)   # ids from ASSET_TYPE_OPTIONS
    overseas_pct: float = 0.0                              # % already overseas (0..100)
    overseas_accounts: List[str] = field(default_factory=list)  # ids from OVERSEAS_ACCOUNT_OPTIONS
    total_capital: float = 0.0                             # CNY
    crypto_held: bool = False
    annual_income: float = 0.0
    liquidity_need: str = "medium"                         # low/medium/high


# ---------------------------------------------------------------------------
# Global base catalog
# ---------------------------------------------------------------------------
@dataclass
class GlobalBase:
    id: str
    name_zh: str
    name_en: str
    category: str                      # onshore / crossborder / offshore
    desc: str
    friction: Dict[str, float]         # capital_control/tax/fx/access/compliance 0..1
    min_capital: float = 0.0           # CNY threshold (0 = none)
    qualified_only: bool = False       # 需要合格投资者认定
    need_overseas_exp: bool = False    # 需要境外经验/账户
    supports: List[str] = field(default_factory=list)   # asset classes it can hold
    tier_range: tuple = ("C1", "C5")  # suitable risk tiers
    notes: str = ""


GLOBAL_BASES: List[GlobalBase] = [
    GlobalBase(
        id="a_share_acct", name_zh="A股证券账户", name_en="A-share brokerage",
        category="onshore",
        desc="境内股票/ETF/可转债，人民币计价，无资本管制，摩擦最低。",
        friction={"capital_control": 0.0, "tax": 0.2, "fx": 0.0, "access": 0.05, "compliance": 0.1},
        min_capital=0, supports=["equity_cn", "fund_cn", "bond_cn"],
        notes="适合全部等级的境内权益与指数配置。"),
    GlobalBase(
        id="cn_public_fund", name_zh="境内公募基金(含QDII)", name_en="Onshore funds incl. QDII",
        category="onshore",
        desc="公募权益/债券/货基；QDII基金可间接配海外(受额度限制)。",
        friction={"capital_control": 0.15, "tax": 0.15, "fx": 0.1, "access": 0.05, "compliance": 0.1},
        min_capital=0, supports=["equity_cn", "equity_global", "bond", "money",
                                 "commodity", "fund", "fund_cn", "wm"],
        notes="低门槛出海首选(通过QDII)，但额度紧张时限购。"),
    GlobalBase(
        id="bank_wm_deposit", name_zh="银行理财/存款", name_en="Bank WM / deposit",
        category="onshore",
        desc="存款/理财/大额存单，低风险流动性底仓。",
        friction={"capital_control": 0.0, "tax": 0.05, "fx": 0.0, "access": 0.0, "compliance": 0.05},
        min_capital=0, supports=["money", "bond", "wm", "fund"],
        tier_range=("C1", "C3"), notes="应急金与保守资金的主要落位。"),
    GlobalBase(
        id="hk_connect", name_zh="沪深港通(北向/南向)", name_en="Stock Connect",
        category="crossborder",
        desc="经境内券商买卖港股(南向)，人民币结算，标的受名单限制。",
        friction={"capital_control": 0.2, "tax": 0.25, "fx": 0.1, "access": 0.2, "compliance": 0.15},
        min_capital=500_000, supports=["equity_hk"],
        notes="50万门槛；红利税与标的范围是主要摩擦。"),
    GlobalBase(
        id="bond_connect", name_zh="债券通", name_en="Bond Connect",
        category="crossborder",
        desc="跨境债券投资通道(南向)，面向合格投资者。",
        friction={"capital_control": 0.25, "tax": 0.2, "fx": 0.1, "access": 0.35, "compliance": 0.2},
        min_capital=1_000_000, qualified_only=True, supports=["bond"],
        notes="机构/合格投资者为主。"),
    GlobalBase(
        id="gbm_wealth_connect", name_zh="跨境理财通(大湾区)", name_en="GBM Wealth Connect",
        category="crossborder",
        desc="大湾区居民双向购买港澳/内地理财产品，额度个人100万。",
        friction={"capital_control": 0.3, "tax": 0.15, "fx": 0.15, "access": 0.3, "compliance": 0.2},
        min_capital=0, supports=["fund", "wm"],
        notes="限大湾区户籍/社保，区域性强。"),
    GlobalBase(
        id="hk_brokerage", name_zh="香港券商账户", name_en="HK brokerage",
        category="offshore",
        desc="港美股/基金/债券一站式，品种全；需资金出境(受外汇管理)。",
        friction={"capital_control": 0.7, "tax": 0.2, "fx": 0.35, "access": 0.4, "compliance": 0.3},
        min_capital=100_000, need_overseas_exp=True,
        supports=["equity_hk", "equity_us", "fund", "bond", "crypto_etf"],
        notes="出海主流落位；资金合规出境是最大摩擦。"),
    GlobalBase(
        id="hk_insurance", name_zh="香港储蓄保险", name_en="HK savings insurance",
        category="offshore",
        desc="美元/港币储蓄险，长期锁定+传承功能，流动性差。",
        friction={"capital_control": 0.7, "tax": 0.1, "fx": 0.35, "access": 0.4, "compliance": 0.25},
        min_capital=100_000, need_overseas_exp=True, supports=["insurance"],
        tier_range=("C1", "C3"), notes="适合长期保障/传承，非交易型。"),
    GlobalBase(
        id="sg_family_office", name_zh="新加坡家办/账户", name_en="Singapore family office",
        category="offshore",
        desc="新加坡单一家办(13O/13U)或多币账户，税收友好、隐私好，门槛高。",
        friction={"capital_control": 0.75, "tax": 0.05, "fx": 0.3, "access": 0.85, "compliance": 0.4},
        min_capital=10_000_000, qualified_only=True, need_overseas_exp=True,
        supports=["equity_global", "fund", "bond", "alternative", "insurance"],
        tier_range=("C3", "C5"), notes="单一家办通常要求 AUM≥等值2000万新币，享税收优惠。"),
    GlobalBase(
        id="us_brokerage", name_zh="美国券商账户", name_en="US brokerage",
        category="offshore",
        desc="直接配美股/ETF，品种最全；涉 FATCA 申报与资金出境。",
        friction={"capital_control": 0.7, "tax": 0.35, "fx": 0.35, "access": 0.5, "compliance": 0.5},
        min_capital=50_000, need_overseas_exp=True, supports=["equity_us", "fund", "bond"],
        notes="非居民涉 30% 股息预提税与遗产税问题。"),
    GlobalBase(
        id="crypto_exchange", name_zh="合规加密交易所", name_en="Regulated crypto exchange",
        category="offshore",
        desc="主流币现货/理财，高波动高弹性；监管与托管风险需自担。",
        friction={"capital_control": 0.6, "tax": 0.2, "fx": 0.3, "access": 0.3, "compliance": 0.6},
        min_capital=0, need_overseas_exp=True, supports=["crypto"],
        tier_range=("C4", "C5"), notes="仅限高风险等级小仓位，注意出入金合规。"),
    GlobalBase(
        id="overseas_realestate", name_zh="海外不动产", name_en="Overseas real estate",
        category="offshore",
        desc="海外住宅/商业地产，抗通胀+分散，流动性差、持有成本高。",
        friction={"capital_control": 0.75, "tax": 0.4, "fx": 0.35, "access": 0.6, "compliance": 0.35},
        min_capital=2_000_000, need_overseas_exp=True, supports=["realestate"],
        tier_range=("C3", "C5"), notes="非流动性资产，占组合比例宜控制。"),
]


# ---------------------------------------------------------------------------
# Friction aggregation
# ---------------------------------------------------------------------------
FRICTION_WEIGHTS = {"capital_control": 0.35, "tax": 0.15, "fx": 0.15,
                    "access": 0.15, "compliance": 0.20}


def base_friction(base: GlobalBase) -> float:
    return sum(base.friction.get(k, 0.0) * w for k, w in FRICTION_WEIGHTS.items())


# ---------------------------------------------------------------------------
# Fit scoring
# ---------------------------------------------------------------------------
_TIER_ORDER = {"C1": 1, "C2": 2, "C3": 3, "C4": 4, "C5": 5}

# map investor-held asset types -> base.supported tags
_ASSET_TO_BASE_TAG = {
    "cash_deposit": ["money"], "a_share": ["equity_cn"], "cn_fund": ["fund_cn", "fund"],
    "bank_wm": ["wm", "money"], "bond": ["bond", "bond_cn"], "realestate": ["realestate"],
    "insurance": ["insurance"], "hk_us_stock": ["equity_hk", "equity_us"],
    "overseas_fund": ["fund"], "crypto": ["crypto"], "gold": ["commodity"],
}


def _capital_fit(base: GlobalBase, capital: float) -> float:
    if base.min_capital <= 0:
        return 1.0
    if capital >= base.min_capital:
        return 1.0
    # below threshold: graded by how close (but never fully accessible)
    return max(0.0, capital / base.min_capital) * 0.5


def _asset_fit(base: GlobalBase, asset_types: List[str]) -> float:
    """Is this base relevant to what the investor holds? A base covers specific
    classes, so relevance (not full-portfolio coverage) is the right notion."""
    if not asset_types:
        return 0.5
    wanted = set()
    for at in asset_types:
        wanted.update(_ASSET_TO_BASE_TAG.get(at, []))
    if not wanted:
        return 0.5
    overlap = wanted & set(base.supports)
    if not overlap:
        return 0.2                     # base irrelevant to current holdings
    return min(1.0, 0.6 + 0.15 * len(overlap))


def _risk_fit(base: GlobalBase, tier: str) -> float:
    lo, hi = base.tier_range
    if _TIER_ORDER[lo] <= _TIER_ORDER[tier] <= _TIER_ORDER[hi]:
        return 1.0
    dist = min(abs(_TIER_ORDER[tier] - _TIER_ORDER[lo]),
               abs(_TIER_ORDER[tier] - _TIER_ORDER[hi]))
    return max(0.0, 1.0 - 0.4 * dist)


def _experience_fit(base: GlobalBase, asset_profile: AssetProfile) -> float:
    if not base.need_overseas_exp:
        return 1.0
    has_offshore = any(a != "none" for a in asset_profile.overseas_accounts)
    if has_offshore or asset_profile.overseas_pct > 5:
        return 1.0
    return 0.35   # no experience: possible but higher friction / learning cost


def _overseas_fit(base: GlobalBase, overseas_pct: float) -> float:
    """Does this base serve the investor's INTENDED overseas allocation?

    overseas_pct is the share the investor wants/needs to place offshore.
      * onshore bases CANNOT hold overseas assets -> penalized as overseas_pct rises
      * crossborder channels serve it partially
      * offshore bases fully serve it -> boosted as overseas_pct rises
    This is what makes "境外100%" correctly rank offshore bases above onshore ones.
    """
    need = max(0.0, min(100.0, overseas_pct)) / 100.0
    if base.category == "onshore":
        return 1.0 - 0.75 * need          # 0 -> 1.0, 100 -> 0.25
    if base.category == "crossborder":
        return 0.6 + 0.4 * need           # 0 -> 0.6, 100 -> 1.0
    return 0.4 + 0.6 * need               # offshore: 0 -> 0.4, 100 -> 1.0


def recommend_bases(tier: str, asset_profile: AssetProfile,
                    lambda_friction: float = 0.8) -> List[Dict]:
    """Rank global bases for the investor. Returns list of
    {base, score, fit_breakdown, friction, reasons} sorted by score desc.
    score = 100 · fit · (1 − min(0.85, λ·friction)) — friction discounts fit."""
    results = []
    for base in GLOBAL_BASES:
        cap_fit = _capital_fit(base, asset_profile.total_capital)
        asset_fit = _asset_fit(base, asset_profile.asset_types)
        risk_fit = _risk_fit(base, tier)
        exp_fit = _experience_fit(base, asset_profile)
        overseas_fit = _overseas_fit(base, asset_profile.overseas_pct)
        fit = cap_fit * asset_fit * risk_fit * exp_fit * overseas_fit
        fric = base_friction(base)
        friction_penalty = min(0.85, lambda_friction * fric)
        score = 100.0 * fit * (1.0 - friction_penalty)

        reasons = []
        if cap_fit < 1.0 and base.min_capital > 0:
            reasons.append(f"门槛 ¥{base.min_capital:,.0f}(资本适配 {cap_fit:.2f})")
        if asset_fit >= 0.6:
            reasons.append("匹配现有资产类型")
        elif asset_fit < 0.3:
            reasons.append("与现有资产匹配度低")
        if asset_profile.overseas_pct >= 50 and base.category == "offshore":
            reasons.append(f"境外占比{asset_profile.overseas_pct:.0f}%，离岸落位契合")
        elif asset_profile.overseas_pct >= 50 and base.category == "onshore":
            reasons.append("境内通道难以承载高境外占比")
        if risk_fit < 1.0:
            reasons.append("风险等级与base不完全匹配")
        if exp_fit < 1.0:
            reasons.append("缺境外经验/账户，学习成本较高")
        if fric >= 0.5:
            reasons.append("摩擦偏高(资本管制/汇兑/合规)")
        elif fric <= 0.15:
            reasons.append("低摩擦通道")

        results.append({
            "id": base.id, "name_zh": base.name_zh, "name_en": base.name_en,
            "category": base.category, "desc": base.desc, "notes": base.notes,
            "score": round(score, 1),
            "fit_breakdown": {"capital": round(cap_fit, 2), "asset": round(asset_fit, 2),
                              "risk": round(risk_fit, 2), "experience": round(exp_fit, 2),
                              "overseas": round(overseas_fit, 2)},
            "friction": round(fric, 3),
            "min_capital": base.min_capital,
            "reasons": reasons,
        })
    results.sort(key=lambda r: -r["score"])
    return results


# ---------------------------------------------------------------------------
# Narrative digest (family-office style)
# ---------------------------------------------------------------------------
_CAT_LABEL = {"onshore": "境内", "crossborder": "跨境通道", "offshore": "离岸"}


def base_digest(ranked: List[Dict], top_n: int = 5) -> str:
    lines = ["【全球资产落位建议 · 家办视角】按「适配度−摩擦」综合打分(0-100)："]
    for i, r in enumerate(ranked[:top_n], 1):
        lines.append(
            f"{i}. {r['name_zh']}({_CAT_LABEL.get(r['category'], r['category'])}) "
            f"评分 {r['score']:.0f} | 摩擦 {r['friction']:.2f} | "
            f"{'; '.join(r['reasons'][:2]) or '综合适配'}")
    lines.append("原则: 优先低摩擦境内通道打底，跨境通道(QDII/港通)拓展，"
                 "离岸(港/新/美)仅用于满足境内无法覆盖的需求，并关注资金合规出境。")
    return "\n".join(lines)
