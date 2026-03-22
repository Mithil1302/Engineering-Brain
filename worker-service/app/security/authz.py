from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Callable, Optional, Set

from fastapi import Header, HTTPException, Request, status
from pydantic import BaseModel, Field


class AuthContext(BaseModel):
    subject: str
    role: str
    tenant_id: str
    repo_scope: list[str] = Field(default_factory=list)
    auth_mode: str = "claims"


def _parse_bool_env(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _normalize_scope(scope_raw: str | None) -> list[str]:
    if not scope_raw:
        return []
    return [x.strip() for x in scope_raw.split(",") if x.strip()]


def _verify_signature(payload_text: str, signature: str | None, signing_key: str | None) -> bool:
    if not signing_key:
        return True
    if not signature:
        return False
    expected = hmac.new(signing_key.encode("utf-8"), payload_text.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip())


def extract_auth_context(
    *,
    authorization: Optional[str],
    x_admin_token: Optional[str],
    x_auth_context: Optional[str],
    x_auth_signature: Optional[str],
    x_auth_subject: Optional[str],
    x_auth_role: Optional[str],
    x_auth_tenant_id: Optional[str],
    x_auth_repo_scope: Optional[str],
    policy_admin_token: str,
    require_auth: bool,
) -> AuthContext:
    supplied_admin = (x_admin_token or "").strip()
    if not supplied_admin and authorization and authorization.lower().startswith("bearer "):
        supplied_admin = authorization.split(" ", 1)[1].strip()

    if policy_admin_token and supplied_admin == policy_admin_token:
        return AuthContext(
            subject="bootstrap-admin",
            role="platform-admin",
            tenant_id="*",
            repo_scope=["*"],
            auth_mode="admin-token",
        )

    if not require_auth:
        return AuthContext(subject="anonymous", role="anonymous", tenant_id="public", repo_scope=["*"], auth_mode="none")

    signing_key = os.getenv("AUTH_CONTEXT_SIGNING_KEY", "").strip()

    payload = None
    payload_text = ""
    if x_auth_context:
        payload_text = x_auth_context
        try:
            payload = json.loads(x_auth_context)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"invalid auth context json: {exc}")
    else:
        payload = {
            "subject": x_auth_subject,
            "role": x_auth_role,
            "tenant_id": x_auth_tenant_id,
            "repo_scope": _normalize_scope(x_auth_repo_scope),
        }
        payload_text = json.dumps(payload, sort_keys=True)

    if not _verify_signature(payload_text, x_auth_signature, signing_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid auth signature")

    try:
        ctx = AuthContext.model_validate(payload)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"invalid auth claims: {exc}")

    if not ctx.subject.strip() or not ctx.role.strip() or not ctx.tenant_id.strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing required auth claims")

    if not ctx.repo_scope:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="empty repo scope")

    return ctx


def enforce_role(ctx: AuthContext, allowed_roles: Set[str]):
    if ctx.role not in allowed_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="role not permitted")


def enforce_repo_scope(ctx: AuthContext, repo: str):
    if not repo.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="repo is required for scope check")
    if "*" in ctx.repo_scope:
        return
    if repo not in ctx.repo_scope:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="repo out of scope")


def build_auth_dependency(
    *,
    policy_admin_token: str,
    allowed_roles: Set[str],
    require_auth: bool,
    repo_getter: Optional[Callable[[Request], Optional[str]]] = None,
    on_denied: Optional[Callable[[Request, Optional[AuthContext], str, int], None]] = None,
):
    async def _dep(
        request: Request,
        authorization: Optional[str] = Header(default=None),
        x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
        x_auth_context: Optional[str] = Header(default=None, alias="X-Auth-Context"),
        x_auth_signature: Optional[str] = Header(default=None, alias="X-Auth-Signature"),
        x_auth_subject: Optional[str] = Header(default=None, alias="X-Auth-Subject"),
        x_auth_role: Optional[str] = Header(default=None, alias="X-Auth-Role"),
        x_auth_tenant_id: Optional[str] = Header(default=None, alias="X-Auth-Tenant-Id"),
        x_auth_repo_scope: Optional[str] = Header(default=None, alias="X-Auth-Repo-Scope"),
        x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-Id"),
    ) -> AuthContext:
        ctx: Optional[AuthContext] = None
        try:
            ctx = extract_auth_context(
                authorization=authorization,
                x_admin_token=x_admin_token,
                x_auth_context=x_auth_context,
                x_auth_signature=x_auth_signature,
                x_auth_subject=x_auth_subject,
                x_auth_role=x_auth_role,
                x_auth_tenant_id=x_auth_tenant_id,
                x_auth_repo_scope=x_auth_repo_scope,
                policy_admin_token=policy_admin_token,
                require_auth=require_auth,
            )
            enforce_role(ctx, allowed_roles)

            if x_tenant_id and ctx.tenant_id != "*" and x_tenant_id.strip() != ctx.tenant_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="tenant context mismatch")

            if repo_getter is not None:
                repo = repo_getter(request)
                if repo:
                    enforce_repo_scope(ctx, repo)

            return ctx
        except HTTPException as exc:
            if on_denied is not None:
                try:
                    on_denied(request, ctx, str(exc.detail), int(exc.status_code))
                except Exception:
                    pass
            raise

    return _dep
