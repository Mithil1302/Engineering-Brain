"""
retry_worker.py — Emit retry orchestration for the policy pipeline.

EmitRetryWorker acquires queued emit-retry jobs from the DB, attempts
re-emission via KafkaEmitter, and handles back-off and dead-lettering.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from .kafka_emitter import KafkaEmitter
from .event_store import EventStore


class EmitRetryWorker:
    """
    Processes queued emit-retry jobs stored in meta.jobs.

    Depends on:
      - EventStore  — acquires / marks / dead-letters retry rows
      - KafkaEmitter — re-emits the event
    """

    def __init__(
        self,
        *,
        event_store: EventStore,
        emitter: KafkaEmitter,
        db_conn_func: Callable,
        enabled: bool = True,
        batch_size: int = 25,
        max_attempts: int = 5,
        backoff_seconds: int = 10,
        on_state_update: Optional[Callable[[str, int], None]] = None,
        on_error: Optional[Callable[[str, Exception], None]] = None,
    ) -> None:
        self._event_store = event_store
        self._emitter = emitter
        self._db_conn = db_conn_func
        self.enabled = enabled
        self.batch_size = batch_size
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds
        # Optional callbacks so the worker can update pipeline state counters
        self._on_state_update = on_state_update or (lambda key, delta: None)
        self._on_error = on_error or (lambda msg, exc: None)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_jobs(self) -> None:
        """Acquire a batch of queued retry jobs and attempt to re-emit each."""
        if not self.enabled:
            return

        with self._db_conn() as conn:
            conn.autocommit = False
            jobs = self._event_store._acquire_retry_jobs(conn, self.batch_size)
            conn.commit()

        for row in jobs:
            self._process_one(row)

    # ------------------------------------------------------------------
    # Job queuing (called by pipeline._handle_message on emit failure)
    # ------------------------------------------------------------------

    def queue_job(
        self,
        conn,
        *,
        emit_type: str,
        base_idempotency_key: str,
        repo: str,
        pr_number: int,
        correlation_id: Optional[str],
        event_payload: Dict[str, Any],
        error: str,
    ) -> bool:
        """Insert an emit-retry job into meta.jobs (idempotent)."""
        retry_key = self._retry_key(
            emit_type=emit_type,
            base_idempotency_key=base_idempotency_key,
            repo=repo,
            pr_number=pr_number,
        )
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO meta.jobs
                    (job_type, idempotency_key, correlation_id, status, payload, created_at, updated_at)
                VALUES (%s, %s, %s, 'queued', %s::jsonb, NOW(), NOW())
                ON CONFLICT (idempotency_key) DO NOTHING
                RETURNING id
                """,
                (
                    "emit_retry",
                    retry_key,
                    correlation_id,
                    json.dumps(
                        {
                            "emit_type": emit_type,
                            "repo": repo,
                            "pr_number": pr_number,
                            "base_idempotency_key": base_idempotency_key,
                            "attempt": 0,
                            "max_attempts": self.max_attempts,
                            "next_attempt_at": datetime.now(timezone.utc).isoformat(),
                            "error": error,
                            "event_payload": event_payload,
                            "queued_at": datetime.now(timezone.utc).isoformat(),
                        }
                    ),
                ),
            )
            row = cur.fetchone()
        return row is not None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _retry_key(*, emit_type: str, base_idempotency_key: str, repo: str, pr_number: int) -> str:
        return f"emit-retry:{emit_type}:{repo}:{pr_number}:{base_idempotency_key}"

    @staticmethod
    def _parse_iso_dt(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(text)
        except Exception:
            return None

    def _due_for_retry(self, payload: Dict[str, Any]) -> bool:
        due = self._parse_iso_dt(payload.get("next_attempt_at"))
        if due is None:
            return True
        return datetime.now(timezone.utc) >= due

    def _process_one(self, row: Dict[str, Any]) -> None:
        """Handle a single retry job row: re-emit or back-off or dead-letter."""
        payload = row.get("payload") or {}

        if not self._due_for_retry(payload):
            # Put back to queued — not ready yet
            with self._db_conn() as conn:
                conn.autocommit = False
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE meta.jobs SET status = 'queued', updated_at = NOW() WHERE id = %s",
                        (row.get("id"),),
                    )
                conn.commit()
            return

        emit_type = str(payload.get("emit_type") or "")
        event_payload = payload.get("event_payload") or {}
        repo = str(payload.get("repo") or "")
        pr_number = int(payload.get("pr_number") or 0)
        base_idem = str(payload.get("base_idempotency_key") or "")
        attempt = int(payload.get("attempt") or 0)
        max_attempts = int(payload.get("max_attempts") or self.max_attempts)

        try:
            self._emitter.emit_by_type(emit_type, event_payload)
            # Success
            with self._db_conn() as conn:
                conn.autocommit = False
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE meta.jobs SET status = 'completed', updated_at = NOW() WHERE id = %s",
                        (row.get("id"),),
                    )
                self._event_store._mark_emit_status_by_idempotency(
                    conn,
                    emit_type=emit_type,
                    repo=repo,
                    pr_number=pr_number,
                    idempotency_key=base_idem,
                    status="emitted",
                    error=None,
                )
                conn.commit()
            self._on_state_update("processed_retry_jobs", 1)
            self._on_state_update("retry_emit_success", 1)

        except Exception as exc:
            next_attempt = attempt + 1
            err_text = str(exc)
            with self._db_conn() as conn:
                conn.autocommit = False
                if next_attempt >= max_attempts:
                    # Dead-letter
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE meta.jobs SET status = 'dead_letter', payload = %s::jsonb, updated_at = NOW() WHERE id = %s",
                            (
                                json.dumps(
                                    {
                                        **payload,
                                        "attempt": next_attempt,
                                        "last_error": err_text,
                                        "dead_lettered_at": datetime.now(timezone.utc).isoformat(),
                                    }
                                ),
                                row.get("id"),
                            ),
                        )
                    self._event_store._mark_emit_status_by_idempotency(
                        conn,
                        emit_type=emit_type,
                        repo=repo,
                        pr_number=pr_number,
                        idempotency_key=base_idem,
                        status="failed",
                        error=err_text,
                    )
                    self._event_store._dead_letter_emit_retry(conn, row=row, error=err_text, attempts=next_attempt)
                    self._on_state_update("dead_lettered_retry_jobs", 1)
                else:
                    # Reschedule with backoff
                    retry_payload = {
                        **payload,
                        "attempt": next_attempt,
                        "last_error": err_text,
                        "next_attempt_at": (
                            datetime.now(timezone.utc)
                            + timedelta(seconds=self.backoff_seconds * next_attempt)
                        ).isoformat(),
                    }
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE meta.jobs SET status = 'queued', payload = %s::jsonb, updated_at = NOW() WHERE id = %s",
                            (json.dumps(retry_payload), row.get("id")),
                        )
                conn.commit()
            self._on_state_update("processed_retry_jobs", 1)
            self._on_state_update("retry_emit_failures", 1)
            self._on_error("emit retry job failed", exc)
