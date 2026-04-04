"""
IngestionPipeline: Orchestrate end-to-end repository ingestion.

Coordinates crawling, chunking, service detection, dependency extraction,
graph population, and embedding population in strict sequence. Tracks progress
in meta.ingestion_runs and emits completion events to Kafka.
"""

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import psycopg2
from fastapi import HTTPException
from kafka import KafkaProducer

from .crawler import GitHubRepoCrawler, RepoCrawlResult
from .chunker import CodeChunker
from .service_detector import ServiceDetector, DependencyExtractor
from .graph_populator import GraphPopulator
from .embedding_populator import EmbeddingPopulator

log = logging.getLogger("ka-chow.ingestion.pipeline")


@dataclass
class IngestionResult:
    """Result of a complete ingestion run."""
    repo: str
    run_id: str
    files_processed: int
    chunks_created: int
    embeddings_created: int
    services_detected: int
    duration_seconds: float
    status: str  # "success" | "failed"


@dataclass
class IngestionStatus:
    """Status of an ingestion run from meta.ingestion_runs."""
    run_id: str
    repo: str
    triggered_by: str
    started_at: datetime
    completed_at: Optional[datetime]
    files_processed: int
    chunks_created: int
    embeddings_created: int
    services_detected: int
    status: str
    error_message: Optional[str]
    commit_sha: Optional[str]


