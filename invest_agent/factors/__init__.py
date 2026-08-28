"""Factor library integration.

Two layers:
  * loader: parses the JSON factor knowledge base (extracted from research
    documents) into a deduplicated, category-indexed catalog with direction
    priors mined from the factor rationale text.
  * lens:   maps factor families to proxies computable on our monthly
    asset-level data (momentum/reversal/low-vol/liquidity), producing a
    screening score per asset.
"""

from .loader import FactorCatalog, load_catalog, default_catalog  # noqa: F401
from .lens import compute_factor_scores, screen_universe  # noqa: F401
from .enrich import enrich_universe  # noqa: F401
