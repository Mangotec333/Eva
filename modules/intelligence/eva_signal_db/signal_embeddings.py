"""
EVA Signal Intelligence — Semantic Embedding Layer
Embeds signals using OpenAI text-embedding-3-small.
Stores vectors as BLOB in SQLite. Deduplicates on cosine similarity.
Adds sentiment + topic tags via LLM.
Version 1.0 | June 2026

Design principles:
- "SaaS multiples compressing" == "bootstrapped exit valuations dropping" → SAME signal
- Dedup threshold: cosine similarity >= 0.88 → treat as duplicate, merge not delete
- Sentiment: bullish | bearish | neutral | cautionary | contrarian
- Topics: auto-tagged from embedding cluster labels
- Falls back gracefully if OPENAI_API_KEY not set (stores NULL embedding, skips dedup)
"""

import os
import json
import sqlite3
import struct
import numpy as np
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Any
from datetime import datetime

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

EMBED_MODEL         = "text-embedding-3-small"   # 1536 dims, $0.02/1M tokens — cheap
EMBED_DIMS          = 1536
DEDUP_THRESHOLD     = 0.88   # cosine similarity >= this = semantic duplicate
SENTIMENT_MODEL     = "gpt-4o-mini"
OPENAI_API_KEY      = os.environ.get("OPENAI_API_KEY", "")


# ─────────────────────────────────────────────
# VECTOR SERIALIZATION (SQLite BLOB)
# ─────────────────────────────────────────────

def vec_to_blob(vec: List[float]) -> bytes:
    """Pack float32 list → bytes for SQLite BLOB storage."""
    return struct.pack(f"{len(vec)}f", *vec)

def blob_to_vec(blob: bytes) -> np.ndarray:
    """Unpack SQLite BLOB → numpy float32 array."""
    n = len(blob) // 4
    return np.array(struct.unpack(f"{n}f", blob), dtype=np.float32)

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


# ─────────────────────────────────────────────
# OPENAI CLIENT
# ─────────────────────────────────────────────

def _get_client():
    if not OPENAI_API_KEY:
        return None
    from openai import OpenAI
    return OpenAI(api_key=OPENAI_API_KEY)


# ─────────────────────────────────────────────
# EMBEDDING
# ─────────────────────────────────────────────

def embed_text(text: str) -> Optional[List[float]]:
    """
    Embed a single text string. Returns list of floats or None if no API key.
    Text is title + body concatenated for rich signal representation.
    """
    client = _get_client()
    if not client:
        return None
    try:
        resp = client.embeddings.create(
            model=EMBED_MODEL,
            input=text[:8000],   # token safety cap
        )
        return resp.data[0].embedding
    except Exception as e:
        print(f"[EVA Embed] Error: {e}")
        return None

def embed_batch(texts: List[str]) -> List[Optional[List[float]]]:
    """
    Embed a batch of texts in one API call (cheaper, faster).
    Returns list aligned with input — None for failures.
    """
    client = _get_client()
    if not client:
        return [None] * len(texts)
    try:
        truncated = [t[:8000] for t in texts]
        resp = client.embeddings.create(
            model=EMBED_MODEL,
            input=truncated,
        )
        # Re-align by index (OpenAI returns sorted by index)
        result = [None] * len(texts)
        for item in resp.data:
            result[item.index] = item.embedding
        return result
    except Exception as e:
        print(f"[EVA Embed Batch] Error: {e}")
        return [None] * len(texts)


# ─────────────────────────────────────────────
# SENTIMENT + TOPIC TAGGING
# ─────────────────────────────────────────────

SENTIMENT_PROMPT = """Analyze this business signal/insight for a bootstrapped founder.

Signal: {text}

Return a JSON object with:
{{
  "sentiment": "bullish" | "bearish" | "neutral" | "cautionary" | "contrarian",
  "sentiment_score": -1.0 to 1.0 (negative=bearish, positive=bullish),
  "topics": ["array", "of", "2-4", "topic", "tags"],
  "urgency": "high" | "medium" | "low",
  "one_line_summary": "distilled insight in plain English, max 15 words"
}}

Valid topic tags: saas, ai-agents, acquisition, rcfe, senior-care, finance, fico,
bootstrapped, growth-hack, mindset, sales, operations, market-trend, deal-flow,
real-estate, personal-development, eva, storeys, batch-ai, hacker-news, google-trends

Only return JSON. No other text."""


