"""
EVA Outreach — sender interface.

The send workflow (approval gate + compliance checks) is fully decoupled from
the transport. v1 ships a ``StubSender`` that only logs — it never transmits a
real email — so nothing leaves the sandbox. A ``GmailSender`` hook is provided
as the wiring point for the connected Gmail connector; it is intentionally not
implemented in v1.

Select the implementation with the ``EVA_OUTREACH_SENDER`` env var
(``stub`` | ``gmail``) or by passing an explicit instance into the service.
"""

from __future__ import annotations

import logging
import os
import sys
import uuid
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger("eva.outreach.sender")


@dataclass
class OutboundMessage:
    to_email: str
    to_name: str
    subject: str
    body: str
    disclosures_text: str
    sender_name: str
    sender_email: str
    sender_address: str
    campaign_id: str
    recipient_id: str


@dataclass
class SendResult:
    ok: bool
    provider: str
    provider_message_id: str = ""
    error: str = ""


class Sender(Protocol):
    """Transport interface. Implementations must not raise on normal failure;
    they return a ``SendResult`` with ``ok=False`` instead."""

    name: str

    def send(self, message: OutboundMessage) -> SendResult: ...


class StubSender:
    """v1 default: logs the message and returns success. No network I/O."""

    name = "stub"

    def __init__(self, sink: list[OutboundMessage] | None = None):
        # Optional in-memory sink so tests/UI can inspect what "would" be sent.
        self.sent: list[OutboundMessage] = sink if sink is not None else []

    def send(self, message: OutboundMessage) -> SendResult:
        self.sent.append(message)
        logger.info(
            "[stub-sender] would send to=%s subject=%r campaign=%s recipient=%s",
            message.to_email,
            message.subject,
            message.campaign_id,
            message.recipient_id,
        )
        return SendResult(
            ok=True,
            provider=self.name,
            provider_message_id=f"stub-{uuid.uuid4()}",
        )


class GmailSender:
    """Wires approved outreach sends to the connected Gmail connector.

    Shells out to ``gmail_send.py`` (a separate process) so the core outreach
    module stays free of network imports. The helper is the single chokepoint
    that talks to Gmail; it returns ok=False with a clear error instead of
    silently faking a send when the transport isn't wired on the host.
    """

    name = "gmail"

    def __init__(self, helper_path: str | None = None):
        # Resolve the helper relative to this file so it works regardless of CWD.
        if helper_path is None:
            here = os.path.dirname(os.path.abspath(__file__))
            helper_path = os.path.join(here, "gmail_send.py")
        self.helper_path = helper_path

    def send(self, message: OutboundMessage) -> SendResult:
        import json
        import subprocess

        payload = {
            "to": [message.to_email] if message.to_email else [],
            "cc": [],
            "bcc": [],
            "subject": message.subject,
            "body": message.body,
        }
        try:
            proc = subprocess.run(
                [sys.executable, self.helper_path],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                timeout=60,
            )
        except FileNotFoundError as exc:
            return SendResult(ok=False, provider=self.name,
                              error=f"helper not found: {exc}")
        except subprocess.TimeoutExpired:
            return SendResult(ok=False, provider=self.name, error="timeout")

        out = proc.stdout.strip()
        try:
            data = json.loads(out) if out else {}
        except json.JSONDecodeError as exc:
            return SendResult(ok=False, provider=self.name,
                              error=f"bad helper output: {exc}; stderr={proc.stderr}")
        return SendResult(
            ok=bool(data.get("ok", False)),
            provider=self.name,
            provider_message_id=str(data.get("provider_message_id", "")),
            error=str(data.get("error", "")) or (proc.stderr.strip() if proc.returncode else ""),
        )


def build_sender(name: str | None = None) -> Sender:
    """Factory. Defaults to the stub logger unless EVA_OUTREACH_SENDER=gmail."""
    choice = (name or os.environ.get("EVA_OUTREACH_SENDER", "stub")).lower()
    if choice == "gmail":
        return GmailSender()
    return StubSender()
