"""
Test Task 14.3.2: Modify a file in the test repo and trigger incremental ingestion via push webhook

This test verifies that:
1. A push webhook to the default branch triggers incremental ingestion
2. A second temporal snapshot is created after the incremental ingestion
3. The snapshot_id differs from the first snapshot
4. Both snapshots are properly recorded in meta.architecture_snapshots

Requirements ref: Requirement 3, Acceptance Criteria 1-3
Design ref: Component 3 (Time Travel System Integration), Component 4 (Webhook Handler)
Task ref: Task 3.1, Task 4.3

Usage:
    python test_task_14_3_2_incremental_ingestion.py
    python test_task_14_3_2_incremental_ingestion.py --repo Mithil1302/Engineering-Brain
    python test_task_14_3_2_incremental_ingestion.py --repo owner/repo --default-branch main
"""

import json
import hmac
import hashlib
import time
import sys
import os
import argparse
import uuid
from datetime import datetime

import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Default test configuration
DEFAULT_REPO = "Mithil1302/Engineering-Brain"
DEFAULT_HEAD_SHA = "1904df2ec66a8b0a16e08d3e7df4304f294ba8cc"
DEFAULT_BRANCH = "main"
DEFAULT_BASE_URL = "http://localhost:8002"
DEFAULT_WEBHOOK_PATH = "/webhooks/github"
DEFAULT_ENV_FILE = ".env"


def load_env_file(env_file):
    """Load environment variables from .env file"""
    if os.path.exists(env_file):
        load_dotenv(env_file)
        print(f"✓ Loaded environment from {env_file}")
    else:
        print(f"⚠ Warning: {env_file} not found, using system environment")


def get_db_connection():
    """Create PostgreSQL connection"""
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "brain"),
        user=os.getenv("POSTGRES_USER", "brain"),
        password=os.getenv("POSTGRES_PASSWORD", "brain"),
    )


def compute_webhook_signature(payload_bytes, secret):
    """Compute HMAC-SHA256 signature for webhook payload"""
    signature = hmac.new(
        secret.encode('utf-8'),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()
    return f"sha256={signature}"


def get_snapshot_count(repo):
    """Get the current count of ingestion snapshots for a repo"""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT COUNT(*) as count
                FROM meta.architecture_snapshots
                WHERE repo = %s AND event_type = 'ingestion'
            """, (repo,))
            result = cur.fetchone()
            return result['count'] if result else 0
    finally:
        conn.close()


def get_latest_snapshot(repo):
    """Get the latest ingestion snapshot for a repo"""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    snapshot_id,
                    repo,
                    timestamp,
                    node_ids,
                    edge_count,
                    services_count,
                    event_type
                FROM meta.architecture_snapshots
                WHERE repo = %s AND event_type = 'ingestion'
                ORDER BY timestamp DESC
                LIMIT 1
            """, (repo,))
            return cur.fetchone()
    finally:
        conn.close()


def wait_for_new_snapshot(repo, initial_count, timeout_seconds=120):
    """
    Wait for a new snapshot to be created.
    Returns the new snapshot or None if timeout.
    """
    start_time = time.time()
    print(f"\n⏳ Waiting for new snapshot (initial count: {initial_count}, timeout: {timeout_seconds}s)...")
    
    while time.time() - start_time < timeout_seconds:
        current_count = get_snapshot_count(repo)
        
        if current_count > initial_count:
            print(f"✓ New snapshot detected! Count increased from {initial_count} to {current_count}")
            return get_latest_snapshot(repo)
        
        # Print progress every 10 seconds
        elapsed = int(time.time() - start_time)
        if elapsed % 10 == 0 and elapsed > 0:
            print(f"  ... still waiting ({elapsed}s elapsed, count still {current_count})")
        
        time.sleep(2)
    
    print(f"✗ Timeout: No new snapshot created after {timeout_seconds}s")
    return None


