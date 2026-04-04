# Task 14.3 Complete Test Guide

## Overview

This guide covers running the complete test suite for Task 14.3 (Temporal Snapshot Verification), which includes all subtasks 14.3.1 through 14.3.7.

## What Gets Tested

### 14.3.1: Ingestion Snapshot Created
- Triggers a full repository ingestion
- Verifies `meta.architecture_snapshots` has a row with `event_type='ingestion'`
- Checks that `node_ids` JSON array is non-empty
- Validates services_count > 0

### 14.3.2: Incremental Ingestion
- Simulates a file modification
- Triggers a second ingestion
- Verifies the ingestion completes successfully

### 14.3.3: Compare Snapshots
- Queries for both ingestion snapshots
- Compares `node_ids` between first and second snapshot
- Reports added, removed, and unchanged nodes

### 14.3.4: Delete Service Test
- Simulates service deletion
- Sets `valid_to` on a test node

### 14.3.5: Verify valid_to Set
- Queries for nodes with `valid_to IS NOT NULL`
- Verifies removed nodes have proper timestamps
- Checks that `valid_to > valid_from`

### 14.3.6: Time Travel Query
- Calls `get_snapshot_at()` with timestamp between ingestions
- Verifies it returns the first snapshot (not the second)
- Tests with current time to get latest snapshot

### 14.3.7: Policy Finding Snapshot
- Creates test policy findings (DOC_DRIFT_*, BREAKING_*)
- Records policy event via `record_policy_event()`
- Verifies snapshots created with `event_type='policy_finding'`

## Prerequisites

### 1. Services Running

```bash
# PostgreSQL
docker-compose up -d postgres

# Worker Service (required for ingestion API)
cd worker-service
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```

### 2. Database Schema

Ensure migration 003 is applied:

```bash
psql -U kachow -d kachow -f worker-service/migrations/003_ingestion_and_gaps.sql
```

### 3. Environment Variables

Create or update `.env`:

```bash
# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=kachow
POSTGRES_USER=kachow
POSTGRES_PASSWORD=kachow123

# Worker Service
WORKER_SERVICE_URL=http://localhost:8001

# Test Repository
TEST_REPO=test-org/test-repo

# GitHub App (for real ingestion)
GITHUB_APP_ID=your_app_id
GITHUB_APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----"
GITHUB_INSTALLATION_ID=your_installation_id
```

### 4. Test Repository

You need a real GitHub repository that:
- Your GitHub App has access to
- Contains at least one service (directory with Dockerfile, package.json, etc.)
- Has some code files (.py, .ts, .js, etc.)

## Running the Tests

### Quick Start

```bash
python test_task14_3_complete.py
```

### Expected Output

```
================================================================================
TASK 14.3 COMPLETE TEST SUITE
Temporal Snapshot Verification
================================================================================

Configuration:
  Worker Service: http://localhost:8001
  Test Repo: test-org/test-repo
  PostgreSQL: localhost:5432/kachow

✓ Worker service is accessible

================================================================================
Task 14.3.1: Verify Ingestion Snapshot Created
================================================================================

1. Cleaning up existing test data...
   ✓ Cleaned up existing test data

2. Triggering first ingestion...
   ✓ Ingestion triggered: run_id=abc-123

Waiting for ingestion to complete (timeout: 300s)...
   ✓ Ingestion completed in 45.2s
   Files processed: 127
   Chunks created: 543
   Services detected: 3

3. Querying meta.architecture_snapshots...
   ✓ Found ingestion snapshot: ingestion_test-org_test-repo_1234567890
   Timestamp: 2026-04-03 14:30:00+00:00
   Node count: 15
   Edge count: 8
   Services count: 3
   ✓ event_type is 'ingestion'
   ✓ node_ids is non-empty (contains 15 nodes)
   ✓ services_count is 3

[... continues for all tests ...]

================================================================================
TEST SUMMARY
================================================================================
Task 14.3.1: ✓ PASSED
Task 14.3.2: ✓ PASSED
Task 14.3.3: ✓ PASSED
Task 14.3.4: ✓ PASSED
Task 14.3.5: ✓ PASSED
Task 14.3.6: ✓ PASSED
Task 14.3.7: ✓ PASSED

================================================================================
✓ ALL TESTS PASSED - Task 14.3 is complete!
================================================================================
```

## Test Duration

- **14.3.1**: ~1-5 minutes (depends on repo size)
- **14.3.2**: ~1-5 minutes (second ingestion)
- **14.3.3**: <1 second (database query)
- **14.3.4**: <1 second (database update)
- **14.3.5**: <1 second (database query)
- **14.3.6**: <1 second (time travel query)
- **14.3.7**: <1 second (policy event recording)

**Total**: ~2-10 minutes (mostly waiting for ingestions)

## Troubleshooting

### Worker Service Not Accessible

```
✗ Worker service is not accessible: Connection refused
```

**Solution**: Start the worker service:
```bash
cd worker-service
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```

### Ingestion Fails

```
✗ Ingestion failed: GitHub authentication failed
```

**Solution**: Check your GitHub App credentials in `.env`:
- `GITHUB_APP_ID`
- `GITHUB_APP_PRIVATE_KEY`
- `GITHUB_INSTALLATION_ID`

