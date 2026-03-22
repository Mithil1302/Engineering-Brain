import json
import subprocess
import time

REPO = "Mithil1302/Pre-Delinquency-Intervention-Engine"
PR_NUMBER = int(time.time()) % 100000
IDEM = f"week2-emit-status-{PR_NUMBER}"


def _produce(payload: dict):
    subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "engbrain-kafka-1",
            "kafka-console-producer",
            "--bootstrap-server",
            "kafka:9092",
            "--topic",
            "repo.events",
        ],
        input=(json.dumps(payload) + "\n").encode(),
        check=True,
    )


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


event = {
    "schema_version": "1.0.0",
    "idempotency_key": IDEM,
    "correlation_id": f"corr-{IDEM}",
    "event_type": "pull_request",
    "repo": {"full_name": REPO, "default_branch": "main"},
    "pull_request": {"number": PR_NUMBER, "title": "week2 emit status test", "author": "validator"},
    "changed_files": [{"path": "api/openapi.yaml", "status": "modified"}],
    "policy_context": {
        "head_spec": {"service_id": "svc", "endpoints": []},
        "base_spec": {"service_id": "svc", "endpoints": []},
        "impact_edges": [],
    },
}

_produce(event)
time.sleep(8)

check_emit_status = _sql(
    f"SELECT emit_status FROM meta.policy_check_runs WHERE repo = '{REPO}' AND pr_number = {PR_NUMBER} AND idempotency_key LIKE '%{IDEM}%' ORDER BY id DESC LIMIT 1;"
)

print({"repo": REPO, "pr_number": PR_NUMBER, "emit_status": check_emit_status})

if check_emit_status != "emitted":
    raise SystemExit(f"expected policy_check_runs.emit_status=emitted, got {check_emit_status}")

print("OK week2 emit status validated")
