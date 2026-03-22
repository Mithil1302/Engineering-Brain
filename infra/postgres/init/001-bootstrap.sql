-- Bootstrap app schemas and metadata tables for KA-CHOW

CREATE SCHEMA IF NOT EXISTS meta;

CREATE TABLE IF NOT EXISTS meta.jobs (
  id BIGSERIAL PRIMARY KEY,
  job_type TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  correlation_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (idempotency_key)
);

CREATE TABLE IF NOT EXISTS meta.policies (
  id BIGSERIAL PRIMARY KEY,
  policy_name TEXT NOT NULL,
  scope TEXT NOT NULL,
  config JSONB NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (policy_name, scope)
);

CREATE TABLE IF NOT EXISTS meta.audit_logs (
  id BIGSERIAL PRIMARY KEY,
  timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  correlation_id TEXT,
  request_id TEXT,
  entities JSONB,
  result JSONB,
  metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON meta.audit_logs (timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_action ON meta.audit_logs (action);
CREATE INDEX IF NOT EXISTS idx_audit_correlation ON meta.audit_logs (correlation_id);

CREATE TABLE IF NOT EXISTS meta.embedding_metadata (
  chunk_id TEXT PRIMARY KEY,
  source_type TEXT NOT NULL,
  repo TEXT,
  path TEXT,
  line_start INT,
  line_end INT,
  op_id TEXT,
  entity_refs JSONB,
  content_hash TEXT NOT NULL,
  tags JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON meta.jobs (status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON meta.jobs (created_at);
CREATE INDEX IF NOT EXISTS idx_embedding_hash ON meta.embedding_metadata (content_hash);

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

CREATE TABLE IF NOT EXISTS meta.poison_pills (
  id BIGSERIAL PRIMARY KEY,
  source_topic TEXT NOT NULL,
  source_partition INT NOT NULL,
  source_offset TEXT NOT NULL,
  error TEXT NOT NULL,
  attempts INT NOT NULL,
  payload_raw TEXT NOT NULL,
  correlation_id TEXT,
  idempotency_key TEXT,
  status TEXT NOT NULL DEFAULT 'quarantined',
  requeue_count INT NOT NULL DEFAULT 0,
  requeued_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_processed_events_first_seen ON meta.processed_events (first_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_poison_pills_status ON meta.poison_pills (status);
CREATE INDEX IF NOT EXISTS idx_poison_pills_created_at ON meta.poison_pills (created_at DESC);

CREATE TABLE IF NOT EXISTS meta.pr_comment_state (
  id BIGSERIAL PRIMARY KEY,
  comment_key TEXT NOT NULL UNIQUE,
  repo TEXT NOT NULL,
  pr_number BIGINT NOT NULL,
  rule_set TEXT NOT NULL,
  latest_fingerprint TEXT NOT NULL,
  delivery_count INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS meta.policy_check_runs (
  id BIGSERIAL PRIMARY KEY,
  repo TEXT NOT NULL,
  pr_number BIGINT NOT NULL,
  correlation_id TEXT,
  idempotency_key TEXT,
  summary_status TEXT NOT NULL,
  findings JSONB NOT NULL,
  markdown_comment TEXT NOT NULL,
  suggested_patches JSONB,
  check_annotations JSONB,
  merge_gate JSONB,
  doc_refresh_plan JSONB,
  knowledge_health JSONB,
  action TEXT NOT NULL,
  deduped BOOLEAN NOT NULL DEFAULT FALSE,
  comment_state_id BIGINT REFERENCES meta.pr_comment_state(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE meta.policy_check_runs ADD COLUMN IF NOT EXISTS merge_gate JSONB;
ALTER TABLE meta.policy_check_runs ADD COLUMN IF NOT EXISTS doc_refresh_plan JSONB;
ALTER TABLE meta.policy_check_runs ADD COLUMN IF NOT EXISTS knowledge_health JSONB;

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
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_doc_refresh_jobs_repo_pr_created ON meta.doc_refresh_jobs (repo, pr_number, created_at DESC);

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

CREATE INDEX IF NOT EXISTS idx_knowledge_health_repo_pr_created ON meta.knowledge_health_snapshots (repo, pr_number, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_pr_comment_state_repo_pr ON meta.pr_comment_state (repo, pr_number);
CREATE INDEX IF NOT EXISTS idx_policy_runs_repo_pr_created ON meta.policy_check_runs (repo, pr_number, created_at DESC);

CREATE TABLE IF NOT EXISTS meta.github_delivery_state (
  id BIGSERIAL PRIMARY KEY,
  comment_key TEXT NOT NULL UNIQUE,
  tenant_id TEXT,
  installation_id TEXT,
  repo_full_name TEXT NOT NULL,
  pr_number BIGINT NOT NULL,
  check_run_id BIGINT,
  comment_id BIGINT,
  last_action TEXT,
  last_status TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS meta.github_delivery_attempts (
  id BIGSERIAL PRIMARY KEY,
  comment_key TEXT,
  tenant_id TEXT,
  installation_id TEXT,
  repo_full_name TEXT,
  pr_number BIGINT,
  action TEXT,
  success BOOLEAN NOT NULL,
  status_code INT,
  error TEXT,
  request_payload JSONB,
  response_payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_github_delivery_state_repo_pr ON meta.github_delivery_state (repo_full_name, pr_number);
CREATE INDEX IF NOT EXISTS idx_github_delivery_attempts_created ON meta.github_delivery_attempts (created_at DESC);

ALTER TABLE meta.github_delivery_state ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE meta.github_delivery_state ADD COLUMN IF NOT EXISTS installation_id TEXT;
ALTER TABLE meta.github_delivery_attempts ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE meta.github_delivery_attempts ADD COLUMN IF NOT EXISTS installation_id TEXT;

CREATE TABLE IF NOT EXISTS meta.tenant_installations (
  id BIGSERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  repo_full_name TEXT NOT NULL,
  installation_id TEXT NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  metadata JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (tenant_id, repo_full_name)
);

CREATE INDEX IF NOT EXISTS idx_tenant_installations_tenant_repo ON meta.tenant_installations (tenant_id, repo_full_name);

CREATE TABLE IF NOT EXISTS meta.architecture_plan_runs (
  id BIGSERIAL PRIMARY KEY,
  repo TEXT NOT NULL,
  pr_number BIGINT,
  correlation_id TEXT,
  plan_id TEXT NOT NULL,
  intent_tags JSONB,
  requirement JSONB NOT NULL,
  decisions JSONB NOT NULL,
  services JSONB NOT NULL,
  infrastructure JSONB NOT NULL,
  artifacts JSONB NOT NULL,
  status TEXT NOT NULL DEFAULT 'planned',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_arch_plan_runs_repo_pr_created ON meta.architecture_plan_runs (repo, pr_number, created_at DESC);

CREATE TABLE IF NOT EXISTS meta.onboarding_paths (
  id BIGSERIAL PRIMARY KEY,
  repo TEXT NOT NULL,
  pr_number BIGINT,
  role TEXT NOT NULL,
  path JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS meta.simulation_runs (
  id BIGSERIAL PRIMARY KEY,
  repo TEXT NOT NULL,
  pr_number BIGINT,
  horizon INT NOT NULL,
  result JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS meta.autofix_runs (
  id BIGSERIAL PRIMARY KEY,
  repo TEXT NOT NULL,
  pr_number BIGINT,
  workflow JSONB NOT NULL,
  status TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_onboarding_repo_pr_created ON meta.onboarding_paths (repo, pr_number, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_simulation_repo_pr_created ON meta.simulation_runs (repo, pr_number, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_autofix_repo_pr_created ON meta.autofix_runs (repo, pr_number, created_at DESC);