### Database Connection Error

```
✗ Database query failed: could not connect to server
```

**Solution**: Ensure PostgreSQL is running:
```bash
docker-compose up -d postgres
```

### No Services Detected

```
✗ services_count is 0, expected > 0
```

**Solution**: Your test repository needs at least one service directory with:
- `Dockerfile`, OR
- `package.json`, OR
- `pyproject.toml`, OR
- `go.mod`

### Ingestion Timeout

```
✗ Ingestion timed out after 300s
```

**Solution**: 
- Check worker service logs for errors
- Verify GitHub API rate limits
- Try a smaller repository
- Increase timeout in the test script

## Manual Verification

After running the tests, you can manually verify the database:

### View All Snapshots

```sql
SELECT snapshot_id, repo, event_type, 
       array_length(node_ids, 1) as node_count,
       edge_count, services_count, timestamp
FROM meta.architecture_snapshots
WHERE repo = 'test-org/test-repo'
ORDER BY timestamp DESC;
```

### View Ingestion Snapshots

```sql
SELECT snapshot_id, 
       array_length(node_ids, 1) as node_count,
       edge_count, services_count, timestamp
FROM meta.architecture_snapshots
WHERE repo = 'test-org/test-repo' 
  AND event_type = 'ingestion'
ORDER BY timestamp DESC;
```

### View Policy Finding Snapshots

```sql
SELECT snapshot_id, 
       event_payload->>'rule_id' as rule_id,
       event_payload->>'message' as message,
       timestamp
FROM meta.architecture_snapshots
WHERE repo = 'test-org/test-repo' 
  AND event_type = 'policy_finding'
ORDER BY timestamp DESC;
```

### View Removed Nodes

```sql
SELECT node_id, node_type, 
       valid_from, valid_to,
       valid_to - valid_from as lifetime
FROM meta.architecture_nodes
WHERE repo = 'test-org/test-repo' 
  AND valid_to IS NOT NULL
ORDER BY valid_to DESC;
```

### View Active Nodes

```sql
SELECT node_id, node_type, valid_from
FROM meta.architecture_nodes
WHERE repo = 'test-org/test-repo' 
  AND valid_to IS NULL
ORDER BY valid_from DESC;
```

## Running Individual Tests

If you want to run tests individually, you can modify the script:

```python
# In test_task14_3_complete.py, modify run_all_tests():

def run_all_tests(self) -> bool:
    results = {}
    
    # Run only specific tests
    results['14.3.1'] = self.test_14_3_1()
    # results['14.3.2'] = self.test_14_3_2()  # Comment out to skip
    # ... etc
```

Or create a custom test runner:

```python
if __name__ == "__main__":
    tester = TemporalSnapshotTester()
    
    # Run only test 14.3.7
    success = tester.test_14_3_7()
    sys.exit(0 if success else 1)
```

## Cleanup

To clean up test data:

```sql
-- Remove all test snapshots
DELETE FROM meta.architecture_snapshots 
WHERE repo = 'test-org/test-repo';

-- Remove all test nodes
DELETE FROM meta.architecture_nodes 
WHERE repo = 'test-org/test-repo';

-- Remove test ingestion runs
DELETE FROM meta.ingestion_runs 
WHERE repo = 'test-org/test-repo';
```

## Next Steps

After all tests pass:

1. Mark tasks 14.3.1 through 14.3.7 as complete in `tasks.md`
2. Review the test output for any warnings
3. Proceed to Task 14.4 (Impact Analyzer Neo4j integration)

## Integration with CI/CD

To run these tests in CI/CD:

```yaml
# .github/workflows/test-temporal-snapshots.yml
name: Test Temporal Snapshots

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: kachow
          POSTGRES_USER: kachow
          POSTGRES_PASSWORD: kachow123
        ports:
          - 5432:5432
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      
      - name: Install dependencies
        run: |
          pip install -r worker-service/requirements.txt
      
      - name: Run migrations
        run: |
          psql -h localhost -U kachow -d kachow -f worker-service/migrations/003_ingestion_and_gaps.sql
        env:
          PGPASSWORD: kachow123
      
      - name: Start worker service
        run: |
          cd worker-service
          python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 &
          sleep 5
      
      - name: Run tests
        run: python test_task14_3_complete.py
        env:
          POSTGRES_HOST: localhost
          POSTGRES_PORT: 5432
          POSTGRES_DB: kachow
          POSTGRES_USER: kachow
          POSTGRES_PASSWORD: kachow123
          WORKER_SERVICE_URL: http://localhost:8001
          TEST_REPO: ${{ secrets.TEST_REPO }}
          GITHUB_APP_ID: ${{ secrets.GITHUB_APP_ID }}
          GITHUB_APP_PRIVATE_KEY: ${{ secrets.GITHUB_APP_PRIVATE_KEY }}
          GITHUB_INSTALLATION_ID: ${{ secrets.GITHUB_INSTALLATION_ID }}
```

## Support

If you encounter issues:

1. Check the worker service logs
2. Verify database schema is up to date
3. Ensure GitHub App has access to test repository
4. Review the test output for specific error messages
5. Check PostgreSQL logs for database errors

For detailed debugging, add `--verbose` flag or set `LOG_LEVEL=DEBUG` in environment.