def test_incremental_ingestion_creates_snapshot(
    repo=DEFAULT_REPO,
    default_branch=DEFAULT_BRANCH,
    head_sha=DEFAULT_HEAD_SHA,
    base_url=DEFAULT_BASE_URL,
    webhook_path=DEFAULT_WEBHOOK_PATH,
    env_file=DEFAULT_ENV_FILE
):
    """
    Test that incremental ingestion via push webhook creates a new temporal snapshot.
    
    Steps:
    1. Get the current snapshot count
    2. Send a push webhook to the default branch with modified files
    3. Wait for ingestion to complete
    4. Verify a new snapshot was created
    5. Compare the new snapshot with the previous one
    """
    
    print("\n" + "="*80)
    print("TEST: Task 14.3.2 - Incremental Ingestion Creates Temporal Snapshot")
    print("="*80)
    print(f"\nConfiguration:")
    print(f"  - Repository: {repo}")
    print(f"  - Default Branch: {default_branch}")
    print(f"  - Head SHA: {head_sha}")
    print(f"  - Webhook URL: {base_url}{webhook_path}")
    print("="*80)
    
    # Load environment
    load_env_file(env_file)
    
    # Get webhook secret
    webhook_secret = os.getenv("GITHUB_WEBHOOK_SECRET")
    if not webhook_secret:
        print("✗ FAIL: GITHUB_WEBHOOK_SECRET not found in environment")
        print("  Please set GITHUB_WEBHOOK_SECRET in your .env file")
        return False
    
    # Step 1: Get initial snapshot state
    print("\n[1] Getting initial snapshot state...")
    initial_count = get_snapshot_count(repo)
    initial_snapshot = get_latest_snapshot(repo)
    
    print(f"  - Initial snapshot count: {initial_count}")
    if initial_snapshot:
        print(f"  - Latest snapshot ID: {initial_snapshot['snapshot_id']}")
        print(f"  - Latest snapshot timestamp: {initial_snapshot['timestamp']}")
    else:
        print("  ⚠ WARNING: No initial snapshot found")
        print("  This test requires at least one ingestion to have completed")
        print("  Run test_task_14_3_1_temporal_snapshot.py first to verify initial state")
    
    # Step 2: Create and send push webhook
    print("\n[2] Creating push webhook payload...")
    
    # Generate a unique commit SHA for this test
    test_commit_sha = (uuid.uuid4().hex + uuid.uuid4().hex)[:40]
    
    # Create payload with modified files
    payload = {
        "ref": f"refs/heads/{default_branch}",
        "repository": {
            "full_name": repo,
            "default_branch": default_branch
        },
        "head_commit": {
            "id": test_commit_sha,
            "message": "Test commit for incremental ingestion",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        },
        "commits": [
            {
                "id": test_commit_sha,
                "added": [],
                "modified": [
                    "worker-service/app/main.py",
                    "README.md"
                ],
                "removed": []
            }
        ]
    }
    
    payload_bytes = json.dumps(payload).encode('utf-8')
    signature = compute_webhook_signature(payload_bytes, webhook_secret)
    
    print(f"  - Commit SHA: {test_commit_sha}")
    print(f"  - Modified files: {payload['commits'][0]['modified']}")
    print(f"  - Signature: {signature[:20]}...")
    
    # Step 3: Send webhook
    print("\n[3] Sending push webhook...")
    webhook_url = f"{base_url}{webhook_path}"
    
    headers = {
        "X-GitHub-Event": "push",
        "X-Hub-Signature-256": signature,
        "X-GitHub-Delivery": f"test-delivery-{uuid.uuid4()}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(
            webhook_url,
            data=payload_bytes,
            headers=headers,
            timeout=10
        )
        
        print(f"  - Response status: {response.status_code}")
        print(f"  - Response body: {response.text[:200]}")
        
        if response.status_code != 200:
            print(f"✗ FAIL: Expected HTTP 200, got {response.status_code}")
            return False
        
        print("  ✓ Webhook accepted (HTTP 200)")
        
    except requests.exceptions.RequestException as e:
        print(f"✗ FAIL: Webhook request failed: {e}")
        print(f"  Make sure agent-service is running at {base_url}")
        return False
    
    # Step 4: Wait for new snapshot
    print("\n[4] Waiting for incremental ingestion to complete...")
    new_snapshot = wait_for_new_snapshot(repo, initial_count, timeout_seconds=120)
    
    if not new_snapshot:
        print("✗ FAIL: No new snapshot created within timeout")
        print("\nDebugging information:")
        print("  - Check if worker-service is running")
        print("  - Check if Kafka is running and accessible")
        print("  - Check worker-service logs for ingestion errors")
        print("  - Verify the ingestion pipeline consumed the repo.ingestion event")
        return False
    
    # Step 5: Verify new snapshot
    print("\n[5] Verifying new snapshot...")
    print(f"  - New snapshot ID: {new_snapshot['snapshot_id']}")
    print(f"  - New snapshot timestamp: {new_snapshot['timestamp']}")
    
    # Verify snapshot_id is different
    if initial_snapshot and new_snapshot['snapshot_id'] == initial_snapshot['snapshot_id']:
        print("✗ FAIL: New snapshot has the same snapshot_id as the previous one")
        return False
    
    print("  ✓ Snapshot ID is unique")
    
    # Verify node_ids is present and non-empty
    node_ids = new_snapshot['node_ids']
    if not node_ids:
        print("✗ FAIL: node_ids field is NULL or empty")
        return False
    
    # Parse node_ids
    try:
        if isinstance(node_ids, str):
            node_ids_list = json.loads(node_ids)
        else:
            node_ids_list = node_ids
        
        if not isinstance(node_ids_list, list):
            print(f"✗ FAIL: node_ids is not a JSON array, got: {type(node_ids_list)}")
            return False
        
        if len(node_ids_list) == 0:
            print("✗ FAIL: node_ids array is empty")
            return False
        
        print(f"  ✓ node_ids contains {len(node_ids_list)} nodes")
        
    except json.JSONDecodeError as e:
        print(f"✗ FAIL: node_ids is not valid JSON: {e}")
        return False
    
    # Step 6: Compare with previous snapshot
    if initial_snapshot:
        print("\n[6] Comparing with previous snapshot...")
        
        # Parse initial node_ids
        initial_node_ids = initial_snapshot['node_ids']
        if isinstance(initial_node_ids, str):
            initial_node_ids_list = json.loads(initial_node_ids)
        else:
            initial_node_ids_list = initial_node_ids
        
        print(f"  - Previous snapshot had {len(initial_node_ids_list)} nodes")
        print(f"  - New snapshot has {len(node_ids_list)} nodes")
        
        # Check if timestamps are different
        if new_snapshot['timestamp'] <= initial_snapshot['timestamp']:
            print("  ⚠ WARNING: New snapshot timestamp is not later than previous")
        else:
            time_diff = (new_snapshot['timestamp'] - initial_snapshot['timestamp']).total_seconds()
            print(f"  ✓ New snapshot is {time_diff:.1f}s after previous snapshot")
    
    # Step 7: Verify snapshot format
    print("\n[7] Verifying snapshot format...")
    repo_slug = repo.replace('/', '_')
    expected_prefix = f"ingestion_{repo_slug}"
    
    if new_snapshot['snapshot_id'].startswith(expected_prefix):
        print(f"  ✓ Snapshot ID follows expected format: {expected_prefix}_*")
    else:
        print(f"  ⚠ WARNING: Unexpected snapshot_id format: {new_snapshot['snapshot_id']}")
        print(f"    Expected prefix: {expected_prefix}")
    
    # Verify event_type
    if new_snapshot['event_type'] != 'ingestion':
        print(f"  ✗ FAIL: event_type should be 'ingestion', got '{new_snapshot['event_type']}'")
        return False
    
    print("  ✓ event_type is 'ingestion'")
    
    # Final summary
    print("\n" + "="*80)
    print("✓ TEST PASSED: Incremental ingestion created new temporal snapshot")
    print("="*80)
    print("\nSummary:")
    print(f"  - Initial snapshots: {initial_count}")
    print(f"  - Final snapshots: {initial_count + 1}")
    print(f"  - New snapshot ID: {new_snapshot['snapshot_id']}")
    print(f"  - Nodes in snapshot: {len(node_ids_list)}")
    print(f"  - Test commit SHA: {test_commit_sha}")
    print("\nNext steps:")
    print("  - Run test_task_14_3_3 to verify snapshot comparison")
    print("  - Check meta.architecture_snapshots for both snapshots")
    
    return True


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Test Task 14.3.2: Incremental Ingestion Creates Temporal Snapshot"
    )
    parser.add_argument("--repo", default=DEFAULT_REPO, help="Repository full name (owner/repo)")
    parser.add_argument("--head-sha", default=DEFAULT_HEAD_SHA, help="Commit SHA")
    parser.add_argument("--default-branch", default=DEFAULT_BRANCH, help="Default branch name")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Agent service base URL")
    parser.add_argument("--webhook-path", default=DEFAULT_WEBHOOK_PATH, help="Webhook endpoint path")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE, help="Environment file path")
    
    args = parser.parse_args()
    
    try:
        success = test_incremental_ingestion_creates_snapshot(
            repo=args.repo,
            default_branch=args.default_branch,
            head_sha=args.head_sha,
            base_url=args.base_url,
            webhook_path=args.webhook_path,
            env_file=args.env_file
        )
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\n\n⚠ Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ TEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
