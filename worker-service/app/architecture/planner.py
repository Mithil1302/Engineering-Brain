"""Advanced architecture planner orchestration and persistence APIs."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from ..llm import get_llm_client
from .plan_store import (
    ensure_architecture_schema,
    get_plan_by_id,
    list_plan_runs,
    persist_plan_run,
)
from .planner_engine import (
    persist_advanced_graph_projection,
    run_advanced_architecture_pipeline,
)
from .refinement_engine import (
    apply_constraint_overrides,
    build_partial_regeneration_plan,
    compute_plan_diff,
)

log = logging.getLogger("ka-chow.architecture")


def _gather_system_context(
    pg_cfg: Dict[str, Any],
    repo: Optional[str],
) -> Dict[str, Any]:
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
                    for k, v in list(r.items()):
                        if isinstance(v, datetime):
                            r[k] = v.isoformat()
                context["recent_policy_runs"] = runs
    except Exception as exc:
        log.warning("System context gathering failed: %s", exc)

    return context


def _list_plans(
    pg_cfg: Dict[str, Any],
    *,
    repo: Optional[str],
    pr_number: Optional[int],
    limit: int = 20,
) -> List[Dict[str, Any]]:
    return list_plan_runs(pg_cfg, repo=repo, pr_number=pr_number, limit=limit)


def generate_architecture_plan(
    requirement: str,
    *,
    repo: str,
    pr_number: Optional[int] = None,
    pg_cfg: Optional[Dict[str, Any]] = None,
    constraints: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if not pg_cfg:
        raise ValueError("pg_cfg is required for advanced architecture planning")

    ensure_architecture_schema(pg_cfg)
    plan = run_advanced_architecture_pipeline(
        requirement=requirement,
        repo=repo,
        pr_number=pr_number,
        pg_cfg=pg_cfg,
        constraints=constraints,
    )

    plan_id = persist_plan_run(
        pg_cfg,
        repo=repo,
        pr_number=pr_number,
        requirement=requirement,
        plan_payload=plan,
    )

    plan.setdefault("_meta", {})["plan_id"] = plan_id
    try:
        persist_advanced_graph_projection(pg_cfg, repo, plan_id, plan)
    except Exception as exc:
        log.warning("graph projection persistence failed: %s", exc)

    # refresh graph mutation payload with final plan id
    for m in plan.get("graph_mutations", []) or []:
        payload = m.get("payload_json")
        try:
            data = json.loads(payload or "{}")
            data["plan_id"] = plan_id
            m["payload_json"] = json.dumps(data)
        except Exception:
            continue

    return plan


def refine_architecture_plan(
    *,
    repo: str,
    base_plan_id: int,
    requirement_delta: Optional[str],
    constraint_overrides: Dict[str, Any],
    pg_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    base = get_plan_by_id(pg_cfg, base_plan_id)
    if not base:
        raise ValueError(f"Base plan {base_plan_id} not found")

    base_requirement = str(base.get("requirement") or "")
    merged_requirement = base_requirement
    if requirement_delta:
        merged_requirement = f"{base_requirement}\n\nDelta:\n{requirement_delta.strip()}"
    merged_requirement = apply_constraint_overrides(merged_requirement, constraint_overrides)

    plan = run_advanced_architecture_pipeline(
        requirement=merged_requirement,
        repo=repo,
        pr_number=base.get("pr_number"),
        pg_cfg=pg_cfg,
        constraints=[f"{k}={v}" for k, v in constraint_overrides.items()],
    )

    new_plan_id = persist_plan_run(
        pg_cfg,
        repo=repo,
        pr_number=base.get("pr_number"),
        requirement=merged_requirement,
        plan_payload=plan,
    )
    plan.setdefault("_meta", {})["plan_id"] = new_plan_id

    base_payload = base.get("plan") if isinstance(base.get("plan"), dict) else {}
    diff = compute_plan_diff(
        base_payload,
        plan,
        changed_constraints=list(constraint_overrides.keys()),
    )
    partial = build_partial_regeneration_plan(diff)

    return {
        "repo": repo,
        "base_plan_id": base_plan_id,
        "new_plan_id": new_plan_id,
        "diff": diff.model_dump(),
        "partial_regeneration": partial,
        "plan": plan,
    }


def diff_architecture_plans(
    *,
    repo: str,
    base_plan_id: int,
    new_plan_id: int,
    pg_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    base = get_plan_by_id(pg_cfg, base_plan_id)
    new = get_plan_by_id(pg_cfg, new_plan_id)
    if not base or not new:
        raise ValueError("one or both plans not found")

    base_payload = base.get("plan") if isinstance(base.get("plan"), dict) else {}
    new_payload = new.get("plan") if isinstance(new.get("plan"), dict) else {}
    changed_constraints = []
    try:
        base_constraints = (base_payload.get("extracted_constraints") or {}).get("constraints", [])
        new_constraints = (new_payload.get("extracted_constraints") or {}).get("constraints", [])
        if base_constraints != new_constraints:
            changed_constraints = ["constraints_updated"]
    except Exception:
        changed_constraints = []

    diff = compute_plan_diff(base_payload, new_payload, changed_constraints)
    return {
        "repo": repo,
        "base_plan_id": base_plan_id,
        "new_plan_id": new_plan_id,
        "diff": diff.model_dump(),
    }


def generate_adr(
    title: str,
    context: str,
    *,
    repo: str,
    system_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    llm = get_llm_client()
    prompt = json.dumps(
        {
            "title": title,
            "context": context,
            "repo": repo,
            "system_info": system_context or {},
            "task": "Generate a full ADR template with context, decision, alternatives, consequences, risks and rollback notes.",
        }
    )
    try:
        resp = llm.generate_json(
            prompt,
            system_prompt=(
                "You are a principal architect writing Architecture Decision Records. "
                "Return JSON and include markdown field with complete ADR document."
            ),
            json_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "status": {"type": "string"},
                    "context": {"type": "string"},
                    "decision": {"type": "string"},
                    "alternatives": {"type": "array", "items": {"type": "string"}},
                    "consequences": {"type": "string"},
                    "risks": {"type": "array", "items": {"type": "string"}},
                    "rollback_notes": {"type": "string"},
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
            "status": "error",
            "context": context,
            "decision": f"Generation failed: {exc}",
            "alternatives": [],
            "consequences": "N/A",
            "risks": [str(exc)],
            "rollback_notes": "N/A",
            "markdown": f"# ADR: {title}\n\nError: {exc}",
        }
