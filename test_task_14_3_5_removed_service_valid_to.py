#!/usr/bin/env python3
"""
Task 14.3.5 verifier:
Verify that removed service nodes have valid_to set in meta.architecture_nodes.

This script assumes 14.3.4 was run after deleting a service directory.
"""

from __future__ import annotations

import argparse
import subprocess


def run_cmd(cmd: list[str], timeout: int = 120) -> tuple[int, str, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def sql_scalar(sql: str) -> str:
    code, out, err = run_cmd(["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "brain", "-d", "brain", "-tAc", sql], timeout=90)
    if code != 0:
        raise RuntimeError(err or "SQL execution failed")
    return out.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Task 14.3.5 removed service valid_to")
    parser.add_argument("--repo", default="Mithil1302/Engineering-Brain")
    parser.add_argument("--expected-removed-service", default=None, help="Optional exact service name expected to be removed")
    args = parser.parse_args()

    # Need at least 2 ingestion snapshots to identify the latest ingestion window.
    snapshot_count = int(sql_scalar(
        "SELECT COUNT(*) FROM meta.architecture_snapshots "
        f"WHERE repo = '{args.repo}' AND event_type = 'ingestion';"
    ) or "0")

    if snapshot_count < 2:
        print("Task 14.3.5")
        print("-----------")
        print(f"FAIL: need at least 2 ingestion snapshots, found={snapshot_count}")
        return 1

    latest_ts = sql_scalar(
        "SELECT timestamp::text FROM meta.architecture_snapshots "
        f"WHERE repo = '{args.repo}' AND event_type='ingestion' "
        "ORDER BY timestamp DESC LIMIT 1;"
    )
    prev_ts = sql_scalar(
        "SELECT timestamp::text FROM meta.architecture_snapshots "
        f"WHERE repo = '{args.repo}' AND event_type='ingestion' "
        "ORDER BY timestamp DESC OFFSET 1 LIMIT 1;"
    )

    # Find services end-dated in the interval between previous and latest ingestion.
    rows_sql = (
        "SELECT name || '|' || node_id || '|' || valid_to::text FROM meta.architecture_nodes "
        f"WHERE repo = '{args.repo}' AND node_type='service' "
        "AND valid_to IS NOT NULL "
        f"AND valid_to >= '{prev_ts}'::timestamptz "
        f"AND valid_to <= '{latest_ts}'::timestamptz "
        "ORDER BY valid_to DESC;"
    )
    code, out, err = run_cmd(["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "brain", "-d", "brain", "-tAc", rows_sql], timeout=90)
    if code != 0:
        print("Task 14.3.5")
        print("-----------")
        print(f"FAIL: SQL failed: {err}")
        return 1

    lines = [ln for ln in out.splitlines() if ln.strip()]

    expected_ok = True
    if args.expected_removed_service:
        expected_ok = any(ln.split("|", 1)[0] == args.expected_removed_service for ln in lines)

    ok = len(lines) > 0 and expected_ok

    print("Task 14.3.5")
    print("-----------")
    print(f"repo={args.repo}")
    print(f"previous_ingestion_ts={prev_ts}")
    print(f"latest_ingestion_ts={latest_ts}")
    print(f"end_dated_services_in_window={len(lines)}")
    if args.expected_removed_service:
        print(f"expected_removed_service={args.expected_removed_service}")
        print(f"expected_service_found={expected_ok}")

    for ln in lines[:10]:
        name, node_id, valid_to = ln.split("|", 2)
        print(f"- {name} ({node_id}) valid_to={valid_to}")

    if ok:
        print("PASS: removed service node(s) have valid_to set")
        return 0

    print("FAIL: no removed service node found with valid_to in latest ingestion window")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
