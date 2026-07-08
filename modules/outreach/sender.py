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
    """Hook for the connected Gmail connector. Not implemented in v1."""

    name = "gmail"

    def send(self, message: OutboundMessage) -> SendResult:
        raise NotImplementedError(
            "GmailSender is a v1 hook only. Wire the connected Gmail connector "
            "here to enable real transmission."
        )


def build_sender(name: str | None = None) -> Sender:
    """Factory. Defaults to the stub logger unless EVA_OUTREACH_SENDER=gmail."""
    choice = (name or os.environ.get("EVA_OUTREACH_SENDER", "stub")).lower()
    if choice == "gmail":
        return GmailSender()
    return StubSender()
