#!/usr/bin/env python3
"""
Task 14.2.3 verifier:
Verify meta.check_run_tracking has a row within 2 seconds of webhook.

Flow:
1) Build signed pull_request webhook payload using GITHUB_WEBHOOK_SECRET.
2) POST to agent-service webhook endpoint.
3) Poll PostgreSQL meta.check_run_tracking for matching (repo, pr_number, head_sha)
   and require row appearance within 2 seconds.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import subprocess
import time
from typing import Optional

import requests


def read_env_value(path: str, key: str) -> Optional[str]:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1]
    return None


def run_cmd(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def query_check_run_id(repo: str, pr_number: int, head_sha: str) -> Optional[int]:
    repo_esc = repo.replace("'", "''")
    sha_esc = head_sha.replace("'", "''")
    sql = (
        "SELECT check_run_id FROM meta.check_run_tracking "
        f"WHERE repo = '{repo_esc}' AND pr_number = {pr_number} AND head_sha = '{sha_esc}' "
        "ORDER BY created_at DESC LIMIT 1;"
    )
    code, out, err = run_cmd(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "brain",
            "-d",
            "brain",
            "-tAc",
            sql,
        ],
        timeout=30,
    )
    if code != 0:
        return None
    if not out:
        return None
    try:
        return int(out)
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Task 14.2.3 check_run_tracking within 2 seconds")
    parser.add_argument("--repo", default="Mithil1302/Engineering-Brain")
    parser.add_argument("--pr-number", type=int, default=1)
    parser.add_argument("--head-sha", default="1904df2ec66a8b0a16e08d3e7df4304f294ba8cc")
    parser.add_argument("--default-branch", default="main")
    parser.add_argument("--base-url", default="http://localhost:8002")
    parser.add_argument("--webhook-path", default="/webhooks/github")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--delivery-id", default="task14-2-3-single")
    parser.add_argument("--timeout-seconds", type=float, default=2.0)
    args = parser.parse_args()

    # Health check
    try:
        h = requests.get(f"{args.base_url.rstrip('/')}/healthz", timeout=5)
        if h.status_code != 200:
            print(f"FAIL: agent-service health status={h.status_code}")
            return 1
    except Exception as e:
        print(f"FAIL: agent-service health check error: {e}")
        return 1

    secret = read_env_value(args.env_file, "GITHUB_WEBHOOK_SECRET")
    if not secret:
        print("FAIL: GITHUB_WEBHOOK_SECRET not found")
        return 1

    payload_obj = {
        "action": "opened",
        "repository": {
            "full_name": args.repo,
            "default_branch": args.default_branch,
        },
        "pull_request": {
            "number": args.pr_number,
            "head": {"sha": args.head_sha},
            "base": {"ref": args.default_branch},
            "additions": 1,
            "deletions": 0,
        },
        "commits": [],
    }
    payload = json.dumps(payload_obj, separators=(",", ":")).encode("utf-8")
    signature = "sha256=" + hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()

    url = args.base_url.rstrip("/") + args.webhook_path

    # Trigger webhook
    t0 = time.perf_counter()
    try:
        resp = requests.post(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": signature,
                "X-GitHub-Delivery": args.delivery_id,
            },
            timeout=20,
        )
    except Exception as e:
        print(f"FAIL: webhook POST failed: {e}")
        return 1

    if resp.status_code != 200:
        print(f"FAIL: webhook status={resp.status_code}, body={resp.text}")
        return 1

    # Poll check_run_tracking within timeout window
    deadline = time.perf_counter() + args.timeout_seconds
    check_run_id = None
    while time.perf_counter() < deadline:
        check_run_id = query_check_run_id(args.repo, args.pr_number, args.head_sha)
        if check_run_id is not None:
            break
        time.sleep(0.2)

    elapsed_ms = (time.perf_counter() - t0) * 1000

    print("Task 14.2.3")
    print("-----------")
    print(f"webhook_status={resp.status_code}")
    print(f"elapsed_ms_total={elapsed_ms:.2f}")
    print(f"check_run_id={check_run_id}")

    if check_run_id is not None:
        print("PASS: meta.check_run_tracking row found within timeout")
        return 0

    print("FAIL: no matching meta.check_run_tracking row found within 2 seconds")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
