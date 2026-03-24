"""
Embedding client + PostgreSQL pgvector store for KA-CHOW RAG pipeline.

Provides:
  - EmbeddingClient — wraps Gemini text-embedding-004
  - EmbeddingStore  — pgvector-backed similarity search
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from google import genai
from google.genai import types

log = logging.getLogger("ka-chow.embeddings")

EMBEDDING_DIM = 768  # text-embedding-004 default dimension


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class EmbeddingResult:
    """One embedded text chunk."""
    text: str
    vector: List[float]
    model: str
    latency_ms: float = 0.0


@dataclass
class SearchResult:
    """A retrieved chunk with similarity score."""
    chunk_id: int
    source_type: str
    source_ref: str
    chunk_text: str
    score: float
    metadata: Dict[str, Any]


# ---------------------------------------------------------------------------
# Embedding client (Gemini SDK)
# ---------------------------------------------------------------------------

class EmbeddingClient:
    """Generate embeddings via Gemini text-embedding-004."""

    def __init__(self, *, api_key: str, model: str = "text-embedding-004"):
        self._api_key = api_key
        self.model = model
        self._client = genai.Client(api_key=api_key) if api_key else None
        self._total_requests = 0
        self._total_texts = 0

    def embed(self, texts: List[str]) -> List[EmbeddingResult]:
        """
        Embed up to 100 texts in a single API call.
        Returns a list of EmbeddingResult in the same order.
        """
        if not self._client:
            raise RuntimeError(
                "Embedding client not configured. Set GEMINI_API_KEY."
            )
        if not texts:
            return []

        # Gemini batches up to 100 texts per call
        results: List[EmbeddingResult] = []
        for batch_start in range(0, len(texts), 100):
            batch = texts[batch_start : batch_start + 100]
            t0 = time.monotonic()
            response = self._client.models.embed_content(
                model=self.model,
                contents=batch,
            )
            elapsed_ms = (time.monotonic() - t0) * 1000

            for i, emb in enumerate(response.embeddings):
                results.append(
                    EmbeddingResult(
                        text=batch[i],
                        vector=list(emb.values),
                        model=self.model,
                        latency_ms=round(elapsed_ms / len(batch), 1),
                    )
                )
            self._total_requests += 1
            self._total_texts += len(batch)
            log.info(
                "Embedded %d texts in %.0fms (model=%s)",
                len(batch), elapsed_ms, self.model,
            )

        return results

    def embed_single(self, text: str) -> List[float]:
        """Convenience: embed one text, return the raw vector."""
        results = self.embed([text])
        return results[0].vector if results else []

    def health(self) -> Dict[str, Any]:
        return {
            "configured": self._client is not None,
            "model": self.model,
            "total_requests": self._total_requests,
            "total_texts": self._total_texts,
        }


# ---------------------------------------------------------------------------
# PostgreSQL pgvector store
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS meta;

CREATE TABLE IF NOT EXISTS meta.embeddings (
    id          BIGSERIAL PRIMARY KEY,
    source_type TEXT        NOT NULL,        -- 'policy_run' | 'doc' | 'graph_node' | 'code' | 'qa'
    source_ref  TEXT        NOT NULL,        -- unique ref within source_type
    chunk_index INT         NOT NULL DEFAULT 0,
    chunk_text  TEXT        NOT NULL,
    embedding   vector(768) NOT NULL,
    metadata    JSONB       NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_type, source_ref, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_embeddings_source
    ON meta.embeddings (source_type, source_ref);

-- HNSW index for fast cosine similarity search
CREATE INDEX IF NOT EXISTS idx_embeddings_hnsw
    ON meta.embeddings
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
"""