class IngestionPipeline:
    """Orchestrates end-to-end repository ingestion with progress tracking."""

    def __init__(
        self,
        crawler: GitHubRepoCrawler,
        chunker: CodeChunker,
        service_detector: ServiceDetector,
        dep_extractor: DependencyExtractor,
        graph_populator: GraphPopulator,
        embedding_populator: EmbeddingPopulator,
        pg_cfg: dict,
        kafka_brokers: list[str],
    ):
        """
        Initialize IngestionPipeline with all required components.
        
        Args:
            crawler: GitHub repository crawler
            chunker: Code chunker
            service_detector: Service boundary detector
            dep_extractor: Dependency extractor (was missing from original design)
            graph_populator: Neo4j graph populator
            embedding_populator: pgvector embedding populator
            pg_cfg: PostgreSQL connection config
            kafka_brokers: Kafka broker addresses
        """
        self.crawler = crawler
        self.chunker = chunker
        self.service_detector = service_detector
        self.dep_extractor = dep_extractor
        self.graph_populator = graph_populator
        self.embedding_populator = embedding_populator
        self.pg_cfg = pg_cfg
        self.kafka_brokers = kafka_brokers
        self._producer: Optional[KafkaProducer] = None

    def _get_producer(self) -> KafkaProducer:
        """Lazy-initialize Kafka producer."""
        if self._producer is None:
            self._producer = KafkaProducer(
                bootstrap_servers=self.kafka_brokers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
        return self._producer

    async def ingest_repo(
        self,
        repo: str,
        run_id: str,
        triggered_by: str = "manual",
        commit_sha: Optional[str] = None,
    ) -> IngestionResult:
        """
        Execute full repository ingestion.
        
        Sequence: crawl → chunk → detect services → extract dependencies →
        populate graph → populate embeddings.
        
        On any exception, calls _fail_run() and returns a failed IngestionResult
        with zeroed counters. Does not re-raise.
        
        Args:
            repo: Repository full name (owner/repo)
            run_id: UUID for this ingestion run
            triggered_by: Source of trigger ("manual", "webhook", "scheduled")
            commit_sha: Optional commit SHA
            
        Returns:
            IngestionResult with status "success" or "failed"
        """
        start_time = time.time()
        
        try:
            # Start run tracking
            await self._start_run(run_id, repo, triggered_by, commit_sha)
            
            # Step 1: Crawl repository
            log.info(f"[{run_id}] Starting full crawl for {repo}")
            crawl_result: RepoCrawlResult = await self.crawler.crawl_repo(repo, changed_files=None)
            files_processed = crawl_result.total_files
            log.info(f"[{run_id}] Crawled {files_processed} files")
            
            # Step 2: Chunk files
            log.info(f"[{run_id}] Chunking {files_processed} files")
            chunks = self.chunker.chunk_files(repo, crawl_result.files)
            chunks_created = len(chunks)
            log.info(f"[{run_id}] Created {chunks_created} chunks")
            
            # Step 3: Detect services
            log.info(f"[{run_id}] Detecting services")
            services = self.service_detector.detect_services(crawl_result.files)
            services_detected = len(services)
            log.info(f"[{run_id}] Detected {services_detected} services")
            
            # Step 4: Extract dependencies
            log.info(f"[{run_id}] Extracting dependencies")
            dependencies = self.dep_extractor.extract_dependencies(
                services, crawl_result.files
            )
            log.info(f"[{run_id}] Extracted {len(dependencies)} dependencies")
            
            # Step 5: Populate graph
            log.info(f"[{run_id}] Populating graph")
            await self.graph_populator.populate_graph(
                repo, services, chunks, dependencies
            )
            log.info(f"[{run_id}] Graph populated")
            
            # Step 6: Populate embeddings
            log.info(f"[{run_id}] Populating embeddings")
            chunks_processed, embeddings_created = await self.embedding_populator.populate_embeddings(
                chunks, run_id
            )
            log.info(f"[{run_id}] Created {embeddings_created} embeddings")
            
            # Complete run
            duration_seconds = time.time() - start_time
            await self._complete_run(
                run_id,
                files_processed,
                chunks_created,
                embeddings_created,
                services_detected,
            )

            # Record temporal ingestion snapshot (non-fatal)
            await self._record_ingestion_snapshot(
                repo=repo,
                run_id=run_id,
                services_detected=services_detected,
            )
            
            # Emit completion event
            await self._emit_completion_event(
                repo,
                run_id,
                files_processed,
                chunks_created,
                embeddings_created,
                services_detected,
                duration_seconds,
                "success",
                triggered_by,
            )
            
            log.info(f"[{run_id}] Ingestion complete in {duration_seconds:.1f}s")
            
            return IngestionResult(
                repo=repo,
                run_id=run_id,
                files_processed=files_processed,
                chunks_created=chunks_created,
                embeddings_created=embeddings_created,
                services_detected=services_detected,
                duration_seconds=duration_seconds,
                status="success",
            )
            
        except Exception as e:
            log.error(f"[{run_id}] Ingestion failed: {e}", exc_info=True)
            duration_seconds = time.time() - start_time
            await self._fail_run(run_id, str(e))
            
            # Return failed result with zeroed counters (do not re-raise)
            return IngestionResult(
                repo=repo,
                run_id=run_id,
                files_processed=0,
                chunks_created=0,
                embeddings_created=0,
                services_detected=0,
                duration_seconds=duration_seconds,
                status="failed",
            )

    async def ingest_on_push(
        self,
        repo: str,
        run_id: str,
        changed_files: list[str],
        triggered_by: str = "webhook",
        commit_sha: Optional[str] = None,
    ) -> IngestionResult:
        """
        Execute incremental ingestion for changed files only.
        
        Same sequence as ingest_repo() but passes changed_files to crawler.
        On exception, calls _fail_run() and re-raises (unlike full ingestion,
        incremental failures should surface to the caller).
        
        Args:
            repo: Repository full name (owner/repo)
            run_id: UUID for this ingestion run
            changed_files: List of file paths that changed
            triggered_by: Source of trigger (typically "webhook")
            commit_sha: Optional commit SHA
            
        Returns:
            IngestionResult with status "success"
            
        Raises:
            Exception: Re-raises any exception after marking run as failed
        """
        start_time = time.time()
        
        try:
            # Start run tracking
            await self._start_run(run_id, repo, triggered_by, commit_sha)
            
            # Step 1: Crawl changed files only
            log.info(f"[{run_id}] Starting incremental crawl for {repo}: {len(changed_files)} files")
            crawl_result: RepoCrawlResult = await self.crawler.crawl_repo(
                repo, changed_files=changed_files
            )
            files_processed = crawl_result.total_files
            log.info(f"[{run_id}] Crawled {files_processed} changed files")
            
            # Step 2: Chunk files
            log.info(f"[{run_id}] Chunking {files_processed} files")
            chunks = self.chunker.chunk_files(repo, crawl_result.files)
            chunks_created = len(chunks)
            log.info(f"[{run_id}] Created {chunks_created} chunks")
            
            # Step 3: Detect services
            log.info(f"[{run_id}] Detecting services")
            services = self.service_detector.detect_services(crawl_result.files)
            services_detected = len(services)
            log.info(f"[{run_id}] Detected {services_detected} services")
            
            # Step 4: Extract dependencies
            log.info(f"[{run_id}] Extracting dependencies")
            dependencies = self.dep_extractor.extract_dependencies(
                services, crawl_result.files
            )
            log.info(f"[{run_id}] Extracted {len(dependencies)} dependencies")
            
            # Step 5: Populate graph (only updates nodes for changed files)
            log.info(f"[{run_id}] Populating graph")
            await self.graph_populator.populate_graph(
                repo, services, chunks, dependencies, is_incremental=True
            )
            log.info(f"[{run_id}] Graph populated")
            
            # Step 6: Populate embeddings
            log.info(f"[{run_id}] Populating embeddings")
            chunks_processed, embeddings_created = await self.embedding_populator.populate_embeddings(
                chunks, run_id
            )
            log.info(f"[{run_id}] Created {embeddings_created} embeddings")
            
            # Complete run
            duration_seconds = time.time() - start_time
            await self._complete_run(
                run_id,
                files_processed,
                chunks_created,
                embeddings_created,
                services_detected,
            )

            # Record temporal ingestion snapshot (non-fatal)
            await self._record_ingestion_snapshot(
                repo=repo,
                run_id=run_id,
                services_detected=services_detected,
            )
            
            # Emit completion event
            await self._emit_completion_event(
                repo,
                run_id,
                files_processed,
                chunks_created,
                embeddings_created,
                services_detected,
                duration_seconds,
                "success",
                triggered_by,
            )
            
            log.info(f"[{run_id}] Incremental ingestion complete in {duration_seconds:.1f}s")
            
            return IngestionResult(
                repo=repo,
                run_id=run_id,
                files_processed=files_processed,
                chunks_created=chunks_created,
                embeddings_created=embeddings_created,
                services_detected=services_detected,
                duration_seconds=duration_seconds,
                status="success",
            )
            
        except Exception as e:
            log.error(f"[{run_id}] Incremental ingestion failed: {e}", exc_info=True)
            await self._fail_run(run_id, str(e))
            raise  # Re-raise for incremental ingestion

    def get_ingestion_status(self, repo: str) -> IngestionStatus:
        """
        Get the latest ingestion status for a repository.
        
        Args:
            repo: Repository full name (owner/repo)
            
        Returns:
            IngestionStatus for the most recent run
            
        Raises:
            HTTPException: 404 if no runs found for repo
        """
        conn = psycopg2.connect(**self.pg_cfg)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, repo, triggered_by, started_at, completed_at,
                           files_processed, chunks_created, embeddings_created,
                           services_detected, status, error_message, commit_sha
                    FROM meta.ingestion_runs
                    WHERE repo = %s
                    ORDER BY started_at DESC
                    LIMIT 1
                    """,
                    (repo,),
                )
                row = cur.fetchone()
                if not row:
                    raise HTTPException(
                        status_code=404,
                        detail=f"No ingestion runs found for repo {repo}",
                    )
                
                return IngestionStatus(
                    run_id=row[0],
                    repo=row[1],
                    triggered_by=row[2],
                    started_at=row[3],
                    completed_at=row[4],
                    files_processed=row[5],
                    chunks_created=row[6],
                    embeddings_created=row[7],
                    services_detected=row[8],
                    status=row[9],
                    error_message=row[10],
                    commit_sha=row[11],
                )
        finally:
            conn.close()

    async def _start_run(
        self,
        run_id: str,
        repo: str,
        triggered_by: str,
        commit_sha: Optional[str],
    ) -> None:
        """
        Insert a new ingestion run record with status='running'.
        
        Args:
            run_id: UUID for this run (used as the id value)
            repo: Repository full name
            triggered_by: Source of trigger
            commit_sha: Optional commit SHA
        """
        conn = psycopg2.connect(**self.pg_cfg)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO meta.ingestion_runs
                    (id, repo, triggered_by, started_at, status, commit_sha)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        run_id,
                        repo,
                        triggered_by,
                        datetime.now(timezone.utc),
                        "running",
                        commit_sha,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    async def _complete_run(
        self,
        run_id: str,
        files_processed: int,
        chunks_created: int,
        embeddings_created: int,
        services_detected: int,
    ) -> None:
        """
        Update ingestion run with success status and final counters.
        
        Args:
            run_id: UUID of the run
            files_processed: Total files processed
            chunks_created: Total chunks created
            embeddings_created: Total embeddings created
            services_detected: Total services detected
        """
        conn = psycopg2.connect(**self.pg_cfg)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE meta.ingestion_runs
                    SET status = %s,
                        completed_at = %s,
                        files_processed = %s,
                        chunks_created = %s,
                        embeddings_created = %s,
                        services_detected = %s
                    WHERE id = %s
                    """,
                    (
                        "success",
                        datetime.now(timezone.utc),
                        files_processed,
                        chunks_created,
                        embeddings_created,
                        services_detected,
                        run_id,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    async def _fail_run(self, run_id: str, error_message: str) -> None:
        """
        Update ingestion run with failed status and error message.
        
        Args:
            run_id: UUID of the run
            error_message: Error description
        """
        conn = psycopg2.connect(**self.pg_cfg)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE meta.ingestion_runs
                    SET status = %s,
                        completed_at = %s,
                        error_message = %s
                    WHERE id = %s
                    """,
                    (
                        "failed",
                        datetime.now(timezone.utc),
                        error_message,
                        run_id,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    async def _emit_completion_event(
        self,
        repo: str,
        run_id: str,
        files_processed: int,
        chunks_created: int,
        embeddings_created: int,
        services_detected: int,
        duration_seconds: float,
        status: str,
        triggered_by: str,
    ) -> None:
        """
        Produce repo.ingestion.complete Kafka event.
        
        Uses exact schema from Appendix C of requirements document.
        Includes services_detected field.
        
        Args:
            repo: Repository full name
            run_id: UUID of the run
            files_processed: Total files processed
            chunks_created: Total chunks created
            embeddings_created: Total embeddings created
            services_detected: Total services detected
            duration_seconds: Total duration
            status: "success" or "failed"
            triggered_by: Source of trigger
        """
        import json
        
        event = {
            "repo": repo,
            "run_id": run_id,
            "files_processed": files_processed,
            "chunks_created": chunks_created,
            "embeddings_created": embeddings_created,
            "services_detected": services_detected,
            "duration_seconds": duration_seconds,
            "status": status,
            "triggered_at": datetime.now(timezone.utc).isoformat(),
        }
        
        try:
            producer = self._get_producer()
            producer.send("repo.ingestion.complete", value=event)
            producer.flush()
            log.info(f"[{run_id}] Emitted repo.ingestion.complete event")
        except Exception as e:
            log.error(f"[{run_id}] Failed to emit completion event: {e}")

    async def _record_ingestion_snapshot(self, repo: str, run_id: str, services_detected: int) -> None:
        """
        Persist one architecture snapshot row for successful ingestion runs.

        This is intentionally non-fatal: ingestion success should not be rolled back
        if snapshot recording fails.
        """
        snapshot_id = f"ingestion_{repo.replace('/', '_')}_{run_id}"

        conn = psycopg2.connect(**self.pg_cfg)
        try:
            with conn.cursor() as cur:
                # Ensure table exists in environments where time-travel schema wasn't initialized.
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS meta.architecture_snapshots (
                        snapshot_id TEXT PRIMARY KEY,
                        repo TEXT NOT NULL,
                        timestamp TIMESTAMPTZ NOT NULL,
                        nodes JSONB NOT NULL DEFAULT '[]',
                        edges JSONB NOT NULL DEFAULT '[]',
                        metrics JSONB,
                        health_score NUMERIC(6,4),
                        drift_score NUMERIC(6,4),
                        node_ids JSONB,
                        edge_count INTEGER DEFAULT 0,
                        services_count INTEGER DEFAULT 0,
                        event_type TEXT DEFAULT 'ingestion',
                        event_payload JSONB,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )

                # Backward-compatible column upgrades for older table shapes.
                cur.execute("ALTER TABLE meta.architecture_snapshots ADD COLUMN IF NOT EXISTS node_ids JSONB")
                cur.execute("ALTER TABLE meta.architecture_snapshots ADD COLUMN IF NOT EXISTS edge_count INTEGER DEFAULT 0")
                cur.execute("ALTER TABLE meta.architecture_snapshots ADD COLUMN IF NOT EXISTS services_count INTEGER DEFAULT 0")
                cur.execute("ALTER TABLE meta.architecture_snapshots ADD COLUMN IF NOT EXISTS event_type TEXT")
                cur.execute("ALTER TABLE meta.architecture_snapshots ADD COLUMN IF NOT EXISTS event_payload JSONB")
                cur.execute("ALTER TABLE meta.architecture_snapshots ADD COLUMN IF NOT EXISTS nodes JSONB DEFAULT '[]'::jsonb")
                cur.execute("ALTER TABLE meta.architecture_snapshots ADD COLUMN IF NOT EXISTS edges JSONB DEFAULT '[]'::jsonb")
                cur.execute("ALTER TABLE meta.architecture_snapshots ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()")

                cur.execute(
                    """
                    SELECT COALESCE(jsonb_agg(node_id), '[]'::jsonb), COUNT(*)
                    FROM meta.graph_nodes
                    WHERE repo = %s AND node_type = 'service'
                    """,
                    (repo,),
                )
                row = cur.fetchone() or ([], 0)
                node_ids = row[0] if row[0] is not None else []
                service_count = int(row[1] or services_detected or 0)

                cur.execute(
                    """
                    INSERT INTO meta.architecture_snapshots
                    (snapshot_id, repo, timestamp, node_ids, edge_count, services_count,
                     event_type, nodes, edges, created_at)
                    VALUES (%s, %s, NOW(), %s::jsonb, %s, %s, %s, %s::jsonb, %s::jsonb, NOW())
                    ON CONFLICT (snapshot_id) DO NOTHING
                    """,
                    (
                        snapshot_id,
                        repo,
                        json.dumps(node_ids),
                        0,
                        service_count,
                        "ingestion",
                        json.dumps([]),
                        json.dumps([]),
                    ),
                )

            conn.commit()
            log.info(f"[{run_id}] Recorded ingestion snapshot {snapshot_id}")
        except Exception as e:
            log.warning(f"[{run_id}] Failed to record ingestion snapshot: {e}")
        finally:
            conn.close()
