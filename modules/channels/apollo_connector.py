"""
EVA Channels — Apollo People-search connector (cold-outreach sourcing)
======================================================================

Sources US-based decision-makers at acquisition-adjacent firms (Private Equity,
M&A advisory, Investment Banking, Search Funds) from Apollo's People Search API
and normalises them into the shape Eva's GHL pipeline needs.

Design notes
------------
* **stdlib only.** Uses ``urllib`` for every network call so it runs inside the
  launcher's minimal env (no ``requests``/``httpx`` required), matching the
  approach in ``ghl_client`` and ``slack_client``.
* **Auth.** Bearer token from ``APOLLO_API_KEY``. Apollo historically also
  accepts an ``X-Api-Key`` header, so both are sent — the token is never
  hardcoded.
* **Fails safe.** Every network path is wrapped: on error the functions return
  ``{"ok": False, "error": ...}`` (search) or ``[]`` (extract) rather than
  raising, so a bad key or a flaky network never crashes the caller.
* **No live reveals here by design.** Extraction reads whatever Apollo returns;
  it does NOT call any credit-consuming "reveal" endpoint. Offline tests inject
  mock JSON via the ``_search_fn`` seam.

Apollo credits: email addresses are only revealed (and credits consumed) when a
reveal is explicitly requested in the Apollo UI/API. See ``README_apollo.md``.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable, Optional

APOLLO_API_BASE = "https://api.apollo.io"
PEOPLE_SEARCH_PATH = "/api/v1/mixed_people/search"

# The acquisition-buyer ICP: who Eva wants in the 7-touch sequence.
DEFAULT_TITLES = [
    "Partner",
    "Managing Director",
    "Principal",
    "Associate",
    "VP",
    "Vice President",
    "Director",
    "Deal Origination",
]

# Firm types — matched as keyword tags against the person's organization.
DEFAULT_FIRM_KEYWORDS = [
    "Private Equity",
    "M&A advisory",
    "Mergers and Acquisitions",
    "Investment Banking",
    "Search Fund",
]

DEFAULT_LOCATIONS = ["United States"]

# Apollo hard-caps a page at 100; the first batch is capped here too.
MAX_PER_PAGE = 100
DEFAULT_BATCH_CAP = 100


class ApolloNotConfigured(Exception):
    """Raised when APOLLO_API_KEY is absent — callers should fail safe."""


def get_api_key() -> str:
    return os.environ.get("APOLLO_API_KEY", "").strip()


def is_configured() -> bool:
    return bool(get_api_key())


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "X-Api-Key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Cache-Control": "no-cache",
    }


def _build_payload(*, titles: list[str], firm_keywords: list[str],
                   locations: list[str], page: int, per_page: int,
                   extra_keywords: str = "") -> dict[str, Any]:
    """Assemble the Apollo People-search request body."""
    per_page = max(1, min(per_page, MAX_PER_PAGE))
    keyword_bits = list(firm_keywords)
    if extra_keywords:
        keyword_bits.append(extra_keywords)
    return {
        "page": page,
        "per_page": per_page,
        "person_titles": titles,
        "person_locations": locations,
        # Firm type is expressed as organization keyword tags; the free-text
        # q_keywords widens the net for phrasing Apollo tags differently.
        "q_organization_keyword_tags": firm_keywords,
        "q_keywords": " ".join(keyword_bits).strip(),
        "contact_email_status": ["verified", "likely to engage"],
    }


def _post_json(url: str, payload: dict, headers: dict, timeout: float) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def search_people(query: str = "", *, page: int = 1,
                  per_page: int = MAX_PER_PAGE,
                  titles: Optional[list[str]] = None,
                  firm_keywords: Optional[list[str]] = None,
                  locations: Optional[list[str]] = None,
                  timeout: float = 30.0) -> dict:
    """Run one page of Apollo People search.

    Returns ``{"ok": True, "people": [...], "pagination": {...}}`` on success,
    or ``{"ok": False, "error": ...}`` on any failure (missing key, network,
    non-2xx, bad JSON). Never raises.
    """
    api_key = get_api_key()
    if not api_key:
        return {"ok": False, "error": "APOLLO_API_KEY not set"}

    payload = _build_payload(
        titles=titles or DEFAULT_TITLES,
        firm_keywords=firm_keywords or DEFAULT_FIRM_KEYWORDS,
        locations=locations or DEFAULT_LOCATIONS,
        page=page,
        per_page=per_page,
        extra_keywords=query or "",
    )
    url = f"{APOLLO_API_BASE}{PEOPLE_SEARCH_PATH}"
    try:
        body = _post_json(url, payload, _headers(api_key), timeout)
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8")[:300]
        except Exception:
            pass
        return {"ok": False, "error": f"apollo http {exc.code}: {detail}"}
    except urllib.error.URLError as exc:
        return {"ok": False, "error": f"apollo network error: {exc.reason}"}
    except (ValueError, TimeoutError) as exc:
        return {"ok": False, "error": f"apollo response error: {exc}"}
    except Exception as exc:  # never let sourcing crash the pipeline
        return {"ok": False, "error": f"apollo unexpected error: {exc}"}

    people = body.get("people") or body.get("contacts") or []
    pagination = body.get("pagination") or {}
    return {"ok": True, "people": people, "pagination": pagination,
            "query": query}


def normalize_person(raw: dict) -> dict:
    """Map an Apollo person record to Eva's contact shape."""
    org = raw.get("organization") or {}
    name = (raw.get("name")
            or " ".join(p for p in [raw.get("first_name"), raw.get("last_name")] if p)
            or "").strip()
    phones = raw.get("phone_numbers") or []
    phone = ""
    if phones:
        first = phones[0]
        phone = first.get("sanitized_number") or first.get("raw_number") or ""
    return {
        "name": name,
        "email": (raw.get("email") or "").strip(),
        "title": (raw.get("title") or "").strip(),
        "company": (org.get("name") or raw.get("organization_name") or "").strip(),
        "linkedin_url": (raw.get("linkedin_url") or "").strip(),
        "phone": phone.strip() if isinstance(phone, str) else "",
    }


