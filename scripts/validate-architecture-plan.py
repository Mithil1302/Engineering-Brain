import json
import urllib.request

from auth_headers import build_claims_headers

base = "http://localhost:8003"

payload = {
    "repo": "Mithil1302/Pre-Delinquency-Intervention-Engine",
    "pr_number": 5001,
    "correlation_id": "corr-arch-plan-001",
    "requirement": {
        "requirement_text": "Design an event-driven API governance platform with dashboard, policy controls, and compliance audit workflow.",
        "domain": "architecture-governance",
        "non_functional": {"availability": "99.9", "latency": "p95<300ms"},
        "constraints": {"language": "python", "runtime": "containers"},
        "team": "platform-architecture",
        "target_cloud": "generic"
    }
}

req = urllib.request.Request(
    base + "/architecture/plan",
    data=json.dumps(payload).encode(),
    headers={
        "Content-Type": "application/json",
        **build_claims_headers(
            subject="arch-validator",
            role="architect",
            tenant_id="t1",
            repo_scope=["Mithil1302/Pre-Delinquency-Intervention-Engine"],
        ),
    },
    method="POST",
)
with urllib.request.urlopen(req) as resp:
    print("POST /architecture/plan", resp.status)
    body = json.loads(resp.read().decode())
    print(json.dumps(body, indent=2))

list_req = urllib.request.Request(
    base + "/architecture/plans?repo=Mithil1302/Pre-Delinquency-Intervention-Engine&pr_number=5001&limit=3",
    headers=build_claims_headers(
        subject="arch-validator",
        role="architect",
        tenant_id="t1",
        repo_scope=["Mithil1302/Pre-Delinquency-Intervention-Engine"],
    ),
)
with urllib.request.urlopen(list_req) as resp:
    print("GET /architecture/plans", resp.status)
    listing = json.loads(resp.read().decode())
    print(json.dumps(listing, indent=2))
    if not listing.get("items"):
        raise SystemExit("No persisted architecture plan runs found")

print("OK architecture planning flow validated")
