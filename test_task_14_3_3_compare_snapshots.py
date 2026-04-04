"""
Test Task 14.3.3: Verify second snapshot created — compare node_ids between first and second snapshot

This test verifies that:
1. At least two temporal snapshots exist for the test repository
2. The node_ids can be compared between snapshots
3. The snapshots have different snapshot_ids
4. The node_ids arrays can be analyzed for differences (added/removed/unchanged nodes)

Requirements ref: Requirement 3, Acceptance Criteria 2-3
Design ref: Component 3 (Time Travel System Integration)
Task ref: Task 3.1.5 (compute diff between snapshots)

Usage:
    python test_task_14_3_3_compare_snapshots.py
    python test_task_14_3_3_compare_snapshots.py --repo Mithil1302/Engineering-Brain
"""

import json
import sys
import os
import argparse

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Default test configuration
DEFAULT_REPO = "Mithil1302/Engineering-Brain"
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


def get_snapshots(repo, limit=10):
    """Get temporal snapshots for a repo, ordered by timestamp DESC"""
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
                    event_type,
                    event_payload
                FROM meta.architecture_snapshots
                WHERE repo = %s AND event_type = 'ingestion'
                ORDER BY timestamp DESC
                LIMIT %s
            """, (repo, limit))
            return cur.fetchall()
    finally:
        conn.close()


def parse_node_ids(node_ids_field):
    """Parse node_ids field (handles both string JSON and native list)"""
    if not node_ids_field:
        return []
    
    if isinstance(node_ids_field, str):
        return json.loads(node_ids_field)
    elif isinstance(node_ids_field, list):
        return node_ids_field
    else:
        raise ValueError(f"Unexpected node_ids type: {type(node_ids_field)}")


def compare_node_ids(first_node_ids, second_node_ids):
    """
    Compare two node_ids arrays and return added, removed, and unchanged nodes.
    
    Returns:
        dict with keys: added, removed, unchanged
    """
    first_set = set(first_node_ids)
    second_set = set(second_node_ids)
    
    return {
        "added": list(second_set - first_set),
        "removed": list(first_set - second_set),
        "unchanged": list(first_set & second_set)
    }


def test_compare_snapshots(repo=DEFAULT_REPO, env_file=DEFAULT_ENV_FILE):
    """
    Test that we can compare node_ids between two temporal snapshots.
    
    Steps:
    1. Verify at least 2 snapshots exist
    2. Get the two most recent snapshots
    3. Parse node_ids from both snapshots
    4. Compare node_ids to identify added, removed, and unchanged nodes
    5. Verify the snapshots have different snapshot_ids
    """
    
    print("\n" + "="*80)
    print("TEST: Task 14.3.3 - Compare node_ids Between Snapshots")
    print("="*80)
    print(f"\nConfiguration:")
    print(f"  - Repository: {repo}")
    print("="*80)
    
    # Load environment
    load_env_file(env_file)
    
    # Step 1: Get snapshots
    print("\n[1] Querying for temporal snapshots...")
    snapshots = get_snapshots(repo, limit=10)
    
    if not snapshots:
        print("✗ FAIL: No temporal snapshots found")
        print("\nThis test requires at least 2 ingestion snapshots to exist.")
        print("Run the following tests first:")
        print("  1. test_task_14_3_1_temporal_snapshot.py")
        print("  2. test_task_14_3_2_incremental_ingestion.py")
        return False
    
    print(f"✓ Found {len(snapshots)} temporal snapshot(s)")
    
    if len(snapshots) < 2:
        print(f"✗ FAIL: Need at least 2 snapshots, found only {len(snapshots)}")
        print("\nCurrent snapshot:")
        print(f"  - Snapshot ID: {snapshots[0]['snapshot_id']}")
        print(f"  - Timestamp: {snapshots[0]['timestamp']}")
        print("\nRun test_task_14_3_2_incremental_ingestion.py to create a second snapshot")
        return False
    
    # Step 2: Get the two most recent snapshots
    print("\n[2] Selecting two most recent snapshots for comparison...")
    second_snapshot = snapshots[0]  # Most recent
    first_snapshot = snapshots[1]   # Second most recent
    
    print(f"\nFirst snapshot (older):")
    print(f"  - Snapshot ID: {first_snapshot['snapshot_id']}")
    print(f"  - Timestamp: {first_snapshot['timestamp']}")
    print(f"  - Services count: {first_snapshot['services_count']}")
    print(f"  - Edge count: {first_snapshot['edge_count']}")
    
    print(f"\nSecond snapshot (newer):")
    print(f"  - Snapshot ID: {second_snapshot['snapshot_id']}")
    print(f"  - Timestamp: {second_snapshot['timestamp']}")
    print(f"  - Services count: {second_snapshot['services_count']}")
    print(f"  - Edge count: {second_snapshot['edge_count']}")
    
    # Step 3: Verify snapshot_ids are different
    print("\n[3] Verifying snapshot_ids are unique...")
    if first_snapshot['snapshot_id'] == second_snapshot['snapshot_id']:
        print("✗ FAIL: Both snapshots have the same snapshot_id")
        print(f"  Snapshot ID: {first_snapshot['snapshot_id']}")
        return False
    
    print("✓ Snapshot IDs are unique")
    
    # Step 4: Parse node_ids from both snapshots
    print("\n[4] Parsing node_ids from both snapshots...")
    
    try:
        first_node_ids = parse_node_ids(first_snapshot['node_ids'])
        print(f"  ✓ First snapshot: {len(first_node_ids)} nodes")
        
        second_node_ids = parse_node_ids(second_snapshot['node_ids'])
        print(f"  ✓ Second snapshot: {len(second_node_ids)} nodes")
        
    except (json.JSONDecodeError, ValueError) as e:
        print(f"✗ FAIL: Could not parse node_ids: {e}")
        return False
    
    # Verify both have non-empty node_ids
    if len(first_node_ids) == 0:
        print("✗ FAIL: First snapshot has empty node_ids array")
        return False
    
    if len(second_node_ids) == 0:
        print("✗ FAIL: Second snapshot has empty node_ids array")
        return False
    
    # Step 5: Compare node_ids
    print("\n[5] Comparing node_ids between snapshots...")
    diff = compare_node_ids(first_node_ids, second_node_ids)
    
    print(f"\nComparison results:")
    print(f"  - Added nodes: {len(diff['added'])}")
    print(f"  - Removed nodes: {len(diff['removed'])}")
    print(f"  - Unchanged nodes: {len(diff['unchanged'])}")
    
    # Show sample node IDs
    if diff['added']:
        print(f"\n  Sample added nodes:")
        for node_id in diff['added'][:3]:
            print(f"    + {node_id}")
        if len(diff['added']) > 3:
            print(f"    ... and {len(diff['added']) - 3} more")
    
    if diff['removed']:
        print(f"\n  Sample removed nodes:")
        for node_id in diff['removed'][:3]:
            print(f"    - {node_id}")
        if len(diff['removed']) > 3:
            print(f"    ... and {len(diff['removed']) - 3} more")
    
    if diff['unchanged']:
        print(f"\n  Sample unchanged nodes:")
        for node_id in diff['unchanged'][:3]:
            print(f"    = {node_id}")
        if len(diff['unchanged']) > 3:
            print(f"    ... and {len(diff['unchanged']) - 3} more")
    
    # Step 6: Verify comparison logic
    print("\n[6] Verifying comparison logic...")
    
    # Verify the math: first + added - removed = second
    expected_second_count = len(first_node_ids) + len(diff['added']) - len(diff['removed'])
    actual_second_count = len(second_node_ids)
    
    if expected_second_count != actual_second_count:
        print(f"✗ FAIL: Node count mismatch")
        print(f"  Expected: {len(first_node_ids)} + {len(diff['added'])} - {len(diff['removed'])} = {expected_second_count}")
        print(f"  Actual: {actual_second_count}")
        return False
    
    print("✓ Node count math is correct:")
    print(f"  {len(first_node_ids)} (first) + {len(diff['added'])} (added) - {len(diff['removed'])} (removed) = {actual_second_count} (second)")
    
    # Verify unchanged + added = second
    reconstructed_second = set(diff['unchanged']) | set(diff['added'])
    if reconstructed_second != set(second_node_ids):
        print("✗ FAIL: Reconstructed second snapshot doesn't match actual")
        return False
    
    print("✓ Reconstructed second snapshot matches actual")
    
    # Step 7: Verify timestamp ordering
    print("\n[7] Verifying timestamp ordering...")
    time_diff = (second_snapshot['timestamp'] - first_snapshot['timestamp']).total_seconds()
    
    if time_diff <= 0:
        print(f"✗ FAIL: Second snapshot timestamp is not later than first")
        print(f"  First: {first_snapshot['timestamp']}")
        print(f"  Second: {second_snapshot['timestamp']}")
        return False
    
    print(f"✓ Second snapshot is {time_diff:.1f}s after first snapshot")
    
    # Final summary
    print("\n" + "="*80)
    print("✓ TEST PASSED: Successfully compared node_ids between snapshots")
    print("="*80)
    print("\nSummary:")
    print(f"  - Total snapshots found: {len(snapshots)}")
    print(f"  - Compared snapshots: 2 most recent")
    print(f"  - First snapshot: {len(first_node_ids)} nodes")
    print(f"  - Second snapshot: {len(second_node_ids)} nodes")
    print(f"  - Nodes added: {len(diff['added'])}")
    print(f"  - Nodes removed: {len(diff['removed'])}")
    print(f"  - Nodes unchanged: {len(diff['unchanged'])}")
    print(f"  - Time between snapshots: {time_diff:.1f}s")
    
    # Additional insights
    if len(diff['added']) == 0 and len(diff['removed']) == 0:
        print("\n⚠ Note: No nodes were added or removed between snapshots")
        print("  This is expected for incremental ingestion of unchanged files")
    
    if len(diff['added']) > 0 or len(diff['removed']) > 0:
        print("\n✓ Architecture changes detected between snapshots")
        print("  This demonstrates the temporal graph's ability to track changes")
    
    print("\nNext steps:")
    print("  - Run test_task_14_3_4 to verify node removal tracking")
    print("  - Check meta.architecture_nodes for valid_to timestamps")
    
    return True


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Test Task 14.3.3: Compare node_ids Between Snapshots"
    )
    parser.add_argument("--repo", default=DEFAULT_REPO, help="Repository full name (owner/repo)")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE, help="Environment file path")
    
    args = parser.parse_args()
    
    try:
        success = test_compare_snapshots(
            repo=args.repo,
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
