"""
EVA Channels — Reddit network chokepoint (the ONLY place Reddit network code
lives). Mirrors outreach's ``gmail_send.py`` and postcards' ``linkedin_post.py``:
reads a JSON request on stdin, writes a JSON result on stdout, never fakes a
post.

Contract (spec section 7)
--------------------------
stdin  : {"title", "body", "subreddit", "kind", "client_id_env",
          "client_secret_env", "username_env", "password_env", "user_agent"}
stdout : {"ok", "provider": "reddit", "post_url", "error"}

On the Eva host, wire ``_post_via_reddit_api``: OAuth password grant against
``https://www.reddit.com/api/v1/access_token`` then POST
``https://oauth.reddit.com/api/submit`` with ``sr``, ``kind=self``, ``title``,
``text`` (required scope: ``submit``). Until then any missing credential yields
``ok=False, error="Reddit credentials not set"`` — an unwired transport fails
loudly and never silently fakes a post.
"""

from __future__ import annotations

import json
import os
import sys


def _post_via_reddit_api(req: dict) -> dict:
    """The single Reddit network call. UNWIRED in v1 (sandbox has no network).

    Host implementation:
      1. POST https://www.reddit.com/api/v1/access_token
         (grant_type=password, HTTP-basic client_id/secret, username/password).
      2. POST https://oauth.reddit.com/api/submit with
         sr=<subreddit>, kind=self, title=<title>, text=<body>, api_type=json.
      3. Parse the returned permalink into post_url.
    Return {"ok": True, "provider": "reddit", "post_url": <url>, "error": ""}.
    """
    # Verify every credential env var is present before attempting anything.
    required_envs = [
        req.get("client_id_env", "REDDIT_CLIENT_ID"),
        req.get("client_secret_env", "REDDIT_CLIENT_SECRET"),
        req.get("username_env", "REDDIT_USERNAME"),
        req.get("password_env", "REDDIT_PASSWORD"),
    ]
    missing = [name for name in required_envs if not os.environ.get(name)]
    if missing:
        return {
            "ok": False,
            "provider": "reddit",
            "post_url": "",
            "error": "Reddit credentials not set",
        }

    # Credentials are present but the real network call is not implemented in
    # this module (out of scope for v1 / offline sandbox). Fail loudly.
    return {
        "ok": False,
        "provider": "reddit",
        "post_url": "",
        "error": (
            "Reddit transport not wired: implement "
            "reddit_post.py::_post_via_reddit_api on the Eva host"
        ),
    }


def main() -> int:
    try:
        raw = sys.stdin.read()
        req = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        print(json.dumps({
            "ok": False, "provider": "reddit", "post_url": "",
            "error": f"invalid request JSON: {exc}",
        }))
        return 0

    try:
        result = _post_via_reddit_api(req)
    except Exception as exc:  # noqa: BLE001 — chokepoint must not crash caller
        result = {
            "ok": False, "provider": "reddit", "post_url": "",
            "error": f"reddit_post.py error: {exc}",
        }
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
