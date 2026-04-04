#!/usr/bin/env python3
"""
Task 14.1 acceptance verifier.

Covers:
- 14.1.1 Trigger ingestion: POST /ingestion/trigger
- 14.1.2 Poll ingestion status: GET /ingestion/status/{repo}

Why run 14.1.1 first?
----------------------
Yes, you should run 14.1.1 before 14.1.2 for a deterministic test.
Without triggering a fresh run, 14.1.2 may read an old status (or 404 if no run exists).

Usage examples
--------------
# Default behavior: trigger first, then poll for up to 5 minutes
python test_task14_1_2_ingestion_status.py --repo Mithil1302/Engineering-Brain

# Poll only (if you already triggered in another process)
python test_task14_1_2_ingestion_status.py --repo Mithil1302/Engineering-Brain --no-trigger-first

# Custom worker-service URL / timeout
python test_task14_1_2_ingestion_status.py --repo owner/repo --base-url http://localhost:8003 --timeout-minutes 5
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests


@dataclass
class TriggerResult:
    ok: bool
    run_id: Optional[str]
    status: Optional[str]
    response_ms: float
    message: str = ""


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def check_worker_health(base_url: str) -> bool:
    try:
        resp = requests.get(f"{base_url.rstrip('/')}/healthz", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


def trigger_ingestion(base_url: str, repo: str) -> TriggerResult:
    endpoint = f"{base_url.rstrip('/')}/ingestion/trigger"
    payload = {"repo": repo}

    t0 = time.perf_counter()
    try:
        resp = requests.post(endpoint, json=payload, timeout=15)
        elapsed_ms = (time.perf_counter() - t0) * 1000
    except Exception as exc:
        return TriggerResult(
            ok=False,
            run_id=None,
            status=None,
            response_ms=0.0,
            message=f"Trigger request failed: {exc}",
        )

    if resp.status_code != 200:
        return TriggerResult(
            ok=False,
            run_id=None,
            status=None,
            response_ms=elapsed_ms,
            message=f"Trigger returned HTTP {resp.status_code}: {resp.text[:300]}",
        )

    try:
        data = resp.json()
    except Exception as exc:
        return TriggerResult(
            ok=False,
            run_id=None,
            status=None,
            response_ms=elapsed_ms,
            message=f"Trigger response is not valid JSON: {exc}",
        )

    run_id = data.get("run_id")
    status = data.get("status")
    if not run_id:
        return TriggerResult(
            ok=False,
            run_id=None,
            status=status,
            response_ms=elapsed_ms,
            message=f"Trigger response missing run_id: {data}",
        )

    return TriggerResult(ok=True, run_id=str(run_id), status=str(status), response_ms=elapsed_ms)


def poll_status(
    base_url: str,
    repo: str,
    expected_run_id: Optional[str],
    timeout_minutes: int,
    poll_interval_seconds: int,
) -> int:
    endpoint = f"{base_url.rstrip('/')}/ingestion/status/{repo}"
    deadline = datetime.now(timezone.utc) + timedelta(minutes=timeout_minutes)

    print(f"[{now_utc()}] Polling: {endpoint}")
    print(f"[{now_utc()}] Timeout: {timeout_minutes} minute(s), interval: {poll_interval_seconds}s")

    while datetime.now(timezone.utc) < deadline:
        try:
            resp = requests.get(endpoint, timeout=10)
        except Exception as exc:
            print(f"[{now_utc()}] poll_error={exc}")
            time.sleep(poll_interval_seconds)
            continue

        if resp.status_code == 404:
            print(f"[{now_utc()}] status=not_found (no ingestion run yet for repo)")
            time.sleep(poll_interval_seconds)
            continue

        if resp.status_code != 200:
            print(f"[{now_utc()}] status=http_{resp.status_code} body={resp.text[:250]}")
            time.sleep(poll_interval_seconds)
            continue

        try:
            data = resp.json()
        except Exception as exc:
            print(f"[{now_utc()}] status=json_error error={exc}")
            time.sleep(poll_interval_seconds)
            continue

        status = str(data.get("status", "unknown"))
        run_id = str(data.get("run_id", ""))
        files_processed = int(data.get("files_processed") or 0)
        chunks_created = int(data.get("chunks_created") or 0)
        embeddings_created = int(data.get("embeddings_created") or 0)
        services_detected = int(data.get("services_detected") or 0)

        run_note = ""
        if expected_run_id and run_id and run_id != expected_run_id:
            run_note = f" (latest_run_id={run_id}, expected={expected_run_id})"

        print(
            f"[{now_utc()}] status={status}"
            f" files={files_processed} chunks={chunks_created}"
            f" embeds={embeddings_created} services={services_detected}{run_note}"
        )

        if status == "success":
            print(f"[{now_utc()}] FINAL=success")
            return 0

        if status == "failed":
            err = data.get("error_message")
            print(f"[{now_utc()}] FINAL=failed")
            if err:
                print(f"[{now_utc()}] ERROR_MESSAGE={err}")
            return 1

        time.sleep(poll_interval_seconds)

    print(f"[{now_utc()}] FINAL=timeout")
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Task 14.1.2 polling verification (with optional 14.1.1 trigger).")
    parser.add_argument("--repo", required=True, help="Repository in owner/repo format.")
    parser.add_argument("--base-url", default="http://localhost:8003", help="worker-service base URL.")
    parser.add_argument("--timeout-minutes", type=int, default=5, help="Polling timeout in minutes.")
    parser.add_argument("--poll-interval-seconds", type=int, default=5, help="Polling interval in seconds.")
    parser.add_argument(
        "--no-trigger-first",
        action="store_true",
        help="Skip 14.1.1 trigger and only poll current latest run for the repo.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    print("=" * 88)
    print("Task 14.1 verifier (14.1.1 + 14.1.2)")
    print("=" * 88)

    if not check_worker_health(args.base_url):
        print(
            "worker-service is not reachable at /healthz.\n"
            "Start Docker stack first (at least worker-service + deps), then rerun."
        )
        return 3

    expected_run_id: Optional[str] = None
    if not args.no_trigger_first:
        print("[INFO] Running 14.1.1 trigger first (recommended and default).")
        trigger = trigger_ingestion(args.base_url, args.repo)
        if not trigger.ok:
            print(f"Trigger failed: {trigger.message}")
            return 4

        expected_run_id = trigger.run_id
        print(
            f"[INFO] Trigger OK: run_id={trigger.run_id} status={trigger.status} "
            f"response_ms={trigger.response_ms:.2f}"
        )
        if trigger.response_ms > 200:
            print("[WARN] Trigger response exceeded 200ms target for 14.1.1.")
    else:
        print("[INFO] Skipping 14.1.1 trigger (--no-trigger-first provided).")

    return poll_status(
        base_url=args.base_url,
        repo=args.repo,
        expected_run_id=expected_run_id,
        timeout_minutes=args.timeout_minutes,
        poll_interval_seconds=args.poll_interval_seconds,
    )


if __name__ == "__main__":
    raise SystemExit(main())
