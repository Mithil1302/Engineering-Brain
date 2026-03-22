import json
import subprocess
import time


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

job_key = f"emit-retry:unsupported:test-repo:1:{int(time.time())}"

payload = {
    "emit_type": "unsupported",
    "repo": "test-repo",
    "pr_number": 1,
    "base_idempotency_key": "test-idem",
    "attempt": 0,
    "max_attempts": 1,
    "next_attempt_at": "2000-01-01T00:00:00+00:00",
    "event_payload": {"foo": "bar"},
}

insert = (
    "INSERT INTO meta.jobs (job_type, idempotency_key, correlation_id, status, payload, created_at, updated_at) "
    f"VALUES ('emit_retry', '{job_key}', 'corr-retry-worker', 'queued', '{json.dumps(payload)}'::jsonb, NOW(), NOW()) "
    "ON CONFLICT (idempotency_key) DO NOTHING;"
)
_sql(insert)

# let worker poll and process retries
for _ in range(8):
    time.sleep(2)
    status = _sql(f"SELECT status FROM meta.jobs WHERE idempotency_key = '{job_key}' LIMIT 1;")
    if status == "dead_letter":
        break

status = _sql(f"SELECT status FROM meta.jobs WHERE idempotency_key = '{job_key}' LIMIT 1;")
poison = _sql(
    "SELECT COUNT(*) FROM meta.poison_pills "
    f"WHERE source_topic = 'internal.emit_retry' AND idempotency_key = '{job_key}';"
)

print({"job_key": job_key, "status": status, "poison_pills": poison})

if status != "dead_letter":
    raise SystemExit(f"expected dead_letter status, got {status}")
if poison != "1":
    raise SystemExit(f"expected poison pill row count 1, got {poison}")

print("OK week2 retry worker dead-letter path validated")
