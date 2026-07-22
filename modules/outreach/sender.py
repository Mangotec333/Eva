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
import smtplib
import ssl
import uuid
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from typing import Protocol

logger = logging.getLogger("eva.outreach.sender")

# Standing sender identity for EVA outbound mail.  Overridable by env for
# non-production use, but these are the defaults the org sends under.
DEFAULT_FROM_NAME = "Vineet Ravi"
DEFAULT_FROM_EMAIL = "info@mangotecusa.com"


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
    """Real transport over Gmail SMTP (smtp.gmail.com:587, STARTTLS).

    Credentials are read from the environment so nothing secret is committed:

        GMAIL_USER            the authenticating Gmail/Workspace account
        GMAIL_APP_PASSWORD    a Google App Password for that account (required)
        EVA_FROM_NAME         display name (default "Vineet Ravi")
        GMAIL_SENDER_EMAIL    From address (default info@mangotecusa.com);
                              ``EVA_FROM_EMAIL`` is accepted as a legacy alias

    Honours the ``Sender`` contract: it does NOT raise on a normal failure
    (missing credentials, SMTP error) — it returns ``SendResult(ok=False, ...)``
    so the caller can record the failure and carry on.
    """

    name = "gmail"

    SMTP_HOST = "smtp.gmail.com"
    SMTP_PORT = 587

    def send(self, message: OutboundMessage) -> SendResult:
        app_password = os.environ.get("GMAIL_APP_PASSWORD", "")
        from_email = (
            message.sender_email
            or os.environ.get("GMAIL_SENDER_EMAIL")
            or os.environ.get("EVA_FROM_EMAIL", DEFAULT_FROM_EMAIL)
        )
        from_name = (
            message.sender_name
            or os.environ.get("EVA_FROM_NAME", DEFAULT_FROM_NAME)
        )
        smtp_user = os.environ.get("GMAIL_USER", from_email)

        if not app_password:
            # Not configured — degrade gracefully rather than raising.
            logger.warning(
                "[gmail-sender] GMAIL_APP_PASSWORD unset; cannot send to %s",
                message.to_email,
            )
            return SendResult(
                ok=False,
                provider=self.name,
                error="GMAIL_APP_PASSWORD not set — Gmail transport unconfigured",
            )

        email = EmailMessage()
        email["From"] = formataddr((from_name, from_email))
        email["To"] = formataddr((message.to_name, message.to_email))
        email["Subject"] = message.subject
        body = message.body
        if message.disclosures_text:
            body = f"{body}\n\n---\n{message.disclosures_text}"
        email.set_content(body)

        try:
            context = ssl.create_default_context()
            with smtplib.SMTP(self.SMTP_HOST, self.SMTP_PORT, timeout=30) as smtp:
                smtp.starttls(context=context)
                smtp.login(smtp_user, app_password)
                smtp.send_message(email)
        except (smtplib.SMTPException, OSError) as exc:
            logger.error("[gmail-sender] send failed to %s: %s", message.to_email, exc)
            return SendResult(ok=False, provider=self.name, error=str(exc))

        logger.info(
            "[gmail-sender] sent to=%s subject=%r campaign=%s recipient=%s",
            message.to_email, message.subject,
            message.campaign_id, message.recipient_id,
        )
        return SendResult(
            ok=True,
            provider=self.name,
            provider_message_id=f"gmail-{uuid.uuid4()}",
        )


def build_sender(name: str | None = None) -> Sender:
    """Factory. Defaults to the stub logger unless EVA_OUTREACH_SENDER=gmail."""
    choice = (name or os.environ.get("EVA_OUTREACH_SENDER", "stub")).lower()
    if choice == "gmail":
        return GmailSender()
    return StubSender()
