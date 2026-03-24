"""
schema.py — DB schema initialisation for the policy module.

Call ensure_schema(db_conn_func) once at startup to create all required
meta.* tables and columns.  Safe to call on every startup because every
statement uses IF NOT EXISTS / ADD COLUMN IF NOT EXISTS.
"""
from __future__ import annotations

from typing import Callable


def ensure_schema(db_conn_func: Callable) -> None:
    """Create or migrate all policy schema objects in the meta schema."""
    with db_conn_func() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE SCHEMA IF NOT EXISTS meta;

                CREATE TABLE IF NOT EXISTS meta.processed_events (
                    id               BIGSERIAL PRIMARY KEY,
                    event_key        TEXT NOT NULL UNIQUE,
                    source_topic     TEXT NOT NULL,
                    source_partition INT  NOT NULL,
                    source_offset    TEXT NOT NULL,
                    correlation_id   TEXT,
                    payload          JSONB,
                    first_seen_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_processed_events_first_seen
                    ON meta.processed_events (first_seen_at DESC);

                CREATE TABLE IF NOT EXISTS meta.policy_check_runs (
                    id               BIGSERIAL PRIMARY KEY,
                    repo             TEXT NOT NULL,
                    pr_number        BIGINT,
                    correlation_id   TEXT,
                    idempotency_key  TEXT,
                    rule_set         TEXT,
                    summary_status   TEXT,
                    response         JSONB,
                    merge_gate       JSONB,
                    doc_refresh_plan JSONB,
                    knowledge_health JSONB,
                    emit_status      TEXT NOT NULL DEFAULT 'pending',
                    emit_error       TEXT,
                    action           TEXT,
                    deduped          BOOLEAN NOT NULL DEFAULT FALSE,
                    comment_state_id BIGINT,
                    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                ALTER TABLE IF EXISTS meta.policy_check_runs
                    ADD COLUMN IF NOT EXISTS merge_gate       JSONB;
                ALTER TABLE IF EXISTS meta.policy_check_runs
                    ADD COLUMN IF NOT EXISTS emit_status      TEXT NOT NULL DEFAULT 'pending';
                ALTER TABLE IF EXISTS meta.policy_check_runs
                    ADD COLUMN IF NOT EXISTS emit_error       TEXT;
                ALTER TABLE IF EXISTS meta.policy_check_runs
                    ADD COLUMN IF NOT EXISTS doc_refresh_plan JSONB;
                ALTER TABLE IF EXISTS meta.policy_check_runs
                    ADD COLUMN IF NOT EXISTS knowledge_health JSONB;

                CREATE TABLE IF NOT EXISTS meta.doc_refresh_jobs (
                    id              BIGSERIAL PRIMARY KEY,
                    repo            TEXT        NOT NULL,
                    pr_number       BIGINT      NOT NULL,
                    correlation_id  TEXT,
                    idempotency_key TEXT,
                    rule_set        TEXT,
                    action          TEXT        NOT NULL,
                    decision        TEXT        NOT NULL,
                    priority        TEXT,
                    plan            JSONB       NOT NULL,
                    emit_status     TEXT        NOT NULL DEFAULT 'pending',
                    emit_error      TEXT,
                    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                ALTER TABLE IF EXISTS meta.doc_refresh_jobs
                    ADD COLUMN IF NOT EXISTS emit_status TEXT NOT NULL DEFAULT 'pending';
                ALTER TABLE IF EXISTS meta.doc_refresh_jobs
                    ADD COLUMN IF NOT EXISTS emit_error  TEXT;

                CREATE TABLE IF NOT EXISTS meta.knowledge_health_snapshots (
                    id              BIGSERIAL    PRIMARY KEY,
                    repo            TEXT         NOT NULL,
                    pr_number       BIGINT,
                    correlation_id  TEXT,
                    idempotency_key TEXT,
                    rule_set        TEXT,
                    summary_status  TEXT,
                    score           NUMERIC(6,2) NOT NULL,
                    grade           TEXT         NOT NULL,
                    snapshot        JSONB        NOT NULL,
                    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS meta.policy_templates (
                    id                BIGSERIAL   PRIMARY KEY,
                    template_name     TEXT        NOT NULL,
                    scope_type        TEXT        NOT NULL,
                    scope_value       TEXT        NOT NULL,
                    rule_pack         TEXT,
                    rules             JSONB       NOT NULL DEFAULT '{}'::jsonb,
                    fail_blocks_merge BOOLEAN     NOT NULL DEFAULT TRUE,
                    warn_blocks_merge BOOLEAN     NOT NULL DEFAULT FALSE,
                    no_docs_no_merge  BOOLEAN     NOT NULL DEFAULT FALSE,
                    metadata          JSONB,
                    enabled           BOOLEAN     NOT NULL DEFAULT TRUE,
                    priority          INT         NOT NULL DEFAULT 100,
                    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (scope_type, scope_value, template_name)
                );

                CREATE TABLE IF NOT EXISTS meta.policy_waivers (
                    id                 BIGSERIAL   PRIMARY KEY,
                    repo               TEXT        NOT NULL,
                    pr_number          BIGINT      NOT NULL,
                    rule_set           TEXT        NOT NULL,
                    requested_by       TEXT        NOT NULL,
                    requested_role     TEXT        NOT NULL,
                    reason             TEXT        NOT NULL,
                    status             TEXT        NOT NULL DEFAULT 'pending',
                    expires_at         TIMESTAMPTZ NOT NULL,
                    requested_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    decided_at         TIMESTAMPTZ,
                    decided_by         TEXT,
                    decided_role       TEXT,
                    decision_notes     TEXT,
                    required_approvals INT         NOT NULL DEFAULT 1,
                    approval_chain     JSONB,
                    scope              JSONB,
                    metadata           JSONB,
                    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS meta.policy_waiver_approvals (
                    id           BIGSERIAL   PRIMARY KEY,
                    waiver_id    BIGINT      NOT NULL REFERENCES meta.policy_waivers(id) ON DELETE CASCADE,
                    approver     TEXT        NOT NULL,
                    approver_role TEXT       NOT NULL,
                    decision     TEXT        NOT NULL,
                    notes        TEXT,
                    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS meta.doc_rewrite_runs (
                    id                 BIGSERIAL    PRIMARY KEY,
                    repo               TEXT         NOT NULL,
                    pr_number          BIGINT       NOT NULL,
                    correlation_id     TEXT,
                    idempotency_key    TEXT,
                    rule_set           TEXT,
                    status             TEXT         NOT NULL,
                    reason             TEXT,
                    quality_gate_score NUMERIC(6,2),
                    bundle             JSONB,
                    emitted_event      JSONB,
                    emit_status        TEXT         NOT NULL DEFAULT 'pending',
                    emit_error         TEXT,
                    created_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                    updated_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW()
                );

                ALTER TABLE IF EXISTS meta.doc_rewrite_runs
                    ADD COLUMN IF NOT EXISTS emit_status TEXT NOT NULL DEFAULT 'pending';
                ALTER TABLE IF EXISTS meta.doc_rewrite_runs
                    ADD COLUMN IF NOT EXISTS emit_error  TEXT;

                CREATE TABLE IF NOT EXISTS meta.jobs (
                    id              BIGSERIAL   PRIMARY KEY,
                    job_type        TEXT        NOT NULL,
                    idempotency_key TEXT        NOT NULL UNIQUE,
                    correlation_id  TEXT,
                    status          TEXT        NOT NULL DEFAULT 'queued',
                    payload         JSONB,
                    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS meta.poison_pills (
                    id               BIGSERIAL   PRIMARY KEY,
                    source_topic     TEXT        NOT NULL,
                    source_partition INT         NOT NULL,
                    source_offset    TEXT        NOT NULL,
                    error            TEXT,
                    attempts         INT         NOT NULL DEFAULT 0,
                    payload_raw      TEXT,
                    correlation_id   TEXT,
                    idempotency_key  TEXT,
                    status           TEXT        NOT NULL DEFAULT 'quarantined',
                    requeue_count    INT         NOT NULL DEFAULT 0,
                    requeued_at      TIMESTAMPTZ,
                    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS meta.comment_state (
                    id           BIGSERIAL   PRIMARY KEY,
                    repo         TEXT        NOT NULL,
                    pr_number    BIGINT      NOT NULL,
                    fingerprint  TEXT        NOT NULL,
                    comment_key  TEXT        NOT NULL,
                    action       TEXT        NOT NULL DEFAULT 'create_comment',
                    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (repo, pr_number)
                );
                """
            )
        conn.commit()
