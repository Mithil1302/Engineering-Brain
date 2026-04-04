"""
KA-CHOW Backend API

Unified REST gateway that aggregates all worker-service capabilities
and exposes them to external consumers (web UI, chat platforms, CLI).

Routes:
  /healthz              — backend health
  /mesh                 — upstream service mesh status
  /policy/*             — policy evaluation, pipeline, dashboard, admin
  /architecture/*       — architecture planning, scaffolding, ADR, explorer
  /assistant/*          — Q&A, conversation, semantic search
  /simulation/*         — impact analysis, failure cascade, time-travel
  /autofix/*            — self-healing patch generation and PR creation
  /onboarding/*         — personalized learning paths and progress tracking
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes.health import router as health_router
from .routes.policy import router as policy_router
from .routes.architecture import router as architecture_router
from .routes.assistant import router as assistant_router
from .routes.simulation import router as simulation_router
from .routes.autofix import router as autofix_router
from .routes.onboarding import router as onboarding_router

app = FastAPI(
    title="KA-CHOW Backend API",
    description="Unified gateway for the KA-CHOW Autonomous Engineering Brain",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(policy_router)
app.include_router(architecture_router)
app.include_router(assistant_router)
app.include_router(simulation_router)
app.include_router(autofix_router)
app.include_router(onboarding_router)
