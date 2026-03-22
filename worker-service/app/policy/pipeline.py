from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import psycopg2
from kafka import KafkaConsumer, KafkaProducer
from psycopg2.extras import RealDictCursor

from .engine import evaluate_policies_with_meta, resolve_policy_pack, summary_status
from .models import (
    ChangedFile,
    EndpointSpec,
    ImpactEdge,
    PolicyConfig,
    PolicyEvaluationRequest,
    ServiceSpec,
)
from .merge_gate import build_merge_gate_decision
from .doc_refresh import build_doc_refresh_plan
from .doc_rewrite import build_doc_rewrite_bundle
from .health_score import build_knowledge_health_score
from .patches import build_suggested_patches
from .renderer import assemble_response


class PolicyPipeline:
    def __init__(self, logger):
        self.log = logger
        self.enabled = os.getenv("POLICY_PIPELINE_ENABLED", "true").lower() == "true"
        self.kafka_brokers = [b.strip() for b in os.getenv("KAFKA_BROKERS", "kafka:9092").split(",") if b.strip()]
        self.consumer_topic = os.getenv("POLICY_INPUT_TOPIC", "repo.events")
        self.output_topic = os.getenv("POLICY_OUTPUT_TOPIC", "pr.checks")
        self.docs_refresh_topic = os.getenv("POLICY_DOC_REFRESH_TOPIC", "docs.refresh")
        self.docs_rewrite_topic = os.getenv("POLICY_DOC_REWRITE_TOPIC", "docs.rewrite")
        self.consumer_group = os.getenv("POLICY_CONSUMER_GROUP", "worker-policy-checks-v1")
        self.rule_set = os.getenv("POLICY_RULE_SET", "rules-v1")
        self.default_service_id = os.getenv("POLICY_DEFAULT_SERVICE_ID", "unknown-service")
        self.doc_refresh_enabled = os.getenv("POLICY_DOC_REFRESH_ENABLED", "true").lower() == "true"
        self.doc_rewrite_enabled = os.getenv("POLICY_DOC_REWRITE_ENABLED", "true").lower() == "true"
        self.doc_rewrite_min_health_score = float(os.getenv("POLICY_DOC_REWRITE_MIN_HEALTH_SCORE", "20.0"))
        self.fail_blocks_merge = os.getenv("POLICY_FAIL_BLOCKS_MERGE", "true").lower() == "true"
        self.warn_blocks_merge = os.getenv("POLICY_WARN_BLOCKS_MERGE", "false").lower() == "true"
        self.health_weight_policy = float(os.getenv("POLICY_HEALTH_WEIGHT_POLICY", "0.45"))
        self.health_weight_docs = float(os.getenv("POLICY_HEALTH_WEIGHT_DOCS", "0.35"))
        self.health_weight_ownership = float(os.getenv("POLICY_HEALTH_WEIGHT_OWNERSHIP", "0.20"))
        self.policy_admin_token = os.getenv("POLICY_ADMIN_TOKEN", "").strip()
        self.emit_retry_enabled = os.getenv("POLICY_EMIT_RETRY_ENABLED", "true").lower() == "true"
        self.emit_retry_batch_size = int(os.getenv("POLICY_EMIT_RETRY_BATCH_SIZE", "25"))
        self.emit_retry_max_attempts = int(os.getenv("POLICY_EMIT_RETRY_MAX_ATTEMPTS", "5"))
        self.emit_retry_backoff_seconds = int(os.getenv("POLICY_EMIT_RETRY_BACKOFF_SECONDS", "10"))

        self.pg_cfg = {
            "host": os.getenv("POSTGRES_HOST", "postgres"),
            "port": int(os.getenv("POSTGRES_PORT", "5432")),
            "user": os.getenv("POSTGRES_USER", "brain"),
            "password": os.getenv("POSTGRES_PASSWORD", "brain"),
            "dbname": os.getenv("POSTGRES_DB", "brain"),
        }

        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.consumer: Optional[KafkaConsumer] = None
        self.producer: Optional[KafkaProducer] = None

        self.state: Dict[str, Any] = {
            "enabled": self.enabled,
            "running": False,
            "processed_events": 0,
            "emitted_checks": 0,
            "deduped_checks": 0,
            "replay_skipped_events": 0,
            "emitted_doc_refresh": 0,
            "emitted_doc_rewrite": 0,
            "emitted_health_snapshots": 0,
            "emit_failures": 0,
            "queued_emit_retries": 0,
            "processed_retry_jobs": 0,
            "retry_emit_success": 0,
            "retry_emit_failures": 0,
            "dead_lettered_retry_jobs": 0,
            "skipped_events": 0,
            "last_error": None,
            "last_processed_at": None,
        }

        # Fail fast on unsupported policy pack to avoid ambiguous runtime behavior.
        resolve_policy_pack(self.rule_set)

    def _db_conn(self):
        return psycopg2.connect(**self.pg_cfg)

    @staticmethod
    def _stable_payload_hash(payload: Dict[str, Any]) -> str:
        raw = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _event_dedup_key(self, payload: Dict[str, Any], request: PolicyEvaluationRequest, selected_rule_set: str) -> str:
        event_idempotency = payload.get("idempotency_key") or self._stable_payload_hash(payload)
        return f"policy:{request.repo}:{request.pr_number}:{selected_rule_set}:{event_idempotency}"

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

    @staticmethod
    def _emit_retry_idempotency_key(*, emit_type: str, base_idempotency_key: str, repo: str, pr_number: int) -> str:
        return f"emit-retry:{emit_type}:{repo}:{pr_number}:{base_idempotency_key}"

    def _queue_emit_retry_job(
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
        retry_key = self._emit_retry_idempotency_key(
            emit_type=emit_type,
            base_idempotency_key=base_idempotency_key,
            repo=repo,
            pr_number=pr_number,
        )
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO meta.jobs (job_type, idempotency_key, correlation_id, status, payload, created_at, updated_at)
                VALUES (%s,%s,%s,'queued',%s::jsonb,NOW(),NOW())
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
                            "max_attempts": self.emit_retry_max_attempts,
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

    @staticmethod
    def _parse_iso_dt(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        text = str(value).strip()
        if not text:
            return None
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

    def _emit_by_type(self, emit_type: str, event_payload: Dict[str, Any]):
        if emit_type == "policy_check":
            self._emit_check_event(event_payload)
            return
        if emit_type == "doc_refresh":
            self._emit_doc_refresh_event(event_payload)
            return
        if emit_type == "doc_rewrite":
            self._emit_doc_rewrite_event(event_payload)
            return
        raise ValueError(f"unsupported emit_type for retry: {emit_type}")

    def _process_emit_retry_jobs(self):
        if not self.emit_retry_enabled:
            return

        with self._db_conn() as conn:
            conn.autocommit = False
            jobs = self._acquire_retry_jobs(conn, self.emit_retry_batch_size)
            conn.commit()

        for row in jobs:
            payload = row.get("payload") or {}
            if not self._due_for_retry(payload):
                with self._db_conn() as conn:
                    conn.autocommit = False
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE meta.jobs SET status = 'queued', updated_at = NOW() WHERE id = %s",
                            (row.get("id"),),
                        )
                    conn.commit()
                continue

            emit_type = str(payload.get("emit_type") or "")
            event_payload = payload.get("event_payload") or {}
            repo = str(payload.get("repo") or "")
            pr_number = int(payload.get("pr_number") or 0)
            base_idem = str(payload.get("base_idempotency_key") or "")
            attempt = int(payload.get("attempt") or 0)
            max_attempts = int(payload.get("max_attempts") or self.emit_retry_max_attempts)

            try:
                self._emit_by_type(emit_type, event_payload)
                with self._db_conn() as conn:
                    conn.autocommit = False
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE meta.jobs SET status = 'completed', updated_at = NOW() WHERE id = %s",
                            (row.get("id"),),
                        )
                    self._mark_emit_status_by_idempotency(
                        conn,
                        emit_type=emit_type,
                        repo=repo,
                        pr_number=pr_number,
                        idempotency_key=base_idem,
                        status="emitted",
                        error=None,
                    )
                    conn.commit()
                self.state["processed_retry_jobs"] += 1
                self.state["retry_emit_success"] += 1
            except Exception as exc:
                next_attempt = attempt + 1
                err_text = str(exc)
                with self._db_conn() as conn:
                    conn.autocommit = False
                    if next_attempt >= max_attempts:
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
                        self._mark_emit_status_by_idempotency(
                            conn,
                            emit_type=emit_type,
                            repo=repo,
                            pr_number=pr_number,
                            idempotency_key=base_idem,
                            status="failed",
                            error=err_text,
                        )
                        self._dead_letter_emit_retry(conn, row=row, error=err_text, attempts=next_attempt)
                        self.state["dead_lettered_retry_jobs"] += 1
                    else:
                        retry_payload = {
                            **payload,
                            "attempt": next_attempt,
                            "last_error": err_text,
                            "next_attempt_at": (datetime.now(timezone.utc) + timedelta(seconds=self.emit_retry_backoff_seconds * next_attempt)).isoformat(),
                        }
                        with conn.cursor() as cur:
                            cur.execute(
                                "UPDATE meta.jobs SET status = 'queued', payload = %s::jsonb, updated_at = NOW() WHERE id = %s",
                                (json.dumps(retry_payload), row.get("id")),
                            )
                    conn.commit()
                self.state["processed_retry_jobs"] += 1
                self.state["retry_emit_failures"] += 1
                self._log_error("emit retry job failed", exc)

    def _ensure_schema(self):
        with self._db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE SCHEMA IF NOT EXISTS meta;
                                CREATE TABLE IF NOT EXISTS meta.processed_events (
                                    id BIGSERIAL PRIMARY KEY,
                                    event_key TEXT NOT NULL UNIQUE,
                                    source_topic TEXT NOT NULL,
                                    source_partition INT NOT NULL,
                                    source_offset TEXT NOT NULL,
                                    correlation_id TEXT,
                                    payload JSONB,
                                    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                                );

                                CREATE INDEX IF NOT EXISTS idx_processed_events_first_seen ON meta.processed_events (first_seen_at DESC);

                    ALTER TABLE IF EXISTS meta.policy_check_runs
                      ADD COLUMN IF NOT EXISTS merge_gate JSONB;
                                ALTER TABLE IF EXISTS meta.policy_check_runs
                                    ADD COLUMN IF NOT EXISTS emit_status TEXT NOT NULL DEFAULT 'pending';
                                ALTER TABLE IF EXISTS meta.policy_check_runs
                                    ADD COLUMN IF NOT EXISTS emit_error TEXT;
                                        ALTER TABLE IF EXISTS meta.policy_check_runs
                                            ADD COLUMN IF NOT EXISTS doc_refresh_plan JSONB;
                                        ALTER TABLE IF EXISTS meta.policy_check_runs
                                            ADD COLUMN IF NOT EXISTS knowledge_health JSONB;

                                        CREATE TABLE IF NOT EXISTS meta.doc_refresh_jobs (
                                            id BIGSERIAL PRIMARY KEY,
                                            repo TEXT NOT NULL,
                                            pr_number BIGINT NOT NULL,
                                            correlation_id TEXT,
                                            idempotency_key TEXT,
                                            rule_set TEXT,
                                            action TEXT NOT NULL,
                                            decision TEXT NOT NULL,
                                            priority TEXT,
                                            plan JSONB NOT NULL,
                                            emit_status TEXT NOT NULL DEFAULT 'pending',
                                            emit_error TEXT,
                                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                                        );

                                        CREATE TABLE IF NOT EXISTS meta.knowledge_health_snapshots (
                                            id BIGSERIAL PRIMARY KEY,
                                            repo TEXT NOT NULL,
                                            pr_number BIGINT,
                                            correlation_id TEXT,
                                            idempotency_key TEXT,
                                            rule_set TEXT,
                                            summary_status TEXT,
                                            score NUMERIC(6,2) NOT NULL,
                                            grade TEXT NOT NULL,
                                            snapshot JSONB NOT NULL,
                                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                                        );

                                        CREATE TABLE IF NOT EXISTS meta.policy_templates (
                                            id BIGSERIAL PRIMARY KEY,
                                            template_name TEXT NOT NULL,
                                            scope_type TEXT NOT NULL,
                                            scope_value TEXT NOT NULL,
                                            rule_pack TEXT,
                                            rules JSONB NOT NULL DEFAULT '{}'::jsonb,
                                            fail_blocks_merge BOOLEAN NOT NULL DEFAULT TRUE,
                                            warn_blocks_merge BOOLEAN NOT NULL DEFAULT FALSE,
                                            no_docs_no_merge BOOLEAN NOT NULL DEFAULT FALSE,
                                            metadata JSONB,
                                            enabled BOOLEAN NOT NULL DEFAULT TRUE,
                                            priority INT NOT NULL DEFAULT 100,
                                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                                            UNIQUE (scope_type, scope_value, template_name)
                                        );

                                        CREATE TABLE IF NOT EXISTS meta.policy_waivers (
                                            id BIGSERIAL PRIMARY KEY,
                                            repo TEXT NOT NULL,
                                            pr_number BIGINT NOT NULL,
                                            rule_set TEXT NOT NULL,
                                            requested_by TEXT NOT NULL,
                                            requested_role TEXT NOT NULL,
                                            reason TEXT NOT NULL,
                                            status TEXT NOT NULL DEFAULT 'pending',
                                            expires_at TIMESTAMPTZ NOT NULL,
                                            requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                                            decided_at TIMESTAMPTZ,
                                            decided_by TEXT,
                                            decided_role TEXT,
                                            decision_notes TEXT,
                                            required_approvals INT NOT NULL DEFAULT 1,
                                            approval_chain JSONB,
                                            scope JSONB,
                                            metadata JSONB,
                                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                                        );

                                        CREATE TABLE IF NOT EXISTS meta.policy_waiver_approvals (
                                            id BIGSERIAL PRIMARY KEY,
                                            waiver_id BIGINT NOT NULL REFERENCES meta.policy_waivers(id) ON DELETE CASCADE,
                                            approver TEXT NOT NULL,
                                            approver_role TEXT NOT NULL,
                                            decision TEXT NOT NULL,
                                            notes TEXT,
                                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                                        );

                                        CREATE TABLE IF NOT EXISTS meta.doc_rewrite_runs (
                                            id BIGSERIAL PRIMARY KEY,
                                            repo TEXT NOT NULL,
                                            pr_number BIGINT NOT NULL,
                                            correlation_id TEXT,
                                            idempotency_key TEXT,
                                            rule_set TEXT,
                                            status TEXT NOT NULL,
                                            reason TEXT,
                                            quality_gate_score NUMERIC(6,2),
                                            bundle JSONB,
                                            emitted_event JSONB,
                                                                                        emit_status TEXT NOT NULL DEFAULT 'pending',
                                                                                        emit_error TEXT,
                                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                                        );

                                                                                ALTER TABLE IF EXISTS meta.doc_refresh_jobs
                                                                                    ADD COLUMN IF NOT EXISTS emit_status TEXT NOT NULL DEFAULT 'pending';
                                                                                ALTER TABLE IF EXISTS meta.doc_refresh_jobs
                                                                                    ADD COLUMN IF NOT EXISTS emit_error TEXT;
                                                                                ALTER TABLE IF EXISTS meta.doc_rewrite_runs
                                                                                    ADD COLUMN IF NOT EXISTS emit_status TEXT NOT NULL DEFAULT 'pending';
                                                                                ALTER TABLE IF EXISTS meta.doc_rewrite_runs
                                                                                    ADD COLUMN IF NOT EXISTS emit_error TEXT;
                    """
                )
            conn.commit()

    def upsert_policy_template(
        self,
        *,
        template_name: str,
        scope_type: str,
        scope_value: str,
        rule_pack: Optional[str],
        rules: Dict[str, Any],
        fail_blocks_merge: bool,
        warn_blocks_merge: bool,
        no_docs_no_merge: bool,
        metadata: Optional[Dict[str, Any]],
        enabled: bool,
        priority: int,
    ) -> Dict[str, Any]:
        self._ensure_schema()
        st = scope_type.strip().lower()
        if st not in {"org", "team", "repo"}:
            raise ValueError("scope_type must be one of: org, team, repo")

        if rule_pack:
            resolve_policy_pack(rule_pack)

        with self._db_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO meta.policy_templates (
                      template_name, scope_type, scope_value, rule_pack, rules,
                      fail_blocks_merge, warn_blocks_merge, no_docs_no_merge,
                      metadata, enabled, priority, created_at, updated_at
                    ) VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb,%s,%s,NOW(),NOW())
                    ON CONFLICT (scope_type, scope_value, template_name)
                    DO UPDATE SET
                      rule_pack = EXCLUDED.rule_pack,
                      rules = EXCLUDED.rules,
                      fail_blocks_merge = EXCLUDED.fail_blocks_merge,
                      warn_blocks_merge = EXCLUDED.warn_blocks_merge,
                      no_docs_no_merge = EXCLUDED.no_docs_no_merge,
                      metadata = EXCLUDED.metadata,
                      enabled = EXCLUDED.enabled,
                      priority = EXCLUDED.priority,
                      updated_at = NOW()
                    RETURNING *
                    """,
                    (
                        template_name.strip(),
                        st,
                        scope_value.strip(),
                        rule_pack,
                        json.dumps(rules or {}),
                        fail_blocks_merge,
                        warn_blocks_merge,
                        no_docs_no_merge,
                        json.dumps(metadata or {}),
                        enabled,
                        int(priority),
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        return dict(row)

    def list_policy_templates(
        self,
        *,
        scope_type: Optional[str] = None,
        scope_value: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        self._ensure_schema()
        with self._db_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM meta.policy_templates
                    WHERE (%s IS NULL OR scope_type = %s)
                      AND (%s IS NULL OR scope_value = %s)
                      AND (%s IS NULL OR enabled = %s)
                    ORDER BY scope_type, scope_value, priority ASC, updated_at DESC
                    """,
                    (scope_type, scope_type, scope_value, scope_value, enabled, enabled),
                )
                rows = cur.fetchall()
        return [dict(r) for r in rows]

    def resolve_effective_policy_template(
        self,
        *,
        repo: str,
        team: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        self._ensure_schema()
        with self._db_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM meta.policy_templates
                    WHERE enabled = TRUE
                      AND (
                        (scope_type = 'repo' AND scope_value = %s)
                        OR (%s IS NOT NULL AND scope_type = 'team' AND scope_value = %s)
                        OR (scope_type = 'org' AND scope_value = '*')
                      )
                    ORDER BY
                      CASE scope_type
                        WHEN 'repo' THEN 3
                        WHEN 'team' THEN 2
                        WHEN 'org' THEN 1
                        ELSE 0
                      END DESC,
                      priority ASC,
                      updated_at DESC
                    LIMIT 1
                    """,
                    (repo, team, team),
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def create_waiver_request(
        self,
        *,
        repo: str,
        pr_number: int,
        rule_set: str,
        requested_by: str,
        requested_role: str,
        reason: str,
        expires_at: str,
        required_approvals: int,
        approval_chain: List[str],
        scope: Dict[str, Any],
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        self._ensure_schema()
        resolve_policy_pack(rule_set)
        with self._db_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO meta.policy_waivers (
                      repo, pr_number, rule_set, requested_by, requested_role, reason,
                      status, expires_at, required_approvals, approval_chain, scope, metadata,
                      requested_at, created_at, updated_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,'pending',%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,NOW(),NOW(),NOW())
                    RETURNING *
                    """,
                    (
                        repo,
                        pr_number,
                        rule_set,
                        requested_by,
                        requested_role,
                        reason,
                        expires_at,
                        max(1, int(required_approvals)),
                        json.dumps(approval_chain or []),
                        json.dumps(scope or {}),
                        json.dumps(metadata or {}),
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        return dict(row)

    def decide_waiver(
        self,
        *,
        waiver_id: int,
        decision: str,
        approver: str,
        approver_role: str,
        notes: Optional[str],
    ) -> Dict[str, Any]:
        self._ensure_schema()
        d = decision.strip().lower()
        if d not in {"approve", "reject"}:
            raise ValueError("decision must be approve or reject")

        with self._db_conn() as conn:
            conn.autocommit = False
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM meta.policy_waivers WHERE id = %s FOR UPDATE", (waiver_id,))
                waiver = cur.fetchone()
                if waiver is None:
                    raise ValueError("waiver not found")

                if waiver["status"] in {"rejected", "expired"}:
                    raise ValueError(f"waiver cannot be updated from status={waiver['status']}")

                cur.execute(
                    """
                    INSERT INTO meta.policy_waiver_approvals (waiver_id, approver, approver_role, decision, notes, created_at)
                    VALUES (%s,%s,%s,%s,%s,NOW())
                    """,
                    (waiver_id, approver, approver_role, d, notes),
                )

                if d == "reject":
                    cur.execute(
                        """
                        UPDATE meta.policy_waivers
                        SET status = 'rejected',
                            decided_at = NOW(),
                            decided_by = %s,
                            decided_role = %s,
                            decision_notes = %s,
                            updated_at = NOW()
                        WHERE id = %s
                        RETURNING *
                        """,
                        (approver, approver_role, notes, waiver_id),
                    )
                    out = cur.fetchone()
                    conn.commit()
                    return dict(out)

                cur.execute(
                    """
                    SELECT COUNT(DISTINCT approver_role)::int AS c
                    FROM meta.policy_waiver_approvals
                    WHERE waiver_id = %s AND decision = 'approve'
                    """,
                    (waiver_id,),
                )
                approved_role_count = int(cur.fetchone()["c"])
                required = int(waiver.get("required_approvals") or 1)
                new_status = "approved" if approved_role_count >= required else "pending"

                cur.execute(
                    """
                    UPDATE meta.policy_waivers
                    SET status = %s,
                        decided_at = CASE WHEN %s = 'approved' THEN NOW() ELSE decided_at END,
                        decided_by = CASE WHEN %s = 'approved' THEN %s ELSE decided_by END,
                        decided_role = CASE WHEN %s = 'approved' THEN %s ELSE decided_role END,
                        decision_notes = CASE WHEN %s = 'approved' THEN %s ELSE decision_notes END,
                        updated_at = NOW()
                    WHERE id = %s
                    RETURNING *
                    """,
                    (new_status, new_status, new_status, approver, new_status, approver_role, new_status, notes, waiver_id),
                )
                out = cur.fetchone()
            conn.commit()
        return dict(out)

    def list_waivers(
        self,
        *,
        repo: Optional[str] = None,
        pr_number: Optional[int] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        self._ensure_schema()
        with self._db_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM meta.policy_waivers
                    WHERE (%s IS NULL OR repo = %s)
                      AND (%s IS NULL OR pr_number = %s)
                      AND (%s IS NULL OR status = %s)
                    ORDER BY id DESC
                    """,
                    (repo, repo, pr_number, pr_number, status, status),
                )
                rows = cur.fetchall()
        return [dict(r) for r in rows]

    def get_active_waiver(
        self,
        *,
        repo: str,
        pr_number: int,
        rule_set: str,
    ) -> Optional[Dict[str, Any]]:
        self._ensure_schema()
        with self._db_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE meta.policy_waivers
                    SET status = 'expired', updated_at = NOW()
                    WHERE status IN ('pending','approved')
                      AND expires_at < NOW()
                    """
                )
                cur.execute(
                    """
                    SELECT *
                    FROM meta.policy_waivers
                    WHERE repo = %s
                      AND pr_number = %s
                      AND rule_set = %s
                      AND status = 'approved'
                      AND expires_at >= NOW()
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (repo, pr_number, rule_set),
                )
                row = cur.fetchone()
            conn.commit()
        return dict(row) if row else None

    def _resolve_effective_runtime_controls(
        self,
        payload: Dict[str, Any],
        request: PolicyEvaluationRequest,
    ) -> Dict[str, Any]:
        policy_ctx = payload.get("policy_context") or {}
        team = payload.get("team") or policy_ctx.get("team")
        template = self.resolve_effective_policy_template(repo=request.repo, team=team)

        merged_rules: Dict[str, Any] = {}
        selected_rule_set = self.rule_set
        fail_blocks_merge = self.fail_blocks_merge
        warn_blocks_merge = self.warn_blocks_merge
        no_docs_no_merge = False

        if template:
            merged_rules.update(template.get("rules") or {})
            if template.get("rule_pack"):
                selected_rule_set = str(template["rule_pack"])
            fail_blocks_merge = bool(template.get("fail_blocks_merge", fail_blocks_merge))
            warn_blocks_merge = bool(template.get("warn_blocks_merge", warn_blocks_merge))
            no_docs_no_merge = bool(template.get("no_docs_no_merge", False))

        if request.config and request.config.rules:
            merged_rules.update({k: v.model_dump() for k, v in request.config.rules.items()})
        if request.config and request.config.rule_pack:
            selected_rule_set = request.config.rule_pack

        config = PolicyConfig.model_validate(
            {
                "rule_pack": selected_rule_set,
                "rules": merged_rules,
            }
        )
        request.config = config

        return {
            "selected_rule_set": selected_rule_set,
            "fail_blocks_merge": fail_blocks_merge,
            "warn_blocks_merge": warn_blocks_merge,
            "no_docs_no_merge": no_docs_no_merge,
            "applied_template": template,
            "team": team,
        }

    def _log_error(self, message: str, err: Exception):
        try:
            self.log.error("%s: %s", message, str(err))
        except Exception:
            pass

    def _is_policy_event(self, payload: Dict[str, Any]) -> bool:
        event_type = payload.get("event_type")
        return event_type in {"pull_request", "spec", "schema", "doc"}

    def _build_request(self, payload: Dict[str, Any]) -> Optional[PolicyEvaluationRequest]:
        repo = payload.get("repo") or {}
        repo_id = repo.get("full_name") or repo.get("name_with_owner") or repo.get("id")
        if not repo_id:
            return None

        changed_files = [
            ChangedFile(path=f.get("path", "unknown"), status=f.get("status", "modified"))
            for f in payload.get("changed_files", [])
        ]

        policy_ctx = payload.get("policy_context") or {}

        if policy_ctx.get("head_spec"):
            head_spec = ServiceSpec.model_validate(policy_ctx["head_spec"])
        else:
            inferred_endpoint = EndpointSpec(
                method="POST" if payload.get("event_type") == "pull_request" else "GET",
                path=f"/inferred/{payload.get('event_type', 'event')}",
                operation_id=f"inferred_{payload.get('event_type', 'event')}",
                owner=(payload.get("owner") or None),
                request_required_fields=[],
                request_enum_fields={},
                response_fields={"status": "string"},
                response_status_codes=["200"],
            )
            head_spec = ServiceSpec(service_id=self.default_service_id, endpoints=[inferred_endpoint])

        base_spec = None
        if policy_ctx.get("base_spec"):
            base_spec = ServiceSpec.model_validate(policy_ctx["base_spec"])

        impact_edges = []
        for edge in policy_ctx.get("impact_edges", []):
            try:
                impact_edges.append(ImpactEdge.model_validate(edge))
            except Exception:
                continue

        owners = policy_ctx.get("owners") or {}
        docs_touched = policy_ctx.get("docs_touched") or []

        pr = payload.get("pull_request") or {}
        pr_number = pr.get("number")

        return PolicyEvaluationRequest(
            repo=repo_id,
            pr_number=pr_number,
            correlation_id=payload.get("correlation_id"),
            head_spec=head_spec,
            base_spec=base_spec,
            changed_files=changed_files,
            owners=owners,
            docs_touched=docs_touched,
            impact_edges=impact_edges,
            config=policy_ctx.get("config"),
        )

    @staticmethod
    def _fingerprint(response_payload: Dict[str, Any]) -> str:
        normalized_findings = []
        for f in response_payload.get("findings", []):
            normalized_findings.append(
                {
                    "rule_id": f.get("rule_id"),
                    "severity": f.get("severity"),
                    "status": f.get("status"),
                    "title": f.get("title"),
                    "description": f.get("description"),
                    "entity_refs": f.get("entity_refs", []),
                    "evidence": f.get("evidence", []),
                    "suggested_action": f.get("suggested_action"),
                }
            )

        raw = json.dumps(
            {
                "summary_status": response_payload.get("summary_status"),
                "markdown_comment": response_payload.get("markdown_comment"),
                "findings": normalized_findings,
            },
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

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
        request: PolicyEvaluationRequest,
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
        request: PolicyEvaluationRequest,
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
        request: PolicyEvaluationRequest,
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

    def _detect_doc_rewrite_conflict(self, conn, repo: str, pr_number: int, bundle: Dict[str, Any]) -> Optional[str]:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, status, bundle
                FROM meta.doc_rewrite_runs
                WHERE repo = %s AND pr_number = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (repo, pr_number),
            )
            row = cur.fetchone()

        if row is None:
            return None

        prior_bundle = row.get("bundle") or {}
        prior_targets = prior_bundle.get("targets") or []
        current_targets = bundle.get("targets") or []
        prior_map = {t.get("file_path"): t.get("content_hash") for t in prior_targets}
        curr_map = {t.get("file_path"): t.get("content_hash") for t in current_targets}

        if prior_map == curr_map:
            return None
        return f"conflict with prior rewrite run id={row['id']}"

    def _persist_doc_rewrite_run(
        self,
        conn,
        *,
        request: PolicyEvaluationRequest,
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

    def _emit_check_event(self, event: Dict[str, Any]):
        if self.producer is None:
            raise RuntimeError("producer not initialized")

        self.producer.send(
            self.output_topic,
            key=(event.get("comment_key") or "policy-check").encode("utf-8"),
            value=json.dumps(event, default=str).encode("utf-8"),
            headers=[
                ("x-correlation-id", str(event.get("correlation_id") or "").encode("utf-8")),
                ("x-repo", str(event.get("repo") or "").encode("utf-8")),
                ("x-pr-number", str(event.get("pr_number") or "").encode("utf-8")),
            ],
        )
        self.producer.flush(timeout=5)

    def _emit_doc_refresh_event(self, event: Dict[str, Any]):
        if self.producer is None:
            raise RuntimeError("producer not initialized")

        self.producer.send(
            self.docs_refresh_topic,
            key=(event.get("doc_refresh_key") or "doc-refresh").encode("utf-8"),
            value=json.dumps(event, default=str).encode("utf-8"),
            headers=[
                ("x-correlation-id", str(event.get("correlation_id") or "").encode("utf-8")),
                ("x-repo", str(event.get("repo") or "").encode("utf-8")),
                ("x-pr-number", str(event.get("pr_number") or "").encode("utf-8")),
            ],
        )
        self.producer.flush(timeout=5)

    def _emit_doc_rewrite_event(self, event: Dict[str, Any]):
        if self.producer is None:
            raise RuntimeError("producer not initialized")

        self.producer.send(
            self.docs_rewrite_topic,
            key=(event.get("rewrite_key") or "doc-rewrite").encode("utf-8"),
            value=json.dumps(event, default=str).encode("utf-8"),
            headers=[
                ("x-correlation-id", str(event.get("correlation_id") or "").encode("utf-8")),
                ("x-repo", str(event.get("repo") or "").encode("utf-8")),
                ("x-pr-number", str(event.get("pr_number") or "").encode("utf-8")),
            ],
        )
        self.producer.flush(timeout=5)

    def list_doc_rewrite_runs(
        self,
        *,
        repo: Optional[str] = None,
        pr_number: Optional[int] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(limit, 500))
        self._ensure_schema()
        with self._db_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM meta.doc_rewrite_runs
                    WHERE (%s IS NULL OR repo = %s)
                      AND (%s IS NULL OR pr_number = %s)
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (repo, repo, pr_number, pr_number, safe_limit),
                )
                rows = cur.fetchall()
        return [dict(r) for r in rows]

    def _handle_message(
        self,
        payload: Dict[str, Any],
        *,
        source_topic: Optional[str] = None,
        source_partition: Optional[int] = None,
        source_offset: Optional[str] = None,
    ):
        if not self._is_policy_event(payload):
            self.state["skipped_events"] += 1
            return

        request = self._build_request(payload)
        if request is None or request.pr_number is None:
            self.state["skipped_events"] += 1
            return

        controls = self._resolve_effective_runtime_controls(payload, request)
        selected_rule_set = controls["selected_rule_set"]

        dedup_key = self._event_dedup_key(payload, request, selected_rule_set)
        source_topic_safe = source_topic or self.consumer_topic
        source_partition_safe = int(source_partition) if source_partition is not None else -1
        source_offset_safe = source_offset or "unknown"

        with self._db_conn() as conn:
            conn.autocommit = False
            inserted = self._register_processed_event(
                conn,
                event_key=dedup_key,
                source_topic=source_topic_safe,
                source_partition=source_partition_safe,
                source_offset=source_offset_safe,
                correlation_id=payload.get("correlation_id"),
                payload=payload,
            )
            if not inserted:
                conn.rollback()
                self.state["deduped_checks"] += 1
                self.state["replay_skipped_events"] += 1
                return
            conn.commit()

        findings, eval_meta = evaluate_policies_with_meta(request, rule_set=selected_rule_set)
        patches = build_suggested_patches(findings)
        status = summary_status(findings)
        merge_gate = build_merge_gate_decision(
            findings,
            rule_set=selected_rule_set,
            fail_blocks_merge=bool(controls["fail_blocks_merge"]),
            warn_blocks_merge=bool(controls["warn_blocks_merge"]),
        )
        active_waiver = self.get_active_waiver(
            repo=request.repo,
            pr_number=request.pr_number,
            rule_set=selected_rule_set,
        )
        if active_waiver and merge_gate.get("decision") == "block":
            merge_gate["decision"] = "allow_with_waiver"
            merge_gate["waiver"] = {
                "waiver_id": active_waiver.get("id"),
                "requested_by": active_waiver.get("requested_by"),
                "requested_role": active_waiver.get("requested_role"),
                "decided_by": active_waiver.get("decided_by"),
                "decided_role": active_waiver.get("decided_role"),
                "expires_at": active_waiver.get("expires_at"),
            }
            reasons = list(merge_gate.get("reasons") or [])
            reasons.append("Approved waiver in effect; merge gate overridden.")
            merge_gate["reasons"] = reasons
        doc_refresh_plan = build_doc_refresh_plan(
            request=request,
            findings=findings,
            suggested_patches=patches,
            merge_gate=merge_gate,
            action="pending",
        )

        if bool(controls.get("no_docs_no_merge")) and int(doc_refresh_plan.get("doc_finding_count") or 0) > 0:
            merge_gate["decision"] = "block"
            blocking_rule_ids = set(merge_gate.get("blocking_rule_ids") or [])
            blocking_rule_ids.add("NO_DOCS_NO_MERGE")
            merge_gate["blocking_rule_ids"] = sorted(blocking_rule_ids)
            reasons = list(merge_gate.get("reasons") or [])
            reasons.append("Template enforces no-docs-no-merge; documentation drift must be resolved.")
            merge_gate["reasons"] = reasons
        response = assemble_response(request, status, findings, patches)
        response_payload = response.model_dump()
        knowledge_health = build_knowledge_health_score(
            request=request,
            findings=findings,
            merge_gate=merge_gate,
            doc_refresh_plan=doc_refresh_plan,
            weights={
                "policy": self.health_weight_policy,
                "docs": self.health_weight_docs,
                "ownership": self.health_weight_ownership,
            },
        )

        event_idempotency = payload.get("idempotency_key") or dedup_key
        fingerprint = self._fingerprint(response_payload)

        with self._db_conn() as conn:
            conn.autocommit = False
            comment_state_id, comment_key, action, deduped = self._upsert_comment_state(
                conn, request.repo, request.pr_number, fingerprint
            )
            doc_refresh_plan["action"] = action
            check_run_id = self._persist_check_run(
                conn,
                request,
                response_payload,
                merge_gate,
                doc_refresh_plan,
                knowledge_health,
                event_idempotency,
                action,
                deduped,
                comment_state_id,
            )
            doc_refresh_job_id = self._persist_doc_refresh_job(
                conn,
                request,
                event_idempotency,
                selected_rule_set,
                action,
                doc_refresh_plan,
            )
            self._persist_knowledge_health_snapshot(
                conn,
                request,
                event_idempotency,
                selected_rule_set,
                str(response_payload.get("summary_status") or "warn"),
                knowledge_health,
            )
            conn.commit()

        self.state["processed_events"] += 1
        self.state["last_processed_at"] = datetime.now(timezone.utc).isoformat()

        if deduped:
            self.state["deduped_checks"] += 1
            return

        out_event = {
            "schema_version": "1.0.0",
            "event_type": "pr_policy_check",
            "rule_set": selected_rule_set,
            "policy_pack_meta": eval_meta,
            "governance": {
                "team": controls.get("team"),
                "no_docs_no_merge": bool(controls.get("no_docs_no_merge")),
                "applied_template": controls.get("applied_template"),
                "active_waiver": active_waiver,
            },
            "merge_gate": merge_gate,
            "doc_refresh_plan": doc_refresh_plan,
            "knowledge_health": knowledge_health,
            "repo": request.repo,
            "repo_full_name": (payload.get("repo") or {}).get("full_name") or request.repo,
            "tenant_id": payload.get("tenant_id") or ((payload.get("tenant") or {}).get("id")),
            "installation_id": payload.get("installation_id") or ((payload.get("tenant") or {}).get("installation_id")),
            "pr_number": request.pr_number,
            "head_sha": ((payload.get("pull_request") or {}).get("head_sha") or (((payload.get("pull_request") or {}).get("head") or {}).get("sha"))),
            "correlation_id": request.correlation_id,
            "idempotency_key": event_idempotency,
            "summary_status": response_payload.get("summary_status"),
            "action": action,
            "comment_key": comment_key,
            "markdown_comment": response_payload.get("markdown_comment"),
            "findings": response_payload.get("findings", []),
            "citations": response_payload.get("citations", []),
            "check_annotations": response_payload.get("check_annotations", []),
            "suggested_patches": response_payload.get("suggested_patches", []),
            "produced_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self._emit_check_event(out_event)
            self.state["emitted_checks"] += 1
            with self._db_conn() as conn3:
                conn3.autocommit = False
                self._update_emit_status(conn3, table="policy_check_runs", row_id=check_run_id, status="emitted")
                conn3.commit()
        except Exception as exc:
            self.state["emit_failures"] += 1
            with self._db_conn() as conn3:
                conn3.autocommit = False
                self._update_emit_status(conn3, table="policy_check_runs", row_id=check_run_id, status="failed", error=str(exc))
                queued = self._queue_emit_retry_job(
                    conn3,
                    emit_type="policy_check",
                    base_idempotency_key=event_idempotency,
                    repo=request.repo,
                    pr_number=request.pr_number,
                    correlation_id=request.correlation_id,
                    event_payload=out_event,
                    error=str(exc),
                )
                conn3.commit()
            if queued:
                self.state["queued_emit_retries"] += 1
            self._log_error("policy check emit failed; queued retry", exc)

        if self.doc_refresh_enabled and bool(doc_refresh_plan.get("should_emit")) and action != "noop":
            doc_event = {
                "schema_version": "1.0.0",
                "event_type": "doc_refresh_plan",
                "rule_set": selected_rule_set,
                "repo": request.repo,
                "repo_full_name": (payload.get("repo") or {}).get("full_name") or request.repo,
                "pr_number": request.pr_number,
                "correlation_id": request.correlation_id,
                "idempotency_key": event_idempotency,
                "doc_refresh_key": f"{request.repo}:{request.pr_number}:{selected_rule_set}",
                "plan": doc_refresh_plan,
                "produced_at": datetime.now(timezone.utc).isoformat(),
            }
            try:
                self._emit_doc_refresh_event(doc_event)
                self.state["emitted_doc_refresh"] += 1
                with self._db_conn() as conn3:
                    conn3.autocommit = False
                    self._update_emit_status(conn3, table="doc_refresh_jobs", row_id=doc_refresh_job_id, status="emitted")
                    conn3.commit()
            except Exception as exc:
                self.state["emit_failures"] += 1
                with self._db_conn() as conn3:
                    conn3.autocommit = False
                    self._update_emit_status(conn3, table="doc_refresh_jobs", row_id=doc_refresh_job_id, status="failed", error=str(exc))
                    queued = self._queue_emit_retry_job(
                        conn3,
                        emit_type="doc_refresh",
                        base_idempotency_key=event_idempotency,
                        repo=request.repo,
                        pr_number=request.pr_number,
                        correlation_id=request.correlation_id,
                        event_payload=doc_event,
                        error=str(exc),
                    )
                    conn3.commit()
                if queued:
                    self.state["queued_emit_retries"] += 1
                self._log_error("doc refresh emit failed; queued retry", exc)

            if self.doc_rewrite_enabled:
                bundle = build_doc_rewrite_bundle(
                    request=request,
                    findings=findings,
                    doc_refresh_plan=doc_refresh_plan,
                    merge_gate=merge_gate,
                    knowledge_health=knowledge_health,
                )
                quality_score = float(knowledge_health.get("score") or 0.0)
                with self._db_conn() as conn2:
                    conn2.autocommit = False
                    if quality_score < self.doc_rewrite_min_health_score:
                        self._persist_doc_rewrite_run(
                            conn2,
                            request=request,
                            idempotency_key=event_idempotency,
                            selected_rule_set=selected_rule_set,
                            status="blocked_quality_gate",
                            reason="knowledge health below doc rewrite threshold",
                            quality_gate_score=quality_score,
                            bundle=bundle,
                        )
                    else:
                        conflict_reason = self._detect_doc_rewrite_conflict(conn2, request.repo, request.pr_number, bundle)
                        if conflict_reason:
                            self._persist_doc_rewrite_run(
                                conn2,
                                request=request,
                                idempotency_key=event_idempotency,
                                selected_rule_set=selected_rule_set,
                                status="conflict",
                                reason=conflict_reason,
                                quality_gate_score=quality_score,
                                bundle=bundle,
                            )
                        else:
                            rewrite_event = {
                                "schema_version": "1.0.0",
                                "event_type": "doc_rewrite_bundle",
                                "repo": request.repo,
                                "pr_number": request.pr_number,
                                "rule_set": selected_rule_set,
                                "correlation_id": request.correlation_id,
                                "idempotency_key": event_idempotency,
                                "doc_refresh_job_id": doc_refresh_job_id,
                                "rewrite_key": f"{request.repo}:{request.pr_number}:{selected_rule_set}",
                                "quality_gate_score": quality_score,
                                "bundle": bundle,
                                "produced_at": datetime.now(timezone.utc).isoformat(),
                            }
                            rewrite_run_id = self._persist_doc_rewrite_run(
                                conn2,
                                request=request,
                                idempotency_key=event_idempotency,
                                selected_rule_set=selected_rule_set,
                                status="queued_for_emit",
                                reason="rewrite bundle queued for emit",
                                quality_gate_score=quality_score,
                                bundle=bundle,
                                emitted_event=rewrite_event,
                            )
                            conn2.commit()

                            try:
                                self._emit_doc_rewrite_event(rewrite_event)
                                self.state["emitted_doc_rewrite"] += 1
                                with self._db_conn() as conn3:
                                    conn3.autocommit = False
                                    self._update_emit_status(conn3, table="doc_rewrite_runs", row_id=rewrite_run_id, status="emitted")
                                    conn3.commit()
                            except Exception as exc:
                                self.state["emit_failures"] += 1
                                with self._db_conn() as conn3:
                                    conn3.autocommit = False
                                    self._update_emit_status(conn3, table="doc_rewrite_runs", row_id=rewrite_run_id, status="failed", error=str(exc))
                                    queued = self._queue_emit_retry_job(
                                        conn3,
                                        emit_type="doc_rewrite",
                                        base_idempotency_key=event_idempotency,
                                        repo=request.repo,
                                        pr_number=request.pr_number,
                                        correlation_id=request.correlation_id,
                                        event_payload=rewrite_event,
                                        error=str(exc),
                                    )
                                    conn3.commit()
                                if queued:
                                    self.state["queued_emit_retries"] += 1
                                self._log_error("doc rewrite emit failed; queued retry", exc)
                    if conn2.closed == 0:
                        conn2.commit()

        self.state["emitted_health_snapshots"] += 1

    def _run_loop(self):
        self.state["running"] = True
        try:
            self._ensure_schema()
            self.consumer = KafkaConsumer(
                self.consumer_topic,
                bootstrap_servers=self.kafka_brokers,
                group_id=self.consumer_group,
                enable_auto_commit=True,
                auto_offset_reset="latest",
                value_deserializer=lambda b: json.loads(b.decode("utf-8")),
                consumer_timeout_ms=1000,
            )
            self.producer = KafkaProducer(bootstrap_servers=self.kafka_brokers)

            while not self.stop_event.is_set():
                try:
                    self._process_emit_retry_jobs()
                except Exception as exc:
                    self.state["last_error"] = str(exc)
                    self._log_error("emit retry processing failed", exc)

                batch = self.consumer.poll(timeout_ms=1000, max_records=50)
                for records in batch.values():
                    for record in records:
                        try:
                            self._handle_message(
                                record.value,
                                source_topic=getattr(record, "topic", self.consumer_topic),
                                source_partition=getattr(record, "partition", -1),
                                source_offset=str(getattr(record, "offset", "unknown")),
                            )
                        except Exception as exc:
                            self.state["last_error"] = str(exc)
                            self._log_error("policy pipeline message handling failed", exc)
        except Exception as exc:
            self.state["last_error"] = str(exc)
            self._log_error("policy pipeline crashed", exc)
        finally:
            self.state["running"] = False
            if self.consumer:
                try:
                    self.consumer.close()
                except Exception:
                    pass
            if self.producer:
                try:
                    self.producer.close()
                except Exception:
                    pass

    def start(self):
        if not self.enabled:
            self.log.info("policy pipeline disabled by configuration")
            return
        if self.thread and self.thread.is_alive():
            return

        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name="policy-pipeline")
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)

    def list_health_snapshots(
        self,
        *,
        repo: Optional[str] = None,
        pr_number: Optional[int] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(limit, 500))
        self._ensure_schema()
        with self._db_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id,
                           repo,
                           pr_number,
                           correlation_id,
                           idempotency_key,
                           rule_set,
                           summary_status,
                           score::float8 AS score,
                           grade,
                           snapshot,
                           created_at
                    FROM meta.knowledge_health_snapshots
                    WHERE (%s IS NULL OR repo = %s)
                      AND (%s IS NULL OR pr_number = %s)
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (repo, repo, pr_number, pr_number, safe_limit),
                )
                rows = cur.fetchall()
        return [dict(r) for r in rows]

    def list_doc_refresh_jobs(
        self,
        *,
        repo: Optional[str] = None,
        pr_number: Optional[int] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(limit, 500))
        self._ensure_schema()
        with self._db_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id,
                           repo,
                           pr_number,
                           correlation_id,
                           idempotency_key,
                           rule_set,
                           action,
                           decision,
                           priority,
                           plan,
                           created_at
                    FROM meta.doc_refresh_jobs
                    WHERE (%s IS NULL OR repo = %s)
                      AND (%s IS NULL OR pr_number = %s)
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (repo, repo, pr_number, pr_number, safe_limit),
                )
                rows = cur.fetchall()
        return [dict(r) for r in rows]

    def list_emit_retry_jobs(
        self,
        *,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(limit, 500))
        with self._db_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, job_type, idempotency_key, correlation_id, status, payload, created_at, updated_at
                    FROM meta.jobs
                    WHERE job_type = 'emit_retry'
                      AND (%s IS NULL OR status = %s)
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (status, status, safe_limit),
                )
                rows = cur.fetchall()
        return [dict(r) for r in rows]

    def list_emit_retry_dead_letters(
        self,
        *,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(limit, 500))
        with self._db_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, source_topic, source_partition, source_offset, error, attempts,
                           payload_raw, correlation_id, idempotency_key, status, requeue_count,
                           requeued_at, created_at, updated_at
                    FROM meta.poison_pills
                    WHERE source_topic = 'internal.emit_retry'
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (safe_limit,),
                )
                rows = cur.fetchall()
        return [dict(r) for r in rows]

    def emit_retry_overview(
        self,
        *,
        repo: Optional[str] = None,
        window_hours: int = 24,
    ) -> Dict[str, Any]:
        safe_window = max(1, min(window_hours, 24 * 30))
        self._ensure_schema()
        with self._db_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT status, COUNT(*)::int AS count
                    FROM meta.jobs
                    WHERE job_type = 'emit_retry'
                      AND (%s IS NULL OR payload->>'repo' = %s)
                    GROUP BY status
                    """,
                    (repo, repo),
                )
                status_counts = {str(r["status"]): int(r["count"]) for r in cur.fetchall()}

                cur.execute(
                    """
                    SELECT id, idempotency_key, correlation_id, status, payload, created_at, updated_at
                    FROM meta.jobs
                    WHERE job_type = 'emit_retry'
                      AND status IN ('queued', 'processing')
                      AND (%s IS NULL OR payload->>'repo' = %s)
                    ORDER BY created_at ASC
                    LIMIT 1
                    """,
                    (repo, repo),
                )
                oldest_inflight = cur.fetchone()

                cur.execute(
                    """
                    SELECT id, idempotency_key, correlation_id, status, payload, created_at, updated_at
                    FROM meta.jobs
                    WHERE job_type = 'emit_retry'
                      AND status IN ('dead_letter', 'queued')
                      AND payload ? 'last_error'
                      AND (%s IS NULL OR payload->>'repo' = %s)
                    ORDER BY updated_at DESC
                    LIMIT 5
                    """,
                    (repo, repo),
                )
                recent_job_errors = [dict(r) for r in cur.fetchall()]

                cur.execute(
                    """
                    SELECT COUNT(*)::int AS c
                    FROM meta.poison_pills
                    WHERE source_topic = 'internal.emit_retry'
                      AND (%s IS NULL OR (payload_raw::jsonb)->>'repo' = %s)
                    """,
                    (repo, repo),
                )
                poison_total = int((cur.fetchone() or {}).get("c") or 0)

                cur.execute(
                    """
                    SELECT COUNT(*)::int AS c
                    FROM meta.poison_pills
                    WHERE source_topic = 'internal.emit_retry'
                      AND status = 'requeued'
                      AND (%s IS NULL OR (payload_raw::jsonb)->>'repo' = %s)
                    """,
                    (repo, repo),
                )
                poison_requeued = int((cur.fetchone() or {}).get("c") or 0)

                cur.execute(
                    """
                    SELECT id, idempotency_key, error, attempts, status, requeue_count, created_at, updated_at
                    FROM meta.poison_pills
                    WHERE source_topic = 'internal.emit_retry'
                      AND (%s IS NULL OR (payload_raw::jsonb)->>'repo' = %s)
                    ORDER BY id DESC
                    LIMIT 5
                    """,
                    (repo, repo),
                )
                recent_poison = [dict(r) for r in cur.fetchall()]

                cur.execute(
                    """
                    SELECT COUNT(*)::int AS c
                    FROM meta.jobs
                    WHERE job_type = 'emit_retry'
                      AND status = 'completed'
                      AND updated_at >= NOW() - make_interval(hours => %s)
                      AND (%s IS NULL OR payload->>'repo' = %s)
                    """,
                    (safe_window, repo, repo),
                )
                completed_window = int((cur.fetchone() or {}).get("c") or 0)

                cur.execute(
                    """
                    SELECT COUNT(*)::int AS c
                    FROM meta.jobs
                    WHERE job_type = 'emit_retry'
                      AND status = 'dead_letter'
                      AND updated_at >= NOW() - make_interval(hours => %s)
                      AND (%s IS NULL OR payload->>'repo' = %s)
                    """,
                    (safe_window, repo, repo),
                )
                dead_letter_window = int((cur.fetchone() or {}).get("c") or 0)

        success_rate = None
        denom = completed_window + dead_letter_window
        if denom > 0:
            success_rate = round((completed_window / denom) * 100.0, 2)

        return {
            "scope": {"repo": repo, "window_hours": safe_window},
            "queue": {
                "status_counts": status_counts,
                "oldest_inflight": dict(oldest_inflight) if oldest_inflight else None,
                "recent_job_errors": recent_job_errors,
            },
            "dead_letter": {
                "total": poison_total,
                "requeued": poison_requeued,
                "recent": recent_poison,
            },
            "window_metrics": {
                "completed": completed_window,
                "dead_lettered": dead_letter_window,
                "success_rate_percent": success_rate,
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

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
                    idem_key = self._emit_retry_idempotency_key(
                        emit_type=emit_type,
                        base_idempotency_key=base,
                        repo=repo,
                        pr_number=pr_number,
                    )

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

    def dashboard_overview(
        self,
        *,
        repo: Optional[str] = None,
        pr_number: Optional[int] = None,
        window: int = 20,
    ) -> Dict[str, Any]:
        safe_window = max(1, min(window, 200))
        self._ensure_schema()

        with self._db_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id,
                           repo,
                           pr_number,
                           rule_set,
                           summary_status,
                           score::float8 AS score,
                           grade,
                           snapshot,
                           created_at
                    FROM meta.knowledge_health_snapshots
                    WHERE (%s IS NULL OR repo = %s)
                      AND (%s IS NULL OR pr_number = %s)
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (repo, repo, pr_number, pr_number),
                )
                latest = cur.fetchone()

                cur.execute(
                    """
                    SELECT id,
                           repo,
                           pr_number,
                           score::float8 AS score,
                           grade,
                           summary_status,
                           created_at
                    FROM meta.knowledge_health_snapshots
                    WHERE (%s IS NULL OR repo = %s)
                      AND (%s IS NULL OR pr_number = %s)
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (repo, repo, pr_number, pr_number, safe_window),
                )
                trend_rows = [dict(r) for r in cur.fetchall()]

                cur.execute(
                    """
                    SELECT decision, COUNT(*)::int AS count
                    FROM meta.doc_refresh_jobs
                    WHERE (%s IS NULL OR repo = %s)
                      AND (%s IS NULL OR pr_number = %s)
                    GROUP BY decision
                    """,
                    (repo, repo, pr_number, pr_number),
                )
                doc_decisions = {str(r["decision"]): int(r["count"]) for r in cur.fetchall()}

                cur.execute(
                    """
                    SELECT action, COUNT(*)::int AS count
                    FROM meta.policy_check_runs
                    WHERE (%s IS NULL OR repo = %s)
                      AND (%s IS NULL OR pr_number = %s)
                    GROUP BY action
                    """,
                    (repo, repo, pr_number, pr_number),
                )
                action_breakdown = {str(r["action"]): int(r["count"]) for r in cur.fetchall()}

        avg_score = round(sum(r["score"] for r in trend_rows) / len(trend_rows), 2) if trend_rows else None
        return {
            "scope": {"repo": repo, "pr_number": pr_number, "window": safe_window},
            "latest_snapshot": dict(latest) if latest else None,
            "trend": trend_rows,
            "metrics": {
                "avg_score": avg_score,
                "trend_points": len(trend_rows),
                "doc_refresh_decisions": doc_decisions,
                "policy_actions": action_breakdown,
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def health(self) -> Dict[str, Any]:
        return {
            **self.state,
            "topic_in": self.consumer_topic,
            "topic_out": self.output_topic,
            "topic_doc_refresh": self.docs_refresh_topic,
            "topic_doc_rewrite": self.docs_rewrite_topic,
            "consumer_group": self.consumer_group,
            "health_weights": {
                "policy": self.health_weight_policy,
                "docs": self.health_weight_docs,
                "ownership": self.health_weight_ownership,
            },
            "doc_rewrite_quality_gate": self.doc_rewrite_min_health_score,
            "emit_retry": {
                "enabled": self.emit_retry_enabled,
                "batch_size": self.emit_retry_batch_size,
                "max_attempts": self.emit_retry_max_attempts,
                "backoff_seconds": self.emit_retry_backoff_seconds,
            },
        }
