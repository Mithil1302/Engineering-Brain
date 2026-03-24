"""
KA-CHOW Contextual Onboarding Engine — LLM-Personalized Paths.

Replaces 3 hardcoded role dictionaries with:
  1. LLM-generated personalized learning paths based on repo context
  2. Tasks linked to actual files, PRs, and system components
  3. Progress tracking with adaptive difficulty
  4. Graph-aware context (services, health, recent activity)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from ..llm import get_llm_client
from ..llm.prompts import OnboardingPathPrompt

log = logging.getLogger("ka-chow.onboarding")


# ---------------------------------------------------------------------------
# System context gathering (for LLM prompt)
# ---------------------------------------------------------------------------

def _gather_onboarding_context(
    pg_cfg: Dict[str, Any],
    repo: str,
) -> Dict[str, Any]:
    """Gather system context for personalizing the onboarding path."""
    context: Dict[str, Any] = {
        "services": [],
        "health_score": None,
        "recent_policy_runs": [],
        "active_waivers": 0,
        "doc_coverage": "unknown",
    }

    try:
        with psycopg2.connect(**pg_cfg) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Health score
                cur.execute(
                    """
                    SELECT score::float8 AS score, grade
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
                    SELECT summary_status, merge_gate, created_at
                    FROM meta.policy_check_runs
                    WHERE repo = %s
                    ORDER BY id DESC LIMIT 5
                    """,
                    (repo,),
                )
                runs = [dict(r) for r in cur.fetchall()]
                for r in runs:
                    for k, v in r.items():
                        if isinstance(v, datetime):
                            r[k] = v.isoformat()
                context["recent_policy_runs"] = runs

                # Active waivers
                cur.execute(
                    """
                    SELECT COUNT(*)::int
                    FROM meta.policy_waivers
                    WHERE repo = %s AND status = 'approved'
                    """,
                    (repo,),
                )
                context["active_waivers"] = cur.fetchone()[0]

    except Exception as exc:
        log.warning("Onboarding context gathering failed: %s", exc)

    return context


# ---------------------------------------------------------------------------
# Onboarding persistence
# ---------------------------------------------------------------------------

_ENSURE_SQL = """
CREATE SCHEMA IF NOT EXISTS meta;
CREATE TABLE IF NOT EXISTS meta.onboarding_paths (
    id              BIGSERIAL PRIMARY KEY,
    repo            TEXT NOT NULL,
    role            TEXT NOT NULL,
    user_id         TEXT,
    path_title      TEXT,
    tasks           JSONB NOT NULL DEFAULT '[]',
    progress        JSONB NOT NULL DEFAULT '{}',
    llm_model       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_onboarding_repo_role ON meta.onboarding_paths (repo, role);
"""


def _ensure_schema(pg_cfg: Dict[str, Any]) -> None:
    try:
        with psycopg2.connect(**pg_cfg) as conn:
            with conn.cursor() as cur:
                cur.execute(_ENSURE_SQL)
            conn.commit()
    except Exception as exc:
        log.warning("Onboarding schema setup failed: %s", exc)


# ---------------------------------------------------------------------------
# LLM-powered onboarding
# ---------------------------------------------------------------------------

def build_onboarding_path(
    *,
    role: str,
    repo: str,
    pg_cfg: Dict[str, Any],
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a personalized onboarding path using LLM.

    Parameters
    ----------
    role : str
        The new team member's role (developer, architect, sre, platform-lead, etc.)
    repo : str
        Repository context.
    pg_cfg : dict
        PostgreSQL connection config.
    user_id : str, optional
        User identifier for progress tracking.
    """
    llm = get_llm_client()

    # Gather context
    system_context = _gather_onboarding_context(pg_cfg, repo)

    # Build prompt
    user_prompt = OnboardingPathPrompt.user_prompt(
        role=role,
        repo=repo,
        system_context=system_context,
    )

    try:
        resp = llm.generate(
            user_prompt,
            system_prompt=OnboardingPathPrompt.system_prompt,
            json_mode=True,
            json_schema=OnboardingPathPrompt.response_schema(),
            temperature=0.5,
            use_cache=False,
        )
        path = resp.as_json()
        if not isinstance(path, dict):
            path = _fallback_path(role, repo)

        llm_model = resp.model
    except Exception as exc:
        log.error("Onboarding path generation failed: %s", exc)
        path = _fallback_path(role, repo)
        llm_model = "fallback"

    # Persist
    _ensure_schema(pg_cfg)
    path_id = -1
    try:
        with psycopg2.connect(**pg_cfg) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO meta.onboarding_paths
                        (repo, role, user_id, path_title, tasks, progress, llm_model, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s::jsonb, '{}'::jsonb, %s, NOW(), NOW())
                    RETURNING id
                    """,
                    (
                        repo, role, user_id,
                        path.get("path_title", f"Onboarding for {role}"),
                        json.dumps(path.get("tasks", [])),
                        llm_model,
                    ),
                )
                path_id = cur.fetchone()[0]
            conn.commit()
    except Exception as exc:
        log.warning("Onboarding persistence failed: %s", exc)

    path["_meta"] = {
        "path_id": path_id,
        "llm_model": llm_model,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return path


def update_progress(
    *,
    path_id: int,
    task_sequence: int,
    completed: bool,
    pg_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    """Update task completion status in an onboarding path."""
    _ensure_schema(pg_cfg)
    try:
        with psycopg2.connect(**pg_cfg) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT tasks, progress FROM meta.onboarding_paths WHERE id = %s", (path_id,))
                row = cur.fetchone()
                if not row:
                    return {"error": f"Path {path_id} not found"}

                progress = row.get("progress") or {}
                if isinstance(progress, str):
                    progress = json.loads(progress)
                progress[str(task_sequence)] = {
                    "completed": completed,
                    "completed_at": datetime.now(timezone.utc).isoformat() if completed else None,
                }

                cur.execute(
                    "UPDATE meta.onboarding_paths SET progress = %s::jsonb, updated_at = NOW() WHERE id = %s",
                    (json.dumps(progress), path_id),
                )
            conn.commit()

        tasks = row.get("tasks") or []
        if isinstance(tasks, str):
            tasks = json.loads(tasks)
        total = len(tasks)
        done = sum(1 for v in progress.values() if isinstance(v, dict) and v.get("completed"))

        return {
            "path_id": path_id,
            "task_sequence": task_sequence,
            "completed": completed,
            "total_tasks": total,
            "completed_tasks": done,
            "progress_pct": round(done / total * 100, 1) if total > 0 else 0,
        }
    except Exception as exc:
        log.error("Progress update failed: %s", exc)
        return {"error": str(exc)}


def answer_question(question: str, repo: str, pg_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Answer an onboarding-related question using LLM."""
    llm = get_llm_client()
    context = _gather_onboarding_context(pg_cfg, repo)

    try:
        resp = llm.generate_json(
            json.dumps({
                "question": question,
                "repo": repo,
                "system_context": context,
                "task": "Answer this onboarding question with specific, actionable guidance.",
            }),
            system_prompt=(
                "You are a staff engineer helping onboard a new team member. "
                "Be specific, reference actual system components, and provide "
                "step-by-step instructions where applicable."
            ),
        )
        if isinstance(resp, dict):
            return resp
        return {"answer": str(resp), "confidence": 0.5}
    except Exception as exc:
        return {"answer": f"I couldn't answer: {exc}", "confidence": 0.0}


# ---------------------------------------------------------------------------
# Fallback (kept for resilience)
# ---------------------------------------------------------------------------

def _fallback_path(role: str, repo: str) -> Dict[str, Any]:
    """Template-based path when LLM is unavailable."""
    base_tasks = [
        {
            "sequence": 1,
            "title": "Explore the Repository",
            "objective": "Understand the project structure and key files",
            "description": f"Clone {repo} and explore the directory structure. Read the README and key config files.",
            "references": ["README.md", "docker-compose.yaml"],
            "exercises": ["List all services and their responsibilities"],
            "estimated_hours": 1,
            "verification": "Can describe the purpose of each top-level directory",
            "difficulty": "beginner",
        },
        {
            "sequence": 2,
            "title": "Run the System Locally",
            "objective": "Get the full system running on your machine",
            "description": "Use docker-compose to start all services. Verify health endpoints.",
            "references": ["docker-compose.yaml", "/healthz endpoints"],
            "exercises": ["Start all services", "Hit each /healthz endpoint"],
            "estimated_hours": 2,
            "verification": "All services return healthy status",
            "difficulty": "beginner",
        },
        {
            "sequence": 3,
            "title": "Understand the Policy Engine",
            "objective": "Learn how policy checks work",
            "description": "Read the policy engine code and understand how findings are generated.",
            "references": ["worker-service/app/policy/engine.py", "worker-service/app/policy/models.py"],
            "exercises": ["Run the policy chain test suite", "Read a policy check result"],
            "estimated_hours": 3,
            "verification": "Can explain how a PR triggers a policy check and what findings look like",
            "difficulty": "intermediate",
        },
    ]

    role_specific: Dict[str, List[Dict[str, Any]]] = {
        "developer": [
            {
                "sequence": 4,
                "title": "Make Your First Fix",
                "objective": "Submit a code change and see KA-CHOW in action",
                "description": "Create a branch, make a change, open a PR, and observe the policy check.",
                "references": ["PR workflow", "policy check output"],
                "exercises": ["Open a PR and trigger a policy check"],
                "estimated_hours": 2,
                "verification": "Successfully observed a policy check on your PR",
                "difficulty": "intermediate",
            },
        ],
        "architect": [
            {
                "sequence": 4,
                "title": "Review Architecture Plans",
                "objective": "Understand how architecture planning works",
                "description": "Use the /architecture/plan endpoint to generate and review plans.",
                "references": ["architecture/planner.py", "architecture/scaffolder.py"],
                "exercises": ["Generate a plan for a new service"],
                "estimated_hours": 3,
                "verification": "Generated and reviewed an architecture plan",
                "difficulty": "advanced",
            },
        ],
    }

    tasks = base_tasks + role_specific.get(role, [])

    return {
        "path_title": f"Onboarding for {role} on {repo}",
        "estimated_total_hours": sum(t.get("estimated_hours", 1) for t in tasks),
        "tasks": tasks,
        "prerequisites": ["Git installed", "Docker installed", "Access to the repository"],
    }
