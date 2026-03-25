
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Request, HTTPException, status

from ..dependencies import (
    pipeline, get_db_conn, PG_CFG, auth_arch_scoped,
    audit_event, enforce_repo_scope, AuthContext
)

router = APIRouter()

from ..architecture.models import ArchitecturePlanRequest, RefinePlanRequest
from ..architecture.planner import (
    generate_architecture_plan,
    generate_adr,
    _list_plans,
    _gather_system_context,
    refine_architecture_plan,
    diff_architecture_plans,
)
from ..architecture.scaffolder import generate_scaffold
from ..architecture.explorer import build_architecture_explorer


# ---------------------------------------------------------------------------
# Request / response models for new endpoints
# ---------------------------------------------------------------------------

class ScaffoldRequest(BaseModel):
    repo: str
    requirement: str
    pr_number: Optional[int] = None
    constraints: Optional[List[str]] = None
    include_types: Optional[List[str]] = Field(
        default=None,
        description="Filter: dockerfile, docker-compose, openapi, k8s, migration, readme",
    )


class ADRRequest(BaseModel):
    repo: str
    title: str
    context: str


class ArchitectureDiffRequest(BaseModel):
    repo: str
    base_plan_id: int
    new_plan_id: int


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/architecture/plan")
def architecture_plan(
    request: ArchitecturePlanRequest,
    http_request: Request,
    auth: AuthContext = Depends(auth_arch_scoped),
):
    """Generate an LLM-powered architecture plan."""
    enforce_repo_scope(auth, request.repo)

    plan = generate_architecture_plan(
        requirement=request.requirement.requirement_text,
        repo=request.repo,
        pr_number=request.pr_number,
        pg_cfg=PG_CFG,
        constraints=request.constraints,
    )

    audit_event(
        actor=auth.subject,
        action="architecture_plan_create",
        result={"status": "success", "plan_id": plan.get("_meta", {}).get("plan_id")},
        role=auth.role,
        tenant_id=auth.tenant_id,
        correlation_id=http_request.headers.get("x-correlation-id"),
        request_id=http_request.headers.get("x-request-id"),
        entities={"repo": request.repo, "pr_number": request.pr_number},
    )
    return plan


@router.get("/architecture/plans")
def architecture_plans(
    repo: Optional[str] = None,
    pr_number: Optional[int] = None,
    limit: int = 50,
    auth: AuthContext = Depends(auth_arch_scoped),
):
    """List past architecture plan runs."""
    if not repo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="repo is required")
    enforce_repo_scope(auth, repo)
    rows = _list_plans(PG_CFG, repo=repo, pr_number=pr_number, limit=limit)
    return {"items": rows, "total": len(rows)}


@router.post("/architecture/scaffold")
def architecture_scaffold(
    request: ScaffoldRequest,
    http_request: Request,
    auth: AuthContext = Depends(auth_arch_scoped),
):
    """Generate a full architecture plan + scaffold files."""
    enforce_repo_scope(auth, request.repo)

    # Step 1: Generate plan
    plan = generate_architecture_plan(
        requirement=request.requirement,
        repo=request.repo,
        pr_number=request.pr_number,
        pg_cfg=PG_CFG,
        constraints=request.constraints,
    )

    # Step 2: Generate scaffold from plan
    files = generate_scaffold(
        plan,
        repo=request.repo,
        include_types=request.include_types,
    )

    audit_event(
        actor=auth.subject,
        action="architecture_scaffold_create",
        result={"status": "success", "file_count": len(files)},
        role=auth.role,
        tenant_id=auth.tenant_id,
        correlation_id=http_request.headers.get("x-correlation-id"),
        request_id=http_request.headers.get("x-request-id"),
        entities={"repo": request.repo},
    )

    return {
        "plan": plan,
        "scaffold_files": files,
        "file_count": len(files),
    }


@router.post("/architecture/refine")
def architecture_refine(
    request: RefinePlanRequest,
    http_request: Request,
    auth: AuthContext = Depends(auth_arch_scoped),
):
    enforce_repo_scope(auth, request.repo)
    result = refine_architecture_plan(
        repo=request.repo,
        base_plan_id=request.base_plan_id,
        requirement_delta=request.requirement_delta,
        constraint_overrides=request.constraint_overrides,
        pg_cfg=PG_CFG,
    )
    audit_event(
        actor=auth.subject,
        action="architecture_plan_refine",
        result={"status": "success", "new_plan_id": result.get("new_plan_id")},
        role=auth.role,
        tenant_id=auth.tenant_id,
        correlation_id=http_request.headers.get("x-correlation-id"),
        request_id=http_request.headers.get("x-request-id"),
        entities={"repo": request.repo, "base_plan_id": request.base_plan_id},
    )
    return result


@router.get("/architecture/plan/{base_plan_id}/diff/{new_plan_id}")
def architecture_plan_diff(
    base_plan_id: int,
    new_plan_id: int,
    repo: str,
    auth: AuthContext = Depends(auth_arch_scoped),
):
    enforce_repo_scope(auth, repo)
    return diff_architecture_plans(
        repo=repo,
        base_plan_id=base_plan_id,
        new_plan_id=new_plan_id,
        pg_cfg=PG_CFG,
    )


@router.post("/architecture/diff")
def architecture_diff(
    request: ArchitectureDiffRequest,
    auth: AuthContext = Depends(auth_arch_scoped),
):
    enforce_repo_scope(auth, request.repo)
    return diff_architecture_plans(
        repo=request.repo,
        base_plan_id=request.base_plan_id,
        new_plan_id=request.new_plan_id,
        pg_cfg=PG_CFG,
    )


@router.post("/architecture/adr")
def architecture_adr(
    request: ADRRequest,
    http_request: Request,
    auth: AuthContext = Depends(auth_arch_scoped),
):
    """Generate an Architecture Decision Record using LLM."""
    enforce_repo_scope(auth, request.repo)

    system_context = _gather_system_context(PG_CFG, request.repo)
    adr = generate_adr(
        title=request.title,
        context=request.context,
        repo=request.repo,
        system_context=system_context,
    )

    audit_event(
        actor=auth.subject,
        action="architecture_adr_create",
        result={"status": "success", "title": request.title},
        role=auth.role,
        tenant_id=auth.tenant_id,
        correlation_id=http_request.headers.get("x-correlation-id"),
        request_id=http_request.headers.get("x-request-id"),
        entities={"repo": request.repo},
    )

    return adr


@router.get("/architecture/explorer")
def architecture_explorer(
    repo: Optional[str] = None,
    pr_number: Optional[int] = None,
    auth: AuthContext = Depends(auth_arch_scoped),
):
    """Explore existing architecture from the knowledge graph."""
    if not repo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="repo is required")
    enforce_repo_scope(auth, repo)
    return build_architecture_explorer(
        repo=repo,
        pr_number=pr_number,
        db_conn_factory=get_db_conn,
        ensure_arch_schema=lambda: None,
    )