def analyze_signal(title: str, body: str) -> Dict:
    """
    Run LLM sentiment + topic analysis on a signal.
    Returns dict with sentiment, sentiment_score, topics, urgency, one_line_summary.
    Falls back to defaults if no API key or LLM error.
    """
    client = _get_client()
    if not client:
        return _default_analysis()

    text = f"{title}\n\n{body}"
    prompt = SENTIMENT_PROMPT.format(text=text[:2000])

    try:
        resp = client.chat.completions.create(
            model=SENTIMENT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=200,
        )
        content = resp.choices[0].message.content.strip()
        content = content.strip("`").strip()
        if content.startswith("json"):
            content = content[4:].strip()
        result = json.loads(content)
        # Ensure topics is always a list
        if isinstance(result.get("topics"), str):
            result["topics"] = [result["topics"]]
        return result
    except Exception as e:
        print(f"[EVA Sentiment] Error: {e}")
        return _default_analysis()


def _default_analysis() -> Dict:
    return {
        "sentiment": "neutral",
        "sentiment_score": 0.0,
        "topics": [],
        "urgency": "low",
        "one_line_summary": "",
    }


# ─────────────────────────────────────────────
# SCHEMA ADDITIONS
# ─────────────────────────────────────────────

EMBEDDINGS_SCHEMA = """
-- Signal embeddings — stored as BLOB (float32 packed)
CREATE TABLE IF NOT EXISTS signal_embeddings (
    signal_id       TEXT PRIMARY KEY REFERENCES signals(id) ON DELETE CASCADE,
    embedding       BLOB NOT NULL,               -- float32 * 1536, packed via struct
    embed_model     TEXT DEFAULT 'text-embedding-3-small',
    embedded_at     TEXT DEFAULT (datetime('now')),
    embed_text      TEXT                         -- the text that was embedded (title + body)
);

CREATE INDEX IF NOT EXISTS idx_embed_signal ON signal_embeddings(signal_id);

-- Semantic dedup log — when a new signal was found to be a near-duplicate
CREATE TABLE IF NOT EXISTS semantic_dedup_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    new_signal_id   TEXT NOT NULL,               -- the incoming signal
    matched_signal_id TEXT NOT NULL,             -- the existing signal it matched
    similarity      REAL NOT NULL,               -- cosine similarity score
    action          TEXT NOT NULL,               -- 'merged' | 'kept_separate' | 'confidence_boosted'
    logged_at       TEXT DEFAULT (datetime('now'))
);

-- Sentiment + topic enrichment per signal
CREATE TABLE IF NOT EXISTS signal_enrichment (
    signal_id           TEXT PRIMARY KEY REFERENCES signals(id) ON DELETE CASCADE,
    sentiment           TEXT,                    -- 'bullish' | 'bearish' | 'neutral' | 'cautionary' | 'contrarian'
    sentiment_score     REAL DEFAULT 0.0,        -- -1.0 to 1.0
    topics              TEXT DEFAULT '[]',       -- JSON array of topic tags
    urgency             TEXT DEFAULT 'low',      -- 'high' | 'medium' | 'low'
    one_line_summary    TEXT,                    -- distilled 15-word insight
    enriched_at         TEXT DEFAULT (datetime('now')),
    enriched_by         TEXT DEFAULT 'gpt-4o-mini'
);

CREATE INDEX IF NOT EXISTS idx_enrich_sentiment ON signal_enrichment(sentiment);
CREATE INDEX IF NOT EXISTS idx_enrich_urgency   ON signal_enrichment(urgency);

-- Enriched signals view — joins signals + enrichment for full context
CREATE VIEW IF NOT EXISTS enriched_signals AS
SELECT
    s.id, s.signal_type, s.source, s.title, s.body,
    s.domain, s.applies_to, s.confidence, s.stance,
    s.is_actionable, s.status, s.opened_at, s.brief_date,
    s.version, s.next_validation_at,
    e.sentiment, e.sentiment_score, e.topics,
    e.urgency, e.one_line_summary
FROM signals s
LEFT JOIN signal_enrichment e ON e.signal_id = s.id
WHERE s.status = 'active'
ORDER BY
    e.urgency = 'high' DESC,
    s.is_actionable DESC,
    e.sentiment_score DESC,
    s.confidence DESC;
"""


