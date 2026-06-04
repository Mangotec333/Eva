"""
Eva Deal Intelligence — DealRepository
SQLite + FTS5 + sqlite-vec (with graceful fallback to FTS5-only if vec unavailable)

Drop into: ~/Eva/modules/deal-db/deal_repository.py
Usage in FastAPI: from deal_repository import DealRepository
"""

import sqlite3
import json
import os
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger("eva.deal_db")

# ── Try loading sqlite-vec. If unavailable, Eva falls back to FTS5+SQL only. ──
try:
    import sqlite_vec  # pip install sqlite-vec
    VEC_AVAILABLE = True
    logger.info("sqlite-vec loaded — semantic search enabled")
except ImportError:
    VEC_AVAILABLE = False
    logger.warning("sqlite-vec not installed — semantic search disabled. Run: pip install sqlite-vec")

# ── Try loading an embedding function (optional, needed for vec search) ──
def _default_embedder(text: str) -> Optional[List[float]]:
    """
    Default no-op embedder. Replace with your preferred provider:
      - OpenAI: openai.embeddings.create(model="text-embedding-3-small", input=text)
      - Local:  ollama.embeddings(model="nomic-embed-text", prompt=text)
    Returns None if not configured — vec search will be skipped for that deal.
    """
    return None

# ── Schema file path ──
_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")
_VEC_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS deal_embeddings USING vec0(
    deal_id TEXT,
    embedding FLOAT[1536]
);
"""

@dataclass
class Deal:
    """Represents a deal record. All monetary values are in USD, rates as decimals."""
    # Identity
    id: str                          # slug: "batch-ai"
    name: str
    alias: Optional[str] = None
    platform: Optional[str] = None  # "Empire Flippers", "Flippa", etc.

    # Classification
    asset_type: Optional[str] = None   # "saas", "rcfe", "content-site", "ecomm"
    market: Optional[str] = None
    tier: int = 2                       # 1=primary, 2=watch, 3=radar, 0=dead
    status: str = "active"

    # Deal Terms
    asking_price: Optional[float] = None
    purchase_price: Optional[float] = None
    multiple: Optional[float] = None
    down_payment: Optional[float] = None
    loan_amount: Optional[float] = None
    loan_rate: Optional[float] = None
    loan_term_yrs: Optional[int] = None
    loan_payment_mo: Optional[float] = None

    # Financials (Monthly)
    gross_revenue_mo: Optional[float] = None
    operating_exp_mo: Optional[float] = None
    ebitda_mo: Optional[float] = None
    total_debt_mo: Optional[float] = None
    noi_mo: Optional[float] = None
    noi_annual: Optional[float] = None
    noi_peak_mo: Optional[float] = None
    mrr: Optional[float] = None
    mrr_peak: Optional[float] = None

    # Real Estate
    cap_rate: Optional[float] = None

    # Risk
    risk_score: float = 5.0
    risk_flags: List[str] = field(default_factory=list)

    # Timeline
    loi_date: Optional[str] = None
    dd_days: Optional[int] = None
    close_date: Optional[str] = None
    exclusivity_days: Optional[int] = None
    holdback_pct: Optional[float] = None
    holdback_days: Optional[int] = None
    transition_days: Optional[int] = None
    transition_hrs_wk: Optional[float] = None

    # Contacts
    seller_name: Optional[str] = None
    seller_email: Optional[str] = None
    broker_name: Optional[str] = None
    broker_platform: Optional[str] = None

    # Eva Metadata
    eva_score: Optional[float] = None
    eva_notes: Optional[str] = None
    watchlist_added: Optional[str] = None
    last_updated: Optional[str] = None
    source_url: Optional[str] = None
    source_doc_id: Optional[str] = None
    extra_fields: Dict[str, Any] = field(default_factory=dict)

    def embedding_text(self) -> str:
        """Build a rich text string for embedding — covers all key deal dimensions."""
        parts = [
            f"{self.name}",
            f"type: {self.asset_type or 'unknown'}",
            f"platform: {self.platform or 'unknown'}",
            f"market: {self.market or 'unknown'}",
            f"status: {self.status}",
            f"tier: {self.tier}",
        ]
        if self.mrr:
            parts.append(f"MRR: ${self.mrr:,.0f}/mo")
        if self.mrr_peak:
            parts.append(f"peak MRR: ${self.mrr_peak:,.0f}/mo")
        if self.noi_mo:
            parts.append(f"NOI: ${self.noi_mo:,.0f}/mo (${(self.noi_mo*12):,.0f}/yr)")
        if self.cap_rate:
            parts.append(f"cap rate: {self.cap_rate*100:.1f}%")
        if self.multiple:
            parts.append(f"multiple: {self.multiple:.1f}x")
        if self.asking_price:
            parts.append(f"asking: ${self.asking_price:,.0f}")
        if self.loan_rate:
            parts.append(f"loan: {self.loan_rate*100:.1f}% {self.loan_term_yrs}yr")
        if self.risk_flags:
            parts.append(f"risks: {', '.join(self.risk_flags)}")
        if self.eva_notes:
            parts.append(f"notes: {self.eva_notes}")
        return ". ".join(parts)

    def to_db_row(self) -> Dict[str, Any]:
        d = asdict(self)
        d["risk_flags"] = json.dumps(d["risk_flags"])
        d["extra_fields"] = json.dumps(d["extra_fields"])
        d.setdefault("watchlist_added", datetime.now(timezone.utc).isoformat())
        return d

    @classmethod
    def from_db_row(cls, row: sqlite3.Row) -> "Deal":
        d = dict(row)
        d["risk_flags"] = json.loads(d.get("risk_flags") or "[]")
        d["extra_fields"] = json.loads(d.get("extra_fields") or "{}")
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class DealRepository:
    """
    Eva's indexed deal store. One .db file, two query modes:
      - Structured SQL  → get_deal(), list_deals(), compare()
      - Keyword search  → search_text() via FTS5 (always available)
      - Semantic search → search_similar() via sqlite-vec (if installed + embedder set)

    Usage:
        repo = DealRepository(db_path="~/Eva/data/eva_deals.db")
        repo.set_embedder(my_openai_embed_fn)  # optional
        repo.upsert(deal)
        results = repo.list_deals(tier=1, status="active")
    """

    def __init__(self, db_path: str = "eva_deals.db", embedder=None):
        self.db_path = os.path.expanduser(db_path)
        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else ".", exist_ok=True)
        self._embedder = embedder or _default_embedder
        self._con = self._connect()
        self._init_schema()

    def set_embedder(self, fn):
        """Inject your embedding function: fn(text: str) -> List[float]"""
        self._embedder = fn

    # ── Connection ────────────────────────────────────────────────────────────
    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path, check_same_thread=False)
        con.row_factory = sqlite3.Row
        if VEC_AVAILABLE:
            con.enable_load_extension(True)
            sqlite_vec.load(con)
            con.enable_load_extension(False)
        return con

    def _init_schema(self):
        with open(_SCHEMA_PATH) as f:
            self._con.executescript(f.read())
        if VEC_AVAILABLE:
            self._con.executescript(_VEC_SCHEMA)
        self._con.commit()

    # ── Write ─────────────────────────────────────────────────────────────────
    def upsert(self, deal: Deal, embed: bool = True) -> None:
        """Insert or replace a deal. Optionally compute and store embedding."""
        row = deal.to_db_row()
        cols = ", ".join(row.keys())
        placeholders = ", ".join(f":{k}" for k in row.keys())
        sql = f"INSERT OR REPLACE INTO deals ({cols}) VALUES ({placeholders})"
        self._con.execute(sql, row)
        self._con.commit()

        if embed and VEC_AVAILABLE and self._embedder is not _default_embedder:
            self._upsert_embedding(deal)

        logger.info(f"Upserted deal: {deal.id}")

    def _upsert_embedding(self, deal: Deal):
        vec = self._embedder(deal.embedding_text())
        if vec is None:
            return
        import struct
        blob = struct.pack(f"{len(vec)}f", *vec)
        self._con.execute(
            "INSERT OR REPLACE INTO deal_embeddings(deal_id, embedding) VALUES (?, ?)",
            (deal.id, blob)
        )
        self._con.commit()

    def log_event(self, deal_id: str, event_type: str,
                  old_value: str = None, new_value: str = None, note: str = None):
        """Track price cuts, status changes, key decisions."""
        self._con.execute(
            "INSERT INTO deal_events(deal_id, event_type, old_value, new_value, note) VALUES (?,?,?,?,?)",
            (deal_id, event_type, old_value, new_value, note)
        )
        self._con.commit()

    def delete(self, deal_id: str):
        self._con.execute("DELETE FROM deals WHERE id = ?", (deal_id,))
        if VEC_AVAILABLE:
            self._con.execute("DELETE FROM deal_embeddings WHERE deal_id = ?", (deal_id,))
        self._con.commit()

    # ── Read ──────────────────────────────────────────────────────────────────
    def get(self, deal_id: str) -> Optional[Deal]:
        """Exact lookup by slug ID."""
        row = self._con.execute("SELECT * FROM deals WHERE id = ?", (deal_id,)).fetchone()
        return Deal.from_db_row(row) if row else None

    def get_by_name(self, name: str) -> Optional[Deal]:
        """Case-insensitive lookup by display name."""
        row = self._con.execute(
            "SELECT * FROM deals WHERE lower(name) = lower(?)", (name,)
        ).fetchone()
        return Deal.from_db_row(row) if row else None

    def list_deals(
        self,
        tier: Optional[int] = None,
        status: Optional[str] = None,
        asset_type: Optional[str] = None,
        order_by: str = "tier ASC, noi_mo DESC",
        limit: int = 50
    ) -> List[Deal]:
        """Filtered structured query — always uses SQL indexes."""
        clauses, params = [], []
        if tier is not None:
            clauses.append("tier = ?"); params.append(tier)
        if status:
            clauses.append("status = ?"); params.append(status)
        if asset_type:
            clauses.append("asset_type = ?"); params.append(asset_type)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM deals {where} ORDER BY {order_by} LIMIT {limit}"
        rows = self._con.execute(sql, params).fetchall()
        return [Deal.from_db_row(r) for r in rows]

    def compare(self, fields: List[str], deal_ids: Optional[List[str]] = None) -> List[Dict]:
        """
        Return selected fields across all deals (or a subset).
        e.g.: repo.compare(["name","noi_mo","multiple","tier"])
        """
        safe_fields = [f for f in fields if f.replace("_","").isalnum()]
        col_sql = ", ".join(safe_fields)
        if deal_ids:
            placeholders = ",".join("?" * len(deal_ids))
            sql = f"SELECT {col_sql} FROM deals WHERE id IN ({placeholders}) ORDER BY tier, noi_mo DESC"
            rows = self._con.execute(sql, deal_ids).fetchall()
        else:
            sql = f"SELECT {col_sql} FROM deals ORDER BY tier ASC, noi_mo DESC"
            rows = self._con.execute(sql).fetchall()
        return [dict(r) for r in rows]

    def get_field(self, deal_id: str, field: str) -> Any:
        """Quick single-field lookup: repo.get_field('batch-ai', 'noi_mo') → 1371.0"""
        if not field.replace("_","").isalnum():
            raise ValueError(f"Invalid field name: {field}")
        row = self._con.execute(f"SELECT {field} FROM deals WHERE id = ?", (deal_id,)).fetchone()
        return row[0] if row else None

    # ── Search ────────────────────────────────────────────────────────────────
    def search_text(self, query: str, limit: int = 10) -> List[Deal]:
        """
        FTS5 keyword search across name, alias, market, notes, risk_flags.
        Always available, zero dependencies.
        """
        sql = """
            SELECT deals.* FROM deals
            JOIN deals_fts ON deals.rowid = deals_fts.rowid
            WHERE deals_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """
        rows = self._con.execute(sql, (query, limit)).fetchall()
        return [Deal.from_db_row(r) for r in rows]

    def search_similar(self, deal_id: str, k: int = 5) -> List[Dict]:
        """
        Semantic KNN search — find k deals most similar to deal_id.
        Requires sqlite-vec installed AND embedder configured.
        Falls back to tier-sorted list if unavailable.
        """
        if not VEC_AVAILABLE or self._embedder is _default_embedder:
            logger.warning("search_similar: falling back to structured query (vec/embedder not configured)")
            return self.compare(["id","name","tier","noi_mo","multiple","asset_type"])

        # Get embedding for reference deal
        ref = self._con.execute(
            "SELECT embedding FROM deal_embeddings WHERE deal_id = ?", (deal_id,)
        ).fetchone()
        if not ref:
            logger.warning(f"search_similar: no embedding for {deal_id}")
            return []

        sql = """
            SELECT d.id, d.name, d.tier, d.noi_mo, d.multiple, d.asset_type, e.distance
            FROM deal_embeddings e
            JOIN deals d ON d.id = e.deal_id
            WHERE e.embedding MATCH ? AND k = ?
              AND e.deal_id != ?
            ORDER BY e.distance
        """
        rows = self._con.execute(sql, (ref[0], k, deal_id)).fetchall()
        return [dict(r) for r in rows]

    def search_hybrid(self, query_text: str, query_embedding: Optional[List[float]] = None,
                      k: int = 10) -> List[Dict]:
        """
        Reciprocal rank fusion of FTS5 + vector search.
        If no embedding provided, falls back to FTS5 only.
        """
        if not VEC_AVAILABLE or query_embedding is None:
            return [asdict(d) if hasattr(d, '__dataclass_fields__') else d
                    for d in self.search_text(query_text, limit=k)]

        import struct
        blob = struct.pack(f"{len(query_embedding)}f", *query_embedding)

        sql = """
            WITH vec_matches AS (
                SELECT deal_id,
                       row_number() OVER (ORDER BY distance) AS rn
                FROM deal_embeddings
                WHERE embedding MATCH ? AND k = ?
            ),
            fts_matches AS (
                SELECT deals.id AS deal_id,
                       row_number() OVER (ORDER BY rank) AS rn
                FROM deals_fts
                JOIN deals ON deals.rowid = deals_fts.rowid
                WHERE deals_fts MATCH ?
                LIMIT ?
            )
            SELECT d.id, d.name, d.tier, d.noi_mo, d.multiple, d.asset_type, d.status,
                   (COALESCE(1.0/(60 + fts.rn), 0) + COALESCE(1.0/(60 + vec.rn), 0)) AS score
            FROM deals d
            LEFT JOIN fts_matches fts ON fts.deal_id = d.id
            LEFT JOIN vec_matches  vec ON vec.deal_id  = d.id
            WHERE fts.deal_id IS NOT NULL OR vec.deal_id IS NOT NULL
            ORDER BY score DESC
            LIMIT ?
        """
        rows = self._con.execute(sql, (blob, k, query_text, k, k)).fetchall()
        return [dict(r) for r in rows]

    # ── Events ────────────────────────────────────────────────────────────────
    def get_events(self, deal_id: str, limit: int = 20) -> List[Dict]:
        rows = self._con.execute(
            "SELECT * FROM deal_events WHERE deal_id = ? ORDER BY created_at DESC LIMIT ?",
            (deal_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Diagnostics ───────────────────────────────────────────────────────────
    def stats(self) -> Dict:
        total   = self._con.execute("SELECT COUNT(*) FROM deals").fetchone()[0]
        by_tier = self._con.execute(
            "SELECT tier, COUNT(*) as n FROM deals GROUP BY tier ORDER BY tier"
        ).fetchall()
        has_vec = VEC_AVAILABLE and self._con.execute(
            "SELECT COUNT(*) FROM deal_embeddings"
        ).fetchone()[0] > 0
        return {
            "total_deals": total,
            "by_tier": {str(r["tier"]): r["n"] for r in by_tier},
            "vec_search_enabled": has_vec,
            "db_path": self.db_path,
        }

    def close(self):
        self._con.close()
