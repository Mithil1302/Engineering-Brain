import logging
import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from .policy.engine import evaluate_policies, summary_status
from .policy.merge_gate import build_merge_gate_decision
from .policy.models import PolicyEvaluationRequest
from .policy.patches import build_suggested_patches
from .policy.renderer import assemble_response
from .policy.doc_refresh import build_doc_refresh_plan
from .policy.health_score import build_knowledge_health_score
from .policy.pipeline import PolicyPipeline
from .architecture.models import ArchitecturePlanRequest, ArchitecturePlanResponse
from .architecture.planner import generate_architecture_plan
from .qa.models import QARequest
from .qa.assistant import answer_question
from .onboarding.engine import build_onboarding_path
from .simulation.time_travel import simulate_health
from .autofix.runner import build_autofix_workflow
from .security.authz import AuthContext, build_auth_dependency, enforce_repo_scope
from .otel_setup import setup_otel

app = FastAPI(title="worker-service")
setup_otel(app)
log = logging.getLogger("worker-service")
pipeline = PolicyPipeline(log)
STATIC_DIR = Path(__file__).resolve().parent / "static"
ARCH_TOPIC = os.getenv("ARCHITECTURE_OUTPUT_TOPIC", "architecture.plans")
PG_CFG = {
    "host": os.getenv("POSTGRES_HOST", "postgres"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "user": os.getenv("POSTGRES_USER", "brain"),
    "password": os.getenv("POSTGRES_PASSWORD", "brain"),
    "dbname": os.getenv("POSTGRES_DB", "brain"),
}

ADMIN_ROLES = {"platform-admin", "security-admin"}
ARCHITECT_ROLES = {"platform-admin", "security-admin", "platform-lead", "architect"}
READ_ROLES = {"platform-admin", "security-admin", "platform-lead", "architect", "developer", "sre"}
AUTOFIX_ROLES = {"platform-admin", "security-admin", "platform-lead", "architect"}


def _db_conn():
    return psycopg2.connect(**PG_CFG)


def _audit_event(
    *,
    actor: str,
    action: str,
    result: dict,
    role: Optional[str] = None,
    tenant_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    request_id: Optional[str] = None,
    entities: Optional[dict] = None,
    metadata: Optional[dict] = None,
):
    try:
        with _db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO meta.audit_logs (timestamp, actor, action, correlation_id, request_id, entities, result, metadata)
                    VALUES (NOW(), %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
                    """,
                    (
                        actor,
                        action,
                        correlation_id,
                        request_id,
                        json.dumps(entities or {}),
                        json.dumps(result or {}),
                        json.dumps({"role": role, "tenant_id": tenant_id, **(metadata or {})}),
                    ),
                )
            conn.commit()
    except Exception:
        # Never fail request path on audit sink issues.
        return


def _audit_denied(request: Request, ctx: Optional[AuthContext], detail: str, status_code: int):
    _audit_event(
        actor=(ctx.subject if ctx else "unknown"),
        action="authz_denied",
        result={"status": "denied", "status_code": status_code, "detail": detail},
        role=(ctx.role if ctx else None),
        tenant_id=(ctx.tenant_id if ctx else None),
        correlation_id=request.headers.get("x-correlation-id"),
        request_id=request.headers.get("x-request-id"),
        entities={"path": str(request.url.path), "method": request.method},
        metadata={"query": dict(request.query_params)},
    )


def _repo_from_query(request: Request) -> Optional[str]:
    repo = request.query_params.get("repo")
    return repo.strip() if repo else None


auth_admin = build_auth_dependency(
    policy_admin_token=pipeline.policy_admin_token,
    allowed_roles=ADMIN_ROLES,
    require_auth=True,
    on_denied=_audit_denied,
)

auth_read_scoped = build_auth_dependency(
    policy_admin_token=pipeline.policy_admin_token,
    allowed_roles=READ_ROLES,
    require_auth=True,
    repo_getter=_repo_from_query,
    on_denied=_audit_denied,
)

auth_arch_scoped = build_auth_dependency(
    policy_admin_token=pipeline.policy_admin_token,
    allowed_roles=ARCHITECT_ROLES,
    require_auth=True,
    repo_getter=_repo_from_query,
    on_denied=_audit_denied,
)

auth_autofix_scoped = build_auth_dependency(
    policy_admin_token=pipeline.policy_admin_token,
    allowed_roles=AUTOFIX_ROLES,
    require_auth=True,
    repo_getter=_repo_from_query,
    on_denied=_audit_denied,
)


class PolicyTemplateUpsertRequest(BaseModel):
    template_name: str
    scope_type: str = Field(description="org|team|repo")
    scope_value: str
    rule_pack: Optional[str] = None
    rules: dict = Field(default_factory=dict)
    fail_blocks_merge: bool = True
    warn_blocks_merge: bool = False
    no_docs_no_merge: bool = False
    metadata: dict = Field(default_factory=dict)
    enabled: bool = True
    priority: int = 100


class WaiverRequest(BaseModel):
    repo: str
    pr_number: int
    rule_set: str = "rules-v1"
    requested_by: str
    requested_role: str
    reason: str
    expires_at: str
    required_approvals: int = 1
    approval_chain: list[str] = Field(default_factory=list)
    scope: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)


class WaiverDecisionRequest(BaseModel):
    decision: str = Field(description="approve|reject")
    approver: str
    approver_role: str
    notes: Optional[str] = None


class RetryDeadLetterRequeueRequest(BaseModel):
    reset_attempt: bool = True


def _ensure_arch_schema():
    with _db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE SCHEMA IF NOT EXISTS meta;
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
                """
            )
        conn.commit()


def _persist_arch_plan(req: ArchitecturePlanRequest, plan_payload: dict):
    _ensure_arch_schema()
    with _db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO meta.architecture_plan_runs (
                  repo, pr_number, correlation_id, plan_id, intent_tags,
                  requirement, decisions, services, infrastructure, artifacts,
                  status, created_at, updated_at
                ) VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,'planned',NOW(),NOW())
                """,
                (
                    req.repo,
                    req.pr_number,
                    req.correlation_id,
                    plan_payload.get("plan_id"),
                    json.dumps(plan_payload.get("intent_tags", [])),
                    json.dumps(plan_payload.get("requirement", {})),
                    json.dumps(plan_payload.get("decisions", [])),
                    json.dumps(plan_payload.get("services", [])),
                    json.dumps(plan_payload.get("infrastructure", [])),
                    json.dumps(plan_payload.get("artifacts", [])),
                ),
            )
        conn.commit()


@app.on_event("startup")
def _startup_pipeline():
    pipeline.start()


@app.on_event("shutdown")
def _shutdown_pipeline():
    pipeline.stop()

@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "worker-service"}


@app.get("/policy/pipeline/health")
def policy_pipeline_health(_auth: AuthContext = Depends(auth_admin)):
    return pipeline.health()


@app.get("/policy/dashboard/overview")
def policy_dashboard_overview(
    repo: Optional[str] = None,
    pr_number: Optional[int] = None,
    window: int = 20,
    _auth: AuthContext = Depends(auth_read_scoped),
):
    if not repo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="repo is required")
    return pipeline.dashboard_overview(repo=repo, pr_number=pr_number, window=window)


@app.get("/policy/dashboard/health-snapshots")
def policy_dashboard_health_snapshots(
    repo: Optional[str] = None,
    pr_number: Optional[int] = None,
    limit: int = 50,
    _auth: AuthContext = Depends(auth_read_scoped),
):
    if not repo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="repo is required")
    return {"items": pipeline.list_health_snapshots(repo=repo, pr_number=pr_number, limit=limit)}


@app.get("/policy/dashboard/doc-refresh-jobs")
def policy_dashboard_doc_refresh_jobs(
    repo: Optional[str] = None,
    pr_number: Optional[int] = None,
    limit: int = 50,
    _auth: AuthContext = Depends(auth_read_scoped),
):
    if not repo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="repo is required")
    return {"items": pipeline.list_doc_refresh_jobs(repo=repo, pr_number=pr_number, limit=limit)}


@app.get("/policy/dashboard/doc-rewrite-runs")
def policy_dashboard_doc_rewrite_runs(
    repo: Optional[str] = None,
    pr_number: Optional[int] = None,
    limit: int = 50,
    _auth: AuthContext = Depends(auth_read_scoped),
):
    if not repo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="repo is required")
    return {"items": pipeline.list_doc_rewrite_runs(repo=repo, pr_number=pr_number, limit=limit)}


@app.get("/policy/dashboard/ui", response_class=HTMLResponse)
def policy_dashboard_ui(_auth: AuthContext = Depends(auth_read_scoped)):
    html_file = STATIC_DIR / "knowledge-dashboard.html"
    if not html_file.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="dashboard UI not found")
    return html_file.read_text(encoding="utf-8")


@app.post("/policy/admin/templates/upsert")
def policy_admin_upsert_template(
    request: PolicyTemplateUpsertRequest,
    http_request: Request,
    auth: AuthContext = Depends(auth_admin),
):
    out = pipeline.upsert_policy_template(
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
    _audit_event(
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


@app.get("/policy/admin/templates")
def policy_admin_list_templates(
    scope_type: Optional[str] = None,
    scope_value: Optional[str] = None,
    enabled: Optional[bool] = None,
    auth: AuthContext = Depends(auth_admin),
):
    return {
        "items": pipeline.list_policy_templates(
            scope_type=scope_type,
            scope_value=scope_value,
            enabled=enabled,
        )
    }


@app.get("/policy/admin/templates/effective")
def policy_admin_effective_template(
    repo: str,
    team: Optional[str] = None,
    auth: AuthContext = Depends(auth_admin),
):
    if "*" not in auth.repo_scope:
        enforce_repo_scope(auth, repo)
    return {
        "template": pipeline.resolve_effective_policy_template(repo=repo, team=team),
        "repo": repo,
        "team": team,
    }


@app.post("/policy/admin/waivers/request")
def policy_admin_request_waiver(
    request: WaiverRequest,
    http_request: Request,
    auth: AuthContext = Depends(auth_admin),
):
    if "*" not in auth.repo_scope:
        enforce_repo_scope(auth, request.repo)
    out = pipeline.create_waiver_request(
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
    _audit_event(
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


@app.post("/policy/admin/waivers/{waiver_id}/decision")
def policy_admin_decide_waiver(
    waiver_id: int,
    request: WaiverDecisionRequest,
    http_request: Request,
    auth: AuthContext = Depends(auth_admin),
):
    out = pipeline.decide_waiver(
        waiver_id=waiver_id,
        decision=request.decision,
        approver=request.approver,
        approver_role=request.approver_role,
        notes=request.notes,
    )
    _audit_event(
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


@app.get("/policy/admin/waivers")
def policy_admin_list_waivers(
    repo: Optional[str] = None,
    pr_number: Optional[int] = None,
    status: Optional[str] = None,
    auth: AuthContext = Depends(auth_admin),
):
    if repo and "*" not in auth.repo_scope:
        enforce_repo_scope(auth, repo)
    return {
        "items": pipeline.list_waivers(repo=repo, pr_number=pr_number, status=status)
    }


@app.get("/policy/admin/emit-retry/jobs")
def policy_admin_list_emit_retry_jobs(
    status: Optional[str] = None,
    limit: int = 100,
    auth: AuthContext = Depends(auth_admin),
):
    return {
        "items": pipeline.list_emit_retry_jobs(status=status, limit=limit),
        "status_filter": status,
    }


@app.get("/policy/admin/emit-retry/dead-letters")
def policy_admin_list_emit_retry_dead_letters(
    limit: int = 100,
    auth: AuthContext = Depends(auth_admin),
):
    return {
        "items": pipeline.list_emit_retry_dead_letters(limit=limit),
    }


@app.get("/policy/admin/emit-retry/overview")
def policy_admin_emit_retry_overview(
    repo: Optional[str] = None,
    window_hours: int = 24,
    auth: AuthContext = Depends(auth_admin),
):
    if repo and "*" not in auth.repo_scope:
        enforce_repo_scope(auth, repo)
    return pipeline.emit_retry_overview(repo=repo, window_hours=window_hours)


@app.post("/policy/admin/emit-retry/dead-letters/{poison_id}/requeue")
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
    _audit_event(
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


@app.post("/architecture/plan")
def architecture_plan(
    request: ArchitecturePlanRequest,
    http_request: Request,
    auth: AuthContext = Depends(auth_arch_scoped),
):
    enforce_repo_scope(auth, request.repo)
    plan = generate_architecture_plan(request)
    payload = plan.model_dump()
    _persist_arch_plan(request, payload)
    out = ArchitecturePlanResponse(
        repo=request.repo,
        pr_number=request.pr_number,
        correlation_id=request.correlation_id,
        plan=plan,
    ).model_dump()
    _audit_event(
        actor=auth.subject,
        action="architecture_plan_create",
        result={"status": "success", "plan_id": payload.get("plan_id")},
        role=auth.role,
        tenant_id=auth.tenant_id,
        correlation_id=http_request.headers.get("x-correlation-id"),
        request_id=http_request.headers.get("x-request-id"),
        entities={"repo": request.repo, "pr_number": request.pr_number},
    )
    return out


@app.get("/architecture/plans")
def architecture_plans(
    repo: Optional[str] = None,
    pr_number: Optional[int] = None,
    limit: int = 50,
    auth: AuthContext = Depends(auth_arch_scoped),
):
    if not repo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="repo is required")
    enforce_repo_scope(auth, repo)
    safe_limit = max(1, min(limit, 500))
    _ensure_arch_schema()
    with _db_conn() as conn:
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
                (repo, repo, pr_number, pr_number, safe_limit),
            )
            rows = cur.fetchall()
    return {"topic": ARCH_TOPIC, "items": [dict(r) for r in rows]}


@app.post("/assistant/ask")
def assistant_ask(request: QARequest, auth: AuthContext = Depends(auth_read_scoped)):
    if not request.repo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="repo is required")
    enforce_repo_scope(auth, request.repo)
    return answer_question(request, PG_CFG).model_dump()


@app.post("/onboarding/path")
def onboarding_path(
    repo: str,
    role: str = "developer",
    pr_number: Optional[int] = None,
    auth: AuthContext = Depends(auth_read_scoped),
):
    enforce_repo_scope(auth, repo)
    qa = answer_question(QARequest(question="system status", repo=repo, pr_number=pr_number, role=role), PG_CFG)
    path = build_onboarding_path(role=role, repo=repo, pr_number=pr_number, evidence=qa.evidence)

    _ensure_arch_schema()
    with _db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO meta.onboarding_paths (repo, pr_number, role, path, created_at)
                VALUES (%s,%s,%s,%s::jsonb,NOW())
                """,
                (repo, pr_number, role, json.dumps(path)),
            )
        conn.commit()
    return path


