"""
routes/architecture.py — Architecture planning, scaffolding, ADR, and explorer.

Proxies to worker-service /architecture/* routes.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from ..config import WORKER_SERVICE_URL
from ..proxy import forward_request

router = APIRouter(prefix="/architecture", tags=["architecture"])


@router.post("/plan")
async def architecture_plan(request: Request):
    """Generate an LLM-powered architecture plan from natural language requirements."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/architecture/plan")


@router.get("/plans")
async def architecture_plans(request: Request):
    """List past architecture plan runs for a repo."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/architecture/plans")


@router.post("/scaffold")
async def architecture_scaffold(request: Request):
    """Generate architecture plan + scaffold files (Dockerfiles, K8s, OpenAPI, etc.)."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/architecture/scaffold")


@router.post("/refine")
async def architecture_refine(request: Request):
    """Refine an existing architecture plan with a requirement delta."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/architecture/refine")


@router.get("/plan/{base_plan_id}/diff/{new_plan_id}")
async def architecture_plan_diff(base_plan_id: int, new_plan_id: int, request: Request):
    """Diff two architecture plan versions."""
    return await forward_request(
        request,
        base_url=WORKER_SERVICE_URL,
        path=f"/architecture/plan/{base_plan_id}/diff/{new_plan_id}",
    )


@router.post("/diff")
async def architecture_diff(request: Request):
    """Diff two architecture plans by ID (POST body)."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/architecture/diff")


@router.post("/adr")
async def architecture_adr(request: Request):
    """Generate an Architecture Decision Record using LLM."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/architecture/adr")


@router.get("/explorer")
async def architecture_explorer(request: Request):
    """Explore the architecture graph for a repo."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/architecture/explorer")
