"""
knowledge_config.py
EVA Knowledge OS — Configuration
"""

import os
from pathlib import Path


class KnowledgeConfig:
    # Root
    MODULE_ROOT: Path = Path(__file__).parent.resolve()

    # Data docs
    DATA_DIR: Path = MODULE_ROOT / "data"
    CULTURE_DOC: Path = DATA_DIR / "culture.md"
    DNA_DOC: Path = DATA_DIR / "dna.md"
    STRATEGY_DOC: Path = DATA_DIR / "strategy.md"
    EXPERIMENTS_DOC: Path = DATA_DIR / "experiments.md"
    DEALS_DOC: Path = DATA_DIR / "deals.md"

    VALID_DOCS: list[str] = ["culture", "strategy", "dna", "experiments", "deals"]

    # Playbooks
    PLAYBOOKS_DIR: Path = MODULE_ROOT / "playbooks"
    PLAYBOOK_EXTENSION: str = ".md"

    # API
    API_PORT: int = 8771
    API_HOST: str = "0.0.0.0"
    ALLOWED_ORIGINS: list[str] = [
        "http://localhost:5173",
        "https://eva.mangotec.ai",
    ]

    # Founder identity
    FOUNDER_NAME: str = "Vineet"
    COMPANY: str = "Mangotec LLC"
    LOCATION: str = "Los Angeles, CA"
    EVA_NORTH_STAR: str = "Your expertise, always on."
    BRAND_POSITIONING: str = (
        "I acquire cash-flowing, value-add healthcare real estate and improve "
        "quality of care through a digital engineering moat."
    )

    # Active sprint
    SPRINT_LABEL: str = "30-Day Sprint"
    SPRINT_GOAL: str = "Acquire health/wellness SaaS — $10K net/month after debt service"
    HELOC_AMOUNT: int = 200_000
    HELOC_RATE: float = 9.5

    # Module version
    VERSION: str = "0.1"
    LAST_UPDATED: str = "2026-05-19"

    @classmethod
    def doc_path(cls, doc_name: str) -> Path:
        """Return the Path for a named doc. Raises ValueError if unknown."""
        mapping = {
            "culture": cls.CULTURE_DOC,
            "dna": cls.DNA_DOC,
            "strategy": cls.STRATEGY_DOC,
            "experiments": cls.EXPERIMENTS_DOC,
            "deals": cls.DEALS_DOC,
        }
        if doc_name not in mapping:
            raise ValueError(f"Unknown doc '{doc_name}'. Valid: {cls.VALID_DOCS}")
        return mapping[doc_name]

    @classmethod
    def as_dict(cls) -> dict:
        """Return config as plain dict for JSON serialisation."""
        return {
            "founder": cls.FOUNDER_NAME,
            "company": cls.COMPANY,
            "location": cls.LOCATION,
            "eva_north_star": cls.EVA_NORTH_STAR,
            "brand_positioning": cls.BRAND_POSITIONING,
            "sprint": {
                "label": cls.SPRINT_LABEL,
                "goal": cls.SPRINT_GOAL,
                "heloc_amount": cls.HELOC_AMOUNT,
                "heloc_rate_pct": cls.HELOC_RATE,
            },
            "version": cls.VERSION,
            "last_updated": cls.LAST_UPDATED,
            "api_port": cls.API_PORT,
            "allowed_origins": cls.ALLOWED_ORIGINS,
            "valid_docs": cls.VALID_DOCS,
        }


config = KnowledgeConfig()
