"""
EVA Postcards — service layer (all enforced rules live here).

Mirrors outreach's ``OutreachService``: the REST API and the CLI both call this
one place so their behavior is identical. Responsibilities:

  * Seed the 8 authored quote-cards (idempotent — keyed on title).
  * Render a card to a 1200x1200 PNG (Adam Grant style) via ``renderer``.
  * Approval gate: a card must be ``approved`` before the scheduler releases it.
    Drafts are never auto-posted.
  * Scheduler ``tick``: post the next due ``approved`` card through the
    publisher and advance ``next_due`` by ``cadence_days``. Idempotent and safe
    to call repeatedly from an external cron.

Every mutating action appends to the append-only publish ledger.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from database import DB_PATH, Store
from models import CARD_TRANSITIONS
from publisher import Publisher, build_publisher
from renderer import render_card

# Where rendered PNGs are written (spec section 7: data/postcards/<id>.png).
IMAGE_DIR = os.environ.get(
    "EVA_POSTCARDS_IMAGE_DIR",
    os.path.join(os.path.dirname(__file__), "data", "postcards"),
)

# The 8 authored quote-cards (spec section 8). Order is stable so seed is
# deterministic and idempotent.
SEED_CARDS = [
    {
        "title": "Skin in the game",
        "theme": "skin_in_the_game",
        "para1": "Skin in the game is not about how much you can afford to lose. "
                 "It's about how much you're willing to stand behind.",
        "para2": "Real conviction shows up in your own capital on the line — not "
                 "just advice, not just introductions, not just encouragement "
                 "from the sidelines.",
    },
    {
        "title": "Transparency",
        "theme": "transparency",
        "para1": "Transparency is not about sharing every number in real time. "
                 "It's about never making an investor connect the dots alone.",
        "para2": "The companies that survive are the ones where the people with "
                 "capital also have clarity — and a team that reaches out for "
                 "help before it's too late.",
    },
    {
        "title": "Failure and tangible assets",
        "theme": "failure_and_tangible_assets",
        "para1": "A good investment is not one that can't fail. It's one that "
                 "leaves something real behind when it does.",
        "para2": "Hope is not a strategy. Tangible assets, honest cash flow, and "
                 "a founder who's been burned before — that's the strategy.",
    },
    {
        "title": "Resourcefulness",
        "theme": "resourcefulness",
        "para1": "Resourcefulness is not about knowing all the answers. It's "
                 "about building a room of people who can find them.",
        "para2": "The strongest companies don't hide their problems from "
                 "investors — they invite their investors to help solve them.",
    },
    {
        "title": "Taking the wheel",
        "theme": "taking_the_wheel",
        "para1": "Taking control is not about distrusting others. It's about "
                 "refusing to watch your kids' college fund vanish into someone "
                 "else's silence.",
        "para2": "There's a difference between being an investor and being an "
                 "owner of your investments. I chose the second one.",
    },
    {
        "title": "Shipping and learning",
        "theme": "shipping_and_learning",
        "para1": "Done is not the enemy of perfect. Waiting for perfect is the "
                 "enemy of done.",
        "para2": "Ship every day. Learn in the open. Eva isn't finished — and "
                 "that's exactly why it's already working.",
    },
    {
        "title": "Partnerships",
        "theme": "partnerships",
        "para1": "A partnership is not about splitting the upside. It's about "
                 "owning the part you're responsible for.",
        "para2": "Win-win isn't a slogan. It's the only structure that survives "
                 "the hard years — and the only one worth building a future "
                 "inside.",
    },
    {
        "title": "The mission",
        "theme": "the_mission",
        "para1": "A business is not a vehicle for returns. Returns are the "
                 "byproduct of a business built to serve real people.",
        "para2": "Give a senior citizen a place to flourish in their last "
                 "chapter — and the returns take care of themselves.",
    },
]


class PostcardError(Exception):
    """Raised when a rule blocks an action. ``code`` is stable."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class NotFoundError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _parse_dt(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class PostcardsService:
    def __init__(
        self,
        store: Optional[Store] = None,
        publisher: Optional[Publisher] = None,
        image_dir: str = IMAGE_DIR,
    ):
        self.store = store or Store()
        self.publisher = publisher or build_publisher()
        self.image_dir = image_dir
        os.makedirs(self.image_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Cards
    # ------------------------------------------------------------------

    def create_card(self, payload: dict, render: bool = True) -> dict:
        card = self.store.insert_card(payload)
        self.store.append_ledger(
            "card_created",
            entity_type="postcard",
            entity_id=card["id"],
            actor=payload.get("actor", "system"),
            details={"title": card["title"], "theme": card["theme"]},
        )
        if render:
            card = self.render(card["id"], actor=payload.get("actor", "system"))
        return card

    def list_cards(self, status: Optional[str] = None) -> list[dict]:
        return self.store.list_cards(status=status)

    def get_card(self, card_id: str) -> dict:
        card = self.store.get_card(card_id)
        if not card:
            raise NotFoundError(f"card {card_id!r} not found")
        return card

    def update_card(self, card_id: str, fields: dict, actor: str = "system") -> dict:
        self.get_card(card_id)
        # A status change goes through the guarded transition helpers.
        status = fields.pop("status", None)
        updated = self.store.update_card(card_id, fields) if fields else self.get_card(card_id)
        if status is not None:
            updated = self._transition(card_id, status, actor)
        return updated

    def _transition(self, card_id: str, status: str, actor: str) -> dict:
        card = self.get_card(card_id)
        if status == card["status"]:
            return card
        allowed_prior = CARD_TRANSITIONS.get(status)
        if allowed_prior is None:
            raise PostcardError("invalid_status", f"unknown card status {status!r}")
        if card["status"] not in allowed_prior:
            raise PostcardError(
                "invalid_transition",
                f"cannot move card from {card['status']!r} to {status!r}",
            )
        updated = self.store.update_card(card_id, {"status": status})
        self.store.append_ledger(
            f"card_{status}",
            entity_type="postcard",
            entity_id=card_id,
            actor=actor,
            details={"from": card["status"], "to": status},
        )
        return updated

    def approve_card(self, card_id: str, actor: str = "system") -> dict:
        return self._transition(card_id, "approved", actor)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render(self, card_id: str, actor: str = "system") -> dict:
        card = self.get_card(card_id)
        out_path = os.path.join(self.image_dir, f"{card_id}.png")
        render_card(card["para1"], card["para2"], out_path)
        updated = self.store.update_card(card_id, {"image_path": out_path})
        self.store.append_ledger(
            "card_rendered",
            entity_type="postcard",
            entity_id=card_id,
            actor=actor,
            details={"image_path": out_path},
        )
        return updated

    # ------------------------------------------------------------------
    # Seed
    # ------------------------------------------------------------------

    def seed(self, actor: str = "system", render: bool = True) -> dict:
        """Load the 8 authored quote-cards. Idempotent: cards already present
        (matched on title) are left untouched."""
        created, skipped = [], []
        for spec in SEED_CARDS:
            existing = self.store.get_card_by_title(spec["title"])
            if existing:
                skipped.append(existing)
                continue
            card = self.create_card({**spec, "status": "draft", "actor": actor}, render=render)
            created.append(card)
        self.store.append_ledger(
            "seed_run",
            entity_type="seed",
            entity_id="",
            actor=actor,
            details={"created": len(created), "skipped": len(skipped)},
        )
        return {"created": created, "skipped": skipped}

    # ------------------------------------------------------------------
    # Schedule
    # ------------------------------------------------------------------

    def get_schedule(self) -> dict:
        return self.store.get_schedule()

    def update_schedule(self, fields: dict, actor: str = "system") -> dict:
        clean = {k: v for k, v in fields.items() if v is not None and k != "actor"}
        updated = self.store.update_schedule(clean)
        self.store.append_ledger(
            "schedule_updated",
            entity_type="schedule",
            entity_id="",
            actor=actor,
            details=clean,
        )
        return updated

    # ------------------------------------------------------------------
    # Scheduler
    # ------------------------------------------------------------------

    def tick(self, actor: str = "system", now: Optional[datetime] = None) -> dict:
        """Post the next due approved card and advance ``next_due``.

        Gates (both must hold to release a card):
          1. the schedule clock has reached ``next_due`` (default start_date),
          2. there is an ``approved`` card that is due.
        Safe to call repeatedly: if nothing is due, nothing happens.
        """
        now_dt = now or _now()
        now_iso = now_dt.isoformat()
        sched = self.store.get_schedule()
        cadence_days = int(sched.get("cadence_days", 3))
        next_due = sched.get("next_due") or sched.get("start_date", "")

        # Gate 1: the schedule clock — nothing is released before next_due
        # (this is what keeps a tick before start_date a no-op).
        if next_due and now_iso < next_due:
            return {"posted": None, "reason": "not_due", "next_due": next_due}

        # Gate 2: an approved card that is due.
        card = self.store.next_due_card(now_iso)
        if not card:
            return {"posted": None, "reason": "no_due_card", "next_due": next_due}

        # Ensure the image exists before handing to the publisher.
        if not card.get("image_path") or not os.path.exists(card["image_path"]):
            card = self.render(card["id"], actor=actor)

        result = self.publisher.publish(card, card["image_path"])

        if not result.ok:
            updated = self.store.update_card(
                card["id"], {"status": "failed", "error": result.error}
            )
            self.store.append_ledger(
                "post_failed",
                entity_type="postcard",
                entity_id=card["id"],
                actor=actor,
                details={"error": result.error, "provider": result.provider},
            )
            return {"posted": None, "reason": "publish_failed",
                    "card": updated, "error": result.error, "next_due": next_due}

        posted_at = now_iso
        updated = self.store.update_card(
            card["id"],
            {"status": "posted", "posted_at": posted_at,
             "post_url": result.post_url, "error": ""},
        )
        new_next_due = self._advance_next_due(next_due, now_dt, cadence_days)
        self.store.update_schedule({"next_due": new_next_due})
        self.store.append_ledger(
            "card_posted",
            entity_type="postcard",
            entity_id=card["id"],
            actor=actor,
            details={
                "provider": result.provider,
                "post_url": result.post_url,
                "posted_at": posted_at,
                "next_due": new_next_due,
            },
        )
        return {"posted": updated, "reason": "posted", "next_due": new_next_due}

    @staticmethod
    def _advance_next_due(next_due: str, now_dt: datetime, cadence_days: int) -> str:
        """Advance from the current next_due by one cadence. Falls back to
        ``now`` if next_due is unset or unparseable."""
        base = _parse_dt(next_due) or now_dt
        return (base + timedelta(days=cadence_days)).isoformat()

    # ------------------------------------------------------------------
    # Ledger
    # ------------------------------------------------------------------

    def query_ledger(self, from_ts=None, to_ts=None, event_type=None) -> list[dict]:
        return self.store.query_ledger(from_ts=from_ts, to_ts=to_ts, event_type=event_type)

    def export_ledger(self, fmt: str = "json") -> str:
        import csv
        import io
        import json

        rows = self.store.query_ledger()
        if fmt == "csv":
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(
                ["id", "ts", "event_type", "entity_type", "entity_id", "actor", "details_json"]
            )
            for r in rows:
                writer.writerow(
                    [r["id"], r["ts"], r["event_type"], r["entity_type"],
                     r["entity_id"], r["actor"], r.get("details_json", "{}")]
                )
            return buf.getvalue()
        return json.dumps(rows, indent=2)

    @property
    def db_path(self) -> str:
        return getattr(self.store, "db_path", DB_PATH)
