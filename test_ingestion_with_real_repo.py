#!/usr/bin/env python3
"""
Complete test for Task 14.1.1 and 14.1.2 using a real public repository.

This script:
1. Triggers ingestion for a real public GitHub repository
2. Polls the status endpoint until completion
3. Verifies success within 5 minutes
"""

import requests
import time
import sys
from datetime import datetime, timedelta

WORKER_SERVICE_URL = "http://localhost:8003"

# Use a small, well-known public repository
# octocat/Hello-World is GitHub's official test repository
REPO = "octocat/Hello-World"

TIMEOUT_MINUTES = 5
POLL_INTERVAL_SECONDS = 5

def trigger_ingestion():
    """Trigger ingestion for the test repository."""
    endpoint = f"{WORKER_SERVICE_URL}/ingestion/trigger"
    payload = {"repo": REPO}
    
    print("=" * 80)
    print("Task 14.1.1: Trigger Ingestion")
    print("=" * 80)
    print(f"POST {endpoint}")
    print(f"Payload: {payload}")
    print("-" * 80)
    
    try:
        start_time = time.time()
        response = requests.post(endpoint, json=payload, timeout=10)
        response_time = (time.time() - start_time) * 1000
        
        print(f"Status Code: {response.status_code}")
        print(f"Response Time: {response_time:.2f}ms")
        
        if response.status_code == 200:
            data = response.json()
            run_id = data.get("run_id")
            status = data.get("status")
            
            print(f"Response: {data}")
            print("-" * 80)
            print(f"✓ HTTP 200 OK")
            print(f"✓ run_id: {run_id}")
            print(f"✓ status: {status}")
            print(f"✓ Response time: {response_time:.2f}ms")
            
            if response_time < 200:
                print(f"✓ Response time < 200ms requirement")
            else:
                print(f"⚠ Response time {response_time:.2f}ms exceeds 200ms target")
            
            print("-" * 80)
            print("✓ Task 14.1.1 PASSED")
            print("=" * 80)
            print()
            return run_id
        else:
            print(f"✗ HTTP {response.status_code}")
            print(f"Response: {response.text}")
            print("=" * 80)
            return None
            
    except Exception as e:
        print(f"✗ Error: {e}")
        print("=" * 80)
        return None

def poll_ingestion_status(run_id):
    """Poll the ingestion status endpoint until success or timeout."""
    endpoint = f"{WORKER_SERVICE_URL}/ingestion/status/{REPO}"
    start_time = datetime.now()
    timeout = timedelta(minutes=TIMEOUT_MINUTES)
    
    print("=" * 80)
    print("Task 14.1.2: Poll Ingestion Status")
    print("=" * 80)
    print(f"Polling: {endpoint}")
    print(f"Expected run_id: {run_id}")
    print(f"Timeout: {TIMEOUT_MINUTES} minutes")
    print(f"Poll interval: {POLL_INTERVAL_SECONDS} seconds")
    print("-" * 80)
    
    attempt = 0
    while datetime.now() - start_time < timeout:
        attempt += 1
        elapsed = (datetime.now() - start_time).total_seconds()
        
        try:
            response = requests.get(endpoint, timeout=10)
            
            if response.status_code == 404:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Attempt {attempt} ({elapsed:.1f}s): No ingestion run found yet (404)")
            elif response.status_code == 200:
                data = response.json()
                status = data.get("status", "unknown")
                returned_run_id = data.get("run_id", "N/A")
                files_processed = data.get("files_processed", 0)
                chunks_created = data.get("chunks_created", 0)
                embeddings_created = data.get("embeddings_created", 0)
                services_detected = data.get("services_detected", 0)
                duration = data.get("duration_seconds", 0)
                error_message = data.get("error_message")
                
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Attempt {attempt} ({elapsed:.1f}s): Status={status}")
                print(f"  Run ID: {returned_run_id}")
                print(f"  Files: {files_processed}, Chunks: {chunks_created}, Embeddings: {embeddings_created}, Services: {services_detected}")
                
                if error_message:
                    print(f"  Error: {error_message}")
                
                if status == "success":
                    print("-" * 80)
                    print(f"✓ SUCCESS: Ingestion completed in {elapsed:.1f}s")
                    print(f"  Total files processed: {files_processed}")
                    print(f"  Total chunks created: {chunks_created}")
                    print(f"  Total embeddings created: {embeddings_created}")
                    print(f"  Services detected: {services_detected}")
                    print(f"  Ingestion duration: {duration:.2f}s")
                    
                    if elapsed < 300:  # 5 minutes
                        print(f"✓ Completed within 5-minute requirement")
                    
                    print("-" * 80)
                    print("✓ Task 14.1.2 PASSED")
                    print("=" * 80)
                    return True
                    
                elif status == "failed":
                    print("-" * 80)
                    print(f"✗ FAILED: Ingestion failed")
                    print(f"  Error: {error_message}")
                    print("-" * 80)
                    print("✗ Task 14.1.2 FAILED")
                    print("=" * 80)
                    return False
                    
                elif status == "running":
                    print(f"  Still running... waiting {POLL_INTERVAL_SECONDS}s")
                else:
                    print(f"  Unknown status: {status}")
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Attempt {attempt} ({elapsed:.1f}s): HTTP {response.status_code}")
                print(f"  Response: {response.text[:200]}")
        
        except requests.exceptions.ConnectionError:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Attempt {attempt} ({elapsed:.1f}s): Connection error")
        except requests.exceptions.Timeout:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Attempt {attempt} ({elapsed:.1f}s): Request timeout")
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Attempt {attempt} ({elapsed:.1f}s): Error - {e}")
        
        time.sleep(POLL_INTERVAL_SECONDS)
    
    # Timeout reached
    elapsed = (datetime.now() - start_time).total_seconds()
    print("-" * 80)
    print(f"✗ TIMEOUT: Ingestion did not complete within {TIMEOUT_MINUTES} minutes ({elapsed:.1f}s elapsed)")
    print("-" * 80)
    print("✗ Task 14.1.2 FAILED")
    print("=" * 80)
    return False

if __name__ == "__main__":
    print("\n")
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 20 + "INGESTION END-TO-END TEST" + " " * 33 + "║")
    print("║" + " " * 78 + "║")
    print("║" + f"  Repository: {REPO}".ljust(78) + "║")
    print("║" + f"  Tasks: 14.1.1 (Trigger) + 14.1.2 (Poll Status)".ljust(78) + "║")
    print("╚" + "═" * 78 + "╝")
    print("\n")
    
    # Step 1: Trigger ingestion
    run_id = trigger_ingestion()
    
    if not run_id:
        print("\n✗ OVERALL RESULT: FAILED (could not trigger ingestion)")
        sys.exit(1)
    
    # Step 2: Poll for completion
    success = poll_ingestion_status(run_id)
    
    if success:
        print("\n✓ OVERALL RESULT: PASSED (both tasks completed successfully)")
        sys.exit(0)
    else:
        print("\n✗ OVERALL RESULT: FAILED (ingestion did not complete successfully)")
        sys.exit(1)
