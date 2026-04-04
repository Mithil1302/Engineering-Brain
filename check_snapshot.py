import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host='localhost',
    port=5432,
    dbname='brain',
    user='brain',
    password='brain'
)

cur = conn.cursor(cursor_factory=RealDictCursor)
cur.execute("""
    SELECT snapshot_id, node_ids, edge_count, services_count, event_type
    FROM meta.architecture_snapshots
    WHERE snapshot_id = 'ingestion_Mithil1302_Engineering-Brain_2a7f1963-3e66-444b-9a30-ef2a9bcda3c7'
""")

result = cur.fetchone()
if result:
    print(f"Snapshot ID: {result['snapshot_id']}")
    print(f"Node IDs: {result['node_ids']}")
    print(f"Edge Count: {result['edge_count']}")
    print(f"Services Count: {result['services_count']}")
    print(f"Event Type: {result['event_type']}")
else:
    print("Snapshot not found")

conn.close()
