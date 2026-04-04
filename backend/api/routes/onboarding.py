"""
routes/onboarding.py — Contextual onboarding path generation and progress tracking.

Proxies to worker-service /onboarding/* routes.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from ..config import WORKER_SERVICE_URL
from ..proxy import forward_request

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.post("/path")
async def onboarding_path(request: Request):
    """Generate a personalized onboarding path for a role."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/onboarding/path")


@router.post("/progress")
async def onboarding_progress(request: Request):
    """Update task completion status in an onboarding path."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/onboarding/progress")


@router.post("/ask")
async def onboarding_ask(request: Request):
    """Answer an onboarding question using LLM."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/onboarding/ask")


@router.get("/history")
async def onboarding_history(request: Request):
    """List past onboarding paths for a repo."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/onboarding/history")
