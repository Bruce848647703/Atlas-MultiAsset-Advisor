"""invest_agent - a multi-asset investment advisory agent built on the
DeepSeek tool-calling harness.

Design principle: the quantitative core (risk profiling, optimization,
backtesting, reporting) is deterministic and unit-testable; the LLM acts
as the conversational interface that invokes those capabilities as tools.
"""

__version__ = "0.1.0"

from .config import load_config, get_config  # noqa: F401
