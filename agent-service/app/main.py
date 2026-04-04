import os
from typing import Optional

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from .github_bridge import GithubBridge
from .otel_setup import setup_otel

app = FastAPI(title="agent-service")
setup_otel(app)
bridge = GithubBridge()


def _require_admin_token(
    authorization: Optional[str] = Header(default=None),
    x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
):
    expected = os.getenv("GITHUB_BRIDGE_ADMIN_TOKEN", "").strip()
    if not expected:
        return

    supplied = (x_admin_token or "").strip()
    if not supplied and authorization and authorization.lower().startswith("bearer "):
        supplied = authorization.split(" ", 1)[1].strip()

    if supplied != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid admin token")


@app.on_event("startup")
def _startup():
    bridge.start()


@app.on_event("shutdown")
def _shutdown():
    bridge.stop()

@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "agent-service"}


@app.get("/github/bridge/health")
def github_bridge_health():
    return bridge.health()


class TenantInstallationUpsertRequest(BaseModel):
    tenant_id: str = Field(min_length=1)
    repo_full_name: str = Field(min_length=1, description="owner/repo")
    installation_id: str = Field(min_length=1)
    enabled: bool = True
    metadata: dict = Field(default_factory=dict)


@app.post("/github/bridge/tenants/installations")
def upsert_tenant_installation(request: TenantInstallationUpsertRequest, _auth: None = Depends(_require_admin_token)):
    return bridge.upsert_tenant_installation(
        tenant_id=request.tenant_id,
        repo_full_name=request.repo_full_name,
        installation_id=request.installation_id,
        enabled=request.enabled,
        metadata=request.metadata,
    )


@app.get("/github/bridge/tenants/installations")
def list_tenant_installations(tenant_id: Optional[str] = None, _auth: None = Depends(_require_admin_token)):
    return {"items": bridge.list_tenant_installations(tenant_id=tenant_id)}


async def _handle_github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: Optional[str] = Header(default=None, alias="X-Hub-Signature-256"),
    x_github_event: Optional[str] = Header(default=None, alias="X-GitHub-Event"),
    x_github_delivery: Optional[str] = Header(default=None, alias="X-GitHub-Delivery"),
):
    body = await request.body()
    if not bridge.verify_webhook_signature(body, x_hub_signature_256):
        return JSONResponse({"error": "invalid signature"}, status_code=401)

    payload = await request.json()
    
    # Process webhook in background to return HTTP 200 within 500ms
    background_tasks.add_task(
        bridge.process_github_webhook,
        event_type=(x_github_event or "").strip(),
        payload=payload,
        delivery_id=(x_github_delivery or "").strip() or None,
    )
    
    return {"ok": True, "delivery_id": (x_github_delivery or "").strip() or None}


@app.post("/github/webhook")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: Optional[str] = Header(default=None, alias="X-Hub-Signature-256"),
    x_github_event: Optional[str] = Header(default=None, alias="X-GitHub-Event"),
    x_github_delivery: Optional[str] = Header(default=None, alias="X-GitHub-Delivery"),
):
    return await _handle_github_webhook(
        request=request,
        background_tasks=background_tasks,
        x_hub_signature_256=x_hub_signature_256,
        x_github_event=x_github_event,
        x_github_delivery=x_github_delivery,
    )


@app.post("/webhooks/github")
async def github_webhook_alias(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: Optional[str] = Header(default=None, alias="X-Hub-Signature-256"),
    x_github_event: Optional[str] = Header(default=None, alias="X-GitHub-Event"),
    x_github_delivery: Optional[str] = Header(default=None, alias="X-GitHub-Delivery"),
):
    return await _handle_github_webhook(
        request=request,
        background_tasks=background_tasks,
        x_hub_signature_256=x_hub_signature_256,
        x_github_event=x_github_event,
        x_github_delivery=x_github_delivery,
    )
