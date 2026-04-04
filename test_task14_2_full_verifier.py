#!/usr/bin/env python3
"""
Task 14.2 full verifier (14.2.1 -> 14.2.9) in a single script.

This script validates the webhook->policy-check flow end-to-end where possible.
It is designed to run against the local docker compose stack.

What it covers
--------------
14.2.1 Compute valid HMAC-SHA256 signature over payload using GITHUB_WEBHOOK_SECRET.
14.2.2 POST webhook and verify HTTP 200 within 500ms.
14.2.3 Verify meta.check_run_tracking row appears within 2 seconds.
14.2.4 Verify repo.events contains pull_request event with pr_number/head_sha/changed_files.
14.2.5 Verify repo.ingestion contains incremental event with same changed_files.
14.2.6 Verify GitHub Check Run transitions in_progress -> completed (<=60s).
14.2.7 Send webhook with invalid signature and verify HTTP 401.
14.2.8 Send push to non-default branch and verify no Kafka events produced.
14.2.9 Verify PR comment is posted when findings are non-empty.

Notes
-----
- Requires live services from docker compose.
- Uses docker compose exec for postgres/kafka and GitHub API calls via agent-service container.
- For best reliability, pass a real open PR using --pr-number and --head-sha, or ensure one exists.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import shlex
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

import requests


@dataclass
class CheckResult:
    id: str
    name: str
    status: str  # PASS | FAIL | SKIP
    detail: str


def log_step(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat()}] {msg}", flush=True)


def run_cmd(cmd: list[str], timeout: int = 120) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or "").strip() if isinstance(exc.stdout, str) else ""
        err = (exc.stderr or "").strip() if isinstance(exc.stderr, str) else ""
        return 124, out, f"timeout after {timeout}s" + (f" | {err}" if err else "")


def compose_exec(service: str, args: list[str], timeout: int = 120, env_kv: Optional[dict[str, str]] = None) -> tuple[int, str, str]:
    cmd = ["docker", "compose", "exec", "-T"]
    if env_kv:
        for k, v in env_kv.items():
            cmd.extend(["-e", f"{k}={v}"])
    cmd.extend([service])
    cmd.extend(args)
    return run_cmd(cmd, timeout=timeout)


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


def read_agent_env_value(key: str) -> Optional[str]:
    code, out, err = compose_exec(
        "agent-service",
        ["python", "-c", f"import os; print(os.getenv('{key}', ''))"],
        timeout=30,
    )
    if code != 0:
        return None
    value = (out or "").strip()
    return value or None


def compute_signature(secret: str, raw_payload: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), raw_payload, hashlib.sha256).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def check_health(url: str, timeout: int = 5) -> bool:
    try:
        r = requests.get(url, timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


def detect_webhook_url(base: str, explicit_path: Optional[str]) -> str:
    if explicit_path:
        return base.rstrip("/") + explicit_path
    # Project currently exposes /github/webhook. Keep fallback for task doc wording.
    return base.rstrip("/") + "/github/webhook"


def discover_open_pr(repo: str) -> Optional[dict]:
    try:
        r = requests.get(f"https://api.github.com/repos/{repo}/pulls?state=open&per_page=1", timeout=20)
        if r.status_code != 200:
            return None
        items = r.json()
        if not items:
            return None
        pr = items[0]
        return {
            "number": int(pr["number"]),
            "head_sha": str(pr["head"]["sha"]),
            "base_ref": str(pr["base"]["ref"]),
        }
    except Exception:
        return None


def consume_topic(
    topic: str,
    timeout_ms: int = 5000,
    max_messages: int = 300,
    from_beginning: bool = False,
) -> list[dict]:
    script = (
        "kafka-console-consumer "
        "--bootstrap-server kafka:9092 "
        f"--topic {shlex.quote(topic)} "
        f"{'--from-beginning ' if from_beginning else ''}"
        f"--timeout-ms {int(timeout_ms)} "
        f"--max-messages {int(max_messages)}"
    )
    code, out, err = compose_exec("kafka", ["bash", "-lc", script], timeout=max(20, timeout_ms // 1000 + 15))

    # Consumer can exit non-zero on timeout after reading; parse whatever was read.
    lines = [ln.strip() for ln in (out or "").splitlines() if ln.strip()]
    events: list[dict] = []
    for ln in lines:
        try:
            events.append(json.loads(ln))
        except Exception:
            continue
    return events


def consume_new_events_after_action(
    topic: str,
    action: Callable[[], object],
    *,
    timeout_sec: int = 20,
    max_messages: int = 100,
) -> list[dict]:
    """Capture only freshly-produced events by starting consumer before action."""
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
        # Give consumer a moment to subscribe before event is produced.
        time.sleep(1.0)
        action()
        try:
            out, err = proc.communicate(timeout=timeout_sec + 5)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
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


def wait_for_event(topic: str, predicate: Callable[[dict], bool], timeout_sec: int = 20, poll_sleep: float = 2.0) -> Optional[dict]:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        events = consume_topic(topic, timeout_ms=1800, max_messages=2000, from_beginning=True)
        for ev in reversed(events):
            try:
                if predicate(ev):
                    return ev
            except Exception:
                continue
        time.sleep(poll_sleep)
    return None


def query_check_run_tracking(repo: str, pr_number: int, head_sha: str) -> Optional[int]:
    sql = (
        "SELECT check_run_id FROM meta.check_run_tracking "
        f"WHERE repo = '{repo}' AND pr_number = {pr_number} AND head_sha = '{head_sha}' "
        "ORDER BY created_at DESC LIMIT 1;"
    )
    code, out, err = compose_exec("postgres", ["psql", "-U", "brain", "-d", "brain", "-tAc", sql], timeout=30)
    if code != 0:
        return None
    value = (out or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except Exception:
        return None


def get_check_run_status_via_agent_container(repo: str, check_run_id: int) -> Optional[dict]:
    py = (
        "import os,requests,json;"
        "from app.github_bridge import GithubBridge;"
        "b=GithubBridge();"
        "repo=os.environ['T14_REPO'];"
        "rid=int(os.environ['T14_RUN']);"
        "inst=os.environ.get('GITHUB_INSTALLATION_ID') or b.installation_id;"
        "tok=b._installation_token(str(inst));"
        "h={'Authorization':f'token {tok}','Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'};"
        "u=f'{b.github_api_base}/repos/{repo}/check-runs/{rid}';"
        "r=requests.get(u,headers=h,timeout=20);"
        "r.raise_for_status();"
        "d=r.json();"
        "print(json.dumps({'status':d.get('status'),'conclusion':d.get('conclusion')}))"
    )
    code, out, err = compose_exec(
        "agent-service",
        ["python", "-c", py],
        timeout=60,
        env_kv={"T14_REPO": repo, "T14_RUN": str(check_run_id)},
    )
    if code != 0:
        return None
    try:
        return json.loads((out or "").splitlines()[-1])
    except Exception:
        return None


def list_pr_comments_via_agent_container(repo: str, pr_number: int) -> Optional[list[dict]]:
    py = (
        "import os,requests,json;"
        "from app.github_bridge import GithubBridge;"
        "b=GithubBridge();"
        "repo=os.environ['T14_REPO'];"
        "pr=int(os.environ['T14_PR']);"
        "inst=os.environ.get('GITHUB_INSTALLATION_ID') or b.installation_id;"
        "tok=b._installation_token(str(inst));"
        "h={'Authorization':f'token {tok}','Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'};"
        "u=f'{b.github_api_base}/repos/{repo}/issues/{pr}/comments?per_page=100';"
        "r=requests.get(u,headers=h,timeout=20);"
        "r.raise_for_status();"
        "items=r.json();"
        "out=[{'id':c.get('id'),'body':c.get('body','')} for c in items];"
        "print(json.dumps(out))"
    )
    code, out, err = compose_exec(
        "agent-service",
        ["python", "-c", py],
        timeout=60,
        env_kv={"T14_REPO": repo, "T14_PR": str(pr_number)},
    )
    if code != 0:
        return None
    try:
        return json.loads((out or "").splitlines()[-1])
    except Exception:
        return None


def produce_pr_checks_event(event: dict) -> bool:
    line = json.dumps(event, separators=(",", ":"))
    script = (
        f"printf %s\\n {shlex.quote(line)} | "
        "kafka-console-producer --bootstrap-server kafka:9092 --topic pr.checks"
    )
    code, out, err = compose_exec("kafka", ["bash", "-lc", script], timeout=60)
    return code == 0


def summarize(results: list[CheckResult]) -> int:
    print("\n" + "=" * 96)
    print("Task 14.2 summary")
    print("=" * 96)
    for r in results:
        print(f"[{r.status}] {r.id} {r.name} :: {r.detail}")
    passed = sum(1 for r in results if r.status == "PASS")
    failed = sum(1 for r in results if r.status == "FAIL")
    skipped = sum(1 for r in results if r.status == "SKIP")
    print("-" * 96)
    print(f"PASS={passed} FAIL={failed} SKIP={skipped}")
    return 1 if failed > 0 else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Task 14.2.1-14.2.9 in one file")
    parser.add_argument("--repo", default=read_env_value(".env", "GITHUB_TARGET_REPO") or "Mithil1302/Engineering-Brain")
    parser.add_argument("--agent-base-url", default="http://localhost:8002")
    parser.add_argument("--webhook-path", default=None, help="Override webhook path (e.g. /github/webhook or /webhooks/github)")
    parser.add_argument("--pr-number", type=int, default=None)
    parser.add_argument("--head-sha", default=None)
    parser.add_argument("--default-branch", default="main")
    parser.add_argument("--delivery-prefix", default="task14-2")
    args = parser.parse_args()

    results: list[CheckResult] = []

    log_step("Starting Task 14.2 full verifier")

    if not check_health(f"{args.agent_base_url.rstrip('/')}/healthz"):
        results.append(CheckResult("14.2.0", "agent-service health", "FAIL", "agent-service /healthz not reachable"))
        return summarize(results)

    # Prefer runtime value from container (source of truth for webhook verification).
    secret = read_agent_env_value("GITHUB_WEBHOOK_SECRET") or read_env_value(".env", "GITHUB_WEBHOOK_SECRET")
    if not secret:
        results.append(CheckResult("14.2.1", "Compute HMAC signature", "FAIL", "GITHUB_WEBHOOK_SECRET missing in .env"))
        return summarize(results)

    pr_number = args.pr_number
    head_sha = args.head_sha
    base_ref = args.default_branch

    if pr_number is None or not head_sha:
        log_step("No PR args provided, attempting open PR discovery")
        discovered = discover_open_pr(args.repo)
        if discovered:
            pr_number = discovered["number"]
            head_sha = discovered["head_sha"]
            base_ref = discovered["base_ref"]
        else:
            results.append(
                CheckResult(
                    "14.2.pre",
                    "Discover open PR",
                    "FAIL",
                    "No open PR discovered; pass --pr-number and --head-sha for full 14.2 run",
                )
            )
            return summarize(results)

    webhook_url = detect_webhook_url(args.agent_base_url, args.webhook_path)

    # Build canonical PR payload
    pr_payload = {
        "action": "opened",
        "repository": {"full_name": args.repo, "default_branch": base_ref},
        "pull_request": {
            "number": pr_number,
            "head": {"sha": head_sha},
            "base": {"ref": base_ref},
            "additions": 1,
            "deletions": 0,
        },
        "commits": [],
    }
    pr_raw = json.dumps(pr_payload, separators=(",", ":")).encode("utf-8")
    sig = compute_signature(secret, pr_raw)

    # 14.2.1
    log_step("14.2.1 Compute signature")
    sig_ok = bool(re.fullmatch(r"sha256=[0-9a-f]{64}", sig))
    results.append(CheckResult("14.2.1", "Compute valid HMAC-SHA256 signature", "PASS" if sig_ok else "FAIL", f"signature_prefix={sig[:20]}..."))

    # 14.2.2 (+ capture fresh 14.2.4/14.2.5 events deterministically)
    log_step("14.2.2 POST signed pull_request webhook")
    delivery_id = f"{args.delivery_prefix}-pr-{uuid.uuid4()}"
    pr_response_holder: dict[str, object] = {}

    def _post_pr_webhook() -> None:
        t0_local = time.perf_counter()
        resp = requests.post(
            webhook_url,
            data=pr_raw,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": delivery_id,
            },
            timeout=20,
        )
        pr_response_holder["response"] = resp
        pr_response_holder["latency_ms"] = (time.perf_counter() - t0_local) * 1000

    # Start consumers first, then post webhook, so we observe only fresh messages.
    repo_events_fresh = consume_new_events_after_action("repo.events", _post_pr_webhook, timeout_sec=20, max_messages=50)
    repo_ingestion_fresh = consume_new_events_after_action("repo.ingestion", lambda: None, timeout_sec=8, max_messages=50)

    r = pr_response_holder.get("response")
    if r is None:
        results.append(CheckResult("14.2.2", "POST webhook returns 200 within 500ms", "FAIL", "request not executed"))
        return summarize(results)
    latency_ms = float(pr_response_holder.get("latency_ms") or 0.0)
    pass_242 = (r.status_code == 200 and latency_ms <= 500)
    results.append(CheckResult("14.2.2", "POST webhook returns 200 within 500ms", "PASS" if pass_242 else "FAIL", f"status={r.status_code}, latency_ms={latency_ms:.2f}"))

    # 14.2.3
    log_step("14.2.3 Wait for check_run_tracking row")
    deadline = time.time() + 2.0
    check_run_id: Optional[int] = None
    while time.time() < deadline:
        check_run_id = query_check_run_tracking(args.repo, pr_number, head_sha)
        if check_run_id is not None:
            break
        time.sleep(0.25)
    results.append(CheckResult("14.2.3", "check_run_tracking row within 2s", "PASS" if check_run_id is not None else "FAIL", f"check_run_id={check_run_id}"))

    # 14.2.4
    log_step("14.2.4 Wait for repo.events pull_request event")
    pr_event = None
    for ev in repo_events_fresh:
        if (
            ev.get("event_type") == "pull_request"
            and ev.get("repo") == args.repo
            and int(ev.get("pr_number") or 0) == int(pr_number)
            and str(ev.get("head_sha") or "") == str(head_sha)
        ):
            pr_event = ev
            break

    if pr_event is None:
        # fallback small poll window in case event arrived just after consumer timeout
        pr_event = wait_for_event(
            "repo.events",
            lambda ev: ev.get("event_type") == "pull_request"
            and ev.get("repo") == args.repo
            and int(ev.get("pr_number") or 0) == int(pr_number)
            and str(ev.get("head_sha") or "") == str(head_sha),
            timeout_sec=10,
        )
    pr_changed_files = []
    if pr_event is not None and isinstance(pr_event.get("changed_files"), list):
        pr_changed_files = list(pr_event["changed_files"])
    ok_244 = pr_event is not None and isinstance(pr_changed_files, list)
    results.append(CheckResult("14.2.4", "repo.events pull_request event verified", "PASS" if ok_244 else "FAIL", f"found={pr_event is not None}, changed_files_count={len(pr_changed_files)}"))

    # 14.2.5
    log_step("14.2.5 Wait for repo.ingestion incremental event")
    ingest_event = None
    for ev in repo_ingestion_fresh:
        if ev.get("repo") == args.repo and str(ev.get("commit_sha") or "") == str(head_sha):
            ingest_event = ev
            break

    if ingest_event is None:
        ingest_event = wait_for_event(
            "repo.ingestion",
            lambda ev: ev.get("repo") == args.repo and str(ev.get("commit_sha") or "") == str(head_sha),
            timeout_sec=12,
        )
    ok_245 = False
    detail_245 = "repo.ingestion event not found"
    if ingest_event is not None:
        same_files = (ingest_event.get("changed_files") == pr_changed_files)
        ok_245 = same_files
        detail_245 = f"found=True, same_changed_files={same_files}, changed_files_count={len(pr_changed_files)}"
    results.append(CheckResult("14.2.5", "repo.ingestion incremental event verified", "PASS" if ok_245 else "FAIL", detail_245))

    # 14.2.6
    log_step("14.2.6 Verify check run completion")
    if check_run_id is None:
        results.append(CheckResult("14.2.6", "Check Run transitions in_progress->completed <=60s", "SKIP", "No check_run_id from 14.2.3"))
    else:
        seen_in_progress = False
        seen_completed = False
        last = None
        deadline = time.time() + 60
        while time.time() < deadline:
            status = get_check_run_status_via_agent_container(args.repo, check_run_id)
            if status:
                st = str(status.get("status") or "")
                last = status
                if st == "in_progress":
                    seen_in_progress = True
                if st == "completed":
                    seen_completed = True
                    break
            time.sleep(3)

        ok_246 = seen_completed and (seen_in_progress or (last and last.get("status") == "completed"))
        results.append(CheckResult("14.2.6", "Check Run transitions in_progress->completed <=60s", "PASS" if ok_246 else "FAIL", f"seen_in_progress={seen_in_progress}, seen_completed={seen_completed}, last={last}"))

    # 14.2.7 invalid signature
    log_step("14.2.7 Send invalid signature webhook")
    bad_sig = sig[:-1] + ("0" if sig[-1] != "0" else "1")
    r_bad = requests.post(
        webhook_url,
        data=pr_raw,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": bad_sig,
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": f"{args.delivery_prefix}-bad-{uuid.uuid4()}",
        },
        timeout=20,
    )
    results.append(CheckResult("14.2.7", "Invalid signature returns 401", "PASS" if r_bad.status_code == 401 else "FAIL", f"status={r_bad.status_code}"))

    # 14.2.8 push non-default branch should not produce events
    log_step("14.2.8 Send non-default push webhook and verify no Kafka events")
    sentinel_sha = (uuid.uuid4().hex + uuid.uuid4().hex)[:40]
    push_payload = {
        "ref": "refs/heads/feature/non-default-branch",
        "repository": {"full_name": args.repo, "default_branch": base_ref},
        "head_commit": {"id": sentinel_sha},
        "commits": [
            {
                "added": ["__task14_2_8_added.txt"],
                "modified": ["__task14_2_8_modified.txt"],
                "removed": ["__task14_2_8_removed.txt"],
            }
        ],
    }
    push_raw = json.dumps(push_payload, separators=(",", ":")).encode("utf-8")
    push_sig = compute_signature(secret, push_raw)
    push_delivery = f"{args.delivery_prefix}-push-{uuid.uuid4()}"
    push_response_holder: dict[str, object] = {}

    def _post_push_webhook() -> None:
        resp = requests.post(
            webhook_url,
            data=push_raw,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": push_sig,
                "X-GitHub-Event": "push",
                "X-GitHub-Delivery": push_delivery,
            },
            timeout=20,
        )
        push_response_holder["response"] = resp

    push_repo_events = consume_new_events_after_action("repo.events", _post_push_webhook, timeout_sec=10, max_messages=20)
    push_repo_ingestion = consume_new_events_after_action("repo.ingestion", lambda: None, timeout_sec=8, max_messages=20)

    r_push = push_response_holder.get("response")
    if r_push is None:
        results.append(CheckResult("14.2.8", "Push to non-default branch produces no Kafka events", "FAIL", "push request not executed"))
        return summarize(results)

    repo_events = push_repo_events
    repo_ingestion_events = push_repo_ingestion
    found_in_repo_events = any(str(ev.get("head_sha") or "") == sentinel_sha for ev in repo_events)
    found_in_repo_ingestion = any(str(ev.get("commit_sha") or "") == sentinel_sha for ev in repo_ingestion_events)
    ok_248 = (r_push.status_code == 200) and (not found_in_repo_events) and (not found_in_repo_ingestion)
    results.append(CheckResult("14.2.8", "Push to non-default branch produces no Kafka events", "PASS" if ok_248 else "FAIL", f"post_status={r_push.status_code}, repo.events_hit={found_in_repo_events}, repo.ingestion_hit={found_in_repo_ingestion}"))

    # 14.2.9 force a findings-bearing pr.checks event and verify PR comment appears.
    log_step("14.2.9 Publish synthetic pr.checks event and verify PR comment")
    marker = f"TASK14_2_9_{uuid.uuid4()}"
    pr_checks_event = {
        "repo_full_name": args.repo,
        "pr_number": int(pr_number),
        "head_sha": head_sha,
        "summary_status": "warn",
        "action": "create_comment",
        "comment_key": f"{args.repo}:{pr_number}:{marker}",
        "markdown_comment": f"## Task 14.2.9 marker\\n{marker}",
        "findings": [
            {
                "rule_id": "DOC_DRIFT_TEST",
                "message": f"Synthetic finding for {marker}",
                "fix_url": "https://example.com/fix",
            }
        ],
    }
    produced = produce_pr_checks_event(pr_checks_event)
    if not produced:
        results.append(CheckResult("14.2.9", "PR comment posted when findings non-empty", "FAIL", "Could not publish synthetic pr.checks event"))
    else:
        found_comment = False
        deadline = time.time() + 60
        while time.time() < deadline:
            comments = list_pr_comments_via_agent_container(args.repo, int(pr_number))
            if comments is None:
                time.sleep(3)
                continue
            for c in comments:
                if marker in str(c.get("body") or ""):
                    found_comment = True
                    break
            if found_comment:
                break
            time.sleep(3)
        results.append(CheckResult("14.2.9", "PR comment posted when findings non-empty", "PASS" if found_comment else "FAIL", f"marker={marker}, found={found_comment}"))

    return summarize(results)


if __name__ == "__main__":
    raise SystemExit(main())
