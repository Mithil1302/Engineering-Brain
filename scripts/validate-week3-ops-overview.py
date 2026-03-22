import json
import urllib.request

from auth_headers import build_claims_headers

BASE = "http://localhost:8003"


def _get(path: str):
    req = urllib.request.Request(
        BASE + path,
        headers=build_claims_headers(
            subject="ops-overview-validator",
            role="platform-admin",
            tenant_id="t1",
            repo_scope=["*"],
        ),
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


out = _get("/policy/admin/emit-retry/overview?window_hours=24")
print(json.dumps(out, indent=2))

if "queue" not in out or "dead_letter" not in out or "window_metrics" not in out:
    raise SystemExit("overview response missing expected sections")

queue = out["queue"]
if "status_counts" not in queue:
    raise SystemExit("overview missing queue.status_counts")

metrics = out["window_metrics"]
if "completed" not in metrics or "dead_lettered" not in metrics:
    raise SystemExit("overview missing window metrics counts")

print("OK week3 ops overview validated")