class EmbeddingStore:
    """
    Persist and search embeddings in PostgreSQL with pgvector.

    Parameters
    ----------
    db_conn_factory : callable
        Returns a psycopg2 connection (context manager).
    embedding_client : EmbeddingClient
        Used for on-the-fly embedding of query text.
    """

    def __init__(
        self,
        *,
        db_conn_factory: Callable,
        embedding_client: EmbeddingClient,
    ):
        self._db = db_conn_factory
        self._emb = embedding_client
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        try:
            with self._db() as conn:
                with conn.cursor() as cur:
                    cur.execute(_SCHEMA_SQL)
                conn.commit()
            self._schema_ready = True
        except Exception as exc:
            log.warning("pgvector schema setup failed (may need pgvector extension): %s", exc)

    # -- ingest -------------------------------------------------------------

    def upsert_chunks(
        self,
        *,
        source_type: str,
        source_ref: str,
        chunks: List[str],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Embed and store text chunks. Replaces existing chunks for the same source.
        Returns number of chunks upserted.
        """
        self.ensure_schema()
        if not chunks:
            return 0

        embeddings = self._emb.embed(chunks)
        meta_json = json.dumps(metadata or {})

        with self._db() as conn:
            with conn.cursor() as cur:
                # Remove old chunks for this source
                cur.execute(
                    "DELETE FROM meta.embeddings WHERE source_type = %s AND source_ref = %s",
                    (source_type, source_ref),
                )
                for i, emb in enumerate(embeddings):
                    vec_literal = "[" + ",".join(str(v) for v in emb.vector) + "]"
                    cur.execute(
                        """
                        INSERT INTO meta.embeddings
                            (source_type, source_ref, chunk_index, chunk_text, embedding, metadata)
                        VALUES (%s, %s, %s, %s, %s::vector, %s::jsonb)
                        """,
                        (source_type, source_ref, i, emb.text, vec_literal, meta_json),
                    )
            conn.commit()

        log.info(
            "Upserted %d chunks for %s:%s", len(chunks), source_type, source_ref
        )
        return len(chunks)

    # -- search -------------------------------------------------------------

    def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        source_types: Optional[List[str]] = None,
        min_score: float = 0.0,
    ) -> List[SearchResult]:
        """
        Semantic similarity search.

        Parameters
        ----------
        query : str
            Natural-language query to embed and search against.
        top_k : int
            Max results.
        source_types : list[str], optional
            Filter by source_type (e.g. ['policy_run', 'doc']).
        min_score : float
            Minimum cosine similarity (0–1).
        """
        self.ensure_schema()
        query_vec = self._emb.embed_single(query)
        if not query_vec:
            return []

        vec_literal = "[" + ",".join(str(v) for v in query_vec) + "]"

        where_clause = ""
        params: list = [vec_literal]
        if source_types:
            placeholders = ",".join(["%s"] * len(source_types))
            where_clause = f"WHERE source_type IN ({placeholders})"
            params.extend(source_types)

        params.extend([min_score, top_k])

        sql = f"""
            SELECT
                id,
                source_type,
                source_ref,
                chunk_text,
                1 - (embedding <=> %s::vector) AS score,
                metadata
            FROM meta.embeddings
            {where_clause}
            HAVING 1 - (embedding <=> %s::vector) >= %s
            ORDER BY embedding <=> %s::vector ASC
            LIMIT %s
        """

        # Rebuild with correct parameter ordering
        sql = f"""
            WITH scored AS (
                SELECT
                    id,
                    source_type,
                    source_ref,
                    chunk_text,
                    1 - (embedding <=> %s::vector) AS score,
                    metadata
                FROM meta.embeddings
                {"WHERE source_type IN (" + ",".join(["%s"] * len(source_types)) + ")" if source_types else ""}
            )
            SELECT * FROM scored
            WHERE score >= %s
            ORDER BY score DESC
            LIMIT %s
        """

        params_final: list = [vec_literal]
        if source_types:
            params_final.extend(source_types)
        params_final.extend([min_score, top_k])

        results: List[SearchResult] = []
        try:
            from psycopg2.extras import RealDictCursor
            with self._db() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(sql, tuple(params_final))
                    for row in cur.fetchall():
                        meta = row.get("metadata") or {}
                        if isinstance(meta, str):
                            meta = json.loads(meta)
                        results.append(
                            SearchResult(
                                chunk_id=int(row["id"]),
                                source_type=str(row["source_type"]),
                                source_ref=str(row["source_ref"]),
                                chunk_text=str(row["chunk_text"]),
                                score=float(row["score"]),
                                metadata=meta,
                            )
                        )
        except Exception as exc:
            log.warning("Embedding search failed: %s", exc)

        return results

    # -- utility ------------------------------------------------------------

    def count(self, *, source_type: Optional[str] = None) -> int:
        """Return total embedded chunks, optionally filtered by source_type."""
        self.ensure_schema()
        with self._db() as conn:
            with conn.cursor() as cur:
                if source_type:
                    cur.execute(
                        "SELECT COUNT(*)::int FROM meta.embeddings WHERE source_type = %s",
                        (source_type,),
                    )
                else:
                    cur.execute("SELECT COUNT(*)::int FROM meta.embeddings")
                return int(cur.fetchone()[0])

    def delete_source(self, *, source_type: str, source_ref: str) -> int:
        """Delete all chunks for a specific source. Returns deleted count."""
        self.ensure_schema()
        with self._db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM meta.embeddings WHERE source_type = %s AND source_ref = %s",
                    (source_type, source_ref),
                )
                deleted = cur.rowcount
            conn.commit()
        return deleted
