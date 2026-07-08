#!/usr/bin/env python3
"""
EVA Outreach — Gmail transport helper.

Invoked as a subprocess by GmailSender.send() so the core outreach module stays
import-free of network code (the sandbox blocks outbound traffic; this helper is
the single chokepoint that talks to the connected Gmail connector).

Contract (stdin -> stdout):
  stdin:  a JSON object on a single line:
          {
            "to": ["..."],            # required
            "cc": ["..."],            # optional, default []
            "bcc": ["..."],           # optional, default []
            "subject": "...",        # required
            "body": "..."             # required, plain text
          }
  stdout: a JSON object: {"ok": true|false, "provider": "gmail",
                          "provider_message_id": "...", "error": "..."}

This helper is designed to be runnable via:
    pplx-tool ... OR the platform's gmail CLI / connector.

In this sandbox there is no direct gmail CLI binary, so the helper detects the
environment and either (a) calls the real transport when available, or
(b) returns ok=False with a clear error so the caller can surface it — it NEVER
silently pretends to send.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys


def _send_via_gmail_api(payload: dict) -> dict:
    """Attempt to transmit via the platform Gmail connector.

    The connector is exposed through the agent runtime, not a standalone CLI
    in this sandbox. When run outside the agent runtime (e.g. on the Eva host
    with the gcal connector wired), this is where the real call lives.
    """
    # Placeholder for the real integration point. On the Eva host, replace this
    # branch with the actual gmail send call (e.g. google API client using the
    # user's OAuth creds, or the platform's gmail tool).
    return {
        "ok": False,
        "provider": "gmail",
        "provider_message_id": "",
        "error": "Gmail transport not wired on this host. Set up the gmail "
                 "OAuth/connector integration in gmail_send.py::_send_via_gmail_api.",
    }


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "provider": "gmail", "error": f"bad json: {exc}"}))
        return 2

    for key in ("to", "subject", "body"):
        if key not in payload:
            print(json.dumps({"ok": False, "provider": "gmail",
                              "error": f"missing key: {key}"}))
            return 2

    payload.setdefault("cc", [])
    payload.setdefault("bcc", [])

    result = _send_via_gmail_api(payload)
    print(json.dumps(result))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
