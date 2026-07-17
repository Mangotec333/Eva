"""
EVA Shopify — configuration loader (config-driven, no hardcoded store).

The store domain, Admin API token, API version, and fulfillment target are read
from (in priority order):

  1. environment variables (EVA_SHOPIFY_*), then
  2. ~/.eva/channels_config.json ``shopify`` block (the file the existing
     oauth_handler.py / shopify_auth.py already write the token into), then
  3. safe empty defaults.

Nothing about a real store is hardcoded — if the user has not supplied a store
domain + token, the service still runs (offline stub mode) and the live-write
paths report ``not_connected`` rather than guessing.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Optional

CONFIG_PATH = os.path.expanduser(
    os.environ.get("EVA_CHANNELS_CONFIG", "~/.eva/channels_config.json")
)

DEFAULT_API_VERSION = "2024-07"


def _load_config_file() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh).get("shopify", {}) or {}
    except (OSError, json.JSONDecodeError):
        return {}


@dataclass
class ShopifyConfig:
    """Resolved Shopify configuration. All fields optional so the module is
    fully constructable (and testable) without live credentials."""

    store_domain: str = ""
    access_token: str = ""
    api_version: str = DEFAULT_API_VERSION
    # Fulfillment / supplier notify target — config-driven, never hardcoded.
    fulfillment_mode: str = "stub"          # stub | webhook | email
    fulfillment_webhook_url: str = ""
    fulfillment_email: str = ""
    product_skus: list[str] = field(default_factory=list)

    @property
    def is_live_ready(self) -> bool:
        """True only when a real store domain + Admin API token are present."""
        return bool(self.store_domain) and self.access_token.startswith("shpat_")

    def missing_for_live(self) -> list[str]:
        missing = []
        if not self.store_domain:
            missing.append("store_domain (EVA_SHOPIFY_STORE_DOMAIN)")
        if not self.access_token.startswith("shpat_"):
            missing.append("access_token (EVA_SHOPIFY_TOKEN, an shpat_ token)")
        return missing


def load_config() -> ShopifyConfig:
    """Resolve config from env first, then ~/.eva/channels_config.json."""
    file_cfg = _load_config_file()

    def pick(env_key: str, file_key: str, default: str = "") -> str:
        return os.environ.get(env_key) or file_cfg.get(file_key, default) or default

    skus_raw = os.environ.get("EVA_SHOPIFY_PRODUCT_SKUS", "")
    skus = [s.strip() for s in skus_raw.split(",") if s.strip()]
    if not skus and isinstance(file_cfg.get("product_skus"), list):
        skus = list(file_cfg["product_skus"])

    return ShopifyConfig(
        store_domain=pick("EVA_SHOPIFY_STORE_DOMAIN", "store_url")
        or pick("EVA_SHOPIFY_STORE_DOMAIN", "shop"),
        access_token=pick("EVA_SHOPIFY_TOKEN", "access_token")
        or file_cfg.get("admin_api_token", ""),
        api_version=pick("EVA_SHOPIFY_API_VERSION", "api_version", DEFAULT_API_VERSION),
        fulfillment_mode=pick("EVA_SHOPIFY_FULFILLMENT_MODE", "fulfillment_mode", "stub"),
        fulfillment_webhook_url=pick(
            "EVA_SHOPIFY_FULFILLMENT_WEBHOOK", "fulfillment_webhook_url"
        ),
        fulfillment_email=pick("EVA_SHOPIFY_FULFILLMENT_EMAIL", "fulfillment_email"),
        product_skus=skus,
    )
