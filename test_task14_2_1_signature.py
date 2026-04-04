#!/usr/bin/env python3
"""
Task 14.2.1 verifier:
Compute valid HMAC-SHA256 signature over test payload using GITHUB_WEBHOOK_SECRET.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sys


DEFAULT_PAYLOAD = {
    "action": "opened",
    "repository": {
        "full_name": "Mithil1302/Engineering-Brain",
        "default_branch": "main",
    },
    "pull_request": {
        "number": 1,
        "head": {"sha": "1904df2ec66a8b0a16e08d3e7df4304f294ba8cc"},
        "base": {"ref": "main"},
        "additions": 1,
        "deletions": 0,
    },
    "commits": [],
}


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


def load_payload(payload_file: str | None) -> bytes:
    if payload_file:
        with open(payload_file, "r", encoding="utf-8") as f:
            obj = json.load(f)
        return json.dumps(obj, separators=(",", ":")).encode("utf-8")
    return json.dumps(DEFAULT_PAYLOAD, separators=(",", ":")).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Task 14.2.1 signature generation")
    parser.add_argument("--env-file", default=".env", help="Path to env file containing GITHUB_WEBHOOK_SECRET")
    parser.add_argument("--payload-file", default=None, help="Optional JSON payload file")
    args = parser.parse_args()

    secret = read_env_value(args.env_file, "GITHUB_WEBHOOK_SECRET")
    if not secret:
        print("FAIL: GITHUB_WEBHOOK_SECRET not found")
        return 1

    raw_payload = load_payload(args.payload_file)
    signature = "sha256=" + hmac.new(secret.encode("utf-8"), raw_payload, hashlib.sha256).hexdigest()

    is_valid = bool(re.fullmatch(r"sha256=[0-9a-f]{64}", signature))

    print("Task 14.2.1")
    print("-----------")
    print(f"payload_bytes={len(raw_payload)}")
    print(f"signature={signature}")
    print(f"valid_format={is_valid}")

    if not is_valid:
        print("FAIL: signature format invalid")
        return 1

    print("PASS: valid HMAC-SHA256 signature computed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
