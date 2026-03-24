
from typing import Optional
from fastapi import APIRouter, Depends, Request, HTTPException, status
import json

from ..dependencies import (
    pipeline, auth_admin, audit_event, enforce_repo_scope, AuthContext
)

router = APIRouter()

from ..policy.admin_models import PolicyTemplateUpsertRequest, WaiverRequest, WaiverDecisionRequest, RetryDeadLetterRequeueRequest

@router.post("/policy/admin/templates/upsert")
def policy_admin_upsert_template(
    request: PolicyTemplateUpsertRequest,
    http_request: Request,
    auth: AuthContext = Depends(auth_admin),
):
    out = pipeline.governance_store.upsert_policy_template(
        template_name=request.template_name,
        scope_type=request.scope_type,
        scope_value=request.scope_value,
        rule_pack=request.rule_pack,
        rules=request.rules,
        fail_blocks_merge=request.fail_blocks_merge,
        warn_blocks_merge=request.warn_blocks_merge,
        no_docs_no_merge=request.no_docs_no_merge,
        metadata=request.metadata,
        enabled=request.enabled,
        priority=request.priority,
    )
    audit_event(
        actor=auth.subject,
        action="policy_template_upsert",
        result={"status": "success", "template_name": request.template_name},
        role=auth.role,
        tenant_id=auth.tenant_id,
        correlation_id=http_request.headers.get("x-correlation-id"),
        request_id=http_request.headers.get("x-request-id"),
        entities={"scope_type": request.scope_type, "scope_value": request.scope_value},
    )
    return out


@router.get("/policy/admin/templates")
def policy_admin_list_templates(
    scope_type: Optional[str] = None,
    scope_value: Optional[str] = None,
    enabled: Optional[bool] = None,
    auth: AuthContext = Depends(auth_admin),
):
    return {
        "items": pipeline.governance_store.list_policy_templates(
            scope_type=scope_type,
            scope_value=scope_value,
            enabled=enabled,
        )
    }


@router.get("/policy/admin/templates/effective")
def policy_admin_effective_template(
    repo: str,
    team: Optional[str] = None,
    org: Optional[str] = None,
    auth: AuthContext = Depends(auth_admin),
):
    if "*" not in auth.repo_scope:
        enforce_repo_scope(auth, repo)
    return {
        "template": pipeline.governance_store.resolve_effective_policy_template(repo=repo, team=team, org=org),
        "repo": repo,
        "team": team,
        "org": org,
    }


@router.post("/policy/admin/waivers/request")
def policy_admin_request_waiver(
    request: WaiverRequest,
    http_request: Request,
    auth: AuthContext = Depends(auth_admin),
):
    if "*" not in auth.repo_scope:
        enforce_repo_scope(auth, request.repo)
    out = pipeline.governance_store.create_waiver_request(
        repo=request.repo,
        pr_number=request.pr_number,
        rule_set=request.rule_set,
        requested_by=request.requested_by,
        requested_role=request.requested_role,
        reason=request.reason,
        expires_at=request.expires_at,
        required_approvals=request.required_approvals,
        approval_chain=request.approval_chain,
        scope=request.scope,
        metadata=request.metadata,
    )
    audit_event(
        actor=auth.subject,
        action="waiver_request_create",
        result={"status": "success", "waiver_repo": request.repo, "pr_number": request.pr_number},
        role=auth.role,
        tenant_id=auth.tenant_id,
        correlation_id=http_request.headers.get("x-correlation-id"),
        request_id=http_request.headers.get("x-request-id"),
        entities={"repo": request.repo, "pr_number": request.pr_number},
    )
    return out


@router.post("/policy/admin/waivers/{waiver_id}/decision")
def policy_admin_decide_waiver(
    waiver_id: int,
    request: WaiverDecisionRequest,
    http_request: Request,
    auth: AuthContext = Depends(auth_admin),
):
    out = pipeline.governance_store.decide_waiver(
        waiver_id=waiver_id,
        decision=request.decision,
        approver=request.approver,
        approver_role=request.approver_role,
        notes=request.notes,
    )
    audit_event(
        actor=auth.subject,
        action="waiver_decision",
        result={"status": "success", "waiver_id": waiver_id, "decision": request.decision},
        role=auth.role,
        tenant_id=auth.tenant_id,
        correlation_id=http_request.headers.get("x-correlation-id"),
        request_id=http_request.headers.get("x-request-id"),
        entities={"waiver_id": waiver_id},
    )
    return out


