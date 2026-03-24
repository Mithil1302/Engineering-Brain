
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse

from ..dependencies import (
    pipeline, parse_optional_ts, auth_read_scoped, enforce_repo_scope, AuthContext
)

router = APIRouter()

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"



@router.get("/policy/dashboard/overview")
def policy_dashboard_overview(
    repo: Optional[str] = None,
    pr_number: Optional[int] = None,
    window: int = 20,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
    _auth: AuthContext = Depends(auth_read_scoped),
):
    if not repo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="repo is required")
    after_dt = parse_optional_ts(created_after, field_name="created_after")
    before_dt = parse_optional_ts(created_before, field_name="created_before")
    return pipeline.dashboard_overview(
        repo=repo,
        pr_number=pr_number,
        window=window,
        created_after=after_dt,
        created_before=before_dt,
    )


@router.get("/policy/dashboard/health-snapshots")
def policy_dashboard_health_snapshots(
    repo: Optional[str] = None,
    pr_number: Optional[int] = None,
    limit: int = 50,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
    _auth: AuthContext = Depends(auth_read_scoped),
):
    if not repo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="repo is required")
    after_dt = parse_optional_ts(created_after, field_name="created_after")
    before_dt = parse_optional_ts(created_before, field_name="created_before")
    return {
        "items": pipeline.list_health_snapshots(
            repo=repo,
            pr_number=pr_number,
            limit=limit,
            created_after=after_dt,
            created_before=before_dt,
        )
    }


@router.get("/policy/dashboard/doc-refresh-jobs")
def policy_dashboard_doc_refresh_jobs(
    repo: Optional[str] = None,
    pr_number: Optional[int] = None,
    limit: int = 50,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
    _auth: AuthContext = Depends(auth_read_scoped),
):
    if not repo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="repo is required")
    after_dt = parse_optional_ts(created_after, field_name="created_after")
    before_dt = parse_optional_ts(created_before, field_name="created_before")
    return {
        "items": pipeline.list_doc_refresh_jobs(
            repo=repo,
            pr_number=pr_number,
            limit=limit,
            created_after=after_dt,
            created_before=before_dt,
        )
    }


@router.get("/policy/dashboard/doc-rewrite-runs")
def policy_dashboard_doc_rewrite_runs(
    repo: Optional[str] = None,
    pr_number: Optional[int] = None,
    limit: int = 50,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
    _auth: AuthContext = Depends(auth_read_scoped),
):
    if not repo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="repo is required")
    after_dt = parse_optional_ts(created_after, field_name="created_after")
    before_dt = parse_optional_ts(created_before, field_name="created_before")
    return {
        "items": pipeline.list_doc_rewrite_runs(
            repo=repo,
            pr_number=pr_number,
            limit=limit,
            created_after=after_dt,
            created_before=before_dt,
        )
    }


@router.get("/policy/dashboard/ui", response_class=HTMLResponse)
def policy_dashboard_ui(_auth: AuthContext = Depends(auth_read_scoped)):
    html_file = STATIC_DIR / "knowledge-dashboard.html"
    if not html_file.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="dashboard UI not found")
    return html_file.read_text(encoding="utf-8")


@router.get("/policy/dashboard/policy-check-runs")
def policy_dashboard_policy_check_runs(
    repo: Optional[str] = None,
    pr_number: Optional[int] = None,
    limit: int = 50,
    _auth: AuthContext = Depends(auth_read_scoped),
):
    if not repo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="repo is required")
    return {"items": pipeline.governance_store.list_policy_check_runs(repo=repo, pr_number=pr_number, limit=limit)}