def apply_embeddings_schema(conn: sqlite3.Connection) -> None:
    """Apply the embeddings + enrichment schema to an existing DB connection."""
    conn.executescript(EMBEDDINGS_SCHEMA)


# ─────────────────────────────────────────────
# SEMANTIC DEDUP ENGINE
# ─────────────────────────────────────────────

class SemanticDedup:
    """
    Checks a new signal's embedding against all existing active signal embeddings.
    If cosine similarity >= DEDUP_THRESHOLD, treats as semantic duplicate.

    On duplicate:
    - Boosts confidence of existing signal (more sources = more confident)
    - Logs the dedup event with similarity score
    - Returns (is_duplicate=True, matched_id)

    Does NOT delete either signal — full audit trail preserved.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def find_semantic_duplicate(
        self,
        new_embedding: List[float],
        exclude_signal_id: Optional[str] = None,
        threshold: float = DEDUP_THRESHOLD,
    ) -> Optional[Tuple[str, float]]:
        """
        Search all stored embeddings for a semantic match.
        Returns (matched_signal_id, similarity) or None.
        Only checks ACTIVE signals.
        """
        rows = self.conn.execute(
            """SELECT se.signal_id, se.embedding
               FROM signal_embeddings se
               JOIN signals s ON s.id = se.signal_id
               WHERE s.status = 'active'
               AND (? IS NULL OR se.signal_id != ?)""",
            (exclude_signal_id, exclude_signal_id)
        ).fetchall()

        if not rows:
            return None

        new_vec = np.array(new_embedding, dtype=np.float32)
        best_match = None
        best_score = 0.0

        for row in rows:
            existing_vec = blob_to_vec(row["embedding"])
            sim = cosine_similarity(new_vec, existing_vec)
            if sim >= threshold and sim > best_score:
                best_score = sim
                best_match = row["signal_id"]

        if best_match:
            return (best_match, best_score)
        return None

    def handle_duplicate(
        self,
        new_signal_id: str,
        matched_signal_id: str,
        similarity: float,
    ) -> str:
        """
        When duplicate detected:
        - Boost matched signal confidence by +0.05 (capped at 0.98)
        - Log to semantic_dedup_log
        - Return action taken
        """
        now = datetime.utcnow().isoformat()

        # Boost confidence of existing signal
        existing = self.conn.execute(
            "SELECT confidence FROM signals WHERE id = ?", (matched_signal_id,)
        ).fetchone()

        if existing:
            new_conf = min(0.98, existing["confidence"] + 0.05)
            self.conn.execute(
                "UPDATE signals SET confidence = ?, updated_at = ? WHERE id = ?",
                (new_conf, now, matched_signal_id)
            )

        # Log the dedup event
        self.conn.execute(
            """INSERT INTO semantic_dedup_log
               (new_signal_id, matched_signal_id, similarity, action)
               VALUES (?, ?, ?, 'confidence_boosted')""",
            (new_signal_id, matched_signal_id, similarity)
        )

        # Mark new signal as superseded by the existing one
        self.conn.execute(
            """UPDATE signals
               SET status = 'superseded', superseded_by = ?,
                   closed_at = ?, close_reason = 'new_evidence',
                   outcome_note = ?,
                   updated_at = ?
               WHERE id = ?""",
            (
                matched_signal_id,
                now,
                f"Semantic duplicate detected (similarity={similarity:.3f}). Confidence boosted on original.",
                now,
                new_signal_id,
            )
        )

        return "confidence_boosted"


# ─────────────────────────────────────────────
# ENRICHMENT PIPELINE
# ─────────────────────────────────────────────

def enrich_signal(
    conn: sqlite3.Connection,
    signal_id: str,
    title: str,
    body: str,
    embedding: Optional[List[float]] = None,
) -> Dict:
    """
    Full enrichment pipeline for one signal:
    1. Generate embedding (or use provided)
    2. Store embedding
    3. Run sentiment + topic analysis
    4. Store enrichment
    Returns enrichment dict.
    """
    # 1. Embed
    if embedding is None:
        embed_input = f"{title}\n\n{body}"
        embedding = embed_text(embed_input)

    if embedding is not None:
        conn.execute(
            """INSERT OR REPLACE INTO signal_embeddings
               (signal_id, embedding, embed_text)
               VALUES (?, ?, ?)""",
            (signal_id, vec_to_blob(embedding), f"{title}\n\n{body}"[:500])
        )

    # 2. Sentiment + topics
    analysis = analyze_signal(title, body)

    conn.execute(
        """INSERT OR REPLACE INTO signal_enrichment
           (signal_id, sentiment, sentiment_score, topics, urgency, one_line_summary)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            signal_id,
            analysis.get("sentiment", "neutral"),
            analysis.get("sentiment_score", 0.0),
            json.dumps(analysis.get("topics", [])),
            analysis.get("urgency", "low"),
            analysis.get("one_line_summary", ""),
        )
    )

    return analysis