@router.get("/policy/admin/waivers")
def policy_admin_list_waivers(
    repo: Optional[str] = None,
    pr_number: Optional[int] = None,
    status: Optional[str] = None,
    auth: AuthContext = Depends(auth_admin),
):
    if repo and "*" not in auth.repo_scope:
        enforce_repo_scope(auth, repo)
    return {
        "items": pipeline.governance_store.list_waivers(repo=repo, pr_number=pr_number, status=status)
    }


@router.get("/policy/admin/waivers/{waiver_id}/history")
def policy_admin_waiver_history(
    waiver_id: int,
    auth: AuthContext = Depends(auth_admin),
):
    try:
        out = pipeline.governance_store.get_waiver_history(waiver_id=waiver_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    repo = (out.get("waiver") or {}).get("repo")
    if repo and "*" not in auth.repo_scope:
        enforce_repo_scope(auth, repo)
    return out


@router.get("/policy/admin/emit-retry/jobs")
def policy_admin_list_emit_retry_jobs(
    status: Optional[str] = None,
    limit: int = 100,
    auth: AuthContext = Depends(auth_admin),
):
    return {
        "items": pipeline.list_emit_retry_jobs(status=status, limit=limit),
        "status_filter": status,
    }


@router.get("/policy/admin/emit-retry/dead-letters")
def policy_admin_list_emit_retry_dead_letters(
    limit: int = 100,
    auth: AuthContext = Depends(auth_admin),
):
    return {
        "items": pipeline.list_emit_retry_dead_letters(limit=limit),
    }


@router.get("/policy/admin/emit-retry/overview")
def policy_admin_emit_retry_overview(
    repo: Optional[str] = None,
    window_hours: int = 24,
    auth: AuthContext = Depends(auth_admin),
):
    if repo and "*" not in auth.repo_scope:
        enforce_repo_scope(auth, repo)
    return pipeline.emit_retry_overview(repo=repo, window_hours=window_hours)


@router.get("/policy/admin/emit-retry/metrics")
def policy_admin_emit_retry_metrics(
    repo: Optional[str] = None,
    window_minutes: int = 60,
    auth: AuthContext = Depends(auth_admin),
):
    if repo and "*" not in auth.repo_scope:
        enforce_repo_scope(auth, repo)
    return pipeline.emit_retry_metrics(repo=repo, window_minutes=window_minutes, update_backlog_sample=False)


@router.get("/policy/admin/emit-retry/alerts")
def policy_admin_emit_retry_alerts(
    repo: Optional[str] = None,
    window_minutes: int = 60,
    auth: AuthContext = Depends(auth_admin),
):
    if repo and "*" not in auth.repo_scope:
        enforce_repo_scope(auth, repo)
    return pipeline.emit_retry_alerts(repo=repo, window_minutes=window_minutes, update_backlog_sample=True)


@router.post("/policy/admin/emit-retry/dead-letters/{poison_id}/requeue")
def policy_admin_requeue_emit_retry_dead_letter(
    poison_id: int,
    request: RetryDeadLetterRequeueRequest,
    http_request: Request,
    auth: AuthContext = Depends(auth_admin),
):
    try:
        out = pipeline.requeue_emit_retry_dead_letter(poison_id=poison_id, reset_attempt=request.reset_attempt)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    audit_event(
        actor=auth.subject,
        action="emit_retry_dead_letter_requeue",
        result={"status": "success", "poison_id": poison_id},
        role=auth.role,
        tenant_id=auth.tenant_id,
        correlation_id=http_request.headers.get("x-correlation-id"),
        request_id=http_request.headers.get("x-request-id"),
        entities={"poison_id": poison_id},
        metadata={"reset_attempt": request.reset_attempt},
    )
    return out

