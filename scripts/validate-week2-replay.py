import json
import subprocess
import time

REPO = "Mithil1302/Pre-Delinquency-Intervention-Engine"
PR_NUMBER = int(time.time()) % 100000
IDEM = f"week2-replay-{PR_NUMBER}"


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
    "repo": {
        "full_name": REPO,
        "default_branch": "main",
    },
    "pull_request": {"number": PR_NUMBER, "title": "week2 replay test", "author": "validator"},
    "changed_files": [{"path": "api/openapi.yaml", "status": "modified"}],
    "policy_context": {
        "head_spec": {"service_id": "svc", "endpoints": []},
        "base_spec": {"service_id": "svc", "endpoints": []},
        "impact_edges": [],
    },
}

# produce same payload twice
_produce(event)
_produce(event)

# allow async worker to process
time.sleep(10)

processed_count = _sql(
    f"SELECT COUNT(*) FROM meta.processed_events WHERE event_key LIKE 'policy:{REPO}:{PR_NUMBER}:rules-v1:%{IDEM}%';"
)
runs_count = _sql(
    f"SELECT COUNT(*) FROM meta.policy_check_runs WHERE repo = '{REPO}' AND pr_number = {PR_NUMBER} AND idempotency_key LIKE '%{IDEM}%';"
)

print({"processed_events": processed_count, "policy_check_runs": runs_count, "repo": REPO, "pr_number": PR_NUMBER})

if processed_count != "1":
    raise SystemExit(f"expected 1 processed_events row, got {processed_count}")
if runs_count != "1":
    raise SystemExit(f"expected 1 policy_check_runs row, got {runs_count}")

print("OK week2 replay guard validated")
