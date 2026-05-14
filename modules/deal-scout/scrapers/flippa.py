"""
EVA Deal Scout — Flippa public listing fetcher.

Attempts a best-effort extraction of a Flippa listing from the public-facing
HTML page.  Flippa is a JS-heavy SPA; we fall back gracefully when data
is not extractable from the static response.
"""

from __future__ import annotations

import re
from typing import Optional

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

BASE_URL = "https://flippa.com/listing/{listing_id}"


def _parse_price(text: str) -> Optional[float]:
    """Extract the first numeric value from a string like '$123,456'."""
    cleaned = re.sub(r"[^\d.]", "", text.replace(",", ""))
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def fetch_flippa_listing(listing_id: str) -> dict:
    """
    Fetch a Flippa public listing and return a partial deal dict.

    Returns a dict with keys that map to DealCreate fields.
    Fields that cannot be extracted are set to None / sensible defaults.
    'error' key is set on failure.
    """
    url = BASE_URL.format(listing_id=listing_id)
    result: dict = {
        "source": "flippa",
        "listing_id": listing_id,
        "url": url,
        "name": None,
        "category": None,
        "monthly_net": None,
        "annual_multiple": None,
        "asking_price": None,
        "age_years": None,
        "status": "tracking",
        "notes": f"Auto-fetched from Flippa listing {listing_id}",
        "raw_html_available": False,
    }

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            result["error"] = f"HTTP {resp.status_code} from Flippa"
            return result

        result["raw_html_available"] = True
        soup = BeautifulSoup(resp.text, "html.parser")

        # --- title / name ---
        title_tag = soup.find("h1") or soup.find("title")
        if title_tag:
            result["name"] = title_tag.get_text(strip=True)[:200]

        # --- asking price ---
        # Flippa often renders price inside a <meta property="og:description"> or
        # a data attribute.  Try multiple heuristics.
        meta_desc = soup.find("meta", property="og:description")
        if meta_desc and meta_desc.get("content"):
            price_match = re.search(
                r"\$\s*([\d,]+(?:\.\d+)?)", meta_desc["content"]
            )
            if price_match:
                result["asking_price"] = float(price_match.group(1).replace(",", ""))

        # Try structured data (JSON-LD)
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                import json

                ld = json.loads(script.string or "{}")
                if isinstance(ld, dict) and ld.get("offers"):
                    offers = ld["offers"]
                    if isinstance(offers, dict):
                        price = offers.get("price") or offers.get("lowPrice")
                        if price:
                            result["asking_price"] = float(price)
            except Exception:
                pass

        # --- category heuristic from URL or title ---
        text_lower = (result.get("name") or "").lower()
        if any(w in text_lower for w in ["saas", "software", "plugin", "app"]):
            result["category"] = "SaaS"
        elif any(w in text_lower for w in ["content", "blog", "media", "news"]):
            result["category"] = "Content"
        elif any(w in text_lower for w in ["education", "course", "tutor", "learn"]):
            result["category"] = "Education"
        elif any(w in text_lower for w in ["service", "agency", "consulting"]):
            result["category"] = "Services"
        elif any(w in text_lower for w in ["digital", "download", "product", "art"]):
            result["category"] = "Digital Products"
        else:
            result["category"] = "Content"  # safe default

        return result

    except requests.exceptions.Timeout:
        result["error"] = "Request timed out fetching Flippa listing"
        return result
    except requests.exceptions.RequestException as exc:
        result["error"] = f"Network error: {exc}"
        return result
    except Exception as exc:
        result["error"] = f"Unexpected error: {exc}"
        return result
