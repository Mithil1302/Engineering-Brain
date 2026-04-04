#!/usr/bin/env python3
"""
Reliable runner for Task 14.2.9.
Run this instead of test_task_14_2_9_pr_comment_posted.py

Usage:  python run_14_2_9.py
"""
from __future__ import annotations
import json, subprocess, time, uuid

def run(cmd, timeout=60):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()

def produce(event: dict) -> bool:
    """Use Python kafka-python inside agent-service — clean binary encoding, no shell escaping."""
    payload = json.dumps(event, separators=(",",":"))
    py = "\n".join([
        "from kafka import KafkaProducer",
        "import json",
        f"p=KafkaProducer(bootstrap_servers=['kafka:9092'])",
        f"fut=p.send('pr.checks',value={repr(payload.encode('utf-8'))})",
        "p.flush(timeout=10)",
        "m=fut.get(timeout=10)",
        "print(f'OK offset={m.offset}')",
        "p.close()",
    ])
    code, out, err = run(["docker","compose","exec","-T","agent-service","python","-c",py])
    print(f"  [kafka] code={code} out={out!r}")
    return code == 0 and "OK" in out

def list_comments(repo, pr_number):
    py = (
        "import os,requests,json;"
        "from app.github_bridge import GithubBridge;"
        "b=GithubBridge();"
        "tok=b._installation_token(b.installation_id);"
        "h={'Authorization':f'token {tok}','Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'};"
        f"r=requests.get(f'{{b.github_api_base}}/repos/{repo}/issues/{pr_number}/comments?per_page=100',headers=h,timeout=20);"
        "r.raise_for_status();"
        "print(json.dumps([{'id':c['id'],'body':c.get('body','')} for c in r.json()]))"
    )
    code, out, err = run(["docker","compose","exec","-T","agent-service","python","-c",py], timeout=30)
    if code!=0 or not out:
        print(f"  [gh api] failed: {err[:100]}")
        return None
    try:
        return json.loads(out.splitlines()[-1])
    except Exception as e:
        print(f"  [gh api] parse error: {e} out={out[:80]!r}")
        return None

def bridge_state():
    code, out, _ = run(["docker","compose","exec","-T","agent-service","python","-c",
        "import requests; print(requests.get('http://localhost:8002/github/bridge/health',timeout=5).text)"])
    if code==0 and out:
        try: return json.loads(out.splitlines()[-1])
        except: pass
    return {}

REPO    = "Mithil1302/Engineering-Brain"
PR      = 1
SHA     = "1904df2ec66a8b0a16e08d3e7df4304f294ba8cc"
TIMEOUT = 90

marker = f"TASK14_2_9_{uuid.uuid4()}"
print(f"\nTask 14.2.9  marker={marker}\n" + "="*60)

b0 = bridge_state()
print(f"  [bridge before] processed={b0.get('processed')} delivered={b0.get('delivered')} failed={b0.get('failed')}")

event = {
    "repo_full_name": REPO, "pr_number": PR, "head_sha": SHA,
    "summary_status": "warn", "action": "create_comment",
    "comment_key": f"{REPO}:{PR}:{marker}",
    "markdown_comment": f"## Task 14.2.9\n{marker}",
    "findings": [{"rule_id":"DOC_DRIFT_TEST","message":f"Synthetic finding for {marker}","fix_url":"https://example.com/fix"}],
}

if not produce(event):
    print("\nFAIL: could not produce Kafka message"); raise SystemExit(1)

time.sleep(4)

found = False
deadline = time.time() + TIMEOUT
i = 0
while time.time() < deadline:
    i += 1
    comments = list_comments(REPO, PR)
    if comments is None:
        time.sleep(4); continue
    print(f"  [poll {i}] {len(comments)} comments")
    for c in comments:
        if marker in str(c.get("body","") or ""):
            found = True
            print(f"  [poll {i}] FOUND marker in comment {c['id']}")
            break
    if found: break
    time.sleep(5)

b1 = bridge_state()
print(f"  [bridge after]  processed={b1.get('processed')} delivered={b1.get('delivered')} failed={b1.get('failed')}")
if b1.get("last_error"): print(f"  [bridge error]  {b1['last_error'][:180]}")

print(f"\nTask 14.2.9\n-----------\nmarker={marker}\nfound={found}")
if found: print("PASS: PR comment posted for non-empty findings"); raise SystemExit(0)
print("FAIL: marker comment not found within timeout"); raise SystemExit(1)
