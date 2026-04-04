#!/usr/bin/env python3
"""
Task 14.2.5 verifier:
Consume repo.ingestion Kafka topic and verify incremental ingestion event
with the same changed_files as the corresponding repo.events pull_request event.
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


def run_cmd(cmd: list[str], timeout: int = 60) -> tuple[int, str, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def read_agent_env_value(key: str) -> Optional[str]:
    code, out, _ = run_cmd(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "agent-service",
            "python",
            "-c",
            f"import os; print(os.getenv('{key}', ''))",
        ],
        timeout=30,
    )
    if code != 0:
        return None
    val = out.strip()
    return val or None


def start_consumer(topic: str, timeout_sec: int, max_messages: int) -> subprocess.Popen:
    script = (
        "kafka-console-consumer "
        "--bootstrap-server kafka:9092 "
        f"--topic {shlex.quote(topic)} "
        f"--timeout-ms {int(timeout_sec * 1000)} "
        f"--max-messages {int(max_messages)}"
    )
    cmd = ["docker", "compose", "exec", "-T", "kafka", "bash", "-lc", script]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def collect_events(proc: subprocess.Popen, timeout_sec: int) -> list[dict]:
    try:
        out, _ = proc.communicate(timeout=timeout_sec + 6)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate()

    events: list[dict] = []
    for ln in (out or "").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            events.append(json.loads(ln))
        except Exception:
            continue
    return events


def consume_topic_from_beginning(topic: str, timeout_ms: int = 8000, max_messages: int = 5000) -> list[dict]:
    group = f"t14-2-5-{uuid.uuid4().hex[:12]}"
    script = (
        "kafka-console-consumer "
        "--bootstrap-server kafka:9092 "
        f"--group {group} "
        f"--topic {shlex.quote(topic)} "
        "--from-beginning "
        f"--timeout-ms {int(timeout_ms)} "
        f"--max-messages {int(max_messages)}"
    )
    _, out, _ = run_cmd(
        ["docker", "compose", "exec", "-T", "kafka", "bash", "-lc", script],
        timeout=max(40, timeout_ms // 1000 + 20),
    )
    events: list[dict] = []
    for ln in (out or "").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            events.append(json.loads(ln))
        except Exception:
            continue
    return events


def matching_pr_events(events: list[dict], repo: str, pr_number: int, head_sha: str) -> list[dict]:
    matched: list[dict] = []
    for ev in events:
        try:
            if (
                ev.get("event_type") == "pull_request"
                and ev.get("repo") == repo
                and int(ev.get("pr_number") or 0) == int(pr_number)
                and str(ev.get("head_sha") or "") == str(head_sha)
                and isinstance(ev.get("changed_files"), list)
            ):
                matched.append(ev)
        except Exception:
            continue
    return matched


def matching_ingestion_events(events: list[dict], repo: str, head_sha: str) -> list[dict]:
    matched: list[dict] = []
    for ev in events:
        try:
            if (
                ev.get("repo") == repo
                and str(ev.get("commit_sha") or "") == str(head_sha)
                and isinstance(ev.get("changed_files"), list)
            ):
                matched.append(ev)
        except Exception:
            continue
    return matched


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Task 14.2.5 repo.ingestion event")
    parser.add_argument("--repo", default="Mithil1302/Engineering-Brain")
    parser.add_argument("--pr-number", type=int, default=1)
    parser.add_argument("--head-sha", default="1904df2ec66a8b0a16e08d3e7df4304f294ba8cc")
    parser.add_argument("--default-branch", default="main")
    parser.add_argument("--base-url", default="http://localhost:8002")
    parser.add_argument("--webhook-path", default="/webhooks/github")
    parser.add_argument("--delivery-id", default="task14-2-5-single")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--timeout-seconds", type=int, default=20)
    args = parser.parse_args()

    try:
        health = requests.get(f"{args.base_url.rstrip('/')}/healthz", timeout=5)
        if health.status_code != 200:
            print(f"FAIL: agent-service health status={health.status_code}")
            return 1
    except Exception as e:
        print(f"FAIL: agent-service health check failed: {e}")
        return 1

    secret = read_agent_env_value("GITHUB_WEBHOOK_SECRET") or read_env_value(args.env_file, "GITHUB_WEBHOOK_SECRET")
    if not secret:
        print("FAIL: GITHUB_WEBHOOK_SECRET not found")
        return 1

    payload_obj = {
        "action": "opened",
        "repository": {"full_name": args.repo, "default_branch": args.default_branch},
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

    before_repo_events = consume_topic_from_beginning("repo.events", timeout_ms=8000, max_messages=5000)
    before_repo_ing = consume_topic_from_beginning("repo.ingestion", timeout_ms=8000, max_messages=5000)
    base_pr_matches = matching_pr_events(before_repo_events, args.repo, args.pr_number, args.head_sha)
    base_ing_matches = matching_ingestion_events(before_repo_ing, args.repo, args.head_sha)
    baseline_pr_count = len(base_pr_matches)
    baseline_ing_count = len(base_ing_matches)

    try:
        time.sleep(1.0)
        url = args.base_url.rstrip("/") + args.webhook_path
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

    time.sleep(8)
    repo_events = consume_topic_from_beginning("repo.events", timeout_ms=8000, max_messages=5000)
    repo_ing_events = consume_topic_from_beginning("repo.ingestion", timeout_ms=8000, max_messages=5000)

    pr_matches = matching_pr_events(repo_events, args.repo, args.pr_number, args.head_sha)
    ing_matches = matching_ingestion_events(repo_ing_events, args.repo, args.head_sha)
    pr_event = pr_matches[-1] if len(pr_matches) > baseline_pr_count else None
    ing_event = ing_matches[-1] if len(ing_matches) > baseline_ing_count else None

    print("Task 14.2.5")
    print("-----------")
    print(f"webhook_status={resp.status_code}")
    print(f"baseline_pr_matches={baseline_pr_count}")
    print(f"baseline_ing_matches={baseline_ing_count}")
    print(f"repo.events_captured={len(repo_events)}")
    print(f"repo.ingestion_captured={len(repo_ing_events)}")

    if pr_event is None:
        print("FAIL: matching repo.events pull_request event not found")
        return 1
    if ing_event is None:
        print("FAIL: matching repo.ingestion event not found")
        return 1

    pr_changed = pr_event.get("changed_files") or []
    ing_changed = ing_event.get("changed_files") or []
    same_files = pr_changed == ing_changed

    print(f"pr_changed_files_count={len(pr_changed)}")
    print(f"ing_changed_files_count={len(ing_changed)}")
    print(f"same_changed_files={same_files}")

    if same_files:
        print("PASS: repo.ingestion incremental event verified with same changed_files")
        return 0

    print("FAIL: changed_files mismatch between repo.events and repo.ingestion")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
