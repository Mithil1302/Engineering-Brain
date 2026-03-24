from __future__ import annotations

import json
import logging
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timezone
from psycopg2.extras import RealDictCursor

class EventStore:
    def __init__(
        self,
        db_conn_func,
        *,
        rule_set: str = "rules-v1",
        ensure_schema: Callable[[], None] = lambda: None,
        emit_retry_idempotency_key_fn: Optional[Callable[..., str]] = None,
    ):
        self._db_conn = db_conn_func
        self.log = logging.getLogger('worker-service')
        self.rule_set = rule_set
        self._ensure_schema = ensure_schema
        self._emit_retry_idempotency_key_fn = emit_retry_idempotency_key_fn

    def _register_processed_event(
        self,
        conn,
        *,
        event_key: str,
        source_topic: str,
        source_partition: int,
        source_offset: str,
        correlation_id: Optional[str],
        payload: Dict[str, Any],
    ) -> bool:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO meta.processed_events (
                  event_key, source_topic, source_partition, source_offset, correlation_id, payload, first_seen_at
                ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,NOW())
                ON CONFLICT (event_key) DO NOTHING
                RETURNING id
                """,
                (
                    event_key,
                    source_topic,
                    int(source_partition),
                    source_offset,
                    correlation_id,
                    json.dumps(payload),
                ),
            )
            row = cur.fetchone()
        return row is not None

    def _acquire_retry_jobs(self, conn, limit: int) -> List[Dict[str, Any]]:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                WITH picked AS (
                  SELECT id
                  FROM meta.jobs
                  WHERE job_type = 'emit_retry'
                    AND status = 'queued'
                  ORDER BY id ASC
                  LIMIT %s
                  FOR UPDATE SKIP LOCKED
                )
                UPDATE meta.jobs j
                SET status = 'processing', updated_at = NOW()
                FROM picked
                WHERE j.id = picked.id
                RETURNING j.*
                """,
                (limit,),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def _mark_emit_status_by_idempotency(
        self,
        conn,
        *,
        emit_type: str,
        repo: str,
        pr_number: int,
        idempotency_key: str,
        status: str,
        error: Optional[str],
    ):
        table_by_type = {
            "policy_check": "policy_check_runs",
            "doc_refresh": "doc_refresh_jobs",
            "doc_rewrite": "doc_rewrite_runs",
        }
        table = table_by_type.get(emit_type)
        if not table:
            return
        with conn.cursor() as cur:
            cur.execute(
                f"""
                WITH target AS (
                  SELECT id
                  FROM meta.{table}
                  WHERE repo = %s
                    AND pr_number = %s
                    AND idempotency_key = %s
                  ORDER BY id DESC
                  LIMIT 1
                )
                UPDATE meta.{table}
                SET emit_status = %s,
                    emit_error = %s
                WHERE id IN (SELECT id FROM target)
                """,
                (repo, pr_number, idempotency_key, status, error),
            )

    def _dead_letter_emit_retry(
        self,
        conn,
        *,
        row: Dict[str, Any],
        error: str,
        attempts: int,
    ):
        payload = row.get("payload") or {}
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO meta.poison_pills (
                  source_topic, source_partition, source_offset, error, attempts, payload_raw,
                  correlation_id, idempotency_key, status, requeue_count, created_at, updated_at
                ) VALUES (
                  %s,%s,%s,%s,%s,%s,%s,%s,'quarantined',0,NOW(),NOW()
                )
                """,
                (
                    "internal.emit_retry",
                    -1,
                    str(row.get("id")),
                    error,
                    int(attempts),
                    json.dumps(payload),
                    row.get("correlation_id"),
                    row.get("idempotency_key"),
                ),
            )

    def _upsert_comment_state(self, conn, repo: str, pr_number: int, fingerprint: str):
        comment_key = f"{repo}:{pr_number}:{self.rule_set}"
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, latest_fingerprint, delivery_count
                FROM meta.pr_comment_state
                WHERE comment_key = %s
                """,
                (comment_key,),
            )
            row = cur.fetchone()

            if row is None:
                cur.execute(
                    """
                    INSERT INTO meta.pr_comment_state (comment_key, repo, pr_number, rule_set, latest_fingerprint, delivery_count, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, 1, NOW(), NOW())
                    RETURNING id
                    """,
                    (comment_key, repo, pr_number, self.rule_set, fingerprint),
                )
                state_id = cur.fetchone()["id"]
                return state_id, comment_key, "create_comment", False

            if row["latest_fingerprint"] == fingerprint:
                cur.execute(
                    """
                    UPDATE meta.pr_comment_state
                    SET updated_at = NOW()
                    WHERE id = %s
                    """,
                    (row["id"],),
                )
                return row["id"], comment_key, "noop", True

            cur.execute(
                """
                UPDATE meta.pr_comment_state
                SET latest_fingerprint = %s,
                    delivery_count = delivery_count + 1,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (fingerprint, row["id"]),
            )
            return row["id"], comment_key, "update_comment", False

    def _persist_check_run(
        self,
        conn,
        request: Any,
        response_payload: Dict[str, Any],
        merge_gate: Dict[str, Any],
        doc_refresh_plan: Dict[str, Any],
        knowledge_health: Dict[str, Any],
        idempotency_key: str,
        action: str,
        deduped: bool,
        comment_state_id: int,
    ) -> int:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO meta.policy_check_runs (
                    repo,
                    pr_number,
                    correlation_id,
                    idempotency_key,
                    summary_status,
                    findings,
                    markdown_comment,
                    suggested_patches,
                    check_annotations,
                    merge_gate,
                    doc_refresh_plan,
                    knowledge_health,
                    emit_status,
                    emit_error,
                    action,
                    deduped,
                    comment_state_id,
                    created_at
                ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s,NOW())
                RETURNING id
                """,
                (
                    request.repo,
                    request.pr_number,
                    request.correlation_id,
                    idempotency_key,
                    response_payload.get("summary_status"),
                    json.dumps(response_payload.get("findings", [])),
                    response_payload.get("markdown_comment"),
                    json.dumps(response_payload.get("suggested_patches", [])),
                    json.dumps(response_payload.get("check_annotations", [])),
                    json.dumps(merge_gate),
                    json.dumps(doc_refresh_plan),
                    json.dumps(knowledge_health),
                    "pending",
                    None,
                    action,
                    deduped,
                    comment_state_id,
                ),
            )
            row = cur.fetchone()
        return int(row[0])

    def _persist_knowledge_health_snapshot(
        self,
        conn,
        request: Any,
        idempotency_key: str,
        selected_rule_set: str,
        summary_status: str,
        knowledge_health: Dict[str, Any],
    ):
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO meta.knowledge_health_snapshots (
                  repo, pr_number, correlation_id, idempotency_key, rule_set, summary_status, score, grade, snapshot, created_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,NOW())
                """,
                (
                    request.repo,
                    request.pr_number,
                    request.correlation_id,
                    idempotency_key,
                    selected_rule_set,
                    summary_status,
                    float(knowledge_health.get("score") or 0.0),
                    str(knowledge_health.get("grade") or "F"),
                    json.dumps(knowledge_health),
                ),
            )

    def _persist_doc_refresh_job(
        self,
        conn,
        request: Any,
        idempotency_key: str,
        selected_rule_set: str,
        action: str,
        doc_refresh_plan: Dict[str, Any],
                ) -> int:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO meta.doc_refresh_jobs (
                                    repo, pr_number, correlation_id, idempotency_key, rule_set, action, decision, priority, plan, emit_status, emit_error, created_at
                                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,NOW())
                                RETURNING id
                """,
                (
                    request.repo,
                    request.pr_number,
                    request.correlation_id,
                    idempotency_key,
                    selected_rule_set,
                    action,
                    str(doc_refresh_plan.get("decision") or "not_needed"),
                    str(doc_refresh_plan.get("priority") or "low"),
                    json.dumps(doc_refresh_plan),
                    "pending",
                    None,
                ),
            )
            row = cur.fetchone()
        return int(row[0])

    def _persist_doc_rewrite_run(
        self,
        conn,
        *,
        request: Any,
        idempotency_key: str,
        selected_rule_set: str,
        status: str,
        reason: str,
        quality_gate_score: float,
        bundle: Dict[str, Any],
        emitted_event: Optional[Dict[str, Any]] = None,
    ) -> int:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO meta.doc_rewrite_runs (
                  repo, pr_number, correlation_id, idempotency_key, rule_set,
                                    status, reason, quality_gate_score, bundle, emitted_event, emit_status, emit_error,
                  created_at, updated_at
                                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,NOW(),NOW())
                RETURNING id
                """,
                (
                    request.repo,
                    request.pr_number,
                    request.correlation_id,
                    idempotency_key,
                    selected_rule_set,
                    status,
                    reason,
                    quality_gate_score,
                    json.dumps(bundle),
                    json.dumps(emitted_event or {}),
                    "pending",
                    None,
                ),
            )
            row = cur.fetchone()
        return int(row[0])

    def _update_emit_status(self, conn, *, table: str, row_id: int, status: str, error: Optional[str] = None):
        if table not in {"policy_check_runs", "doc_refresh_jobs", "doc_rewrite_runs"}:
            raise ValueError(f"unsupported emit status table: {table}")
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE meta.{table} SET emit_status = %s, emit_error = %s WHERE id = %s",
                (status, error, row_id),
            )

    def requeue_emit_retry_dead_letter(
        self,
        *,
        poison_id: int,
        reset_attempt: bool = True,
    ) -> Dict[str, Any]:
        self._ensure_schema()
        with self._db_conn() as conn:
            conn.autocommit = False
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM meta.poison_pills WHERE id = %s FOR UPDATE",
                    (poison_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise ValueError("poison pill not found")

                if row.get("source_topic") != "internal.emit_retry":
                    raise ValueError("poison pill is not an emit_retry dead-letter")

                payload_raw = row.get("payload_raw") or "{}"
                payload = json.loads(payload_raw)

                if reset_attempt:
                    payload["attempt"] = 0
                payload["next_attempt_at"] = datetime.now(timezone.utc).isoformat()

                idem_key = str(row.get("idempotency_key") or "")
                if not idem_key:
                    emit_type = str(payload.get("emit_type") or "unknown")
                    repo = str(payload.get("repo") or "unknown")
                    pr_number = int(payload.get("pr_number") or 0)
                    base = str(payload.get("base_idempotency_key") or f"poison:{poison_id}")
                    if self._emit_retry_idempotency_key_fn:
                        idem_key = self._emit_retry_idempotency_key_fn(
                            emit_type=emit_type,
                            base_idempotency_key=base,
                            repo=repo,
                            pr_number=pr_number,
                        )
                    else:
                        idem_key = f"emit-retry:{emit_type}:{repo}:{pr_number}:{base}"

                cur.execute(
                    """
                    INSERT INTO meta.jobs (job_type, idempotency_key, correlation_id, status, payload, created_at, updated_at)
                    VALUES ('emit_retry', %s, %s, 'queued', %s::jsonb, NOW(), NOW())
                    ON CONFLICT (idempotency_key)
                    DO UPDATE SET
                        status = 'queued',
                        payload = EXCLUDED.payload,
                        updated_at = NOW()
                    RETURNING id, status
                    """,
                    (idem_key, row.get("correlation_id"), json.dumps(payload)),
                )
                job_row = cur.fetchone()

                cur.execute(
                    """
                    UPDATE meta.poison_pills
                    SET status = 'requeued',
                        requeue_count = requeue_count + 1,
                        requeued_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                    RETURNING id, status, requeue_count, requeued_at
                    """,
                    (poison_id,),
                )
                poison_row = cur.fetchone()
            conn.commit()

        return {
            "poison_pill": dict(poison_row),
            "job": dict(job_row),
        }

