"""
EVA Deal Scout — source adapter registry.

Each adapter turns a source-specific payload into normalized ``RawDeal`` rows.
Adapters declare a *trust level* (used by the scoring gate) and whether they are
live yet.  Sources that are configured but not implemented live in ``SEEDS`` so
new adapters can be added incrementally without touching the pipeline.

Trust levels (per spec)
-----------------------
    Empire Flippers .................. high    (bypasses the US filter)
    Acquire.com / Flippa / BizBuySell  medium
    everything in SEEDS .............. medium/low (no scrape yet)

Live adapters accept a list of already-fetched listing dicts (the network fetch
itself is delegated to the existing ``scrapers`` package or an external caller),
normalize them, and yield ``RawDeal`` objects.  This keeps the adapters pure and
unit-testable without network access.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from pipeline_models import RawDeal

# Canonical adapter keys the pipeline normalizes every source label down to.
# Real datasets use inconsistent casing/spelling (e.g. "Empire Flippers",
# "empire_flippers", "Acquire.com", "acquire_com") — all collapse to one key.
_SOURCE_ALIASES: dict[str, str] = {
    "empire_flippers": "empire_flippers",
    "empireflippers": "empire_flippers",
    "empire flippers": "empire_flippers",
    "ef": "empire_flippers",
    "acquire_com": "acquire_com",
    "acquire.com": "acquire_com",
    "acquire": "acquire_com",
    "flippa": "flippa",
    "bizbuysell": "bizbuysell",
    "biz buy sell": "bizbuysell",
}


def canonical_source(value: str, default: str = "") -> str:
    """Map any source/marketplace/platform label to a canonical adapter key."""
    key = (value or "").strip().lower()
    if key in _SOURCE_ALIASES:
        return _SOURCE_ALIASES[key]
    norm = key.replace(".", "_").replace(" ", "_")
    return _SOURCE_ALIASES.get(norm, norm or default)


def listing_id_from_url(url: str) -> str:
    """Stable per-listing id = last path segment of the URL (query stripped).

    The real datasets carry inconsistent explicit ids across files (a unified
    ``deal_id`` vs a bare ``listing_id``) but a consistent listing URL, so the
    URL tail is the reliable cross-file dedupe key.
    """
    if not url:
        return ""
    path = url.split("?")[0].split("#")[0].rstrip("/")
    if "/" not in path:
        return path
    return path.rsplit("/", 1)[-1]

# ---------------------------------------------------------------------------
# Category normalization shared by all adapters
# ---------------------------------------------------------------------------

def normalize_category(raw: str) -> str:
    lc = (raw or "").lower()
    if any(w in lc for w in ("saas", "software", "plugin", "app", "micro-saas")):
        return "SaaS"
    if any(w in lc for w in ("content", "blog", "media", "news", "affiliate")):
        return "Content"
    if any(w in lc for w in ("education", "course", "tutor", "elearning", "learn")):
        return "Education"
    if any(w in lc for w in ("service", "agency", "consulting")):
        return "Services"
    if any(w in lc for w in ("ecommerce", "e-commerce", "store", "shopify", "amazon", "fba")):
        return "E-commerce"
    if any(w in lc for w in ("digital", "download", "product", "art")):
        return "Digital Products"
    return "Content"


def _f(payload: dict, *keys: str, default: float = 0.0) -> float:
    for k in keys:
        v = payload.get(k)
        if v is None:
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return default


def _s(payload: dict, *keys: str, default: str = "") -> str:
    for k in keys:
        v = payload.get(k)
        if v not in (None, ""):
            return str(v)
    return default


def _country(payload: dict, *keys: str) -> str:
    """Normalize country/market values to a short code where obvious."""
    val = _s(payload, *keys).strip()
    lc = val.lower()
    if lc in ("us", "usa", "united states", "united states of america"):
        return "US"
    if lc in ("uk", "gb", "united kingdom", "great britain"):
        return "GB"
    return val.upper()[:2] if len(val) <= 3 and val else val


# ---------------------------------------------------------------------------
# Adapter definition
# ---------------------------------------------------------------------------

@dataclass
class SourceAdapter:
    key: str
    label: str
    trust_level: str                 # "high" | "medium" | "low"
    live: bool                       # implemented vs seed-only
    normalize: Callable[[dict], RawDeal] | None = None
    ef_multiple_monthly: bool = False  # EF quotes monthly multiples → ÷12
    feed_url: str = ""               # public listing/feed page for a wide run
    access: str = "public"           # "public" | "gated" (needs auth/browser)
    # Where financials come from. "self_reported" is the safe default for a
    # marketplace that hosts unverified seller listings (e.g. Acquire.com —
    # only identity/incorporation gets a "Verified business" badge, numbers
    # are not audited). Only bump to "verified" for sources that independently
    # audit financials (Empire Flippers reviews bank statements).
    financial_verification: str = "self_reported"

    def to_raw_deals(self, payloads: Iterable[dict]) -> list[RawDeal]:
        if not self.live or self.normalize is None:
            raise NotImplementedError(f"adapter {self.key!r} is seed-only (no scrape yet)")
        out = []
        for p in payloads:
            deal = self.normalize(p)
            deal.source = self.key
            deal.trust_level = self.trust_level
            deal.financial_verification = self.financial_verification
            out.append(deal)
        return out


# ---------------------------------------------------------------------------
# Concrete normalizers
# ---------------------------------------------------------------------------

def _base_raw(payload: dict, *, ef_monthly: bool = False) -> RawDeal:
    multiple = _f(payload, "annual_multiple", "multiple", "raw_monthly_multiple")
    if ef_monthly and multiple:
        multiple = round(multiple / 12.0, 2)
    status = _s(payload, "status", "market_status").lower()
    is_closed = bool(payload.get("is_closed") or payload.get("sold") or
                     status in ("sold", "closed"))
    market_status = _s(payload, "market_status", default=("sold" if is_closed else "available"))
    url = _s(payload, "url", "listing_url", "source_url")
    # URL tail is the stable cross-file dedupe id; fall back to explicit ids.
    listing_id = listing_id_from_url(url) or _s(payload, "listing_id", "deal_id", "id")
    return RawDeal(
        id="",
        source="",
        listing_id=listing_id,
        url=url,
        name=_s(payload, "name", "title", "listing_name", default="Unnamed listing")[:200],
        category=normalize_category(_s(payload, "category", "niche", "type",
                                       "type_of_business", "business_type_niche")),
        monthly_net=_f(payload, "monthly_net", "monthly_net_usd", "net_profit",
                       "monthly_profit", "monthly_net_profit_usd", "monthly_profit_usd"),
        annual_multiple=multiple,
        asking_price=_f(payload, "asking_price", "asking_price_usd", "price",
                        "list_price", "sale_price_usd"),
        age_years=_f(payload, "age_years", "age"),
        currency=_s(payload, "currency", default="USD"),
        registration_country=_country(payload, "registration_country", "country"),
        primary_customer_market=_country(payload, "primary_customer_market", "customer_market", "market"),
        seller_location=_country(payload, "seller_location", "seller_country"),
        is_closed=is_closed,
        market_status=market_status,
        sold_price=_f(payload, "sold_price", "sale_price", "sale_price_usd"),
        sold_at=_s(payload, "sold_at", "closed_at", "sale_date", "deal_date"),
        owner_hours_per_week=_f(payload, "owner_hours_per_week", "owner_hours"),
        incoming_score=_f(payload, "incoming_score", "overall_score", "score"),
        notes=_s(payload, "notes", "score_note"),
        raw_json=json.dumps(payload, default=str),
    )


def _norm_ef(p: dict) -> RawDeal:
    return _base_raw(p, ef_monthly=True)


def _norm_generic(p: dict) -> RawDeal:
    return _base_raw(p)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ADAPTERS: dict[str, SourceAdapter] = {
    "empire_flippers": SourceAdapter(
        key="empire_flippers", label="Empire Flippers", trust_level="high",
        live=True, normalize=_norm_ef, ef_multiple_monthly=True,
        feed_url="https://empireflippers.com/marketplace/", access="public",
        financial_verification="verified",
    ),
    "acquire_com": SourceAdapter(
        key="acquire_com", label="Acquire.com", trust_level="medium",
        live=True, normalize=_norm_generic,
        feed_url="https://acquire.com/all-startups/", access="gated",
        financial_verification="self_reported",
    ),
    "flippa": SourceAdapter(
        key="flippa", label="Flippa", trust_level="medium",
        live=True, normalize=_norm_generic,
        feed_url="https://flippa.com/buy/monetization/", access="public",
    ),
    "bizbuysell": SourceAdapter(
        key="bizbuysell", label="BizBuySell", trust_level="medium",
        live=True, normalize=_norm_generic,
        feed_url="https://www.bizbuysell.com/online-and-technology-businesses-for-sale/",
        access="public",
    ),
    # ---- newly activated (previously SEED-only) sources ----
    "quietlight": SourceAdapter(
        key="quietlight", label="QuietLight", trust_level="medium",
        live=True, normalize=_norm_generic,
        feed_url="https://quietlight.com/listings/", access="public",
    ),
    "fe_international": SourceAdapter(
        key="fe_international", label="FE International", trust_level="medium",
        live=True, normalize=_norm_generic,
        feed_url="https://feinternational.com/buy-a-website/", access="public",
    ),
    "websiteclosers": SourceAdapter(
        key="websiteclosers", label="WebsiteClosers", trust_level="medium",
        live=True, normalize=_norm_generic,
        feed_url="https://www.websiteclosers.com/businesses-for-sale/", access="public",
    ),
    "investors_club": SourceAdapter(
        key="investors_club", label="Investors Club", trust_level="medium",
        live=True, normalize=_norm_generic,
        feed_url="https://investors.club/deal-flow/", access="gated",
    ),
    "motion_invest": SourceAdapter(
        key="motion_invest", label="Motion Invest", trust_level="medium",
        live=True, normalize=_norm_generic,
        feed_url="https://www.motioninvest.com/listings/", access="public",
    ),
    "dealslide": SourceAdapter(
        key="dealslide", label="Dealslide", trust_level="low",
        live=True, normalize=_norm_generic,
        feed_url="https://dealslide.com/listings/", access="public",
    ),
    "businessesforsale": SourceAdapter(
        key="businessesforsale", label="BusinessesForSale", trust_level="low",
        live=True, normalize=_norm_generic,
        feed_url="https://www.businessesforsale.com/us/search/internet-businesses-for-sale",
        access="public",
    ),
}

# The 7 sources activated out of the former SEED tier in this release.  Kept as
# an explicit set so a wide source run and the docs can target exactly them.
ACTIVATED_SOURCES: tuple[str, ...] = (
    "quietlight", "fe_international", "websiteclosers", "investors_club",
    "motion_invest", "dealslide", "businessesforsale",
)

# No sources remain seed-only — every configured source now has a live adapter.
SEEDS: dict[str, dict[str, str]] = {}


def get_adapter(key: str) -> SourceAdapter:
    if key in ADAPTERS:
        return ADAPTERS[key]
    if key in SEEDS:
        seed = SEEDS[key]
        return SourceAdapter(key=key, label=seed["label"], trust_level=seed["trust_level"], live=False)
    raise KeyError(f"unknown source {key!r}")


def financial_verification_for(source: str) -> str:
    """Financial-verification tier for any known source; default 'self_reported'
    (safe assumption — most marketplaces don't audit seller-provided numbers)."""
    if source in ADAPTERS:
        return ADAPTERS[source].financial_verification
    return "self_reported"


def trust_level_for(source: str) -> str:
    """Trust level for any known source (adapter or seed); default 'low'."""
    if source in ADAPTERS:
        return ADAPTERS[source].trust_level
    if source in SEEDS:
        return SEEDS[source]["trust_level"]
    return "low"


def list_sources() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for k, a in ADAPTERS.items():
        out[k] = {"label": a.label, "trust_level": a.trust_level, "live": True,
                  "feed_url": a.feed_url, "access": a.access}
    for k, s in SEEDS.items():
        out[k] = {"label": s["label"], "trust_level": s["trust_level"], "live": False}
    return out
