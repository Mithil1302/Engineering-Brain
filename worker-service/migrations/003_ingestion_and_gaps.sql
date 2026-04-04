-- Migration 003: Ingestion pipeline, QA event log, Slack sessions, Check Run tracking
-- All statements use IF NOT EXISTS for idempotency.
-- Run by ensure_schema() in pipeline.py at startup.

-- Ingestion runs tracking
CREATE TABLE IF NOT EXISTS meta.ingestion_runs (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    repo             TEXT        NOT NULL,
    triggered_by     TEXT        NOT NULL,   -- 'webhook', 'manual', 'scheduled'
    started_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at     TIMESTAMPTZ,
    files_processed  INTEGER     DEFAULT 0,
    chunks_created   INTEGER     DEFAULT 0,
    embeddings_created INTEGER   DEFAULT 0,
    services_detected INTEGER    DEFAULT 0,
    status           TEXT        NOT NULL DEFAULT 'running',  -- 'running', 'success', 'failed'
    error_message    TEXT,
    commit_sha       TEXT
);

CREATE INDEX IF NOT EXISTS idx_ingestion_runs_repo
    ON meta.ingestion_runs (repo, started_at DESC);

-- QA event log for gap detection
CREATE TABLE IF NOT EXISTS meta.qa_event_log (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    question         TEXT        NOT NULL,
    intent           TEXT,
    sub_intent       TEXT,
    confidence       FLOAT,
    chunk_count      INTEGER,
    top_chunk_source TEXT,
    had_rag_results  BOOLEAN     NOT NULL DEFAULT FALSE,
    session_id       TEXT,
    repo             TEXT        NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_qa_event_log_repo_created
    ON meta.qa_event_log (repo, created_at DESC);

-- Partial index for gap detection queries (only no-RAG rows — stays small)
CREATE INDEX IF NOT EXISTS idx_qa_event_log_gap_detection
    ON meta.qa_event_log (repo, confidence, created_at DESC)
    WHERE had_rag_results = false;

-- Slack session continuity
CREATE TABLE IF NOT EXISTS meta.slack_sessions (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    slack_channel  TEXT        NOT NULL,
    slack_user     TEXT        NOT NULL,
    session_id     TEXT        NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (slack_channel, slack_user)
);

-- GitHub Check Run tracking (allows pipeline.py to update Check Run after policy eval)
CREATE TABLE IF NOT EXISTS meta.check_run_tracking (
    repo          TEXT    NOT NULL,
    pr_number     INTEGER NOT NULL,
    head_sha      TEXT    NOT NULL,
    check_run_id  BIGINT  NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (repo, pr_number, head_sha)
);

-- Graph nodes mirror (PostgreSQL fallback for Impact Analyzer when Neo4j is unavailable)
CREATE TABLE IF NOT EXISTS meta.graph_nodes (
    node_id    TEXT        NOT NULL,
    repo       TEXT        NOT NULL,
    node_type  TEXT        NOT NULL,  -- 'service', 'api', 'schema'
    label      TEXT        NOT NULL,
    properties JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (node_id, repo)
);

CREATE INDEX IF NOT EXISTS idx_graph_nodes_repo_type
    ON meta.graph_nodes (repo, node_type);

CREATE INDEX IF NOT EXISTS idx_graph_nodes_label
    ON meta.graph_nodes (repo, node_type, label);

-- Temporal graph enhancements for Task 3.5
-- Add event_type and event_payload columns to architecture_snapshots for policy finding events

-- 3.5.1: Add event_type column (values: 'ingestion', 'policy_finding')
ALTER TABLE meta.architecture_snapshots 
    ADD COLUMN IF NOT EXISTS event_type TEXT;

-- 3.5.2: Add event_payload column (NULL for ingestion snapshots, populated for policy finding events)
ALTER TABLE meta.architecture_snapshots 
    ADD COLUMN IF NOT EXISTS event_payload JSONB;

-- 3.5.3: Add unique constraint on snapshot_id (required for ON CONFLICT in record_policy_event())
-- Note: snapshot_id is already PRIMARY KEY, so this constraint is implicitly satisfied.
-- This comment documents that the PRIMARY KEY constraint serves the ON CONFLICT requirement.

-- 3.5.4: Advisory note on idx_arch_nodes_temporal
-- The index idx_arch_nodes_temporal on meta.architecture_nodes (repo, valid_from, valid_to)
-- is advisory and will be prompted by _verify_temporal_index() at runtime.
-- It is NOT included in this migration to avoid errors if meta.architecture_nodes
-- schema varies across deployments.
