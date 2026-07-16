"""
EVA Brand-Builder — persistent persona configs (NOT always-running agents).

Personas are stored configs that shape briefs. Three of them, each a
``{focus, hooks[], archetypes[], channels[], tone}`` dict:

  * awareness_persona — top-of-funnel signal + reach (Deal Teardowns, Contrarian)
  * authority_persona — proprietary-data thought leadership (Data/Proof, Frameworks)
  * brand_persona     — founder narrative + trust (Build-in-Public, Founder Lessons)

The defaults below are seeded from the blueprint's own archetypes / awareness
loops when a pipeline is seeded, then persisted as JSON. ``select_persona`` maps a
content archetype to the persona best suited to voice it — this is how the
planner assigns each brief a persona. Stdlib only.
"""

from __future__ import annotations

PERSONA_NAMES = ("awareness_persona", "authority_persona", "brand_persona")

# archetype (lowercased, substring) → persona name
_ARCHETYPE_TO_PERSONA = {
    "deal teardown": "awareness_persona",
    "contrarian": "awareness_persona",
    "data": "authority_persona",
    "proof": "authority_persona",
    "framework": "authority_persona",
    "build-in-public": "brand_persona",
    "build in public": "brand_persona",
    "founder lesson": "brand_persona",
}


def default_personas(blueprint: dict | None = None) -> dict[str, dict]:
    """Build the three persona configs, enriched from a blueprint if given."""
    bp = blueprint or {}
    loops = bp.get("awareness_loops", []) or []
    hooks = [ln.get("hook", "") for ln in loops if ln.get("hook")]

    def hooks_for(keywords: list[str]) -> list[str]:
        picked = [h for h in hooks if any(k in h.lower() for k in keywords)]
        return picked or hooks[:2]

    return {
        "awareness_persona": {
            "name": "awareness_persona",
            "focus": "Top-of-funnel signal + reach; make the market aware of the problem Eva solves.",
            "hooks": hooks_for(["ran", "everyone says", "flagged"]),
            "archetypes": ["Deal Teardowns", "Contrarian Thesis"],
            "channels": ["X (Twitter)", "LinkedIn"],
            "tone": "punchy, specific, data-first, no hype",
        },
        "authority_persona": {
            "name": "authority_persona",
            "focus": "Proprietary-data thought leadership; establish Eva as the referenceable expert.",
            "hooks": hooks_for(["scored", "pattern", "92"]),
            "archetypes": ["Data/Proof Posts", "Frameworks"],
            "channels": ["LinkedIn", "Newsletter", "Podcast (guest appearances)"],
            "tone": "credible, evidence-backed, no unsubstantiated superlatives",
        },
        "brand_persona": {
            "name": "brand_persona",
            "focus": "Founder narrative + trust; the human behind Eva building in public.",
            "hooks": hooks_for(["upgraded", "v5", "v6", "wrong"]),
            "archetypes": ["Build-in-Public", "Founder Lessons"],
            "channels": ["LinkedIn", "X (Twitter)"],
            "tone": "authentic, reflective, human, honest about mistakes",
        },
    }


def select_persona(archetype: str) -> str:
    """Return the persona name best suited to voice a given content archetype."""
    a = (archetype or "").lower()
    for key, persona in _ARCHETYPE_TO_PERSONA.items():
        if key in a:
            return persona
    return "authority_persona"  # safe default: lead with credibility


__all__ = ["PERSONA_NAMES", "default_personas", "select_persona"]
