import json
import urllib.request
import urllib.parse

from auth_headers import build_claims_headers

base = "http://localhost:8003"


def post(path: str, payload: dict):
    req = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            **build_claims_headers(
                subject="gov-validator",
                role="platform-admin",
                tenant_id="t1",
                repo_scope=["*"],
            ),
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        print(path, resp.status)
        print(resp.read().decode())


def get(path: str):
    parsed = urllib.parse.urlparse(path)
    q = urllib.parse.parse_qs(parsed.query)
    repo = (q.get("repo") or ["*"])[0]
    req = urllib.request.Request(
        base + path,
        headers=build_claims_headers(
            subject="gov-validator",
            role="platform-admin",
            tenant_id="t1",
            repo_scope=[repo if repo else "*"],
        ),
    )
    with urllib.request.urlopen(req) as resp:
        print(path, resp.status)
        print(resp.read().decode())


post(
    "/policy/admin/templates/upsert",
    {
        "template_name": "org-default-strict-docs",
        "scope_type": "org",
        "scope_value": "*",
        "rule_pack": "rules-v1",
        "rules": {
            "DOC_DRIFT_ENDPOINT_CHANGED_NO_DOC": {"enabled": True, "severity": "high"},
            "DOC_DRIFT_MISSING_OWNER": {"enabled": True, "severity": "high"},
        },
        "fail_blocks_merge": True,
        "warn_blocks_merge": True,
        "no_docs_no_merge": True,
        "metadata": {"owner": "platform-architecture"},
        "enabled": True,
        "priority": 100,
    },
)

post(
    "/policy/admin/templates/upsert",
    {
        "template_name": "team-risk-overrides",
        "scope_type": "team",
        "scope_value": "risk-engineering",
        "rule_pack": "rules-v1",
        "rules": {
            "IMPACT_PROPAGATION": {"enabled": True, "severity": "high"},
        },
        "fail_blocks_merge": True,
        "warn_blocks_merge": False,
        "no_docs_no_merge": True,
        "metadata": {"owner": "team-risk-engineering"},
        "enabled": True,
        "priority": 10,
    },
)

get("/policy/admin/templates")
get("/policy/admin/templates/effective?repo=Mithil1302/Pre-Delinquency-Intervention-Engine&team=risk-engineering")
