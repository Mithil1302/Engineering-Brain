
from typing import Optional, List
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status
from psycopg2.extras import RealDictCursor
import json

from ..dependencies import (
    get_db_conn, PG_CFG, auth_arch_scoped, enforce_repo_scope, AuthContext
)

router = APIRouter()

from ..simulation.time_travel import simulate_health
from ..simulation.impact_analyzer import (
    analyze_impact,
    simulate_failure_cascade,
    get_dependency_graph,
)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ImpactAnalysisRequest(BaseModel):
    repo: str
    change_description: str
    service_id: Optional[str] = None
    endpoint: Optional[str] = None


class FailureCascadeRequest(BaseModel):
    repo: str
    failing_service: str


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def _ensure_schema():
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE SCHEMA IF NOT EXISTS meta;
                CREATE TABLE IF NOT EXISTS meta.simulation_runs (
                    id BIGSERIAL PRIMARY KEY,
                    repo TEXT NOT NULL,
                    pr_number BIGINT,
                    sim_type TEXT NOT NULL DEFAULT 'time_travel',
                    horizon INT,
                    result JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)
        conn.commit()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/simulation/time-travel")
def simulation_time_travel(
    repo: str,
    pr_number: Optional[int] = None,
    horizon: int = 5,
    auth: AuthContext = Depends(auth_arch_scoped),
):
    """Time-travel simulation: project future health based on trends."""
    enforce_repo_scope(auth, repo)
    safe_horizon = max(1, min(horizon, 50))
    _ensure_schema()
    with get_db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, score::float8 AS score, grade, summary_status, created_at
                FROM meta.knowledge_health_snapshots
                WHERE (%s IS NULL OR repo = %s)
                  AND (%s IS NULL OR pr_number = %s)
                ORDER BY id DESC
                LIMIT 100
                """,
                (repo, repo, pr_number, pr_number),
            )
            history = [dict(r) for r in cur.fetchall()]

    result = simulate_health(history, horizon=safe_horizon)

    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO meta.simulation_runs (repo, pr_number, sim_type, horizon, result, created_at)
                VALUES (%s,%s,'time_travel',%s,%s::jsonb,NOW())
                """,
                (repo, pr_number, safe_horizon, json.dumps(result)),
            )
        conn.commit()
    return result


@router.post("/simulation/impact")
def simulation_impact(
    request: ImpactAnalysisRequest,
    auth: AuthContext = Depends(auth_arch_scoped),
):
    """What-if impact analysis with LLM-powered explanations."""
    enforce_repo_scope(auth, request.repo)

    result = analyze_impact(
        change_description=request.change_description,
        repo=request.repo,
        service_id=request.service_id,
        endpoint=request.endpoint,
        pg_cfg=PG_CFG,
    )

    # Persist
    _ensure_schema()
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO meta.simulation_runs (repo, sim_type, result, created_at)
                VALUES (%s, 'impact', %s::jsonb, NOW())
                """,
                (request.repo, json.dumps(result, default=str)),
            )
        conn.commit()

    return result


@router.post("/simulation/failure-cascade")
def simulation_failure_cascade(
    request: FailureCascadeRequest,
    auth: AuthContext = Depends(auth_arch_scoped),
):
    """Simulate what happens when a service goes down."""
    enforce_repo_scope(auth, request.repo)

    result = simulate_failure_cascade(
        failing_service=request.failing_service,
        repo=request.repo,
        pg_cfg=PG_CFG,
    )

    # Persist
    _ensure_schema()
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO meta.simulation_runs (repo, sim_type, result, created_at)
                VALUES (%s, 'failure_cascade', %s::jsonb, NOW())
                """,
                (request.repo, json.dumps(result, default=str)),
            )
        conn.commit()

    return result


@router.get("/simulation/graph")
def simulation_graph(
    repo: Optional[str] = None,
    auth: AuthContext = Depends(auth_arch_scoped),
):
    """Get the service dependency graph."""
    if not repo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="repo is required")
    enforce_repo_scope(auth, repo)
    return get_dependency_graph(repo, PG_CFG)


@router.get("/simulation/history")
def simulation_history(
    repo: Optional[str] = None,
    sim_type: Optional[str] = None,
    limit: int = 20,
    auth: AuthContext = Depends(auth_arch_scoped),
):
    """List past simulation runs."""
    if not repo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="repo is required")
    enforce_repo_scope(auth, repo)
    _ensure_schema()
    with get_db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, repo, pr_number, sim_type, horizon, result, created_at
                FROM meta.simulation_runs
                WHERE (%s IS NULL OR repo = %s)
                  AND (%s IS NULL OR sim_type = %s)
                ORDER BY id DESC
                LIMIT %s
                """,
                (repo, repo, sim_type, sim_type, min(limit, 100)),
            )
            rows = [dict(r) for r in cur.fetchall()]
    from datetime import datetime
    for r in rows:
        for k, v in r.items():
            if isinstance(v, datetime):
                r[k] = v.isoformat()
    return {"items": rows, "total": len(rows)}