def enrich_batch(
    conn: sqlite3.Connection,
    signals: List[Dict],   # list of {id, title, body}
) -> List[Dict]:
    """
    Batch enrich a list of signals — one embedding API call for all.
    Returns list of enrichment results aligned with input.
    """
    texts = [f"{s['title']}\n\n{s['body']}" for s in signals]
    embeddings = embed_batch(texts)

    results = []
    for i, signal in enumerate(signals):
        emb = embeddings[i]
        result = enrich_signal(
            conn,
            signal_id=signal["id"],
            title=signal["title"],
            body=signal["body"],
            embedding=emb,
        )
        results.append(result)

    return results


# ─────────────────────────────────────────────
# TOPIC CLUSTER SUMMARY (for weekly mining report)
# ─────────────────────────────────────────────

def cluster_summary(conn: sqlite3.Connection, days: int = 7) -> Dict:
    """
    Summarize the signal landscape from the last N days.
    Groups by topic, sentiment distribution, top urgent signals.
    Used in weekly brief mining report.
    """
    since = f"datetime('now', '-{days} days')"

    # Sentiment distribution
    sentiment_rows = conn.execute(
        f"""SELECT e.sentiment, COUNT(*) as count
            FROM signal_enrichment e
            JOIN signals s ON s.id = e.signal_id
            WHERE s.opened_at >= {since} AND s.status = 'active'
            GROUP BY e.sentiment
            ORDER BY count DESC"""
    ).fetchall()

    # Top topics
    topic_rows = conn.execute(
        f"""SELECT e.topics
            FROM signal_enrichment e
            JOIN signals s ON s.id = e.signal_id
            WHERE s.opened_at >= {since} AND s.status = 'active'"""
    ).fetchall()

    topic_counts: Dict[str, int] = {}
    for row in topic_rows:
        try:
            topics = json.loads(row["topics"] or "[]")
            for t in topics:
                topic_counts[t] = topic_counts.get(t, 0) + 1
        except Exception:
            pass

    top_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:8]

    # High urgency signals
    urgent = conn.execute(
        f"""SELECT s.title, s.signal_type, e.sentiment, e.one_line_summary
            FROM signals s
            JOIN signal_enrichment e ON e.signal_id = s.id
            WHERE e.urgency = 'high'
              AND s.opened_at >= {since}
              AND s.status = 'active'
            ORDER BY s.opened_at DESC
            LIMIT 5"""
    ).fetchall()

    # Dedup events this week
    dedup_count = conn.execute(
        f"""SELECT COUNT(*) FROM semantic_dedup_log
            WHERE logged_at >= {since}"""
    ).fetchone()[0]

    return {
        "period_days": days,
        "sentiment_distribution": [dict(r) for r in sentiment_rows],
        "top_topics": [{"topic": t, "count": c} for t, c in top_topics],
        "high_urgency_signals": [dict(r) for r in urgent],
        "semantic_dedup_events": dedup_count,
    }
