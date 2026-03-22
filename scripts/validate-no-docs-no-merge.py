import json
import time
import urllib.request
import subprocess

from auth_headers import build_claims_headers

base = "http://localhost:8003"

# Produce a docs-drift event for team with no docs touched.
event = {
    "schema_version": "1.0.0",
    "idempotency_key": "phase-no-docs-001",
    "correlation_id": "corr-no-docs-001",
    "produced_at": "2026-03-22T12:00:00Z",
    "repo": {
        "id": "Mithil1302/Pre-Delinquency-Intervention-Engine",
        "full_name": "Mithil1302/Pre-Delinquency-Intervention-Engine",
        "url": "https://github.com/Mithil1302/Pre-Delinquency-Intervention-Engine",
        "default_branch": "main",
    },
    "team": "risk-engineering",
    "event_type": "pull_request",
    "pull_request": {"number": 2, "title": "no docs enforcement test", "author": "Mithil1302"},
    "changed_files": [{"path": "api/openapi.yaml", "status": "modified"}],
    "policy_context": {
        "head_spec": {
            "service_id": "pre-delinquency-engine",
            "endpoints": [
                {
                    "method": "POST",
                    "path": "/risk/score",
                    "operation_id": "createRiskScore",
                    "request_required_fields": ["customerId"],
                    "request_enum_fields": {"channel": ["SMS", "EMAIL"]},
                    "response_fields": {"score": "number", "status": "string"},
                    "response_status_codes": ["200"],
                }
            ],
        },
        "base_spec": {
            "service_id": "pre-delinquency-engine",
            "endpoints": [
                {
                    "method": "POST",
                    "path": "/risk/score",
                    "operation_id": "createRiskScore",
                    "request_required_fields": ["customerId"],
                    "request_enum_fields": {"channel": ["SMS", "EMAIL"]},
                    "response_fields": {"score": "number", "status": "string"},
                    "response_status_codes": ["200"],
                }
            ],
        },
        "impact_edges": [],
    },
}

payload = json.dumps(event)
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
    input=payload.encode(),
    check=True,
)

req = urllib.request.Request(
    base + "/policy/dashboard/overview?repo=Mithil1302/Pre-Delinquency-Intervention-Engine&pr_number=2&window=1",
    headers=build_claims_headers(
        subject="nodocs-validator",
        role="developer",
        tenant_id="t1",
        repo_scope=["Mithil1302/Pre-Delinquency-Intervention-Engine"],
    ),
)
with urllib.request.urlopen(req) as _:
    pass

# give worker a moment
time.sleep(10)

# read latest policy_check_runs merge_gate and assert NO_DOCS_NO_MERGE exists
cmd = [
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
    "SELECT merge_gate::text FROM meta.policy_check_runs ORDER BY id DESC LIMIT 1;",
]
result = subprocess.check_output(cmd).decode().strip()
print(result)
if "NO_DOCS_NO_MERGE" not in result:
    raise SystemExit("Expected NO_DOCS_NO_MERGE marker in merge_gate")
print("OK no-docs-no-merge enforced")
