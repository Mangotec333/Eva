"""
EVA Projects — service layer (all enforced rules live here).

Mirrors outreach's ``OutreachService`` and postcards' ``PostcardsService``: the
REST API and the CLI both call this one place so their behaviour is identical.
Responsibilities:

  * CRUD for tree nodes (add / update / move / delete).
  * Delete cascades to the whole subtree.
  * Move reparents a node and refuses to make a node a child of its own
    descendant (no cycles).
  * Import replaces the tree from a nested JSON document; export returns it.
  * ``seed`` loads the current roadmap (the tree ported from
    ``project_mindmap.html``). Idempotent on top-level title.
  * Nested-tree assembly for the mind-map view / API.

Every mutating action appends to the append-only project ledger.
"""

from __future__ import annotations

from typing import List, Optional

from database import DB_PATH, Store

# ---------------------------------------------------------------------------
# Seed roadmap — ported verbatim from project_mindmap.html's `data` object.
# The synthetic "Root" wrapper is dropped; its children become the top-level
# roots. `name` -> `title`. Idempotent on top-level title (spec section 7).
# ---------------------------------------------------------------------------

SEED_TREE: List[dict] = [
    {
        "title": "Storeys — $10M PE raise",
        "tier": "t1",
        "status": "inprog",
        "meta": "biggest revenue, first",
        "children": [
            {"title": "T1.1 Verify live pages", "status": "done",
             "meta": "storeys.io = marketplace page; no fundraise page"},
            {"title": "T1.2 Fundraise landing page", "status": "inprog", "tier": "t1",
             "meta": "PENDING: where does it live?", "children": [
                {"title": "Option A: /investors route on storeys.io",
                 "status": "pending", "meta": "needs codebase access"},
                {"title": "Option B: separate fast page (Vercel)",
                 "status": "pending", "meta": "ship today, mirror email story"},
                {"title": "Option C: both — fast now, proper later",
                 "status": "pending", "meta": "recommended"},
             ]},
            {"title": "T1.3 Wire Gmail OAuth → gmail_send.py",
             "status": "pending", "tier": "t1", "meta": "Eva host"},
            {"title": "T1.4 Send Tai Lopez email + queue 3-5 more",
             "status": "pending", "tier": "t1", "meta": "draft ready in Gmail"},
            {"title": "T1.5 Accredited-investor verification reply + intake",
             "status": "pending", "tier": "t1", "meta": "SEC 506(c)"},
            {"title": "T1.6 Publish Storeys LinkedIn post",
             "status": "pending", "tier": "t1", "meta": "drafted, drives inbound"},
            {"title": "T1.7 Track replies → verify → calls → close",
             "status": "pending", "tier": "t1"},
        ],
    },
    {
        "title": "Eva — Postcards SaaS (first user-tryable product)",
        "tier": "t2",
        "status": "inprog",
        "meta": "MRR seed",
        "children": [
            {"title": "T2.1 Postcards module — PR #14", "status": "done",
             "meta": "shipped, 9/9 tests",
             "link": "https://github.com/Mangotec333/Eva/pull/14"},
            {"title": "T2.2 Wire LinkedIn OAuth → linkedin_post.py",
             "status": "pending", "tier": "t2", "meta": "Eva host"},
            {"title": "T2.3 Minimal Postcards web UI", "status": "pending",
             "tier": "t2", "meta": "connect → feed → approve"},
            {"title": "T2.4 Deploy to subdomain + waitlist page",
             "status": "pending", "tier": "t2", "meta": "eva-waitlist never built"},
            {"title": "T2.5 Onboard first users (dogfood → beta)",
             "status": "pending", "tier": "t2"},
            {"title": "8 quote-cards rendered", "status": "done",
             "meta": "3 of 8 as PNGs"},
            {"title": "2-phase schedule: 3×daily test → autonomous",
             "status": "pending", "tier": "t2", "meta": "2 weeks, then every 3 days"},
        ],
    },
    {
        "title": "Eva — Modules built",
        "tier": "t3",
        "status": "inprog",
        "children": [
            {"title": "Outreach + Investor Verification — PR #13", "status": "done",
             "link": "https://github.com/Mangotec333/Eva/pull/13",
             "meta": "11/11 tests, Gmail adapter wired"},
            {"title": "Postcards — PR #14", "status": "done",
             "link": "https://github.com/Mangotec333/Eva/pull/14"},
            {"title": "Existing: Logger, Morning OS, Deal Scout, Command Center, "
                      "Content Engine, Autostart", "status": "done",
             "meta": "pre-session"},
            {"title": "GmailSender wired (stub until host OAuth)", "status": "done"},
            {"title": "LinkedInPublisher wired (stub until host OAuth)",
             "status": "done"},
        ],
    },
    {
        "title": "Standards & scale",
        "tier": "t3",
        "status": "pending",
        "children": [
            {"title": "T3.1 Investigate Eva tracking gap", "status": "pending",
             "tier": "t3", "meta": "Logger coverage vs missing"},
            {"title": "T3.2 Codify 2-week 3×daily → autonomous protocol",
             "status": "pending", "tier": "t3", "meta": "Eva module release standard"},
            {"title": "T3.3 Modus Operandi framework as skill", "status": "pending",
             "tier": "t3", "meta": "auto-loads every project"},
            {"title": "T3.4 Collapsible mind-map tracker", "status": "inprog",
             "tier": "t3", "meta": "this view"},
            {"title": "T3.5 Scope Deal Scout as second product", "status": "pending",
             "tier": "t3", "meta": "bigger market, more integration"},
        ],
    },
    {
        "title": "Assets & reference (saved)",
        "tier": "t3",
        "status": "done",
        "children": [
            {"title": "Storeys fundraising reference (Google Doc)", "status": "done",
             "link": "https://docs.google.com/document/d/12lRA_QCaoPAwnSdtuYXlCU3egPM9wTxr4P2oCEHinEQ/edit"},
            {"title": "Tai Lopez tailored email (Gmail draft)", "status": "done"},
            {"title": "LinkedIn post draft", "status": "done"},
            {"title": "8 quote-cards (content + 3 PNGs)", "status": "done"},
            {"title": "Contact saved to memory", "status": "done",
             "meta": "Vineet Ravi · Porter Ranch · Vineeth@mangotecusa.com"},
        ],
    },
]