@app.post("/simulation/time-travel")
def simulation_time_travel(
    repo: str,
    pr_number: Optional[int] = None,
    horizon: int = 5,
    auth: AuthContext = Depends(auth_arch_scoped),
):
    enforce_repo_scope(auth, repo)
    safe_horizon = max(1, min(horizon, 50))
    _ensure_arch_schema()
    with _db_conn() as conn:
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
    with _db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO meta.simulation_runs (repo, pr_number, horizon, result, created_at)
                VALUES (%s,%s,%s,%s::jsonb,NOW())
                """,
                (repo, pr_number, safe_horizon, json.dumps(result)),
            )
        conn.commit()
    return result


@app.post("/autofix/run")
def autofix_run(
    repo: str,
    http_request: Request,
    pr_number: Optional[int] = None,
    auth: AuthContext = Depends(auth_autofix_scoped),
):
    enforce_repo_scope(auth, repo)
    _ensure_arch_schema()
    with _db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT findings, doc_refresh_plan
                FROM meta.policy_check_runs
                WHERE (%s IS NULL OR repo = %s)
                  AND (%s IS NULL OR pr_number = %s)
                ORDER BY id DESC
                LIMIT 1
                """,
                (repo, repo, pr_number, pr_number),
            )
            row = cur.fetchone()

    findings = (row or {}).get("findings") or []
    doc_refresh_plan = (row or {}).get("doc_refresh_plan") or {}
    workflow = build_autofix_workflow(
        repo=repo,
        pr_number=pr_number,
        findings=findings,
        doc_refresh_plan=doc_refresh_plan,
    )

    with _db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO meta.autofix_runs (repo, pr_number, workflow, status, created_at, updated_at)
                VALUES (%s,%s,%s::jsonb,%s,NOW(),NOW())
                RETURNING id
                """,
                (repo, pr_number, json.dumps(workflow), workflow.get("status") or "queued"),
            )
            rid = cur.fetchone()["id"]
        conn.commit()
    _audit_event(
        actor=auth.subject,
        action="autofix_run_create",
        result={"status": "success", "run_id": rid},
        role=auth.role,
        tenant_id=auth.tenant_id,
        correlation_id=http_request.headers.get("x-correlation-id"),
        request_id=http_request.headers.get("x-request-id"),
        entities={"repo": repo, "pr_number": pr_number},
    )
    return {"run_id": rid, "workflow": workflow}


@app.post("/policy/evaluate")
def policy_evaluate(request: PolicyEvaluationRequest, auth: AuthContext = Depends(auth_read_scoped)):
    enforce_repo_scope(auth, request.repo)
    selected_rule_set = (request.config.rule_pack if request.config and request.config.rule_pack else "rules-v1")
    findings = evaluate_policies(request, rule_set=selected_rule_set)
    patches = build_suggested_patches(findings)
    status = summary_status(findings)
    response = assemble_response(request, status, findings, patches)
    payload = response.model_dump()
    merge_gate = build_merge_gate_decision(findings, rule_set=selected_rule_set)
    payload["merge_gate"] = merge_gate
    payload["doc_refresh_plan"] = build_doc_refresh_plan(
        request=request,
        findings=findings,
        suggested_patches=patches,
        merge_gate=merge_gate,
        action="preview",
    )
    payload["knowledge_health"] = build_knowledge_health_score(
        request=request,
        findings=findings,
        merge_gate=merge_gate,
        doc_refresh_plan=payload["doc_refresh_plan"],
    )
    payload["rule_set"] = selected_rule_set
    return payload
