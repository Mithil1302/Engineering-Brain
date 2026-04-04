#!/usr/bin/env python3
"""
Task 14.2.4 verifier:
Consume repo.events Kafka topic and verify pull_request event with
correct pr_number, head_sha, and changed_files.
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


def consume_new_events_after_action(
    topic: str,
    action,
    *,
    timeout_sec: int = 20,
    max_messages: int = 80,
) -> list[dict]:
    script = (
        "kafka-console-consumer "
        "--bootstrap-server kafka:9092 "
        f"--topic {shlex.quote(topic)} "
        f"--timeout-ms {int(timeout_sec * 1000)} "
        f"--max-messages {int(max_messages)}"
    )

    cmd = ["docker", "compose", "exec", "-T", "kafka", "bash", "-lc", script]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        time.sleep(1.0)
        action()
        try:
            out, _ = proc.communicate(timeout=timeout_sec + 6)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, _ = proc.communicate()
    finally:
        if proc.poll() is None:
            proc.kill()

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
    group = f"t14-2-4-{uuid.uuid4().hex[:12]}"
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Task 14.2.4 repo.events pull_request event")
    parser.add_argument("--repo", default="Mithil1302/Engineering-Brain")
    parser.add_argument("--pr-number", type=int, default=1)
    parser.add_argument("--head-sha", default="1904df2ec66a8b0a16e08d3e7df4304f294ba8cc")
    parser.add_argument("--default-branch", default="main")
    parser.add_argument("--base-url", default="http://localhost:8002")
    parser.add_argument("--webhook-path", default="/webhooks/github")
    parser.add_argument("--delivery-id", default="task14-2-4-single")
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

    url = args.base_url.rstrip("/") + args.webhook_path
    response_holder: dict[str, object] = {}

    def _post_webhook() -> None:
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
        response_holder["resp"] = resp

    before_events = consume_topic_from_beginning("repo.events", timeout_ms=8000, max_messages=5000)
    before_matches = matching_pr_events(before_events, args.repo, args.pr_number, args.head_sha)
    baseline_count = len(before_matches)

    _post_webhook()

    resp = response_holder.get("resp")
    if resp is None:
        print("FAIL: webhook request not executed")
        return 1
    if getattr(resp, "status_code", None) != 200:
        print(f"FAIL: webhook status={resp.status_code}, body={resp.text}")
        return 1

    time.sleep(6)
    after_events = consume_topic_from_beginning("repo.events", timeout_ms=8000, max_messages=5000)
    events_captured = len(after_events)
    after_matches = matching_pr_events(after_events, args.repo, args.pr_number, args.head_sha)
    matched = after_matches[-1] if len(after_matches) > baseline_count else None

    print("Task 14.2.4")
    print("-----------")
    print(f"webhook_status={resp.status_code}")
    print(f"baseline_matching_events={baseline_count}")
    print(f"events_captured={events_captured}")
    if matched is not None:
        print(f"matched_pr_number={matched.get('pr_number')}")
        print(f"matched_head_sha={matched.get('head_sha')}")
        print(f"changed_files_count={len(matched.get('changed_files') or [])}")
        print("PASS: repo.events pull_request event verified")
        return 0

    print("FAIL: expected repo.events pull_request event not found")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
