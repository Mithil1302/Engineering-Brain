from __future__ import annotations

import os
import hashlib
import hmac
import json

from fastapi.testclient import TestClient

os.environ.setdefault("POLICY_PIPELINE_ENABLED", "false")
os.environ.setdefault("AUTH_CONTEXT_SIGNING_KEY", "test-signing-key-week1")

from app.main import app  # noqa: E402


client = TestClient(app)


def _claims_headers(*, subject: str, role: str, tenant: str, repos: list[str]) -> dict[str, str]:
    payload = {
        "subject": subject,
        "role": role,
        "tenant_id": tenant,
        "repo_scope": repos,
    }
    payload_text = json.dumps(payload, sort_keys=True)
    signing_key = os.environ.get("AUTH_CONTEXT_SIGNING_KEY", "")
    sig = hmac.new(signing_key.encode("utf-8"), payload_text.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "X-Auth-Context": payload_text,
        "X-Auth-Signature": sig,
    }


def test_admin_endpoint_requires_auth():
    payload = {
        "template_name": "x",
        "scope_type": "org",
        "scope_value": "*",
        "rule_pack": "rules-v1",
        "rules": {},
    }
    r = client.post("/policy/admin/templates/upsert", json=payload)
    assert r.status_code == 401


def test_admin_endpoint_blocks_wrong_role():
    payload = {
        "template_name": "x",
        "scope_type": "org",
        "scope_value": "*",
        "rule_pack": "rules-v1",
        "rules": {},
    }
    headers = _claims_headers(subject="dev1", role="developer", tenant="t1", repos=["repo/a"])
    r = client.post("/policy/admin/templates/upsert", json=payload, headers=headers)
    assert r.status_code == 403


def test_repo_scope_denied_for_architecture_read():
    headers = _claims_headers(subject="arch1", role="architect", tenant="t1", repos=["repo/allowed"])
    r = client.get(
        "/architecture/plans",
        params={"repo": "repo/blocked", "pr_number": 1, "limit": 2},
        headers=headers,
    )
    assert r.status_code == 403


def test_repo_scope_allows_policy_evaluate():
    headers = _claims_headers(
        subject="dev2",
        role="developer",
        tenant="t1",
        repos=["Mithil1302/Pre-Delinquency-Intervention-Engine"],
    )
    payload = {
        "repo": "Mithil1302/Pre-Delinquency-Intervention-Engine",
        "pr_number": 99,
        "head_spec": {"service_id": "svc", "endpoints": []},
        "changed_files": [],
    }
    r = client.post("/policy/evaluate", json=payload, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["repo"] == "Mithil1302/Pre-Delinquency-Intervention-Engine"


def test_tenant_context_mismatch_denied():
    headers = _claims_headers(
        subject="dev3",
        role="developer",
        tenant="tenant-alpha",
        repos=["Mithil1302/Pre-Delinquency-Intervention-Engine"],
    )
    headers["X-Tenant-Id"] = "tenant-beta"
    payload = {
        "repo": "Mithil1302/Pre-Delinquency-Intervention-Engine",
        "pr_number": 100,
        "head_spec": {"service_id": "svc", "endpoints": []},
        "changed_files": [],
    }
    r = client.post("/policy/evaluate", json=payload, headers=headers)
    assert r.status_code == 403
