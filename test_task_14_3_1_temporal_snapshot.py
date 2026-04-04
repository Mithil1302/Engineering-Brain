"""
Test Task 14.3.1: Verify temporal snapshot creation after ingestion

This test verifies that after a successful ingestion:
1. A row exists in meta.architecture_snapshots with event_type='ingestion'
2. The node_ids field contains a non-empty JSON array
3. The snapshot is properly linked to the ingestion run

This is a verification test that checks the database state after ingestion has run.
Run this after a successful ingestion to verify temporal snapshot creation.
"""

import json
import os
import sys

import psycopg2
from psycopg2.extras import RealDictCursor


def get_db_connection():
    """Create PostgreSQL connection"""
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "brain"),
        user=os.getenv("POSTGRES_USER", "brain"),
        password=os.getenv("POSTGRES_PASSWORD", "brain"),
    )


def test_temporal_snapshot_after_ingestion():
    """Test that temporal snapshots are created after ingestion"""
    
    print("\n" + "="*80)
    print("TEST: Task 14.3.1 - Temporal Snapshot Creation After Ingestion")
    print("="*80)
    print("\nThis test verifies the database state after ingestion has completed.")
    print("It checks that temporal snapshots are properly recorded.")
    print("="*80)
    
    # Verify temporal snapshot was created
    print("\n[1] Querying for temporal snapshots with event_type='ingestion'...")
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            repo = os.getenv("TEST_REPO", "Mithil1302/Engineering-Brain")
            # Query for all ingestion snapshots for this specific repo
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
                WHERE event_type = 'ingestion' AND repo = %s
                ORDER BY timestamp DESC
                LIMIT 10
            """, (repo,))
            
            snapshots = cur.fetchall()
            
            if not snapshots:
                print("✗ FAIL: No temporal snapshots found with event_type='ingestion'")
                print("\nChecking if table exists and has any data...")
                cur.execute("""
                    SELECT COUNT(*) as total_count,
                           COUNT(CASE WHEN event_type = 'ingestion' THEN 1 END) as ingestion_count,
                           COUNT(CASE WHEN event_type = 'policy_finding' THEN 1 END) as policy_count
                    FROM meta.architecture_snapshots
                """)
                counts = cur.fetchone()
                print(f"  Total snapshots: {counts['total_count']}")
                print(f"  Ingestion snapshots: {counts['ingestion_count']}")
                print(f"  Policy finding snapshots: {counts['policy_count']}")
                return False
            
            print(f"✓ Found {len(snapshots)} temporal snapshot(s) with event_type='ingestion'")
            print("\nAnalyzing snapshots:")
            
            success = True
            for idx, snapshot in enumerate(snapshots, 1):
                print(f"\n--- Snapshot {idx} ---")
                print(f"  Snapshot ID: {snapshot['snapshot_id']}")
                print(f"  Repo: {snapshot['repo']}")
                print(f"  Timestamp: {snapshot['timestamp']}")
                print(f"  Event type: {snapshot['event_type']}")
                
                # Verify node_ids is a non-empty JSON array
                node_ids = snapshot['node_ids']
                if not node_ids:
                    print("  ✗ FAIL: node_ids field is NULL or empty")
                    success = False
                    continue
                
                # Parse JSON
                try:
                    if isinstance(node_ids, str):
                        node_ids_list = json.loads(node_ids)
                    else:
                        node_ids_list = node_ids
                    
                    if not isinstance(node_ids_list, list):
                        print(f"  ✗ FAIL: node_ids is not a JSON array, got: {type(node_ids_list)}")
                        success = False
                        continue
                    
                    if len(node_ids_list) == 0:
                        print("  ✗ FAIL: node_ids array is empty")
                        success = False
                        continue
                    
                    print(f"  ✓ node_ids contains {len(node_ids_list)} nodes")
                    print(f"    Sample node IDs: {node_ids_list[:3]}")
                    
                except json.JSONDecodeError as e:
                    print(f"  ✗ FAIL: node_ids is not valid JSON: {e}")
                    success = False
                    continue
                
                # Verify other fields
                if snapshot['edge_count'] is None:
                    print("  ⚠ WARNING: edge_count is NULL")
                else:
                    print(f"  ✓ Edge count: {snapshot['edge_count']}")
                
                if snapshot['services_count'] is None:
                    print("  ⚠ WARNING: services_count is NULL")
                else:
                    print(f"  ✓ Services count: {snapshot['services_count']}")
                
                # Verify event_payload is NULL for ingestion events
                if snapshot['event_payload'] is not None:
                    print(f"  ⚠ WARNING: event_payload should be NULL for ingestion events")
                else:
                    print("  ✓ event_payload is NULL (correct for ingestion events)")
            
            if not success:
                return False
            
            # Check if there are corresponding nodes in architecture_nodes
            print(f"\n[2] Verifying architecture_nodes table...")
            cur.execute("""
                SELECT 
                    repo,
                    COUNT(*) as total_nodes,
                    COUNT(CASE WHEN valid_to IS NULL THEN 1 END) as active_nodes,
                    COUNT(CASE WHEN valid_to IS NOT NULL THEN 1 END) as historical_nodes
                FROM meta.architecture_nodes
                GROUP BY repo
                ORDER BY repo
            """)
            
            node_stats = cur.fetchall()
            
            if not node_stats:
                print("⚠ WARNING: No nodes found in architecture_nodes table")
            else:
                print(f"✓ Found nodes for {len(node_stats)} repo(s):")
                for stat in node_stats:
                    print(f"  - {stat['repo']}: {stat['active_nodes']} active, {stat['historical_nodes']} historical")
            
            # Verify snapshot_id format
            print(f"\n[3] Verifying snapshot ID format...")
            for snapshot in snapshots:
                repo_slug = snapshot['repo'].replace('/', '_')
                if snapshot['snapshot_id'].startswith(f"ingestion_{repo_slug}"):
                    print(f"  ✓ {snapshot['snapshot_id']} follows expected format")
                else:
                    print(f"  ⚠ WARNING: Unexpected snapshot_id format: {snapshot['snapshot_id']}")
            
    finally:
        conn.close()
    
    print("\n" + "="*80)
    print("✓ TEST PASSED: Temporal snapshots verified successfully")
    print("="*80)
    
    return True


if __name__ == "__main__":
    success = test_temporal_snapshot_after_ingestion()
    sys.exit(0 if success else 1)
