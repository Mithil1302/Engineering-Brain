"""
routes/health.py — Backend health and mesh status.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..config import (
    AGENT_SERVICE_URL,
    GRAPH_SERVICE_URL,
    REQUEST_TIMEOUT,
    WORKER_SERVICE_URL,
)

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz():
    """Backend API health check."""
    return {"status": "ok", "service": "backend-api"}


@router.get("/mesh")
async def mesh():
    """Check reachability of all upstream services."""
    services = {
        "worker": f"{WORKER_SERVICE_URL}/healthz",
        "agent":  f"{AGENT_SERVICE_URL}/healthz",
        "graph":  f"{GRAPH_SERVICE_URL}/healthz",
    }
    results = {}
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        for name, url in services.items():
            try:
                resp = await client.get(url)
                results[name] = {"ok": resp.status_code == 200, "status": resp.status_code}
            except Exception as exc:
                results[name] = {"ok": False, "error": str(exc)}

    overall = all(v["ok"] for v in results.values())
    return JSONResponse(
        status_code=200 if overall else 503,
        content={"ok": overall, "services": results},
    )
