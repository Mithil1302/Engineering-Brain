import json
import subprocess
import time
import urllib.request

from auth_headers import build_claims_headers

BASE = "http://localhost:8003"


def _sql(query: str) -> str:
    return (
        subprocess.check_output(
            [
                "docker",
                "exec",
                "engbrain-postgres-1",
                "psql",
                "-U",
                "brain",
                "-d",
                "brain",
                "-t",
                "-A",
                "-c",
                query,
            ]
        )
        .decode()
        .strip()
    )


def _get(path: str):
    req = urllib.request.Request(
        BASE + path,
        headers=build_claims_headers(
            subject="ops-validator",
            role="platform-admin",
            tenant_id="t1",
            repo_scope=["*"],
        ),
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


def _post(path: str, payload: dict):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            **build_claims_headers(
                subject="ops-validator",
                role="platform-admin",
                tenant_id="t1",
                repo_scope=["*"],
            ),
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


# seed an emit-retry poison pill for requeue operation
seed_key = f"emit-retry:ops-seed:{int(time.time())}"
seed_payload = {
    "emit_type": "policy_check",
    "repo": "test-repo",
    "pr_number": 1,
    "base_idempotency_key": "seed-idem",
    "attempt": 4,
    "max_attempts": 5,
    "next_attempt_at": "2000-01-01T00:00:00+00:00",
    "event_payload": {
        "schema_version": "1.0.0",
        "event_type": "pr_policy_check",
        "repo": "test-repo",
        "pr_number": 1,
        "idempotency_key": "seed-idem",
    },
}

_sql(
    "INSERT INTO meta.poison_pills (source_topic, source_partition, source_offset, error, attempts, payload_raw, correlation_id, idempotency_key, status, requeue_count, created_at, updated_at) "
    f"VALUES ('internal.emit_retry', -1, '{seed_key}', 'seed', 1, '{json.dumps(seed_payload)}', 'corr-seed', '{seed_key}', 'quarantined', 0, NOW(), NOW());"
)

poison_id = _sql(f"SELECT id FROM meta.poison_pills WHERE idempotency_key = '{seed_key}' ORDER BY id DESC LIMIT 1;")
if not poison_id:
    raise SystemExit("failed to seed poison pill")

jobs = _get("/policy/admin/emit-retry/jobs?limit=5")
print("jobs", len(jobs.get("items") or []))

dlq = _get("/policy/admin/emit-retry/dead-letters?limit=5")
print("dead-letters", len(dlq.get("items") or []))
if not dlq.get("items"):
    raise SystemExit("expected dead letters list to be non-empty")

out = _post(f"/policy/admin/emit-retry/dead-letters/{poison_id}/requeue", {"reset_attempt": True})
print(json.dumps(out, indent=2))

status = _sql(f"SELECT status FROM meta.poison_pills WHERE id = {poison_id};")
if status != "requeued":
    raise SystemExit(f"expected poison pill status requeued, got {status}")

job_status = _sql(f"SELECT status FROM meta.jobs WHERE id = {out['job']['id']};")
if job_status not in {"queued", "processing", "completed"}:
    raise SystemExit(f"unexpected requeue job status {job_status}")

print("OK week3 ops endpoints validated")
