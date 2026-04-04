#!/usr/bin/env python3
"""
Poll the ingestion status endpoint to verify successful completion.
Task 14.1.2: Poll GET /ingestion/status/test-org/test-repo — verify status="success" within 5 minutes
"""

import requests
import time
import sys
from datetime import datetime, timedelta

WORKER_SERVICE_URL = "http://localhost:8003"
REPO = "Mithil1302/Engineering-Brain"  # Update to your target repo
TIMEOUT_MINUTES = 5  # Increased to 5 minutes for full ingestion
POLL_INTERVAL_SECONDS = 5

def poll_ingestion_status():
    """Poll the ingestion status endpoint until success or timeout."""
    # FastAPI route uses {repo:path} to handle the forward slash
    endpoint = f"{WORKER_SERVICE_URL}/ingestion/status/{REPO}"
    start_time = datetime.now()
    timeout = timedelta(minutes=TIMEOUT_MINUTES)
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting to poll {endpoint}")
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
                run_id = data.get("run_id", "N/A")
                files_processed = data.get("files_processed", 0)
                chunks_created = data.get("chunks_created", 0)
                embeddings_created = data.get("embeddings_created", 0)
                services_detected = data.get("services_detected", 0)
                duration = data.get("duration_seconds", 0)
                
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Attempt {attempt} ({elapsed:.1f}s): Status={status}")
                print(f"  Run ID: {run_id}")
                print(f"  Files: {files_processed}, Chunks: {chunks_created}, Embeddings: {embeddings_created}, Services: {services_detected}")
                print(f"  Duration: {duration:.2f}s")
                
                if status == "success":
                    print("-" * 80)
                    print(f"✓ SUCCESS: Ingestion completed successfully in {elapsed:.1f}s")
                    print(f"  Total files processed: {files_processed}")
                    print(f"  Total chunks created: {chunks_created}")
                    print(f"  Total embeddings created: {embeddings_created}")
                    print(f"  Services detected: {services_detected}")
                    print(f"  Ingestion duration: {duration:.2f}s")
                    return True
                elif status == "failed":
                    error_message = data.get("error_message", "No error message")
                    print("-" * 80)
                    print(f"✗ FAILED: Ingestion failed")
                    print(f"  Error: {error_message}")
                    return False
                elif status == "running":
                    print(f"  Still running... waiting {POLL_INTERVAL_SECONDS}s")
                else:
                    print(f"  Unknown status: {status}")
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Attempt {attempt} ({elapsed:.1f}s): HTTP {response.status_code}")
                print(f"  Response: {response.text[:200]}")
        
        except requests.exceptions.ConnectionError:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Attempt {attempt} ({elapsed:.1f}s): Connection error - is worker-service running?")
        except requests.exceptions.Timeout:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Attempt {attempt} ({elapsed:.1f}s): Request timeout")
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Attempt {attempt} ({elapsed:.1f}s): Error - {e}")
        
        time.sleep(POLL_INTERVAL_SECONDS)
    
    # Timeout reached
    elapsed = (datetime.now() - start_time).total_seconds()
    print("-" * 80)
    print(f"✗ TIMEOUT: Ingestion did not complete within {TIMEOUT_MINUTES} minutes ({elapsed:.1f}s elapsed)")
    return False

if __name__ == "__main__":
    print("=" * 80)
    print("Task 14.1.2: Poll Ingestion Status Verification")
    print("=" * 80)
    
    success = poll_ingestion_status()
    
    print("=" * 80)
    sys.exit(0 if success else 1)
