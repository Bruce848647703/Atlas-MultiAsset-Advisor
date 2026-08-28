"""Configuration loading.

Central place to load the YAML configs under ``config/``. Loaded once and
cached; call :func:`load_config` with ``force=True`` to reload.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Dict

import yaml

_CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")
_CACHE: Dict[str, Any] = {}


def _load(name: str) -> Dict[str, Any]:
    path = os.path.join(_CONFIG_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_config(force: bool = False) -> Dict[str, Any]:
    """Return the merged configuration dictionary."""
    global _CACHE
    if _CACHE and not force:
        return _CACHE
    cfg: Dict[str, Any] = {}
    cfg.update(_load("agent.yaml"))
    cfg["assets"] = _load("assets.yaml")
    cfg["risk"] = _load("risk_profiles.yaml")
    _CACHE = cfg
    return cfg


def get_config() -> Dict[str, Any]:
    return load_config()


def asset_universe() -> list:
    return load_config()["assets"]["assets"]


def class_priors() -> Dict[str, Dict[str, float]]:
    return load_config()["assets"]["class_priors"]


def risk_tiers() -> Dict[str, Any]:
    return load_config()["risk"]["risk_tiers"]


def client_segments() -> Dict[str, Any]:
    return load_config()["risk"]["client_segments"]
