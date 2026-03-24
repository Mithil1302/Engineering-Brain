"""
KA-CHOW Autonomous Architecture Planner — LLM-Powered Implementation.

Replaces hardcoded tag→template mapping with:
  1. LLM-driven architecture plan generation (Gemini)
  2. ADR (Architecture Decision Record) document generation
  3. Scaffold manifest creation (Dockerfiles, k8s YAML, OpenAPI specs)
  4. Plan persistence to PostgreSQL for audit trail
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from ..llm import get_llm_client
from ..llm.prompts import ArchitecturePlannerPrompt
from ..llm.chains import ReasoningChain
from .models import ArchitecturePlan, PlanArtifact

log = logging.getLogger("ka-chow.architecture")


# ---------------------------------------------------------------------------
# System context gathering
# ---------------------------------------------------------------------------

def _gather_system_context(
    pg_cfg: Dict[str, Any],
    repo: Optional[str],
) -> Dict[str, Any]:
    """
    Gather current system context from the database for LLM context.
    Includes: health scores, services, recent policy runs.
    """
    context: Dict[str, Any] = {
        "services": [],
        "endpoints": [],
        "health_score": None,
        "recent_policy_runs": [],
        "tech_stack": [
            "Python/FastAPI", "Node.js", "PostgreSQL", "Neo4j",
            "Kafka", "gRPC", "Docker", "Kubernetes",
        ],
    }

    try:
        with psycopg2.connect(**pg_cfg) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Latest health score
                if repo:
                    cur.execute(
                        """
                        SELECT score::float8 AS score, grade, summary_status
                        FROM meta.knowledge_health_snapshots
                        WHERE repo = %s
                        ORDER BY id DESC LIMIT 1
                        """,
                        (repo,),
                    )
                    row = cur.fetchone()
                    if row:
                        context["health_score"] = dict(row)

                # Recent policy runs
                cur.execute(
                    """
                    SELECT repo, pr_number, summary_status, merge_gate, created_at
                    FROM meta.policy_check_runs
                    WHERE (%s IS NULL OR repo = %s)
                    ORDER BY id DESC LIMIT 5
                    """,
                    (repo, repo),
                )
                runs = [dict(r) for r in cur.fetchall()]
                for r in runs:
                    for k, v in r.items():
                        if isinstance(v, datetime):
                            r[k] = v.isoformat()
                context["recent_policy_runs"] = runs

    except Exception as exc:
        log.warning("System context gathering failed: %s", exc)

    return context


# ---------------------------------------------------------------------------
# Plan persistence
# ---------------------------------------------------------------------------

_ENSURE_SQL = """
CREATE SCHEMA IF NOT EXISTS meta;
CREATE TABLE IF NOT EXISTS meta.architecture_plan_runs (
    id              BIGSERIAL PRIMARY KEY,
    repo            TEXT NOT NULL,
    pr_number       BIGINT,
    requirement     TEXT NOT NULL,
    plan            JSONB NOT NULL,
    adrs            JSONB NOT NULL DEFAULT '[]',
    scaffold        JSONB NOT NULL DEFAULT '{}',
    llm_model       TEXT,
    llm_tokens      INT DEFAULT 0,
    llm_latency_ms  FLOAT DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_arch_plans_repo ON meta.architecture_plan_runs (repo);
"""


def _persist_plan(
    pg_cfg: Dict[str, Any],
    *,
    repo: str,
    pr_number: Optional[int],
    requirement: str,
    plan: Dict[str, Any],
    adrs: List[Dict[str, Any]],
    scaffold: Dict[str, Any],
    llm_model: str,
    llm_tokens: int,
    llm_latency_ms: float,
) -> int:
    """Persist an architecture plan run. Returns the row ID."""
    try:
        with psycopg2.connect(**pg_cfg) as conn:
            with conn.cursor() as cur:
                cur.execute(_ENSURE_SQL)
                cur.execute(
                    """
                    INSERT INTO meta.architecture_plan_runs
                        (repo, pr_number, requirement, plan, adrs, scaffold,
                         llm_model, llm_tokens, llm_latency_ms, created_at)
                    VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s, NOW())
                    RETURNING id
                    """,
                    (
                        repo,
                        pr_number,
                        requirement,
                        json.dumps(plan),
                        json.dumps(adrs),
                        json.dumps(scaffold),
                        llm_model,
                        llm_tokens,
                        llm_latency_ms,
                    ),
                )
                row_id = int(cur.fetchone()[0])
            conn.commit()
        return row_id
    except Exception as exc:
        log.warning("Plan persistence failed: %s", exc)
        return -1


def _list_plans(
    pg_cfg: Dict[str, Any],
    *,
    repo: Optional[str],
    pr_number: Optional[int],
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """List past architecture plan runs."""
    try:
        with psycopg2.connect(**pg_cfg) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(_ENSURE_SQL)
                cur.execute(
                    """
                    SELECT id, repo, pr_number, requirement, plan, adrs, scaffold,
                           llm_model, llm_tokens, llm_latency_ms, created_at
                    FROM meta.architecture_plan_runs
                    WHERE (%s IS NULL OR repo = %s)
                      AND (%s IS NULL OR pr_number = %s)
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (repo, repo, pr_number, pr_number, max(1, min(limit, 100))),
                )
                rows = [dict(r) for r in cur.fetchall()]
                for r in rows:
                    for k, v in r.items():
                        if isinstance(v, datetime):
                            r[k] = v.isoformat()
                return rows
    except Exception as exc:
        log.warning("Plan listing failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# LLM-powered plan generation
# ---------------------------------------------------------------------------

def generate_architecture_plan(
    requirement: str,
    *,
    repo: str,
    pr_number: Optional[int] = None,
    pg_cfg: Optional[Dict[str, Any]] = None,
    constraints: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Generate a full architecture plan using LLM.

    Returns the plan dict with services, ADRs, risks, and migration steps.
    Also persists the plan to PostgreSQL if pg_cfg is provided.
    """
    llm = get_llm_client()

    # Gather system context
    system_context = {}
    if pg_cfg:
        system_context = _gather_system_context(pg_cfg, repo)

    # Build prompt
    user_prompt = ArchitecturePlannerPrompt.user_prompt(
        requirement=requirement,
        system_context=system_context,
        constraints=constraints,
    )

    # Generate plan
    try:
        resp = llm.generate(
            user_prompt,
            system_prompt=ArchitecturePlannerPrompt.system_prompt,
            json_mode=True,
            json_schema=ArchitecturePlannerPrompt.response_schema(),
            temperature=0.4,
            use_cache=False,
        )
        plan = resp.as_json()
        if not isinstance(plan, dict):
            plan = {"title": "Generated Plan", "summary": str(plan), "services": [], "adrs": [], "risks": []}

        llm_model = resp.model
        llm_tokens = resp.input_tokens + resp.output_tokens
        llm_latency_ms = resp.latency_ms
    except Exception as exc:
        log.error("Architecture plan generation failed: %s", exc)
        plan = {
            "title": "Plan Generation Failed",
            "summary": f"LLM call failed: {exc}",
            "services": [],
            "adrs": [],
            "risks": [{"description": str(exc), "severity": "high", "mitigation": "Retry or check LLM configuration"}],
        }
        llm_model = "error"
        llm_tokens = 0
        llm_latency_ms = 0

    # Persist
    plan_id = -1
    if pg_cfg:
        plan_id = _persist_plan(
            pg_cfg,
            repo=repo,
            pr_number=pr_number,
            requirement=requirement,
            plan=plan,
            adrs=plan.get("adrs", []),
            scaffold={},
            llm_model=llm_model,
            llm_tokens=llm_tokens,
            llm_latency_ms=llm_latency_ms,
        )

    plan["_meta"] = {
        "plan_id": plan_id,
        "llm_model": llm_model,
        "llm_tokens": llm_tokens,
        "llm_latency_ms": llm_latency_ms,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    return plan


def generate_adr(
    title: str,
    context: str,
    *,
    repo: str,
    system_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate a standalone Architecture Decision Record using LLM.
    """
    llm = get_llm_client()

    prompt = json.dumps({
        "title": title,
        "context": context,
        "repo": repo,
        "system_info": system_context or {},
        "task": "Generate a detailed ADR following the standard template: Title, Status, Context, Decision, Consequences, Alternatives Considered.",
    })

    try:
        resp = llm.generate_json(
            prompt,
            system_prompt=(
                "You are a principal architect writing Architecture Decision Records (ADRs). "
                "Follow the Michael Nygard ADR template exactly. Be specific and actionable."
            ),
            json_schema={
                "type": "object",
                "properties": {
                    "adr_number": {"type": "integer"},
                    "title": {"type": "string"},
                    "status": {"type": "string"},
                    "context": {"type": "string"},
                    "decision": {"type": "string"},
                    "consequences": {"type": "string"},
                    "alternatives": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "option": {"type": "string"},
                                "pros": {"type": "array", "items": {"type": "string"}},
                                "cons": {"type": "array", "items": {"type": "string"}},
                            },
                        },
                    },
                    "markdown": {"type": "string"},
                },
                "required": ["title", "context", "decision", "consequences", "markdown"],
            },
        )
        return resp if isinstance(resp, dict) else {"title": title, "markdown": str(resp)}
    except Exception as exc:
        log.error("ADR generation failed: %s", exc)
        return {
            "title": title,
            "status": "Error",
            "context": context,
            "decision": f"Generation failed: {exc}",
            "consequences": "N/A",
            "markdown": f"# ADR: {title}\n\n**Error:** {exc}",
        }
