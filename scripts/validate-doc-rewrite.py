import json
import subprocess
import time
import urllib.request

from auth_headers import build_claims_headers

BASE = "http://localhost:8003"
pr_number = int(time.time()) % 100000

# Produce doc refresh event trigger.
event = {
    "schema_version": "1.0.0",
    "idempotency_key": "phase-doc-rewrite-001",
    "correlation_id": "corr-doc-rewrite-002",
    "produced_at": "2026-03-22T12:30:00Z",
    "repo": {
        "id": "Mithil1302/Pre-Delinquency-Intervention-Engine",
        "full_name": "Mithil1302/Pre-Delinquency-Intervention-Engine",
        "url": "https://github.com/Mithil1302/Pre-Delinquency-Intervention-Engine",
        "default_branch": "main",
    },
    "team": "risk-engineering",
    "event_type": "pull_request",
    "pull_request": {"number": pr_number, "title": "doc rewrite test", "author": "Mithil1302"},
    "changed_files": [{"path": "api/openapi.yaml", "status": "modified"}],
    "policy_context": {
        "head_spec": {
            "service_id": "pre-delinquency-engine",
            "endpoints": [
                {
                    "method": "POST",
                    "path": "/risk/score",
                    "operation_id": "createRiskScore",
                    "request_required_fields": ["customerId", "loanId"],
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
    input=(json.dumps(event) + "\n").encode(),
    check=True,
)

time.sleep(10)

req = urllib.request.Request(
    BASE + f"/policy/dashboard/doc-rewrite-runs?repo=Mithil1302/Pre-Delinquency-Intervention-Engine&pr_number={pr_number}&limit=3",
    headers=build_claims_headers(
        subject="doc-validator",
        role="developer",
        tenant_id="t1",
        repo_scope=["Mithil1302/Pre-Delinquency-Intervention-Engine"],
    ),
)
with urllib.request.urlopen(req) as r:
    body = r.read().decode()
    print(body)
    if '"status": "emitted"' not in body and '"status":"emitted"' not in body:
        raise SystemExit("expected emitted doc rewrite run")

print("OK doc rewrite orchestration validated")
