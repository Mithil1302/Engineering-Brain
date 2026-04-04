#!/usr/bin/env python3
"""Test GitHub authentication"""
import requests

WORKER_SERVICE_URL = "http://localhost:8003"
REPO = "Mithil1302/Engineering-Brain"

print("Testing ingestion trigger...")
response = requests.post(
    f"{WORKER_SERVICE_URL}/ingestion/trigger",
    json={"repo": REPO},
    timeout=10
)

print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")

if response.status_code == 200:
    run_id = response.json()["run_id"]
    print(f"\n✓ Triggered successfully with run_id: {run_id}")
    print("\nWait 10 seconds and check status...")
    
    import time
    time.sleep(10)
    
    status_response = requests.get(
        f"{WORKER_SERVICE_URL}/ingestion/status/{REPO}",
        timeout=10
    )
    
    print(f"\nStatus check: {status_response.status_code}")
    if status_response.status_code == 200:
        print(f"Status data: {status_response.json()}")
    else:
        print(f"Status response: {status_response.text}")
else:
    print("\n✗ Failed to trigger ingestion")
