import json
import urllib.request

from auth_headers import build_claims_headers

base = "http://localhost:8003"

questions = [
    {
        "question": "What is the latest merge gate decision for this PR?",
        "repo": "Mithil1302/Pre-Delinquency-Intervention-Engine",
        "pr_number": 2,
        "channel": "chat",
        "role": "developer",
    },
    {
        "question": "Show documentation automation status and rewrite run",
        "repo": "Mithil1302/Pre-Delinquency-Intervention-Engine",
        "pr_number": 2,
        "channel": "web",
        "role": "architect",
    },
    {
        "question": "What is our latest architecture plan?",
        "repo": "Mithil1302/Pre-Delinquency-Intervention-Engine",
        "pr_number": 5001,
        "channel": "api",
        "role": "platform-lead",
    },
]

for q in questions:
    req = urllib.request.Request(
        base + "/assistant/ask",
        data=json.dumps(q).encode(),
        headers={
            "Content-Type": "application/json",
            **build_claims_headers(
                subject="qa-validator",
                role=q.get("role") or "developer",
                tenant_id="t1",
                repo_scope=[q["repo"]],
            ),
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        print("/assistant/ask", resp.status)
        body = json.loads(resp.read().decode())
        print(json.dumps(body, indent=2))
        if not body.get("answer"):
            raise SystemExit("assistant answer missing")

print("OK assistant QA validated")
