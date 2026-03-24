
from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status
import json

from ..dependencies import (
    PG_CFG, get_db_conn, auth_read_scoped, enforce_repo_scope, AuthContext
)

router = APIRouter()

from ..onboarding.engine import (
    build_onboarding_path,
    update_progress,
    answer_question as onboarding_answer,
)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class OnboardingPathRequest(BaseModel):
    repo: str
    role: str = "developer"
    user_id: Optional[str] = None


class ProgressUpdateRequest(BaseModel):
    path_id: int
    task_sequence: int
    completed: bool = True


class OnboardingQuestionRequest(BaseModel):
    question: str
    repo: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/onboarding/path")
def onboarding_path(
    request: OnboardingPathRequest,
    auth: AuthContext = Depends(auth_read_scoped),
):
    """Generate a personalized onboarding path using LLM."""
    enforce_repo_scope(auth, request.repo)
    path = build_onboarding_path(
        role=request.role,
        repo=request.repo,
        pg_cfg=PG_CFG,
        user_id=request.user_id or auth.subject,
    )
    return path


@router.post("/onboarding/progress")
def onboarding_progress(
    request: ProgressUpdateRequest,
    auth: AuthContext = Depends(auth_read_scoped),
):
    """Update task completion status in an onboarding path."""
    result = update_progress(
        path_id=request.path_id,
        task_sequence=request.task_sequence,
        completed=request.completed,
        pg_cfg=PG_CFG,
    )
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])
    return result


@router.post("/onboarding/ask")
def onboarding_ask(
    request: OnboardingQuestionRequest,
    auth: AuthContext = Depends(auth_read_scoped),
):
    """Answer an onboarding question using LLM."""
    enforce_repo_scope(auth, request.repo)
    return onboarding_answer(request.question, request.repo, PG_CFG)


@router.get("/onboarding/history")
def onboarding_history(
    repo: Optional[str] = None,
    role: Optional[str] = None,
    limit: int = 20,
    auth: AuthContext = Depends(auth_read_scoped),
):
    """List past onboarding paths."""
    if not repo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="repo is required")
    enforce_repo_scope(auth, repo)
    try:
        from psycopg2.extras import RealDictCursor
        from ..onboarding.engine import _ensure_schema
        _ensure_schema(PG_CFG)
        with get_db_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, repo, role, user_id, path_title, tasks, progress,
                           llm_model, created_at, updated_at
                    FROM meta.onboarding_paths
                    WHERE (%s IS NULL OR repo = %s)
                      AND (%s IS NULL OR role = %s)
                    ORDER BY id DESC LIMIT %s
                    """,
                    (repo, repo, role, role, min(limit, 100)),
                )
                rows = [dict(r) for r in cur.fetchall()]
                from datetime import datetime
                for r in rows:
                    for k, v in r.items():
                        if isinstance(v, datetime):
                            r[k] = v.isoformat()
                return {"items": rows, "total": len(rows)}
    except Exception as exc:
        return {"items": [], "total": 0, "error": str(exc)}
