"""
EVA Networking-Agent — venture directive ingestion.

Community Scout runs across three ventures, and each needs its own ICP, offer,
and brand voice so discovery/scoring/drafting stay on-message. Rather than
re-briefing the agent by hand, ``directives.py`` pulls each venture's directive
the same way Brand Builder pulls a blueprint: a venture blueprint markdown is the
source of truth when present, and a built-in default is used otherwise so the
module is fully usable offline.

Resolution order for a venture's blueprint md (first hit wins):
  1. ``EVA_NETWORKING_DIRECTIVES_DIR/<venture>.md``
  2. ``modules/networking-agent/seed/directive_<venture>.md``
  3. ``modules/brand-builder/seed/brand_blueprint_<venture>.md`` (shared source)
  4. built-in ``DEFAULT_DIRECTIVES[venture]``

A parsed blueprint contributes its ICP segments, offer/CTA and do-not-say voice
rules; anything the markdown doesn't spell out falls back to the built-in
default. Stdlib only (no network), mirroring brand-builder/blueprint.py parsing.
"""

from __future__ import annotations

import os
from pathlib import Path

VENTURES = ["eva_growth_agency", "storeys", "shopify"]

# Built-in directives — the honest default when no richer blueprint md is found.
DEFAULT_DIRECTIVES: dict[str, dict] = {
    "eva_growth_agency": {
        "venture": "eva_growth_agency",
        "display_name": "Eva Growth Agency",
        "icp": [
            "online-business acquirers (buyers)",
            "M&A brokers / marketplaces",
            "online-business sellers",
            "LPs / passive capital partners",
            "ETA / search-fund community",
        ],
        "offer": (
            "AI deal-sourcing + 11-parameter scoring that surfaces the few "
            "online businesses actually worth acquiring."
        ),
        "cta": (
            "Send a listing you're evaluating — get a free Eva deal audit, "
            "no strings."
        ),
        "brand_voice": [
            "Lead with proprietary data and specific observations.",
            "No guaranteed-returns or financial-advice language.",
            "Every performance claim must be substantiatable on demand.",
        ],
        "do_not_say": ["Guaranteed returns", "risk-free", "get rich"],
        "keywords": [
            "acquisition", "ETA", "search fund", "buy a business",
            "SaaS acquisition", "SDE", "seller financing", "due diligence",
        ],
    },
    "storeys": {
        "venture": "storeys",
        "display_name": "Storeys",
        "icp": [
            "RCFE / senior-living operators",
            "senior-housing real-estate investors",
            "assisted-living facility owners",
            "healthcare real-estate LPs",
        ],
        "offer": (
            "Sourcing + underwriting for RCFE / senior-living real estate — "
            "find, score, and structure senior-housing deals."
        ),
        "cta": (
            "Share an RCFE or senior-living deal you're weighing — get a free "
            "underwriting read."
        ),
        "brand_voice": [
            "Operator-to-operator, licensing-aware tone.",
            "Respect resident-care and regulatory sensitivity.",
            "No medical or care-quality claims.",
        ],
        "do_not_say": ["guaranteed occupancy", "risk-free", "care guarantees"],
        "keywords": [
            "RCFE", "assisted living", "senior living", "board and care",
            "senior housing", "memory care", "residential care facility",
        ],
    },
    "shopify": {
        "venture": "shopify",
        "display_name": "Shopify / E-commerce",
        "icp": [
            "Shopify store operators",
            "dropshipping operators",
            "DTC / e-commerce founders",
            "product-sourcing & 3PL operators",
        ],
        "offer": (
            "Store-growth + acquisition playbooks for Shopify and e-commerce "
            "operators — build, buy, or scale the storefront."
        ),
        "cta": (
            "Tell me your store's biggest bottleneck — get a free growth teardown."
        ),
        "brand_voice": [
            "Practical, metrics-first (CAC, AOV, contribution margin).",
            "No hype or overnight-success framing.",
            "Concrete tactics over motivational fluff.",
        ],
        "do_not_say": ["passive income", "overnight success", "guaranteed sales"],
        "keywords": [
            "shopify", "dropshipping", "ecommerce", "DTC", "print on demand",
            "product research", "conversion rate", "abandoned cart",
        ],
    },
}


def _blueprint_candidates(venture: str) -> list[Path]:
    here = Path(__file__).parent
    repo_modules = here.parent
    out: list[Path] = []
    env_dir = os.environ.get("EVA_NETWORKING_DIRECTIVES_DIR", "").strip()
    if env_dir:
        out.append(Path(env_dir) / f"{venture}.md")
    out.append(here / "seed" / f"directive_{venture}.md")
    out.append(repo_modules / "brand-builder" / "seed"
               / f"brand_blueprint_{venture}.md")
    return out


def _parse_blueprint_md(path: Path) -> dict:
    """Best-effort pull of ICP / offer / voice from a brand blueprint md.

    Reuses brand-builder's parser when importable; falls back to an empty
    overlay so a missing/odd file never breaks directive resolution.
    """
    try:
        import sys
        bb = Path(__file__).parent.parent / "brand-builder"
        if str(bb) not in sys.path:
            sys.path.insert(0, str(bb))
        import blueprint as bp_mod  # type: ignore
    except Exception:
        return {}
    try:
        bp = bp_mod.parse_blueprint(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    overlay: dict = {}
    segments = [s.get("segment", "") for s in bp.get("audience", {}).get("segments", [])]
    segments = [s for s in segments if s]
    if segments:
        overlay["icp"] = segments
    ladder = bp.get("cta_ladder", [])
    if ladder:
        overlay["offer"] = ladder[-1].get("cta", "") or overlay.get("offer", "")
        overlay["cta"] = ladder[0].get("cta", "") or overlay.get("cta", "")
    if bp.get("do_not_say"):
        overlay["do_not_say"] = bp["do_not_say"]
    return {k: v for k, v in overlay.items() if v}


def get_directive(venture: str) -> dict:
    """Return the resolved directive for a venture (blueprint md over default)."""
    key = (venture or "").strip().lower()
    base = DEFAULT_DIRECTIVES.get(key)
    if base is None:
        return {"venture": key, "error": f"unknown venture: {venture!r}",
                "known": VENTURES}
    directive = {**base, "source": "default"}
    for cand in _blueprint_candidates(key):
        if cand.exists():
            overlay = _parse_blueprint_md(cand)
            if overlay:
                directive.update(overlay)
                directive["source"] = str(cand)
            break
    return directive


def list_directives() -> list[dict]:
    return [get_directive(v) for v in VENTURES]


__all__ = ["VENTURES", "DEFAULT_DIRECTIVES", "get_directive", "list_directives"]
