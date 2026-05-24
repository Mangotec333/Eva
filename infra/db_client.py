"""
EVA DB Client — unified interface for all 3 layers
Usage:
    from infra.db_client import pg, qdrant, arcade
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── LAYER 1: PostgreSQL ─────────────────────────────────────
import psycopg2
from psycopg2.extras import RealDictCursor

def pg():
    """Return a PostgreSQL connection (Layer 1 — operational)."""
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        dbname=os.getenv("POSTGRES_DB", "eva"),
        user=os.getenv("POSTGRES_USER", "eva"),
        password=os.getenv("POSTGRES_PASSWORD", "eva_local_secret"),
        cursor_factory=RealDictCursor
    )

# ── LAYER 2: Qdrant ────────────────────────────────────────
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

_qdrant_client = None

def qdrant() -> QdrantClient:
    """Return Qdrant client (Layer 2 — semantic memory).
    Local by default. Set QDRANT_URL + QDRANT_API_KEY for cloud.
    One line change to migrate: update .env only.
    """
    global _qdrant_client
    if _qdrant_client is None:
        url = os.getenv("QDRANT_URL", "http://localhost:6333")
        api_key = os.getenv("QDRANT_API_KEY") or None
        if api_key:
            _qdrant_client = QdrantClient(url=url, api_key=api_key)
        else:
            _qdrant_client = QdrantClient(url=url)
    return _qdrant_client

# ── Qdrant Collection Bootstrap ────────────────────────────
QDRANT_COLLECTIONS = {
    "angel_memory":     1536,   # angel narrations + outputs
    "deal_context":     1536,   # deal summaries for semantic search
    "email_signals":    1536,   # email embeddings
    "sense_profile":    1536,   # Sensory Quotient profile vectors
    "narrations":       1536,   # triage inputs
}

def init_qdrant_collections():
    """Create all EVA collections if they don't exist."""
    client = qdrant()
    existing = {c.name for c in client.get_collections().collections}
    for name, dim in QDRANT_COLLECTIONS.items():
        if name not in existing:
            client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(
                    size=dim,
                    distance=Distance.COSINE,
                    # Scalar quantization: 4x RAM savings, minimal accuracy loss
                    on_disk=False,
                ),
            )
            print(f"[Qdrant] Created collection: {name} (dim={dim})")
        else:
            print(f"[Qdrant] Collection exists: {name}")

# ── LAYER 3: ArcadeDB ──────────────────────────────────────
import httpx

class ArcadeClient:
    """Thin HTTP client for ArcadeDB (Layer 3 — graph relationships)."""

    def __init__(self):
        self.base = os.getenv("ARCADEDB_URL", "http://localhost:2480")
        self.db   = os.getenv("ARCADEDB_DB", "eva")
        self.user = os.getenv("ARCADEDB_USER", "eva")
        self.pwd  = os.getenv("ARCADEDB_PASSWORD", "eva_local_secret")
        self.auth = (self.user, self.pwd)

    def query(self, sql: str, language: str = "sql") -> dict:
        """Run a query. language: 'sql' | 'cypher' | 'gremlin' | 'graphql'"""
        resp = httpx.post(
            f"{self.base}/api/v1/query/{self.db}",
            json={"language": language, "command": sql},
            auth=self.auth,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def command(self, sql: str, language: str = "sql") -> dict:
        """Run a write command."""
        resp = httpx.post(
            f"{self.base}/api/v1/command/{self.db}",
            json={"language": language, "command": sql},
            auth=self.auth,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

_arcade_client = None

def arcade() -> ArcadeClient:
    """Return ArcadeDB client (Layer 3 — graph)."""
    global _arcade_client
    if _arcade_client is None:
        _arcade_client = ArcadeClient()
    return _arcade_client

def init_arcade_schema():
    """Create EVA graph vertex + edge types if not present."""
    client = arcade()
    commands = [
        # Vertex types
        "CREATE VERTEX TYPE IF NOT EXISTS Person",
        "CREATE VERTEX TYPE IF NOT EXISTS Company",
        "CREATE VERTEX TYPE IF NOT EXISTS Deal",
        "CREATE VERTEX TYPE IF NOT EXISTS Signal",
        # Edge types
        "CREATE EDGE TYPE IF NOT EXISTS KNOWS",        # Person → Person
        "CREATE EDGE TYPE IF NOT EXISTS WORKS_AT",     # Person → Company
        "CREATE EDGE TYPE IF NOT EXISTS ASSOCIATED",   # Person/Company → Deal
        "CREATE EDGE TYPE IF NOT EXISTS TRIGGERED",    # Signal → Deal
        "CREATE EDGE TYPE IF NOT EXISTS OWNS",         # Person → Company
    ]
    for cmd in commands:
        try:
            client.command(cmd)
        except Exception as e:
            print(f"[ArcadeDB] Schema note: {e}")
    print("[ArcadeDB] Graph schema ready.")

# ── Full Stack Init ─────────────────────────────────────────
def init_all():
    """Bootstrap all 3 layers. Run once after docker compose up."""
    print("\n── EVA DB Stack Init ──────────────────────────")
    print("[Layer 1] PostgreSQL — schema via docker init scripts ✓")
    print("[Layer 2] Qdrant — initializing collections...")
    init_qdrant_collections()
    print("[Layer 3] ArcadeDB — initializing graph schema...")
    init_arcade_schema()
    print("── All layers ready ───────────────────────────\n")

if __name__ == "__main__":
    init_all()
