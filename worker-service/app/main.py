
from fastapi import FastAPI
from .otel_setup import setup_otel
import logging

from .dependencies import pipeline, validate_ingestion_env_vars
from fastapi.staticfiles import StaticFiles

from .policy.routes_admin import router as policy_admin_router
from .policy.routes_dash import router as policy_dash_router
from .policy.routes import router as policy_router
from .architecture.routes import router as architecture_router
from .qa.routes import router as qa_router
from .onboarding.routes import router as onboarding_router
from .simulation.routes import router as simulation_router 
from .autofix.routes import router as autofix_router
from .ingestion.routes import router as ingestion_router
from .adapters.slack.routes import slack_router
from .adapters.cli.routes import cli_router

app = FastAPI(title="worker-service")
setup_otel(app)
log = logging.getLogger("worker-service")

@app.on_event("startup")
def _startup_pipeline():
    validate_ingestion_env_vars()
    pipeline.start()

@app.on_event("shutdown")
def _shutdown_pipeline():
    pipeline.stop()

@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "worker-service"}

app.include_router(policy_admin_router)
app.include_router(policy_dash_router)
app.include_router(policy_router)
app.include_router(architecture_router)
app.include_router(qa_router)
app.include_router(onboarding_router)
app.include_router(simulation_router)
app.include_router(autofix_router)
app.include_router(ingestion_router, prefix="/ingestion")
app.include_router(slack_router, prefix="/adapters/slack")
app.include_router(cli_router, prefix="/adapters/cli")

app.mount("/static", StaticFiles(directory="/app/app/static"), name="static")
