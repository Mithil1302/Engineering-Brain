import json
import urllib.request

from auth_headers import build_claims_headers

BASE = "http://localhost:8003"
REPO = "Mithil1302/Pre-Delinquency-Intervention-Engine"


def post(path: str, payload: dict):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            **build_claims_headers(
                subject="waiver-validator",
                role="platform-admin",
                tenant_id="t1",
                repo_scope=[REPO],
            ),
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        body = resp.read().decode()
        print(path, resp.status)
        print(body)
        return json.loads(body)


def get(path: str):
    req = urllib.request.Request(
        BASE + path,
        headers=build_claims_headers(
            subject="waiver-validator",
            role="platform-admin",
            tenant_id="t1",
            repo_scope=[REPO],
        ),
    )
    with urllib.request.urlopen(req) as resp:
        body = resp.read().decode()
        print(path, resp.status)
        print(body)
        return json.loads(body)


waiver = post(
    "/policy/admin/waivers/request",
    {
        "repo": "Mithil1302/Pre-Delinquency-Intervention-Engine",
        "pr_number": 2,
        "rule_set": "rules-v1",
        "requested_by": "divya",
        "requested_role": "developer",
        "reason": "Temporary exception for controlled rollout",
        "expires_at": "2026-12-31T00:00:00Z",
        "required_approvals": 2,
        "approval_chain": ["staff-engineer", "architecture-reviewer"],
        "scope": {"rules": ["BREAKING_REQUEST_TIGHTENING", "BREAKING_RESPONSE_CHANGE"]},
        "metadata": {"ticket": "ENG-1234"},
    },
)

wid = waiver["id"]

post(
    f"/policy/admin/waivers/{wid}/decision",
    {
        "decision": "approve",
        "approver": "alice",
        "approver_role": "staff-engineer",
        "notes": "Approved with condition",
    },
)

post(
    f"/policy/admin/waivers/{wid}/decision",
    {
        "decision": "approve",
        "approver": "bob",
        "approver_role": "architecture-reviewer",
        "notes": "Architecture sign-off",
    },
)

get("/policy/admin/waivers?repo=Mithil1302/Pre-Delinquency-Intervention-Engine&pr_number=2")
