import json
import urllib.error
import urllib.request

from auth_headers import build_claims_headers

BASE = "http://localhost:8003"


def call(method: str, path: str, payload: dict | None = None, headers: dict | None = None):
    req = urllib.request.Request(
        BASE + path,
        data=(json.dumps(payload).encode() if payload is not None else None),
        headers={"Content-Type": "application/json", **(headers or {})},
        method=method,
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode()
            print(path, resp.status)
            print(body)
            return resp.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        print(path, exc.code)
        print(body)
        return exc.code, body


# 1) Unauthorized admin call should fail
status, _ = call(
    "POST",
    "/policy/admin/templates/upsert",
    payload={"template_name": "week1", "scope_type": "org", "scope_value": "*", "rule_pack": "rules-v1", "rules": {}},
)
if status != 401:
    raise SystemExit(f"expected 401, got {status}")

# 2) Wrong role should fail
status, _ = call(
    "POST",
    "/policy/admin/templates/upsert",
    payload={"template_name": "week1", "scope_type": "org", "scope_value": "*", "rule_pack": "rules-v1", "rules": {}},
    headers=build_claims_headers(
        subject="dev1",
        role="developer",
        tenant_id="t1",
        repo_scope=["Mithil1302/Pre-Delinquency-Intervention-Engine"],
    ),
)
if status != 403:
    raise SystemExit(f"expected 403, got {status}")

# 3) Scoped allowed request should pass
status, _ = call(
    "POST",
    "/policy/evaluate",
    payload={
        "repo": "Mithil1302/Pre-Delinquency-Intervention-Engine",
        "pr_number": 77,
        "head_spec": {"service_id": "svc", "endpoints": []},
        "changed_files": [],
    },
    headers=build_claims_headers(
        subject="dev2",
        role="developer",
        tenant_id="t1",
        repo_scope=["Mithil1302/Pre-Delinquency-Intervention-Engine"],
    ),
)
if status != 200:
    raise SystemExit(f"expected 200, got {status}")

# 4) Tenant mismatch should fail
status, _ = call(
    "POST",
    "/policy/evaluate",
    payload={
        "repo": "Mithil1302/Pre-Delinquency-Intervention-Engine",
        "pr_number": 78,
        "head_spec": {"service_id": "svc", "endpoints": []},
        "changed_files": [],
    },
    headers=build_claims_headers(
        subject="dev2",
        role="developer",
        tenant_id="tenant-alpha",
        repo_scope=["Mithil1302/Pre-Delinquency-Intervention-Engine"],
        tenant_context="tenant-beta",
    ),
)
if status != 403:
    raise SystemExit(f"expected 403 for tenant mismatch, got {status}")

print("OK week1 authz validation passed")
