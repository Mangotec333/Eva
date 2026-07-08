"""
EVA Deal Analyzer Agent — Cost-Gate Cascade orchestrator (simplified)
=====================================================================

The deterministic v7 score is the AUTHORITATIVE, free engine. This module is the
cheap routing/logging layer around it — NOT a multi-brain router. It answers two
questions from ``config/cost_gates.yaml`` (env-overridable):

  route_deal(deal, v7_score)      -> CostTier in {SHORTLIST, LOG_ONLY}
                                     (>= shortlist_threshold => SHORTLIST)
  should_second_opinion(...)      -> bool (true only for SHORTLIST)

SHORTLIST is the "deep-dive" bucket (optional paid enrichment + optional Claude
second-opinion). LOG_ONLY deals are scored + persisted with no paid work and no
brain (tokens=0). Testing mode (EVA_TEST_MODE=1 or testing.open_all_gates) is a
SEPARATE concern read here via ``is_testing_mode()`` — it does not change routing
but tells the loop to give every Gate-1 survivor full treatment for training data.

stdlib + PyYAML (already a dependency). No new pip deps, no network.
"""

from __future__ import annotations

import copy
import enum
import os
from typing import Any, Optional

try:  # PyYAML is present in the runtime; degrade to defaults if ever absent.
    import yaml  # type: ignore
except Exception:  # pragma: no cover - defensive
    yaml = None  # type: ignore

# config/ lives at the repo root; this module runs "flat" from the agent dir.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CONFIG_PATH = os.path.join(_REPO_ROOT, "config", "cost_gates.yaml")

# Single source of truth for defaults, mirroring config/cost_gates.yaml. Used
# when the file is missing/unreadable so the cascade never hard-fails on config.
DEFAULT_CONFIG: dict[str, Any] = {
    "shortlist_threshold": 7.5,
    "price_band": {"min_profit_usd": 1000, "max_multiple": 5.0},
    "allowed_categories": ["SaaS", "Content", "FBA", "DTC", "Ecommerce", "Apps"],
    "enrichment": {"free": ["statista", "bing"], "paid": ["cb_insights", "similarweb"]},
    "second_opinion": {"enabled": False, "provider": "claude"},
    "testing": {"open_all_gates": False},
}


class CostTier(str, enum.Enum):
    """The two routing buckets (NOT three). Deep-dive vs cheap-log."""
    SHORTLIST = "SHORTLIST"   # >= shortlist_threshold: optional paid enrichment + brain
    LOG_ONLY = "LOG_ONLY"     # below threshold: scored + persisted, no paid work, no brain


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge ``override`` onto a copy of ``base`` (dicts only)."""
    out = copy.deepcopy(base)
    for key, val in (override or {}).items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def load_config(path: Optional[str] = None) -> dict:
    """Load cost-gate config: file merged over DEFAULT_CONFIG, then env overrides.

    Missing/unreadable file or absent PyYAML degrades to DEFAULT_CONFIG so the
    cascade always has a complete, valid config. Env overrides applied last:
      EVA_SHORTLIST_THRESHOLD -> shortlist_threshold
      EVA_TEST_MODE=1         -> testing.open_all_gates = True
    """
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    file_path = path or CONFIG_PATH
    if yaml is not None and os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as fh:
                loaded = yaml.safe_load(fh) or {}
            if isinstance(loaded, dict):
                cfg = _deep_merge(cfg, loaded)
        except (OSError, ValueError):
            pass  # keep defaults on any read/parse error — never hard-fail

    thr = os.environ.get("EVA_SHORTLIST_THRESHOLD")
    if thr:
        try:
            cfg["shortlist_threshold"] = float(thr)
        except ValueError:
            pass
    if _env_flag("EVA_TEST_MODE"):
        cfg.setdefault("testing", {})["open_all_gates"] = True
    return cfg


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def shortlist_threshold(config: Optional[dict] = None) -> float:
    cfg = config or load_config()
    try:
        return float(cfg.get("shortlist_threshold", DEFAULT_CONFIG["shortlist_threshold"]))
    except (TypeError, ValueError):
        return float(DEFAULT_CONFIG["shortlist_threshold"])


def route_deal(deal: Any, v7_score: float, config: Optional[dict] = None) -> CostTier:
    """Route a scored deal into SHORTLIST (>= threshold) or LOG_ONLY.

    ``deal`` is accepted for signature symmetry / future use; routing is driven
    by the authoritative v7 score against the configured threshold. Never raises:
    a non-numeric score falls to LOG_ONLY.
    """
    try:
        score = float(v7_score)
    except (TypeError, ValueError):
        return CostTier.LOG_ONLY
    return CostTier.SHORTLIST if score >= shortlist_threshold(config) else CostTier.LOG_ONLY


def should_second_opinion(deal: Any, v7_score: float, config: Optional[dict] = None) -> bool:
    """True only for SHORTLIST deals. Whether the brain ACTUALLY runs also
    requires second_opinion.enabled + a configured key — that gate lives in the
    agent loop; this is purely the tier check."""
    return route_deal(deal, v7_score, config) is CostTier.SHORTLIST


def second_opinion_enabled(config: Optional[dict] = None) -> bool:
    cfg = config or load_config()
    return bool((cfg.get("second_opinion") or {}).get("enabled", False))


def is_testing_mode(config: Optional[dict] = None) -> bool:
    """Testing mode opens all gates: EVA_TEST_MODE=1 OR testing.open_all_gates."""
    if _env_flag("EVA_TEST_MODE"):
        return True
    cfg = config or load_config()
    return bool((cfg.get("testing") or {}).get("open_all_gates", False))
