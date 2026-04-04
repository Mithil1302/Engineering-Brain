#!/usr/bin/env python3
"""
Task 14.2.9 verifier:
Verify PR comment is posted when pr.checks event contains non-empty findings.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import time
import uuid


def run_cmd(cmd: list[str], timeout: int = 120) -> tuple[int, str, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def produce_pr_checks_event(event: dict) -> bool:
    line = json.dumps(event, separators=(",", ":"))
    script = (
        f"printf %s\\n {shlex.quote(line)} | "
        "kafka-console-producer --bootstrap-server kafka:9092 --topic pr.checks"
    )
    code, _, _ = run_cmd(["docker", "compose", "exec", "-T", "kafka", "bash", "-lc", script], timeout=90)
    return code == 0


def list_pr_comments(repo: str, pr_number: int) -> list[dict] | None:
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
        "print(json.dumps([{'id':c.get('id'),'body':c.get('body','')} for c in items]))"
    )
    code, out, _ = run_cmd(
        [
            "docker", "compose", "exec", "-T",
            "-e", f"T14_REPO={repo}",
            "-e", f"T14_PR={pr_number}",
            "agent-service", "python", "-c", py,
        ],
        timeout=120,
    )
    if code != 0 or not out:
        return None
    try:
        return json.loads(out.splitlines()[-1])
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Task 14.2.9 PR comment posting")
    parser.add_argument("--repo", default="Mithil1302/Engineering-Brain")
    parser.add_argument("--pr-number", type=int, default=1)
    parser.add_argument("--head-sha", default="1904df2ec66a8b0a16e08d3e7df4304f294ba8cc")
    parser.add_argument("--timeout-seconds", type=int, default=60)
    args = parser.parse_args()

    marker = f"TASK14_2_9_{uuid.uuid4()}"

    event = {
        "repo_full_name": args.repo,
        "pr_number": int(args.pr_number),
        "head_sha": args.head_sha,
        "summary_status": "warn",
        "action": "create_comment",
        "comment_key": f"{args.repo}:{args.pr_number}:{marker}",
        "markdown_comment": f"## Task 14.2.9 marker\\n{marker}",
        "findings": [
            {
                "rule_id": "DOC_DRIFT_TEST",
                "message": f"Synthetic finding for {marker}",
                "fix_url": "https://example.com/fix",
            }
        ],
    }

    produced = produce_pr_checks_event(event)
    if not produced:
        print("Task 14.2.9")
        print("-----------")
        print("FAIL: could not publish pr.checks event")
        return 1

    found = False
    deadline = time.time() + args.timeout_seconds
    while time.time() < deadline:
        comments = list_pr_comments(args.repo, int(args.pr_number))
        if comments is None:
            time.sleep(3)
            continue
        for c in comments:
            if marker in str(c.get("body") or ""):
                found = True
                break
        if found:
            break
        time.sleep(3)

    print("Task 14.2.9")
    print("-----------")
    print(f"marker={marker}")
    print(f"found={found}")

    if found:
        print("PASS: PR comment posted for non-empty findings")
        return 0

    print("FAIL: marker comment not found within timeout")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
