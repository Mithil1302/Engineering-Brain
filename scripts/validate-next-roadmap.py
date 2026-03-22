import json
import urllib.request

from auth_headers import build_claims_headers

BASE = "http://localhost:8003"


def post(url: str, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        BASE + url,
        data=data,
        headers={
            "Content-Type": "application/json",
            **build_claims_headers(
                subject="roadmap-validator",
                role="platform-lead",
                tenant_id="t1",
                repo_scope=["Mithil1302/Pre-Delinquency-Intervention-Engine"],
            ),
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        out = json.loads(resp.read().decode())
        print(url, resp.status)
        print(json.dumps(out, indent=2))
        return out

# 1) Q&A
post(
    "/assistant/ask",
    {
        "question": "What is the latest architecture plan?",
        "repo": "Mithil1302/Pre-Delinquency-Intervention-Engine",
        "pr_number": 5001,
        "role": "platform-lead",
        "channel": "web",
    },
)

# 2) Onboarding path
onb = post("/onboarding/path?repo=Mithil1302/Pre-Delinquency-Intervention-Engine&pr_number=2&role=architect")
if not onb.get("tasks"):
    raise SystemExit("onboarding tasks missing")

# 3) Time travel simulation
sim = post("/simulation/time-travel?repo=Mithil1302/Pre-Delinquency-Intervention-Engine&pr_number=2&horizon=6")
if not sim.get("projection"):
    raise SystemExit("simulation projection missing")

# 4) Autonomous autofix workflow
af = post("/autofix/run?repo=Mithil1302/Pre-Delinquency-Intervention-Engine&pr_number=2")
if not af.get("workflow"):
    raise SystemExit("autofix workflow missing")

print("OK roadmap increment validation passed")