class ProjectError(Exception):
    """Raised when a rule blocks an action. ``code`` is stable."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class NotFoundError(Exception):
    pass


class ProjectsService:
    def __init__(self, store: Optional[Store] = None):
        self.store = store or Store()

    # ------------------------------------------------------------------
    # Nodes — CRUD
    # ------------------------------------------------------------------

    def create_node(self, payload: dict) -> dict:
        parent_id = payload.get("parent_id")
        if parent_id:
            if not self.store.get_node(parent_id):
                raise NotFoundError(f"parent {parent_id!r} not found")
        sort_order = payload.get("sort_order")
        if sort_order is None:
            sort_order = self.store.max_sort_order(parent_id) + 1
        node = self.store.insert_node(
            {
                "parent_id": parent_id,
                "title": payload["title"],
                "tier": payload.get("tier", "none"),
                "status": payload.get("status", ""),
                "meta": payload.get("meta", ""),
                "link": payload.get("link", ""),
                "sort_order": sort_order,
            }
        )
        self.store.append_ledger(
            "node_created",
            entity_id=node["id"],
            actor=payload.get("actor", "system"),
            details={"title": node["title"], "parent_id": parent_id},
        )
        return node

    def get_node(self, node_id: str) -> dict:
        node = self.store.get_node(node_id)
        if not node:
            raise NotFoundError(f"node {node_id!r} not found")
        return node

    def list_nodes(self) -> List[dict]:
        return self.store.list_nodes()

    def update_node(self, node_id: str, fields: dict, actor: str = "system") -> dict:
        node = self.get_node(node_id)
        clean = {k: v for k, v in fields.items() if v is not None and k != "actor"}
        if "tier" in clean and not clean["tier"]:
            clean["tier"] = "none"
        if not clean:
            return node
        updated = self.store.update_node(node_id, clean)
        self.store.append_ledger(
            "node_updated",
            entity_id=node_id,
            actor=actor,
            details={"changed": {k: clean[k] for k in clean}},
        )
        return updated

    def move_node(
        self,
        node_id: str,
        new_parent_id: Optional[str],
        sort_order: Optional[int] = None,
        actor: str = "system",
    ) -> dict:
        node = self.get_node(node_id)
        if new_parent_id:
            if new_parent_id == node_id:
                raise ProjectError("invalid_move", "a node cannot be its own parent")
            if not self.store.get_node(new_parent_id):
                raise NotFoundError(f"parent {new_parent_id!r} not found")
            # Prevent making a node a child of its own descendant (cycle).
            if new_parent_id in self._descendant_ids(node_id):
                raise ProjectError(
                    "cycle",
                    "cannot move a node under one of its own descendants",
                )
        old_parent = node["parent_id"]
        fields: dict = {"parent_id": new_parent_id}
        fields["sort_order"] = (
            sort_order
            if sort_order is not None
            else self.store.max_sort_order(new_parent_id) + 1
        )
        updated = self.store.update_node(node_id, fields)
        self.store.append_ledger(
            "node_moved",
            entity_id=node_id,
            actor=actor,
            details={"from_parent": old_parent, "to_parent": new_parent_id},
        )
        return updated

    def delete_node(self, node_id: str, actor: str = "system") -> dict:
        self.get_node(node_id)
        subtree = [node_id] + self._descendant_ids(node_id)
        self.store.delete_node(node_id)  # ON DELETE CASCADE removes the subtree
        self.store.append_ledger(
            "node_deleted",
            entity_id=node_id,
            actor=actor,
            details={"deleted_ids": subtree, "count": len(subtree)},
        )
        return {"deleted": subtree, "count": len(subtree)}

    def _descendant_ids(self, node_id: str) -> List[str]:
        """All descendant ids of ``node_id`` (excluding itself)."""
        out: List[str] = []
        frontier = [node_id]
        while frontier:
            current = frontier.pop()
            for child in self.store.children_of(current):
                out.append(child["id"])
                frontier.append(child["id"])
        return out

    # ------------------------------------------------------------------
    # Tree assembly / export
    # ------------------------------------------------------------------

    def get_tree(self) -> List[dict]:
        """Full tree as nested JSON (list of roots, each with ``children``)."""
        rows = self.store.list_nodes()
        by_parent: dict = {}
        for row in rows:
            by_parent.setdefault(row["parent_id"], []).append(row)

        def build(parent_id: Optional[str]) -> List[dict]:
            nodes = sorted(
                by_parent.get(parent_id, []),
                key=lambda r: (r["sort_order"], r["created_at"]),
            )
            result = []
            for n in nodes:
                node = dict(n)
                node["children"] = build(n["id"])
                result.append(node)
            return result

        return build(None)

    def export_tree(self) -> List[dict]:
        """Portable nested tree (title/tier/status/meta/link/children only)."""

        def strip(nodes: List[dict]) -> List[dict]:
            out = []
            for n in nodes:
                entry = {
                    "title": n["title"],
                    "tier": n["tier"],
                    "status": n["status"],
                    "meta": n["meta"],
                    "link": n["link"],
                }
                children = strip(n.get("children", []))
                if children:
                    entry["children"] = children
                out.append(entry)
            return out

        return strip(self.get_tree())

    # ------------------------------------------------------------------
    # Import / seed
    # ------------------------------------------------------------------

    def import_tree(self, nodes: List[dict], actor: str = "system") -> dict:
        """Replace the whole tree from a nested JSON document (spec section 5).

        Wipes existing nodes and rebuilds, so re-importing the same document is
        idempotent (no duplicates).
        """
        self.store.delete_all_nodes()
        created = self._insert_subtree(nodes, parent_id=None)
        self.store.append_ledger(
            "tree_imported",
            entity_id="",
            actor=actor,
            details={"created": created, "roots": len(nodes)},
        )
        return {"created": created, "roots": len(nodes)}

    def _insert_subtree(
        self, nodes: List[dict], parent_id: Optional[str]
    ) -> int:
        count = 0
        for order, spec in enumerate(nodes):
            node = self.store.insert_node(
                {
                    "parent_id": parent_id,
                    "title": spec["title"],
                    "tier": spec.get("tier", "none"),
                    "status": spec.get("status", ""),
                    "meta": spec.get("meta", ""),
                    "link": spec.get("link", ""),
                    "sort_order": order,
                }
            )
            count += 1
            children = spec.get("children") or []
            if children:
                count += self._insert_subtree(children, parent_id=node["id"])
        return count

    def seed(self, actor: str = "system") -> dict:
        """Load the current roadmap tree. Idempotent on top-level title: a root
        already present (matched on title) is left untouched, along with its
        subtree."""
        created, skipped = [], []
        for order, spec in enumerate(SEED_TREE):
            existing = self.store.get_root_by_title(spec["title"])
            if existing:
                skipped.append(spec["title"])
                continue
            root = self.store.insert_node(
                {
                    "parent_id": None,
                    "title": spec["title"],
                    "tier": spec.get("tier", "none"),
                    "status": spec.get("status", ""),
                    "meta": spec.get("meta", ""),
                    "link": spec.get("link", ""),
                    "sort_order": order,
                }
            )
            self._insert_subtree(spec.get("children") or [], parent_id=root["id"])
            created.append(spec["title"])
        self.store.append_ledger(
            "seed_run",
            entity_id="",
            actor=actor,
            details={"created": created, "skipped": skipped},
        )
        return {"created": created, "skipped": skipped}

    # ------------------------------------------------------------------
    # Ledger
    # ------------------------------------------------------------------

    def query_ledger(self, from_ts=None, to_ts=None, event_type=None) -> List[dict]:
        return self.store.query_ledger(
            from_ts=from_ts, to_ts=to_ts, event_type=event_type
        )

    def export_ledger(self, fmt: str = "json") -> str:
        import csv
        import io
        import json

        rows = self.store.query_ledger()
        if fmt == "csv":
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(
                ["id", "ts", "event_type", "entity_id", "actor", "details_json"]
            )
            for r in rows:
                writer.writerow(
                    [r["id"], r["ts"], r["event_type"], r["entity_id"],
                     r["actor"], r.get("details_json", "{}")]
                )
            return buf.getvalue()
        return json.dumps(rows, indent=2)

    @property
    def db_path(self) -> str:
        return getattr(self.store, "db_path", DB_PATH)
