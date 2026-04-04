#!/usr/bin/env python3
"""
Task 14.3.4 verifier:
After deleting a service directory in the target repo, trigger full ingestion and verify
that active service count decreases and a new ingestion snapshot is created.

Note: This script assumes you have already deleted a service directory in the source repo.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import time
import json

import requests


def run_cmd(cmd: list[str], timeout: int = 120) -> tuple[int, str, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def active_service_count(repo: str) -> int:
    """Count active services from meta.graph_nodes (populated by ingestion pipeline)."""
    sql = (
        "SELECT COUNT(*) FROM meta.graph_nodes "
        f"WHERE repo = '{repo}' AND node_type = 'service';"
    )
    code, out, _ = run_cmd(["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "brain", "-d", "brain", "-tAc", sql], timeout=60)
    if code != 0 or not out:
        return 0
    try:
        return int(out.strip())
    except Exception:
        return 0


def ingestion_snapshot_count(repo: str) -> int:
    sql = (
        "SELECT COUNT(*) FROM meta.architecture_snapshots "
        f"WHERE repo = '{repo}' AND event_type = 'ingestion';"
    )
    code, out, _ = run_cmd(["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "brain", "-d", "brain", "-tAc", sql], timeout=60)
    if code != 0 or not out:
        return 0
    try:
        return int(out.strip())
    except Exception:
        return 0


def get_run_status(run_id: str) -> tuple[str | None, str | None]:
    sql = (
        "SELECT status, COALESCE(error_message, '') "
        "FROM meta.ingestion_runs "
        f"WHERE id = '{run_id}' "
        "LIMIT 1;"
    )
    code, out, err = run_cmd(
        ["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "brain", "-d", "brain", "-tAc", sql],
        timeout=60,
    )
    if code != 0 or not out:
        return None, None

    # psql -tAc with two selected columns returns lines like: status|error
    line = out.splitlines()[-1].strip()
    if "|" in line:
        status, error_message = line.split("|", 1)
        return status.strip() or None, (error_message.strip() or None)
    return line.strip() or None, None


def wait_ingestion_run_success(run_id: str, timeout_sec: int = 300) -> tuple[bool, str | None]:
    deadline = time.time() + timeout_sec
    last_status = None
    last_error = None
    while time.time() < deadline:
        status, error_message = get_run_status(run_id)
        if status:
            last_status = status
            last_error = error_message
            if status == "success":
                return True, None
            if status == "failed":
                return False, error_message
        time.sleep(3)
    return False, f"timeout waiting for run_id={run_id}, last_status={last_status}, last_error={last_error}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Task 14.3.4 service deletion via full ingestion")
    parser.add_argument("--repo", default="Mithil1302/Engineering-Brain")
    parser.add_argument("--worker-base-url", default="http://localhost:8003")
    parser.add_argument("--timeout-seconds", type=int, default=360)
    args = parser.parse_args()

    # Health check
    try:
        h = requests.get(f"{args.worker_base_url.rstrip('/')}/healthz", timeout=5)
        if h.status_code != 200:
            print(f"FAIL: worker-service health status={h.status_code}")
            return 1
    except Exception as e:
        print(f"FAIL: worker-service health check failed: {e}")
        return 1

    before_services = active_service_count(args.repo)
    before_snaps = ingestion_snapshot_count(args.repo)

    r = requests.post(
        f"{args.worker_base_url.rstrip('/')}/ingestion/trigger",
        json={"repo": args.repo},
        timeout=20,
    )
    if r.status_code != 200:
        print(f"FAIL: ingestion trigger status={r.status_code}, body={r.text}")
        return 1

    try:
        body = r.json()
    except Exception:
        body = {}
    run_id = body.get("run_id")
    if not run_id:
        print(f"FAIL: trigger response missing run_id, body={r.text}")
        return 1

    ok_status, failure_reason = wait_ingestion_run_success(run_id, timeout_sec=args.timeout_seconds)
    if not ok_status:
        print("FAIL: ingestion did not reach success state")
        if failure_reason:
            print(f"Reason: {failure_reason}")
        return 1

    after_services = active_service_count(args.repo)
    after_snaps = ingestion_snapshot_count(args.repo)

    # For task 14.3.4 we expect deletion to reduce active services and create a new snapshot.
    services_decreased = after_services < before_services
    snapshot_created = after_snaps > before_snaps

    print("Task 14.3.4")
    print("-----------")
    print(f"before_active_services={before_services}")
    print(f"after_active_services={after_services}")
    print(f"run_id={run_id}")
    print(f"before_ingestion_snapshots={before_snaps}")
    print(f"after_ingestion_snapshots={after_snaps}")
    print(f"services_decreased={services_decreased}")
    print(f"snapshot_created={snapshot_created}")

    if services_decreased and snapshot_created:
        print("PASS: full ingestion reflected service deletion")
        return 0

    print("FAIL: expected active service count to decrease and snapshot count to increase")
    print("Hint: make sure you actually deleted a service directory in the source repo before running.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
