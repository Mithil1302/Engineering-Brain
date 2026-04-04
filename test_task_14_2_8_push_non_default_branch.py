#!/usr/bin/env python3
"""
Task 14.2.8 verifier:
Send push webhook to non-default branch and verify no Kafka events are produced
for that commit in repo.events and repo.ingestion.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import shlex
import subprocess
import time
import uuid

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


def run_cmd(cmd: list[str], timeout: int = 120) -> tuple[int, str, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def consume_topic(topic: str, timeout_ms: int = 6000, max_messages: int = 5000) -> list[dict]:
    group = f"t14-2-8-{uuid.uuid4().hex[:10]}"
    script = (
        "kafka-console-consumer "
        "--bootstrap-server kafka:9092 "
        f"--group {group} "
        f"--topic {shlex.quote(topic)} "
        "--from-beginning "
        f"--timeout-ms {timeout_ms} "
        f"--max-messages {max_messages}"
    )
    _, out, _ = run_cmd(["docker", "compose", "exec", "-T", "kafka", "bash", "-lc", script], timeout=90)
    events: list[dict] = []
    for ln in out.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            events.append(json.loads(ln))
        except Exception:
            continue
    return events


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Task 14.2.8 non-default push behavior")
    parser.add_argument("--repo", default="Mithil1302/Engineering-Brain")
    parser.add_argument("--default-branch", default="main")
    parser.add_argument("--base-url", default="http://localhost:8002")
    parser.add_argument("--webhook-path", default="/webhooks/github")
    parser.add_argument("--env-file", default=".env")
    args = parser.parse_args()

    # Health check
    try:
        h = requests.get(f"{args.base_url.rstrip('/')}/healthz", timeout=5)
        if h.status_code != 200:
            print(f"FAIL: health status={h.status_code}")
            return 1
    except Exception as e:
        print(f"FAIL: health check failed: {e}")
        return 1

    secret = read_env_value(args.env_file, "GITHUB_WEBHOOK_SECRET")
    if not secret:
        print("FAIL: GITHUB_WEBHOOK_SECRET not found")
        return 1

    sentinel_sha = (uuid.uuid4().hex + uuid.uuid4().hex)[:40]

    before_events = consume_topic("repo.events")
    before_ing = consume_topic("repo.ingestion")
    before_events_hits = sum(1 for e in before_events if str(e.get("head_sha") or "") == sentinel_sha)
    before_ing_hits = sum(1 for e in before_ing if str(e.get("commit_sha") or "") == sentinel_sha)

    payload_obj = {
        "ref": "refs/heads/feature/non-default-branch",
        "repository": {
            "full_name": args.repo,
            "default_branch": args.default_branch,
        },
        "head_commit": {"id": sentinel_sha},
        "commits": [
            {
                "added": ["__t14_2_8_added.txt"],
                "modified": ["__t14_2_8_modified.txt"],
                "removed": ["__t14_2_8_removed.txt"],
            }
        ],
    }
    payload = json.dumps(payload_obj, separators=(",", ":")).encode("utf-8")
    sig = "sha256=" + hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()

    url = args.base_url.rstrip("/") + args.webhook_path
    resp = requests.post(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": sig,
            "X-GitHub-Delivery": f"task14-2-8-{uuid.uuid4()}",
        },
        timeout=20,
    )

    # Give consumers a short settling window
    time.sleep(3)

    after_events = consume_topic("repo.events")
    after_ing = consume_topic("repo.ingestion")

    after_events_hits = sum(1 for e in after_events if str(e.get("head_sha") or "") == sentinel_sha)
    after_ing_hits = sum(1 for e in after_ing if str(e.get("commit_sha") or "") == sentinel_sha)

    new_events_hits = after_events_hits - before_events_hits
    new_ing_hits = after_ing_hits - before_ing_hits

    ok = (resp.status_code == 200) and (new_events_hits == 0) and (new_ing_hits == 0)

    print("Task 14.2.8")
    print("-----------")
    print(f"post_status={resp.status_code}")
    print(f"repo.events_new_hits={new_events_hits}")
    print(f"repo.ingestion_new_hits={new_ing_hits}")

    if ok:
        print("PASS: non-default push produced no Kafka events")
        return 0

    print("FAIL: expected HTTP 200 with zero Kafka emissions for sentinel commit")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
