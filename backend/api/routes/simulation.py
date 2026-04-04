"""
routes/simulation.py — What-if impact analysis, failure cascade, time-travel.

Proxies to worker-service /simulation/* routes.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from ..config import WORKER_SERVICE_URL
from ..proxy import forward_request

router = APIRouter(prefix="/simulation", tags=["simulation"])


@router.post("/time-travel")
async def simulation_time_travel(request: Request):
    """Project future health scores based on historical trends."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/simulation/time-travel")


@router.post("/impact")
async def simulation_impact(request: Request):
    """What-if impact analysis: which services are affected by a proposed change."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/simulation/impact")


@router.post("/failure-cascade")
async def simulation_failure_cascade(request: Request):
    """Simulate a failure cascade when a service goes down."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/simulation/failure-cascade")


@router.get("/graph")
async def simulation_graph(request: Request):
    """Get the service dependency graph for a repo."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/simulation/graph")


@router.get("/history")
async def simulation_history(request: Request):
    """List past simulation runs."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/simulation/history")