def _has_email(contact: dict) -> bool:
    email = contact.get("email", "")
    # Apollo returns a "locked" placeholder for un-revealed emails; treat those
    # as no-email so we never try to enrol a fake address.
    return bool(email) and "email_not_unlocked" not in email.lower()


def extract_contacts(query: str = "", *, max_contacts: int = DEFAULT_BATCH_CAP,
                     titles: Optional[list[str]] = None,
                     firm_keywords: Optional[list[str]] = None,
                     locations: Optional[list[str]] = None,
                     require_email: bool = True,
                     timeout: float = 30.0,
                     _search_fn: Optional[Callable[..., dict]] = None) -> dict:
    """Paginate Apollo search and return up to ``max_contacts`` normalised rows.

    ``_search_fn`` is an injection seam for offline tests (defaults to the live
    :func:`search_people`). The first batch is capped at ``max_contacts`` (<=100
    by default). Returns
    ``{"ok", "contacts": [...], "raw_count", "pages", "error"?}``.
    """
    search = _search_fn or search_people
    cap = max(1, min(max_contacts, DEFAULT_BATCH_CAP))

    contacts: list[dict] = []
    seen: set[str] = set()
    raw_count = 0
    pages = 0
    page = 1

    while len(contacts) < cap:
        remaining = cap - len(contacts)
        per_page = min(MAX_PER_PAGE, max(remaining, 1))
        result = search(query, page=page, per_page=per_page, titles=titles,
                        firm_keywords=firm_keywords, locations=locations,
                        timeout=timeout)
        if not result.get("ok"):
            if contacts:
                break  # keep what we already have; report partial success
            return {"ok": False, "error": result.get("error", "search failed"),
                    "contacts": [], "raw_count": 0, "pages": pages}

        people = result.get("people") or []
        pages += 1
        raw_count += len(people)
        if not people:
            break

        for raw in people:
            contact = normalize_person(raw)
            if require_email and not _has_email(contact):
                continue
            key = contact["email"].lower() or contact["linkedin_url"].lower()
            if not key or key in seen:
                continue
            seen.add(key)
            contacts.append(contact)
            if len(contacts) >= cap:
                break

        pagination = result.get("pagination") or {}
        total_pages = pagination.get("total_pages")
        if total_pages is not None and page >= total_pages:
            break
        page += 1

    return {"ok": True, "contacts": contacts, "raw_count": raw_count,
            "pages": pages, "query": query}


def creds_status() -> dict:
    """Non-secret credential report for the /apollo/creds route."""
    return {
        "configured": is_configured(),
        "env_var": "APOLLO_API_KEY",
        "base_url": APOLLO_API_BASE,
        "note": "Bearer token; email reveals consume Apollo credits.",
    }


__all__ = [
    "APOLLO_API_BASE",
    "DEFAULT_TITLES",
    "DEFAULT_FIRM_KEYWORDS",
    "DEFAULT_LOCATIONS",
    "DEFAULT_BATCH_CAP",
    "ApolloNotConfigured",
    "get_api_key",
    "is_configured",
    "search_people",
    "normalize_person",
    "extract_contacts",
    "creds_status",
]
