#!/usr/bin/env python3
"""
EVA LinkedIn Analytics — LinkedIn read chokepoint.

This is the *single* place where a real network call to LinkedIn is made. Every
other part of the module treats reading analytics as an interface; only this
script knows about LinkedIn. Keeping the transport isolated here means wiring
live analytics on the Eva host is one function: ``_fetch_via_linkedin_api``.

Contract (spec section 7), identical in spirit to postcards' ``linkedin_post.py``:

  stdin  JSON: {"author_urn": "urn:li:organization:123",
                "access_token_env": "LINKEDIN_ACCESS_TOKEN",
                "window_days": 28}
  stdout JSON: {"ok": true|false, "provider": "linkedin",
                "posts": [{"post_urn","share_urn","posted_at","text","post_url",
                           "impressions","unique_impressions","clicks",
                           "reactions","comments","shares","engagement_rate",
                           "raw"}],
                "error": "..."}

Until wired, ``_fetch_via_linkedin_api`` returns ``ok=False`` with a clear error
so the module never silently fakes analytics.
"""

from __future__ import annotations

import json
import os
import sys


def _fetch_via_linkedin_api(
    author_urn: str, access_token: str, window_days: int
) -> dict:
    """Read post analytics for ``author_urn`` from LinkedIn. NOT wired in the
    sandbox.

    On the Eva host, implement this using the LinkedIn REST API:
      1. List the author's UGC posts:
         GET https://api.linkedin.com/v2/ugcPosts?q=authors&authors=List({author_urn})
      2. Per-post lifetime statistics (organization shares):
         GET https://api.linkedin.com/rest/organizationalEntityShareStatistics
             ?q=shares&shares=List(urn:li:share:...)
         (or the person-post statistics endpoint where available).
      3. Aggregate reactions/comments:
         GET https://api.linkedin.com/v2/socialActions/{share_urn}
      4. Normalize each post into the stdout ``posts[]`` shape above and return
         ``ok=True``. ``engagement_rate`` may be left null — the service computes
         it canonically as (reactions+comments+shares)/impressions.

    Required OAuth scopes (organization): ``r_organization_social`` and
    ``r_organization_statistics``. Until that is configured, we fail loudly
    rather than pretend success.
    """
    return {
        "ok": False,
        "provider": "linkedin",
        "posts": [],
        "error": (
            "LinkedIn transport is not wired on this host. Implement "
            "linkedin_analytics.py::_fetch_via_linkedin_api using the LinkedIn "
            "ugcPosts + organizationalEntityShareStatistics + socialActions APIs "
            "with an OAuth token (r_organization_social, r_organization_statistics "
            "scopes). No analytics were read."
        ),
    }


def run(request: dict) -> dict:
    author_urn = request.get("author_urn", "")
    token_env = request.get("access_token_env", "LINKEDIN_ACCESS_TOKEN")
    try:
        window_days = int(request.get("window_days", 28) or 28)
    except (TypeError, ValueError):
        window_days = 28

    if not author_urn:
        return {"ok": False, "provider": "linkedin", "posts": [],
                "error": "missing 'author_urn' in request"}

    access_token = os.environ.get(token_env, "")
    if not access_token:
        return {
            "ok": False,
            "provider": "linkedin",
            "posts": [],
            "error": (
                f"LinkedIn access token not set in ${token_env}. Set it on the "
                "Eva host (OAuth: r_organization_social, r_organization_statistics) "
                "before reading analytics."
            ),
        }

    try:
        return _fetch_via_linkedin_api(author_urn, access_token, window_days)
    except Exception as exc:  # noqa: BLE001 — chokepoint must never crash caller
        return {"ok": False, "provider": "linkedin", "posts": [],
                "error": f"linkedin analytics fetch failed: {exc}"}


def main() -> int:
    try:
        request = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "provider": "linkedin", "posts": [],
                          "error": f"invalid request JSON: {exc}"}))
        return 0
    print(json.dumps(run(request)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
