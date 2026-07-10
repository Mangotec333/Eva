#!/usr/bin/env python3
"""
EVA Postcards — LinkedIn publish chokepoint.

This is the *single* place where a real network call to LinkedIn is made. Every
other part of the module treats publishing as an interface; only this script
knows about LinkedIn. Keeping the transport isolated here means wiring live
publishing on the Eva host is one function: ``_post_via_linkedin_api``.

Contract (spec section 7), identical in spirit to outreach's ``gmail_send.py``:

  stdin  JSON: {"text": "...", "image_path": "...",
                "access_token_env": "LINKEDIN_ACCESS_TOKEN"}
  stdout JSON: {"ok": true|false, "provider": "linkedin",
                "post_url": "...", "error": "..."}

Until wired, ``_post_via_linkedin_api`` returns ``ok=False`` with a clear error
so the module never silently fakes a post.
"""

from __future__ import annotations

import json
import os
import sys


def _post_via_linkedin_api(
    text: str, image_path: str, access_token: str
) -> dict:
    """Publish an image post to LinkedIn. NOT wired in the sandbox.

    On the Eva host, implement this using the LinkedIn API:
      1. Register + upload the image via the Images API
         (POST /rest/images?action=initializeUpload, then PUT the bytes).
      2. Create a UGC post referencing the uploaded image asset
         (POST /rest/posts or /v2/ugcPosts) with an author of
         urn:li:person:<id> and ``text`` as the commentary.
      3. Return the created post URL.

    Requires a LinkedIn OAuth access token with the ``w_member_social`` scope.
    Until that is configured, we fail loudly rather than pretend success.
    """
    return {
        "ok": False,
        "provider": "linkedin",
        "post_url": "",
        "error": (
            "LinkedIn transport is not wired on this host. Implement "
            "linkedin_post.py::_post_via_linkedin_api using the LinkedIn "
            "Images upload + UGC Posts API with an OAuth token "
            "(w_member_social scope). No post was made."
        ),
    }


def run(request: dict) -> dict:
    text = request.get("text", "")
    image_path = request.get("image_path", "")
    token_env = request.get("access_token_env", "LINKEDIN_ACCESS_TOKEN")

    if not text:
        return {"ok": False, "provider": "linkedin", "post_url": "",
                "error": "missing 'text' in request"}
    if not image_path or not os.path.exists(image_path):
        return {"ok": False, "provider": "linkedin", "post_url": "",
                "error": f"image_path not found: {image_path!r}"}

    access_token = os.environ.get(token_env, "")
    if not access_token:
        return {
            "ok": False,
            "provider": "linkedin",
            "post_url": "",
            "error": (
                f"no LinkedIn access token in ${token_env}. Set it on the Eva "
                "host (OAuth, w_member_social scope) before publishing."
            ),
        }

    try:
        return _post_via_linkedin_api(text, image_path, access_token)
    except Exception as exc:  # noqa: BLE001 — chokepoint must never crash caller
        return {"ok": False, "provider": "linkedin", "post_url": "",
                "error": f"linkedin post failed: {exc}"}


def main() -> int:
    try:
        request = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "provider": "linkedin", "post_url": "",
                          "error": f"invalid request JSON: {exc}"}))
        return 0
    print(json.dumps(run(request)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
