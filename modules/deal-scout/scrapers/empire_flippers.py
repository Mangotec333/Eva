"""
EVA Deal Scout — Empire Flippers public listing fetcher.

Empire Flippers renders listing data in structured HTML / JSON-LD.
We extract what we can from the public page and normalise the multiple to
annual (EF quotes monthly multiples — divide by 12 to get annual).
"""

from __future__ import annotations

import json
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

BASE_URL = "https://empireflippers.com/listing/{listing_id}"


def _extract_number(text: str) -> Optional[float]:
    """Strip currency / commas and return the first float."""
    cleaned = re.sub(r"[^\d.]", "", text.replace(",", ""))
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _ef_category_to_internal(ef_category: str) -> str:
    """Map EF category names to EVA internal categories."""
    lc = ef_category.lower()
    if "saas" in lc or "software" in lc:
        return "SaaS"
    if "content" in lc or "blog" in lc or "media" in lc:
        return "Content"
    if "education" in lc or "course" in lc or "elearning" in lc:
        return "Education"
    if "service" in lc or "agency" in lc:
        return "Services"
    if "digital" in lc or "product" in lc or "download" in lc or "ecommerce" in lc:
        return "Digital Products"
    return "Content"


def fetch_ef_listing(listing_id: str) -> dict:
    """
    Fetch an Empire Flippers public listing and return a partial deal dict.

    EF quotes multiples as monthly — we convert to annual (÷ 12).
    Returns a dict with DealCreate-compatible keys.
    'error' key is set on failure.
    """
    url = BASE_URL.format(listing_id=listing_id)
    result: dict = {
        "source": "empire_flippers",
        "listing_id": listing_id,
        "url": url,
        "name": None,
        "category": None,
        "monthly_net": None,
        "annual_multiple": None,   # will be EF multiple / 12 after extraction
        "asking_price": None,
        "age_years": None,
        "status": "tracking",
        "notes": f"Auto-fetched from Empire Flippers listing {listing_id}",
        "raw_html_available": False,
    }

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            result["error"] = f"HTTP {resp.status_code} from Empire Flippers"
            return result

        result["raw_html_available"] = True
        soup = BeautifulSoup(resp.text, "html.parser")

        # --- title / name ---
        title_tag = soup.find("h1") or soup.find("title")
        if title_tag:
            result["name"] = title_tag.get_text(strip=True)[:200]

        # --- JSON-LD structured data (best source) ---
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                ld = json.loads(script.string or "{}")
                if isinstance(ld, dict):
                    # Asking price
                    if ld.get("offers"):
                        offers = ld["offers"]
                        if isinstance(offers, dict):
                            price = offers.get("price") or offers.get("lowPrice")
                            if price:
                                result["asking_price"] = float(price)
                    # Category
                    if ld.get("category"):
                        result["category"] = _ef_category_to_internal(ld["category"])
                    if ld.get("name") and not result["name"]:
                        result["name"] = ld["name"][:200]
            except Exception:
                pass

        # --- Meta og:description heuristic ---
        meta_desc = soup.find("meta", property="og:description")
        if meta_desc and meta_desc.get("content"):
            content = meta_desc["content"]
            # Try to extract price
            if result["asking_price"] is None:
                price_match = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", content)
                if price_match:
                    result["asking_price"] = float(
                        price_match.group(1).replace(",", "")
                    )
            # Try to extract monthly net profit
            net_match = re.search(
                r"(?:net\s+profit|monthly\s+net)[^\$]*\$\s*([\d,]+(?:\.\d+)?)",
                content,
                re.IGNORECASE,
            )
            if net_match:
                result["monthly_net"] = float(net_match.group(1).replace(",", ""))

            # Try to extract multiple (EF quotes monthly — divide by 12)
            mult_match = re.search(r"([\d.]+)\s*x\s+multiple", content, re.IGNORECASE)
            if mult_match:
                raw_multiple = float(mult_match.group(1))
                result["annual_multiple"] = round(raw_multiple / 12.0, 2)

        # --- Category heuristic fallback ---
        if result["category"] is None:
            text_lower = (result.get("name") or "").lower()
            if any(w in text_lower for w in ["saas", "software", "plugin", "app"]):
                result["category"] = "SaaS"
            elif any(w in text_lower for w in ["content", "blog", "media"]):
                result["category"] = "Content"
            elif any(w in text_lower for w in ["education", "course", "tutor"]):
                result["category"] = "Education"
            elif any(w in text_lower for w in ["service", "agency"]):
                result["category"] = "Services"
            else:
                result["category"] = "Content"

        return result

    except requests.exceptions.Timeout:
        result["error"] = "Request timed out fetching Empire Flippers listing"
        return result
    except requests.exceptions.RequestException as exc:
        result["error"] = f"Network error: {exc}"
        return result
    except Exception as exc:
        result["error"] = f"Unexpected error: {exc}"
        return result
