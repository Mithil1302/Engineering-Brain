#!/usr/bin/env python3
"""
Quick 1-minute test for Task 14.1.1 and 14.1.2
"""

import requests
import time
import sys
from datetime import datetime, timedelta

WORKER_SERVICE_URL = "http://localhost:8003"
REPO = "Mithil1302/Engineering-Brain"  # GitHub's official test repository
TIMEOUT_MINUTES = 1  # Only 1 minute
POLL_INTERVAL_SECONDS = 3  # Poll every 3 seconds

def trigger_ingestion():
    """Trigger ingestion."""
    endpoint = f"{WORKER_SERVICE_URL}/ingestion/trigger"
    payload = {"repo": REPO}
    
    print("=" * 80)
    print("Task 14.1.1: Trigger Ingestion")
    print("=" * 80)
    
    try:
        start_time = time.time()
        response = requests.post(endpoint, json=payload, timeout=10)
        response_time = (time.time() - start_time) * 1000
        
        if response.status_code == 200:
            data = response.json()
            run_id = data.get("run_id")
            print(f"✓ Triggered: run_id={run_id}, time={response_time:.0f}ms")
            return run_id
        else:
            print(f"✗ HTTP {response.status_code}")
            return None
    except Exception as e:
        print(f"✗ Error: {e}")
        return None

def poll_ingestion_status(run_id):
    """Poll for 1 minute."""
    endpoint = f"{WORKER_SERVICE_URL}/ingestion/status/{REPO}"
    start_time = datetime.now()
    timeout = timedelta(minutes=TIMEOUT_MINUTES)
    
    print("\n" + "=" * 80)
    print("Task 14.1.2: Poll Status (1 minute timeout)")
    print("=" * 80)
    
    attempt = 0
    while datetime.now() - start_time < timeout:
        attempt += 1
        elapsed = (datetime.now() - start_time).total_seconds()
        
        try:
            response = requests.get(endpoint, timeout=10)
            
            if response.status_code == 404:
                print(f"[{elapsed:5.1f}s] Attempt {attempt:2d}: Waiting... (404)")
            elif response.status_code == 200:
                data = response.json()
                status = data.get("status", "unknown")
                files = data.get("files_processed", 0)
                chunks = data.get("chunks_created", 0)
                
                print(f"[{elapsed:5.1f}s] Attempt {attempt:2d}: {status} - Files:{files}, Chunks:{chunks}")
                
                if status == "success":
                    print("-" * 80)
                    print(f"✓ SUCCESS in {elapsed:.1f}s")
                    print(f"  Files: {files}, Chunks: {chunks}")
                    return True
                elif status == "failed":
                    error = data.get("error_message", "Unknown error")
                    print("-" * 80)
                    print(f"✗ FAILED: {error}")
                    return False
        except Exception as e:
            print(f"[{elapsed:5.1f}s] Attempt {attempt:2d}: Error - {e}")
        
        time.sleep(POLL_INTERVAL_SECONDS)
    
    print("-" * 80)
    print(f"⏱ TIMEOUT after 1 minute")
    return False

if __name__ == "__main__":
    print("\n🧪 Quick 1-Minute Ingestion Test\n")
    
    run_id = trigger_ingestion()
    if not run_id:
        print("\n✗ FAILED to trigger")
        sys.exit(1)
    
    success = poll_ingestion_status(run_id)
    
    if success:
        print("\n✓ PASSED\n")
        sys.exit(0)
    else:
        print("\n✗ FAILED or TIMEOUT\n")
        sys.exit(1)
