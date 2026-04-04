"""
routes/autofix.py — Self-healing autofix generation and PR creation.

Proxies to worker-service /autofix/* routes.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from ..config import WORKER_SERVICE_URL
from ..proxy import forward_request

router = APIRouter(prefix="/autofix", tags=["autofix"])


@router.post("/generate")
async def autofix_generate(request: Request):
    """Generate an autofix patch (dry run, no PR created)."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/autofix/generate")


@router.post("/apply")
async def autofix_apply(request: Request):
    """Generate an autofix patch AND create a GitHub PR."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/autofix/apply")


@router.get("/history")
async def autofix_history(request: Request):
    """List past autofix runs for a repo."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/autofix/history")
