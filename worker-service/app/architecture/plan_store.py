from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

_ENSURE_SQL = """
CREATE SCHEMA IF NOT EXISTS meta;
CREATE TABLE IF NOT EXISTS meta.architecture_plan_runs (
    id BIGSERIAL PRIMARY KEY,
    repo TEXT NOT NULL,
    pr_number BIGINT,
    requirement TEXT NOT NULL,
    plan JSONB NOT NULL,
    adrs JSONB NOT NULL DEFAULT '[]',
    scaffold JSONB NOT NULL DEFAULT '{}',
    extracted_constraints JSONB NOT NULL DEFAULT '{}',
    conflicts JSONB NOT NULL DEFAULT '[]',
    ambiguity_report JSONB NOT NULL DEFAULT '{}',
    clarification_questions JSONB NOT NULL DEFAULT '[]',
    llm_model TEXT,
    llm_tokens INT DEFAULT 0,
    llm_latency_ms FLOAT DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_arch_plans_repo ON meta.architecture_plan_runs (repo);
"""


def ensure_architecture_schema(pg_cfg: Dict[str, Any]) -> None:
    with psycopg2.connect(**pg_cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(_ENSURE_SQL)
        conn.commit()


def persist_plan_run(
    pg_cfg: Dict[str, Any],
    *,
    repo: str,
    pr_number: Optional[int],
    requirement: str,
    plan_payload: Dict[str, Any],
) -> int:
    ensure_architecture_schema(pg_cfg)
    with psycopg2.connect(**pg_cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO meta.architecture_plan_runs
                    (repo, pr_number, requirement, plan, adrs, scaffold,
                     extracted_constraints, conflicts, ambiguity_report, clarification_questions,
                     llm_model, llm_tokens, llm_latency_ms, created_at)
                VALUES
                    (%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s,NOW())
                RETURNING id
                """,
                (
                    repo,
                    pr_number,
                    requirement,
                    json.dumps(plan_payload),
                    json.dumps(plan_payload.get("adrs", [])),
                    json.dumps(plan_payload.get("scaffold", {})),
                    json.dumps(plan_payload.get("extracted_constraints", {})),
                    json.dumps((plan_payload.get("extracted_constraints", {}) or {}).get("conflicts", [])),
                    json.dumps((plan_payload.get("extracted_constraints", {}) or {}).get("ambiguity_report", {})),
                    json.dumps((plan_payload.get("extracted_constraints", {}) or {}).get("clarification_questions", [])),
                    (plan_payload.get("_meta") or {}).get("llm_model"),
                    int((plan_payload.get("_meta") or {}).get("llm_tokens", 0)),
                    float((plan_payload.get("_meta") or {}).get("llm_latency_ms", 0.0)),
                ),
            )
            row_id = int(cur.fetchone()[0])
        conn.commit()
    return row_id


def list_plan_runs(
    pg_cfg: Dict[str, Any],
    *,
    repo: Optional[str],
    pr_number: Optional[int],
    limit: int = 20,
) -> List[Dict[str, Any]]:
    ensure_architecture_schema(pg_cfg)
    with psycopg2.connect(**pg_cfg) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT *
                FROM meta.architecture_plan_runs
                WHERE (%s IS NULL OR repo = %s)
                  AND (%s IS NULL OR pr_number = %s)
                ORDER BY id DESC
                LIMIT %s
                """,
                (repo, repo, pr_number, pr_number, max(1, min(limit, 200))),
            )
            rows = [dict(r) for r in cur.fetchall()]

    for r in rows:
        for k, v in list(r.items()):
            if isinstance(v, datetime):
                r[k] = v.isoformat()
    return rows


def get_plan_by_id(pg_cfg: Dict[str, Any], plan_id: int) -> Optional[Dict[str, Any]]:
    ensure_architecture_schema(pg_cfg)
    with psycopg2.connect(**pg_cfg) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM meta.architecture_plan_runs WHERE id = %s", (plan_id,))
            row = cur.fetchone()
            if not row:
                return None
            out = dict(row)
            for k, v in list(out.items()):
                if isinstance(v, datetime):
                    out[k] = v.isoformat()
            return out
