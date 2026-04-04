#!/usr/bin/env python3
"""
Task 14.2.2 verifier:
POST to agent-service/webhooks/github with signed pull_request webhook,
verify HTTP 200 within 500ms.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import time

import requests


def read_env_value(path: str, key: str) -> str | None:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Task 14.2.2 webhook POST performance")
    parser.add_argument("--repo", default="Mithil1302/Engineering-Brain")
    parser.add_argument("--pr-number", type=int, default=1)
    parser.add_argument("--head-sha", default="1904df2ec66a8b0a16e08d3e7df4304f294ba8cc")
    parser.add_argument("--default-branch", default="main")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--base-url", default="http://localhost:8002")
    parser.add_argument("--webhook-path", default="/webhooks/github")
    parser.add_argument("--delivery-id", default="task14-2-2-single")
    parser.add_argument("--timeout-seconds", type=int, default=20)
    args = parser.parse_args()

    health_url = args.base_url.rstrip("/") + "/healthz"
    try:
        h = requests.get(health_url, timeout=5)
        if h.status_code != 200:
            print(f"FAIL: agent-service health check returned {h.status_code}")
            return 1
    except Exception as e:
        print(f"FAIL: agent-service health check failed: {e}")
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
    if not re.fullmatch(r"sha256=[0-9a-f]{64}", signature):
        print("FAIL: computed signature format invalid")
        return 1

    url = args.base_url.rstrip("/") + args.webhook_path

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
            timeout=args.timeout_seconds,
        )
    except Exception as e:
        print(f"FAIL: webhook POST request failed: {e}")
        return 1
    latency_ms = (time.perf_counter() - t0) * 1000

    print("Task 14.2.2")
    print("-----------")
    print(f"url={url}")
    print(f"status={resp.status_code}")
    print(f"latency_ms={latency_ms:.2f}")
    print(f"body={resp.text}")

    ok = (resp.status_code == 200 and latency_ms <= 500)
    if ok:
        print("PASS: HTTP 200 within 500ms")
        return 0

    if resp.status_code != 200:
        print("FAIL: expected HTTP 200")
    else:
        print("FAIL: latency exceeded 500ms")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
