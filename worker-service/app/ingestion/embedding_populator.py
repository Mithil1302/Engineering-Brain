"""
EmbeddingPopulator: Write chunks to pgvector with SHA-256 deduplication and progress tracking.

Processes chunks in batches, updates ingestion run progress after each batch,
and marks runs as failed on exception while preserving existing embeddings.
"""

import asyncio
import logging
import os
import psycopg2
from typing import Tuple

from ..llm.embeddings import EmbeddingStore
from .chunker import Chunk

log = logging.getLogger("ka-chow.ingestion.embedding_populator")


class EmbeddingPopulator:
    """Write chunks to pgvector using EmbeddingStore with batch processing and progress tracking."""

    def __init__(self, embedding_store: EmbeddingStore, pg_cfg: dict, batch_size: int = 50):
        """
        Initialize EmbeddingPopulator.

        Parameters
        ----------
        embedding_store : EmbeddingStore
            The pgvector store for upserting embeddings.
        pg_cfg : dict
            PostgreSQL connection configuration.
        batch_size : int
            Number of files to process per batch (default 50).
        """
        self.embedding_store = embedding_store
        self.pg_cfg = pg_cfg
        self.batch_size = batch_size
        self.max_retries = int(os.getenv("EMBEDDING_MAX_RETRIES", "5"))
        self.retry_base_seconds = float(os.getenv("EMBEDDING_RETRY_BASE_SECONDS", "5"))
        self.quota_wait_seconds = float(os.getenv("EMBEDDING_QUOTA_WAIT_SECONDS", "45"))

    async def populate_embeddings(self, chunks: list[Chunk], run_id: str) -> Tuple[int, int]:
        """
        Upsert chunks into pgvector in batches.

        Parameters
        ----------
        chunks : list[Chunk]
            List of chunks to embed and store.
        run_id : str
            The ingestion run ID for progress tracking.

        Returns
        -------
        tuple[int, int]
            (chunks_processed, embeddings_created) where chunks_processed is the count
            of chunks sent to the API and embeddings_created is the count returned by upsert_chunks().

        Raises
        ------
        Exception
            Re-raises any exception after marking the run as failed. Existing embeddings
            are preserved because there is no DELETE path.
        """
        chunks_processed = 0
        embeddings_created = 0

        # Group by file first so we always upsert a complete file at once.
        # This avoids cross-batch deletion/reinsert issues for multi-chunk files.
        file_groups: dict[str, list[Chunk]] = {}
        for chunk in chunks:
            file_groups.setdefault(chunk.file_path, []).append(chunk)

        grouped_files = list(file_groups.items())

        for i in range(0, len(grouped_files), self.batch_size):
            file_batch = grouped_files[i : i + self.batch_size]
            batch = [c for _, file_chunks in file_batch for c in file_chunks]
            created = None
            last_error: Exception | None = None
            for attempt in range(self.max_retries + 1):
                try:
                    created = await self._process_batch(batch)
                    break
                except Exception as e:
                    last_error = e
                    err_text = str(e)
                    is_quota = ("RESOURCE_EXHAUSTED" in err_text) or ("429" in err_text)
                    if attempt >= self.max_retries:
                        break

                    if is_quota:
                        wait_seconds = self.quota_wait_seconds
                    else:
                        wait_seconds = self.retry_base_seconds * (2 ** attempt)

                    log.warning(
                        "Embedding batch %s attempt %s failed (%s). Retrying in %.1fs",
                        i // self.batch_size,
                        attempt + 1,
                        err_text,
                        wait_seconds,
                    )
                    await asyncio.sleep(wait_seconds)

            if created is None:
                log.error(f"Embedding batch {i // self.batch_size} failed: {last_error}")
                await self._mark_run_failed(run_id, str(last_error))
                raise last_error if last_error is not None else RuntimeError("Unknown embedding failure")

            chunks_processed += len(batch)
            embeddings_created += created
            await self._update_progress(run_id, chunks_processed, embeddings_created)

        return chunks_processed, embeddings_created

    async def _process_batch(self, batch: list[Chunk]) -> int:
        """
        Call EmbeddingStore.upsert_chunks() for one batch.

        Builds chunk text list and metadata dict propagating last_modified from chunk metadata
        into the embedding metadata for freshness scoring in Task 7.

        Parameters
        ----------
        batch : list[Chunk]
            Batch of chunks to process.

        Returns
        -------
        int
            Count of embeddings created.
        """
        records = []
        for c in batch:
            metadata = {
                "repo": c.repo,
                "extension": c.extension,
                "source_type": c.source_type,
                "last_modified": c.metadata.get("last_modified"),
                "chunk_id": c.chunk_id,
                "start_line": c.start_line,
                "end_line": c.end_line,
            }
            for key, value in c.metadata.items():
                if key not in metadata:
                    metadata[key] = value

            records.append(
                {
                    "source_type": c.source_type,
                    "source_ref": c.file_path,
                    "chunk_text": c.content,
                    "metadata": metadata,
                }
            )

        # Offload sync DB + embedding SDK work to a thread so event loop remains responsive.
        created = await asyncio.to_thread(self.embedding_store.upsert_chunk_records, records)
        return created

    async def _update_progress(
        self, run_id: str, chunks_processed: int, embeddings_created: int
    ) -> None:
        """
        UPDATE chunks_created and embeddings_created on meta.ingestion_runs.

        Called after every batch, not just at the end.

        Parameters
        ----------
        run_id : str
            The ingestion run ID.
        chunks_processed : int
            Total chunks processed so far.
        embeddings_created : int
            Total embeddings created so far.
        """
        await asyncio.to_thread(
            self._update_progress_sync,
            run_id,
            chunks_processed,
            embeddings_created,
        )

    async def _mark_run_failed(self, run_id: str, error_message: str) -> None:
        """
        UPDATE status = 'failed', error_message, completed_at = NOW() WHERE id = run_id.

        Parameters
        ----------
        run_id : str
            The ingestion run ID.
        error_message : str
            The error message to store.
        """
        await asyncio.to_thread(self._mark_run_failed_sync, run_id, error_message)

    def _update_progress_sync(self, run_id: str, chunks_processed: int, embeddings_created: int) -> None:
        with psycopg2.connect(**self.pg_cfg) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE meta.ingestion_runs
                    SET chunks_created = %s, embeddings_created = %s
                    WHERE id = %s
                    """,
                    (chunks_processed, embeddings_created, run_id),
                )
            conn.commit()

    def _mark_run_failed_sync(self, run_id: str, error_message: str) -> None:
        with psycopg2.connect(**self.pg_cfg) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE meta.ingestion_runs
                    SET status = 'failed', error_message = %s, completed_at = NOW()
                    WHERE id = %s
                    """,
                    (error_message, run_id),
                )
            conn.commit()
