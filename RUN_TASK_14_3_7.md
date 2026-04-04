# How to Run Task 14.3.7 Verification

## Quick Start

```bash
python test_task14_3_7_policy_finding_snapshot.py
```

## Prerequisites

1. **PostgreSQL Running**
   - Host: localhost:5432
   - Database: kachow
   - User: kachow
   - Password: kachow123

2. **Database Schema**
   - `meta.architecture_snapshots` table must exist
   - Migration 003 must be applied

3. **Python Dependencies**
   - psycopg2
   - worker-service modules

## Environment Variables

The test uses these defaults (can be overridden):

```bash
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=kachow
POSTGRES_USER=kachow
POSTGRES_PASSWORD=kachow123
```

## What the Test Does

1. **Creates Test Findings**
   - 2 DOC_DRIFT_* findings
   - 1 BREAKING_* finding
   - 1 STYLE_VIOLATION finding (should be filtered out)

2. **Records Policy Event**
   - Calls `TemporalGraphStore.record_policy_event()`
   - Inserts snapshots into `meta.architecture_snapshots`

3. **Verifies Database**
   - Checks exactly 3 snapshots created
   - Verifies `event_type='policy_finding'`
   - Validates snapshot format
   - Confirms filtering works
   - Tests ON CONFLICT protection

## Expected Output

```
================================================================================
Task 14.3.7: Policy Finding Temporal Snapshot Test
================================================================================

1. Testing with 4 findings (3 relevant, 1 irrelevant)
   Repo: test-org/test-repo
   Run ID: 999

2. Cleaning up existing test data...
   Deleted 0 existing policy_finding snapshots for test-org/test-repo

3. Recording policy event...
   ✓ record_policy_event() completed successfully

4. Verifying meta.architecture_snapshots records...
   ✓ Found 3 policy_finding snapshot(s)
   ✓ Correct number of snapshots (3)

   [Details for each snapshot...]

   ✓ All expected rule_ids found
   ✓ STYLE_VIOLATION correctly filtered out

5. Testing ON CONFLICT (re-delivery protection)...
   ✓ ON CONFLICT working: still 3 rows after re-delivery

================================================================================
✓ Task 14.3.7: ALL CHECKS PASSED
================================================================================
```

## Troubleshooting

### Database Connection Error
```
Error: could not connect to server
```
**Solution:** Ensure PostgreSQL is running and accessible at localhost:5432

### Table Does Not Exist
```
Error: relation "meta.architecture_snapshots" does not exist
```
**Solution:** Run migration 003:
```bash
psql -U kachow -d kachow -f worker-service/migrations/003_ingestion_and_gaps.sql
```

### Import Error
```
ModuleNotFoundError: No module named 'app'
```
**Solution:** The test adds worker-service to sys.path automatically. Ensure you're running from the project root.

## Manual Verification

After running the test, you can manually verify the database:

```sql
-- View all policy finding snapshots
SELECT snapshot_id, repo, event_type, 
       event_payload->>'rule_id' as rule_id,
       event_payload->>'message' as message,
       timestamp
FROM meta.architecture_snapshots
WHERE event_type = 'policy_finding'
ORDER BY timestamp DESC;

-- Count by repo
SELECT repo, COUNT(*) as finding_count
FROM meta.architecture_snapshots
WHERE event_type = 'policy_finding'
GROUP BY repo;

-- View specific test data
SELECT *
FROM meta.architecture_snapshots
WHERE repo = 'test-org/test-repo' 
  AND event_type = 'policy_finding';
```

## Cleanup

The test automatically cleans up its test data before running. To manually clean up:

```sql
DELETE FROM meta.architecture_snapshots 
WHERE repo = 'test-org/test-repo' 
  AND event_type = 'policy_finding';
```

## Integration with Full System

In production, this functionality is triggered by:

1. **Webhook receives PR event** → `agent-service/app/github_bridge.py`
2. **Policy check runs** → `worker-service/app/policy/pipeline.py`
3. **Findings generated** → Policy engine evaluates rules
4. **Temporal snapshot created** → `_record_policy_temporal()` calls `record_policy_event()`

The test verifies step 4 in isolation.
