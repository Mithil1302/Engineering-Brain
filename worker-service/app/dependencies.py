import os
import json
import logging
import psycopg2
from typing import Optional
from datetime import datetime, timezone
from fastapi import Request, HTTPException, status, Depends
from .policy.pipeline import PolicyPipeline
from .security.authz import AuthContext, build_auth_dependency, enforce_repo_scope

from .llm import get_llm_client, get_embedding_client
from .llm.embeddings import EmbeddingStore

log = logging.getLogger("worker-service")
pipeline = PolicyPipeline(log)

PG_CFG = {
    "host": os.getenv("POSTGRES_HOST", "postgres"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "user": os.getenv("POSTGRES_USER", "brain"),
    "password": os.getenv("POSTGRES_PASSWORD", "brain"),
    "dbname": os.getenv("POSTGRES_DB", "brain"),
}

# LLM singletons — lazy-initialised on first access
llm_client = get_llm_client()
embedding_client = get_embedding_client()
embedding_store = EmbeddingStore(
    db_conn_factory=lambda: psycopg2.connect(**PG_CFG),
    embedding_client=embedding_client,
)

ADMIN_ROLES = {"platform-admin", "security-admin"}
ARCHITECT_ROLES = {"platform-admin", "security-admin", "platform-lead", "architect"}
READ_ROLES = {"platform-admin", "security-admin", "platform-lead", "architect", "developer", "sre"}
AUTOFIX_ROLES = {"platform-admin", "security-admin", "platform-lead", "architect"}

def get_db_conn():
    return psycopg2.connect(**PG_CFG)

def audit_event(
    *,
    actor: str,
    action: str,
    result: dict,
    role: Optional[str] = None,
    tenant_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    request_id: Optional[str] = None,
    entities: Optional[dict] = None,
    metadata: Optional[dict] = None,
):
    try:
        with get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO meta.audit_logs (timestamp, actor, action, correlation_id, request_id, entities, result, metadata)
                    VALUES (NOW(), %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
                    """,
                    (
                        actor,
                        action,
                        correlation_id,
                        request_id,
                        json.dumps(entities or {}),
                        json.dumps(result or {}),
                        json.dumps({"role": role, "tenant_id": tenant_id, **(metadata or {})}),
                    ),
                )
            conn.commit()
    except Exception:
        pass

def audit_denied(request: Request, ctx: Optional[AuthContext], detail: str, status_code: int):
    audit_event(
        actor=(ctx.subject if ctx else "unknown"),
        action="authz_denied",
        result={"status": "denied", "status_code": status_code, "detail": detail},
        role=(ctx.role if ctx else None),
        tenant_id=(ctx.tenant_id if ctx else None),
        correlation_id=request.headers.get("x-correlation-id"),
        request_id=request.headers.get("x-request-id"),
        entities={"path": str(request.url.path), "method": request.method},
        metadata={"query": dict(request.query_params)},
    )

def repo_from_query(request: Request) -> Optional[str]:
    repo = request.query_params.get("repo")
    return repo.strip() if repo else None

def parse_optional_ts(value: Optional[str], *, field_name: str) -> Optional[datetime]:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} must be a valid ISO-8601 datetime",
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


auth_admin = build_auth_dependency(
    policy_admin_token=pipeline.policy_admin_token,
    allowed_roles=ADMIN_ROLES,
    require_auth=True,
    on_denied=audit_denied,
)

auth_read_scoped = build_auth_dependency(
    policy_admin_token=pipeline.policy_admin_token,
    allowed_roles=READ_ROLES,
    require_auth=True,
    repo_getter=repo_from_query,
    on_denied=audit_denied,
)

auth_arch_scoped = build_auth_dependency(
    policy_admin_token=pipeline.policy_admin_token,
    allowed_roles=ARCHITECT_ROLES,
    require_auth=True,
    repo_getter=repo_from_query,
    on_denied=audit_denied,
)

auth_autofix_scoped = build_auth_dependency(
    policy_admin_token=pipeline.policy_admin_token,
    allowed_roles=AUTOFIX_ROLES,
    require_auth=True,
    repo_getter=repo_from_query,
    on_denied=audit_denied,
)
