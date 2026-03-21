import logging
from fastapi import FastAPI
from .policy.engine import evaluate_policies, summary_status
from .policy.models import PolicyEvaluationRequest
from .policy.patches import build_suggested_patches
from .policy.renderer import assemble_response
from .policy.pipeline import PolicyPipeline
from .otel_setup import setup_otel

app = FastAPI(title="worker-service")
setup_otel(app)
log = logging.getLogger("worker-service")
pipeline = PolicyPipeline(log)


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
def policy_pipeline_health():
    return pipeline.health()


@app.post("/policy/evaluate")
def policy_evaluate(request: PolicyEvaluationRequest):
    findings = evaluate_policies(request)
    patches = build_suggested_patches(findings)
    status = summary_status(findings)
    response = assemble_response(request, status, findings, patches)
    return response.model_dump()
