from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any


def _load_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def resolve_signing_key() -> str:
    from_env = os.getenv("AUTH_CONTEXT_SIGNING_KEY", "").strip()
    if from_env:
        return from_env

    # fallback for local script execution from repository root
    env_map = _load_env_file(Path(".env"))
    return env_map.get("AUTH_CONTEXT_SIGNING_KEY", "").strip()


def build_claims_headers(*, subject: str, role: str, tenant_id: str, repo_scope: list[str], tenant_context: str | None = None) -> dict[str, str]:
    payload: dict[str, Any] = {
        "subject": subject,
        "role": role,
        "tenant_id": tenant_id,
        "repo_scope": repo_scope,
    }
    payload_text = json.dumps(payload, sort_keys=True)
    headers = {
        "X-Auth-Context": payload_text,
    }

    signing_key = resolve_signing_key()
    if signing_key:
        sig = hmac.new(signing_key.encode("utf-8"), payload_text.encode("utf-8"), hashlib.sha256).hexdigest()
        headers["X-Auth-Signature"] = sig

    if tenant_context:
        headers["X-Tenant-Id"] = tenant_context

    return headers
