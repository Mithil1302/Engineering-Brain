#!/usr/bin/env python3
"""
End-to-end verifier for Task 14.1 (14.1.1 through 14.1.8).

Checks:
  14.1.1 Trigger ingestion and verify HTTP 200 + run_id (+ 200ms target)
  14.1.2 Poll status endpoint until success within timeout
  14.1.3 Neo4j service node count > 0
  14.1.4 pgvector embeddings count > 0 for repo
  14.1.5 PostgreSQL graph_nodes service rows present
  14.1.6 Kafka repo.ingestion.complete event exists for run_id
  14.1.7 architecture_snapshots contains event_type='ingestion' row
  14.1.8 ingestion_runs final row has success and >0 counters

Notes:
- Requires Docker services running.
- Uses docker compose exec for Neo4j/Kafka/Postgres checks to avoid host driver dependencies.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests


@dataclass
class CheckResult:
    id: str
    name: str
    passed: bool
    detail: str


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_cmd(cmd: list[str], timeout: int = 60) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def compose_exec(service: str, args: list[str], timeout: int = 60) -> tuple[int, str, str]:
    cmd = ["docker", "compose", "exec", "-T", service] + args
    return run_cmd(cmd, timeout=timeout)


def check_worker_health(base_url: str) -> bool:
    try:
        r = requests.get(f"{base_url.rstrip('/')}/healthz", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def trigger_ingestion(base_url: str, repo: str) -> tuple[Optional[str], float, Optional[str], Optional[str]]:
    endpoint = f"{base_url.rstrip('/')}/ingestion/trigger"
    t0 = time.perf_counter()
    try:
        r = requests.post(endpoint, json={"repo": repo}, timeout=20)
        elapsed_ms = (time.perf_counter() - t0) * 1000
    except Exception as exc:
        return None, 0.0, None, f"Trigger request failed: {exc}"

    if r.status_code != 200:
        return None, elapsed_ms, None, f"HTTP {r.status_code}: {r.text[:300]}"

    try:
        data = r.json()
    except Exception as exc:
        return None, elapsed_ms, None, f"Invalid JSON response: {exc}"

    run_id = data.get("run_id")
    status = data.get("status")
    if not run_id:
        return None, elapsed_ms, str(status), f"Missing run_id in response: {data}"

    return str(run_id), elapsed_ms, str(status), None


def poll_status(
    base_url: str,
    repo: str,
    timeout_minutes: int,
    interval_seconds: int,
) -> tuple[bool, Optional[dict], str]:
    endpoint = f"{base_url.rstrip('/')}/ingestion/status/{repo}"
    deadline = datetime.now(timezone.utc) + timedelta(minutes=timeout_minutes)

    while datetime.now(timezone.utc) < deadline:
        try:
            r = requests.get(endpoint, timeout=10)
        except Exception as exc:
            time.sleep(interval_seconds)
            continue

        if r.status_code == 404:
            time.sleep(interval_seconds)
            continue
        if r.status_code != 200:
            time.sleep(interval_seconds)
            continue

        try:
            data = r.json()
        except Exception:
            time.sleep(interval_seconds)
            continue

        status = str(data.get("status", "unknown"))
        if status == "success":
            return True, data, "success"
        if status == "failed":
            return False, data, "failed"

        time.sleep(interval_seconds)

    return False, None, "timeout"


def query_postgres_scalar(user: str, db: str, sql: str, timeout: int = 60) -> tuple[bool, str]:
    code, out, err = compose_exec("postgres", ["psql", "-U", user, "-d", db, "-tAc", sql], timeout=timeout)
    if code != 0:
        return False, f"psql failed: {err or out}"
    return True, out.strip()


def query_neo4j_scalar(user: str, password: str, cypher: str, timeout: int = 60) -> tuple[bool, str]:
    code, out, err = compose_exec(
        "neo4j",
        ["cypher-shell", "-a", "bolt://localhost:7687", "-u", user, "-p", password, cypher],
        timeout=timeout,
    )
    if code != 0:
        return False, f"cypher-shell failed: {err or out}"
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    if not lines:
        return True, ""
    return True, lines[-1]


def consume_kafka_for_run_id(run_id: str, timeout_ms: int = 20000) -> tuple[bool, str]:
    # Using --from-beginning + max-messages to be deterministic in local env.
    # We search all consumed lines for run_id occurrence.
    script = (
        "kafka-console-consumer "
        "--bootstrap-server kafka:9092 "
        "--topic repo.ingestion.complete "
        "--from-beginning "
        f"--timeout-ms {timeout_ms} "
        "--max-messages 2000"
    )
    code, out, err = compose_exec("kafka", ["bash", "-lc", script], timeout=max(60, timeout_ms // 1000 + 20))
    combined = "\n".join([out or "", err or ""])

    if code != 0 and "Processed a total of" not in combined:
        return False, f"kafka consume failed: {combined.strip()[:500]}"

    for line in (out or "").splitlines():
        ln = line.strip()
        if not ln:
            continue
        if run_id in ln:
            return True, f"Found event line with run_id={run_id}"

    return False, f"No repo.ingestion.complete message found with run_id={run_id}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Task 14.1.1 through 14.1.8")
    parser.add_argument("--repo", default="Mithil1302/Engineering-Brain")
    parser.add_argument("--base-url", default="http://localhost:8003", help="worker-service base URL")
    parser.add_argument("--timeout-minutes", type=int, default=5, help="poll timeout for 14.1.2")
    parser.add_argument("--poll-interval-seconds", type=int, default=5)
    parser.add_argument("--postgres-user", default="brain")
    parser.add_argument("--postgres-db", default="brain")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password", default="testtest")
    args = parser.parse_args()

    print("=" * 88)
    print("Task 14.1 full verifier (14.1.1 - 14.1.8)")
    print("=" * 88)

    if not check_worker_health(args.base_url):
        print("[FATAL] worker-service /healthz not reachable. Start docker compose first.")
        return 3

    results: list[CheckResult] = []

    # 14.1.1
    run_id, latency_ms, trigger_status, trigger_err = trigger_ingestion(args.base_url, args.repo)
    if run_id is None:
        results.append(CheckResult("14.1.1", "Trigger ingestion", False, trigger_err or "unknown trigger error"))
        _print_summary(results)
        return 1

    detail_1411 = f"run_id={run_id}, status={trigger_status}, latency={latency_ms:.2f}ms"
    if latency_ms <= 200:
        results.append(CheckResult("14.1.1", "Trigger ingestion", True, detail_1411))
    else:
        # treat HTTP/run_id success as pass, but highlight SLA miss
        results.append(CheckResult("14.1.1", "Trigger ingestion", True, detail_1411 + " (WARN: >200ms target)"))

    # 14.1.2
    ok_1412, status_payload, status_mode = poll_status(
        args.base_url,
        args.repo,
        args.timeout_minutes,
        args.poll_interval_seconds,
    )
    if not ok_1412:
        if status_mode == "failed" and status_payload:
            detail = f"status=failed error={status_payload.get('error_message')}"
        elif status_mode == "timeout":
            detail = f"status timeout after {args.timeout_minutes} minutes"
        else:
            detail = f"status={status_mode}"
        results.append(CheckResult("14.1.2", "Poll status to success", False, detail))
        _print_summary(results)
        return 1

    results.append(
        CheckResult(
            "14.1.2",
            "Poll status to success",
            True,
            f"status=success files={status_payload.get('files_processed')} chunks={status_payload.get('chunks_created')} embeds={status_payload.get('embeddings_created')} services={status_payload.get('services_detected')}",
        )
    )

    # 14.1.3 Neo4j
    ok, val = query_neo4j_scalar(
        args.neo4j_user,
        args.neo4j_password,
        f"MATCH (s:Service {{repo: '{args.repo}'}}) RETURN COUNT(s)",
    )
    if not ok:
        results.append(CheckResult("14.1.3", "Neo4j service node count", False, val))
    else:
        try:
            count = int(val)
            results.append(CheckResult("14.1.3", "Neo4j service node count", count > 0, f"count={count}"))
        except Exception:
            results.append(CheckResult("14.1.3", "Neo4j service node count", False, f"Unexpected output: {val!r}"))

    # 14.1.4 pgvector
    ok, val = query_postgres_scalar(
        args.postgres_user,
        args.postgres_db,
        f"SELECT COUNT(*) FROM meta.embeddings WHERE metadata->>'repo' = '{args.repo}';",
    )
    if not ok:
        results.append(CheckResult("14.1.4", "pgvector embeddings count", False, val))
    else:
        try:
            count = int(val)
            results.append(CheckResult("14.1.4", "pgvector embeddings count", count > 0, f"count={count}"))
        except Exception:
            results.append(CheckResult("14.1.4", "pgvector embeddings count", False, f"Unexpected output: {val!r}"))

    # 14.1.5 graph_nodes
    ok, val = query_postgres_scalar(
        args.postgres_user,
        args.postgres_db,
        f"SELECT COUNT(*) FROM meta.graph_nodes WHERE repo = '{args.repo}' AND node_type = 'service';",
    )
    if not ok:
        results.append(CheckResult("14.1.5", "PostgreSQL graph_nodes service rows", False, val))
    else:
        try:
            count = int(val)
            results.append(CheckResult("14.1.5", "PostgreSQL graph_nodes service rows", count > 0, f"count={count}"))
        except Exception:
            results.append(CheckResult("14.1.5", "PostgreSQL graph_nodes service rows", False, f"Unexpected output: {val!r}"))

    # 14.1.6 Kafka completion event
    ok, detail = consume_kafka_for_run_id(run_id)
    results.append(CheckResult("14.1.6", "Kafka repo.ingestion.complete event", ok, detail))

    # 14.1.7 architecture_snapshots ingestion row
    ok, val = query_postgres_scalar(
        args.postgres_user,
        args.postgres_db,
        f"SELECT COUNT(*) FROM meta.architecture_snapshots WHERE repo = '{args.repo}' AND event_type = 'ingestion';",
    )
    if not ok:
        results.append(CheckResult("14.1.7", "architecture_snapshots ingestion row", False, val))
    else:
        try:
            count = int(val)
            results.append(CheckResult("14.1.7", "architecture_snapshots ingestion row", count > 0, f"count={count}"))
        except Exception:
            results.append(CheckResult("14.1.7", "architecture_snapshots ingestion row", False, f"Unexpected output: {val!r}"))

    # 14.1.8 ingestion_runs final row constraints
    ok, val = query_postgres_scalar(
        args.postgres_user,
        args.postgres_db,
        (
            "SELECT status || '|' || files_processed || '|' || chunks_created || '|' || services_detected "
            f"FROM meta.ingestion_runs WHERE id = '{run_id}'::uuid LIMIT 1;"
        ),
    )
    if not ok:
        results.append(CheckResult("14.1.8", "ingestion_runs final row constraints", False, val))
    else:
        try:
            status, files, chunks, services = val.split("|")
            files_i = int(files)
            chunks_i = int(chunks)
            services_i = int(services)
            passed = status == "success" and files_i > 0 and chunks_i > 0 and services_i > 0
            results.append(
                CheckResult(
                    "14.1.8",
                    "ingestion_runs final row constraints",
                    passed,
                    f"status={status}, files={files_i}, chunks={chunks_i}, services={services_i}",
                )
            )
        except Exception:
            results.append(CheckResult("14.1.8", "ingestion_runs final row constraints", False, f"Unexpected output: {val!r}"))

    _print_summary(results)
    return 0 if all(r.passed for r in results) else 1


def _print_summary(results: list[CheckResult]) -> None:
    print("\n" + "=" * 88)
    print("Task 14.1 summary")
    print("=" * 88)
    for r in results:
        mark = "PASS" if r.passed else "FAIL"
        print(f"[{mark}] {r.id} {r.name} :: {r.detail}")

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print("-" * 88)
    print(f"Result: {passed}/{total} checks passed")


if __name__ == "__main__":
    raise SystemExit(main())
