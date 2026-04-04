"""
routes/policy.py — Policy evaluation, pipeline health, and dashboard endpoints.

Proxies to worker-service /policy/* routes.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from ..config import WORKER_SERVICE_URL
from ..proxy import forward_request

router = APIRouter(prefix="/policy", tags=["policy"])


@router.post("/evaluate")
async def policy_evaluate(request: Request):
    """Evaluate policy rules against a PR spec."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/policy/evaluate")


@router.get("/pipeline/health")
async def pipeline_health(request: Request):
    """Policy pipeline health (admin)."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/policy/pipeline/health")


@router.get("/pipeline/readiness")
async def pipeline_readiness(request: Request):
    """Policy pipeline readiness signals (admin)."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/policy/pipeline/readiness")


# -- Dashboard --

@router.get("/dashboard/overview")
async def dashboard_overview(request: Request):
    """Policy dashboard overview for a repo."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/policy/dashboard/overview")


@router.get("/dashboard/health-snapshots")
async def dashboard_health_snapshots(request: Request):
    """Knowledge health snapshot history."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/policy/dashboard/health-snapshots")


@router.get("/dashboard/doc-refresh-jobs")
async def dashboard_doc_refresh_jobs(request: Request):
    """Doc refresh job history."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/policy/dashboard/doc-refresh-jobs")


@router.get("/dashboard/doc-rewrite-runs")
async def dashboard_doc_rewrite_runs(request: Request):
    """Doc rewrite run history."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/policy/dashboard/doc-rewrite-runs")


@router.get("/dashboard/policy-check-runs")
async def dashboard_policy_check_runs(request: Request):
    """Policy check run history."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/policy/dashboard/policy-check-runs")


# -- Admin --

@router.post("/admin/templates/upsert")
async def admin_upsert_template(request: Request):
    """Upsert a policy template (admin)."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/policy/admin/templates/upsert")


@router.get("/admin/templates")
async def admin_list_templates(request: Request):
    """List policy templates (admin)."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/policy/admin/templates")


@router.get("/admin/templates/effective")
async def admin_effective_template(request: Request):
    """Resolve effective policy template for a repo (admin)."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/policy/admin/templates/effective")


@router.post("/admin/waivers/request")
async def admin_request_waiver(request: Request):
    """Request a policy waiver (admin)."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/policy/admin/waivers/request")


@router.post("/admin/waivers/{waiver_id}/decision")
async def admin_decide_waiver(waiver_id: int, request: Request):
    """Approve or reject a waiver (admin)."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path=f"/policy/admin/waivers/{waiver_id}/decision")


@router.get("/admin/waivers")
async def admin_list_waivers(request: Request):
    """List waivers (admin)."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/policy/admin/waivers")


@router.get("/admin/waivers/{waiver_id}/history")
async def admin_waiver_history(waiver_id: int, request: Request):
    """Waiver approval history (admin)."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path=f"/policy/admin/waivers/{waiver_id}/history")


@router.get("/admin/emit-retry/jobs")
async def admin_emit_retry_jobs(request: Request):
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/policy/admin/emit-retry/jobs")


@router.get("/admin/emit-retry/dead-letters")
async def admin_emit_retry_dead_letters(request: Request):
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/policy/admin/emit-retry/dead-letters")


@router.get("/admin/emit-retry/overview")
async def admin_emit_retry_overview(request: Request):
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/policy/admin/emit-retry/overview")


@router.get("/admin/emit-retry/metrics")
async def admin_emit_retry_metrics(request: Request):
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/policy/admin/emit-retry/metrics")


@router.get("/admin/emit-retry/alerts")
async def admin_emit_retry_alerts(request: Request):
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/policy/admin/emit-retry/alerts")


@router.post("/admin/emit-retry/dead-letters/{poison_id}/requeue")
async def admin_requeue_dead_letter(poison_id: int, request: Request):
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path=f"/policy/admin/emit-retry/dead-letters/{poison_id}/requeue")
