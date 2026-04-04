#!/usr/bin/env python3
"""
Task 14.2.7 verifier:
Send webhook with invalid signature and verify HTTP 401 is returned.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os

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
    parser = argparse.ArgumentParser(description="Verify Task 14.2.7 invalid signature behavior")
    parser.add_argument("--repo", default="Mithil1302/Engineering-Brain")
    parser.add_argument("--pr-number", type=int, default=1)
    parser.add_argument("--head-sha", default="1904df2ec66a8b0a16e08d3e7df4304f294ba8cc")
    parser.add_argument("--default-branch", default="main")
    parser.add_argument("--base-url", default="http://localhost:8002")
    parser.add_argument("--webhook-path", default="/webhooks/github")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--delivery-id", default="task14-2-7-invalid-signature")
    args = parser.parse_args()

    # Health check first
    try:
        h = requests.get(f"{args.base_url.rstrip('/')}/healthz", timeout=5)
        if h.status_code != 200:
            print(f"FAIL: agent-service health status={h.status_code}")
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

    valid_sig = "sha256=" + hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    # Corrupt one character to make signature invalid while preserving format
    invalid_sig = valid_sig[:-1] + ("0" if valid_sig[-1] != "0" else "1")

    url = args.base_url.rstrip("/") + args.webhook_path

    try:
        r = requests.post(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": invalid_sig,
                "X-GitHub-Delivery": args.delivery_id,
            },
            timeout=20,
        )
    except Exception as e:
        print(f"FAIL: webhook request failed: {e}")
        return 1

    print("Task 14.2.7")
    print("-----------")
    print(f"status={r.status_code}")
    print(f"body={r.text}")

    if r.status_code == 401:
        print("PASS: invalid signature rejected with HTTP 401")
        return 0

    print("FAIL: expected HTTP 401 for invalid signature")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
