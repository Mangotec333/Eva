"""
EVA Retro-Agent — Weekly Retrospective Log source (behind a Protocol).

Answers lens (d): "did last week's stated course-correction priorities actually
get worked on?" To answer it, the retro must read the most recent dated entry
from the **"Eva — Weekly Retrospective Log"** Google Doc.

Per EVA_AGENT_CATALOG.md, kb_index's Google-Docs transport is **stub-only** today
— live Docs isn't wired. So, exactly like ``kb_index`` stubs its Docs transport,
this reads against a **local markdown mirror** behind the same Protocol seam:

- ``RetroLogSource`` — the Protocol: ``read_latest_priorities() -> LogEntry``.
- ``StubRetroLogSource`` — offline, deterministic (tests inject a fixed entry).
- ``LocalFileRetroLogSource`` — reads a local markdown mirror of the log and
  parses the most recent dated entry's priority bullets.
- ``GoogleDocsRetroLogSource`` — the real Docs path. **Not wired yet** (mirrors
  kb_index): it returns an honest not-wired result rather than faking a read, so
  swapping to live Docs later is *additive* (drop in the API call) not a rewrite.

The markdown mirror format (newest entry can be anywhere; the parser picks the
one with the max date):

    ## 2026-07-16
    Course-correction priorities:
    - Close the batch.ai LOI (seller reply)
    - Ship the GHL pipeline for Eva Morning Brief
    - Land the first paying Morning Brief customer
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable

# Default local mirror location (gitignored; created by the founder / a future
# Docs→local sync). Overridable for tests / alternate hosts.
DEFAULT_LOG_PATH = os.environ.get(
    "EVA_RETRO_LOG_PATH",
    os.path.expanduser("~/.eva/retro/weekly_retro_log.md"),
)

_DATE_HEADING = re.compile(r"^#{1,6}\s*(\d{4}-\d{2}-\d{2})", re.MULTILINE)
_BULLET = re.compile(r"^\s*[-*+]\s+(.*\S)\s*$")


@dataclass
class LogEntry:
    """The most recent dated entry parsed from the retrospective log."""
    date: Optional[str] = None
    priorities: list[str] = field(default_factory=list)
    source: str = ""
    ok: bool = False
    error: str = ""


@runtime_checkable
class RetroLogSource(Protocol):
    def read_latest_priorities(self) -> LogEntry:
        """Return the most recent dated entry's course-correction priorities.

        Must NEVER raise to the caller and must NEVER fake a read — an
        unwired/absent source returns ``ok=False`` with a clear ``error`` and an
        empty priority list (the digest then just notes it had no prior baseline).
        """


class StubRetroLogSource:
    """Offline source: returns an injected fixed entry (used in tests)."""

    def __init__(self, priorities: Optional[list[str]] = None,
                 date: Optional[str] = None) -> None:
        self._priorities = list(priorities or [])
        self._date = date

    def read_latest_priorities(self) -> LogEntry:
        return LogEntry(date=self._date, priorities=list(self._priorities),
                        source="stub", ok=True)


def parse_log_markdown(text: str) -> LogEntry:
    """Parse the most-recent dated entry's priority bullets from log markdown.

    Pure/deterministic. Picks the entry whose date heading is the max date, then
    collects the bullet lines beneath it (up to the next date heading)."""
    matches = list(_DATE_HEADING.finditer(text or ""))
    if not matches:
        return LogEntry(source="local", ok=False, error="no dated entries found")
    # newest = max date; ties broken by later position in file.
    newest = max(matches, key=lambda m: (m.group(1), m.start()))
    block_start = newest.end()
    # block ends at the next date heading after this one (by file position).
    later = [m.start() for m in matches if m.start() > newest.start()]
    block_end = min(later) if later else len(text)
    block = text[block_start:block_end]
    priorities = [m.group(1).strip() for line in block.splitlines()
                  for m in [_BULLET.match(line)] if m]
    return LogEntry(date=newest.group(1), priorities=priorities,
                    source="local", ok=True)


class LocalFileRetroLogSource:
    """Reads a local markdown mirror of the Weekly Retrospective Log."""

    def __init__(self, path: str = DEFAULT_LOG_PATH) -> None:
        self.path = path

    def read_latest_priorities(self) -> LogEntry:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                text = fh.read()
        except FileNotFoundError:
            return LogEntry(source="local", ok=False,
                            error=f"log mirror not found: {self.path}")
        except OSError as exc:
            return LogEntry(source="local", ok=False, error=str(exc))
        entry = parse_log_markdown(text)
        entry.source = f"local:{self.path}"
        return entry


class GoogleDocsRetroLogSource:
    """Real Google-Docs path — NOT wired yet (mirrors kb_index's stub-only Docs
    transport). Returns an honest not-wired result instead of faking a read.

    When Docs is wired later this becomes additive: implement ``_read_doc()`` to
    fetch the doc body via the Docs API and hand it to ``parse_log_markdown`` —
    no other module changes.
    """

    RETRO_LOG_DOC_TITLE = "Eva — Weekly Retrospective Log"

    def __init__(self, document_id: Optional[str] = None) -> None:
        self.document_id = document_id

    def read_latest_priorities(self) -> LogEntry:
        return LogEntry(
            source="google_docs",
            ok=False,
            error="google-docs transport not wired (stub-only, per EVA_AGENT_CATALOG.md)",
        )


def make_retro_log_source(offline: Optional[bool] = None,
                          path: str = DEFAULT_LOG_PATH) -> RetroLogSource:
    """Resolve a source: the local mirror when it exists, else an empty Stub.

    Never raises. Google Docs stays behind ``GoogleDocsRetroLogSource`` until the
    shared Docs transport is wired; until then the local mirror is authoritative.
    """
    if offline is None:
        offline = os.environ.get("EVA_RETRO_OFFLINE") == "1"
    if not offline and os.path.exists(path):
        return LocalFileRetroLogSource(path)
    if os.path.exists(path):
        return LocalFileRetroLogSource(path)
    return StubRetroLogSource()


__all__ = [
    "LogEntry", "RetroLogSource", "StubRetroLogSource",
    "LocalFileRetroLogSource", "GoogleDocsRetroLogSource",
    "parse_log_markdown", "make_retro_log_source", "DEFAULT_LOG_PATH",
]
