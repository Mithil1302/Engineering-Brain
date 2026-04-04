# Task 14.3 Complete Test Suite - Summary

## What Was Created

I've created a comprehensive test suite for Task 14.3 (Temporal Snapshot Verification) that tests all subtasks 14.3.1 through 14.3.7 in a single automated run.

## Files Created

### 1. `test_task14_3_complete.py` (Main Test Script)
**Purpose**: Automated test suite that runs all 7 subtasks sequentially

**Features**:
- Automatic cleanup of test data
- Sequential test execution with dependency handling
- Detailed progress reporting
- Database verification
- Time travel testing
- Policy finding snapshot testing

**Key Methods**:
- `test_14_3_1()` - Verify ingestion snapshot created
- `test_14_3_2()` - Incremental ingestion test
- `test_14_3_3()` - Compare snapshots
- `test_14_3_4()` - Delete service test
- `test_14_3_5()` - Verify valid_to set
- `test_14_3_6()` - Test get_snapshot_at() time travel
- `test_14_3_7()` - Policy finding snapshot

### 2. `TASK_14_3_COMPLETE_GUIDE.md` (Detailed Guide)
**Purpose**: Comprehensive documentation for running the tests

**Contents**:
- Detailed explanation of each test
- Prerequisites and setup instructions
- Expected output examples
- Troubleshooting guide
- Manual verification queries
- CI/CD integration examples

### 3. `TASK_14_3_QUICK_START.md` (Quick Reference)
**Purpose**: Fast reference for running tests

**Contents**:
- TL;DR commands
- Quick checklist
- Common issues and fixes
- Quick verification queries

### 4. `TASK_14_3_SUMMARY.md` (This File)
**Purpose**: Overview of what was created and how to use it

## How to Use

### Quick Start (2 commands)

```bash
# 1. Start services
docker-compose up -d postgres
cd worker-service && python -m uvicorn app.main:app --port 8001 &

# 2. Run tests
python test_task14_3_complete.py
```

### What Happens

1. **Test 14.3.1**: Triggers first ingestion, verifies snapshot created
2. **Test 14.3.2**: Triggers second ingestion (simulates file change)
3. **Test 14.3.3**: Compares the two snapshots, reports differences
4. **Test 14.3.4**: Simulates service deletion
5. **Test 14.3.5**: Verifies deleted nodes have valid_to timestamp
6. **Test 14.3.6**: Tests time travel query (get_snapshot_at)
7. **Test 14.3.7**: Tests policy finding snapshots (DOC_DRIFT, BREAKING)

### Expected Duration

- **Fast path**: ~2 minutes (if ingestion is quick)
- **Normal path**: ~5-10 minutes (typical ingestion time)
- **Slow path**: Up to 15 minutes (large repos or slow GitHub API)

Most time is spent waiting for ingestions to complete (14.3.1 and 14.3.2).

## Prerequisites Checklist

Before running the tests, ensure:

- [ ] PostgreSQL is running on localhost:5432
- [ ] Database `kachow` exists with user `kachow`
- [ ] Migration 003 has been applied
- [ ] Worker service is running on localhost:8001
- [ ] `.env` file has GitHub App credentials
- [ ] Test repository is accessible by your GitHub App
- [ ] Test repository has at least one service directory

## Test Coverage

### Database Tables Verified

✓ `meta.architecture_snapshots`
- Ingestion snapshots (event_type='ingestion')
- Policy finding snapshots (event_type='policy_finding')
- Snapshot format and structure
- ON CONFLICT protection

✓ `meta.architecture_nodes`
- Node creation with valid_from
- Node removal with valid_to
- Temporal validity constraints

✓ `meta.ingestion_runs`
- Ingestion status tracking
- Progress counters
- Error handling

### Functionality Verified

✓ **Ingestion Pipeline Integration**
- Full repository ingestion
- Incremental ingestion (simulated)
- Snapshot creation on completion

✓ **Temporal Graph Store**
- `record_ingestion_snapshot()` method
- `record_policy_event()` method
- `get_snapshot_at()` time travel query
- Node lifecycle management (valid_from/valid_to)

✓ **Policy Integration**
- DOC_DRIFT_* finding recording
- BREAKING_* finding recording
- Filtering of non-relevant findings
- ON CONFLICT re-delivery protection

## Success Criteria

All tests pass when:

1. ✓ First ingestion creates snapshot with non-empty node_ids
2. ✓ Second ingestion creates a different snapshot
3. ✓ Snapshots can be compared (added/removed/unchanged nodes)
4. ✓ Deleted nodes have valid_to timestamp set
5. ✓ valid_to > valid_from for all removed nodes
6. ✓ Time travel query returns correct historical state
7. ✓ Policy findings create policy_finding snapshots

## Troubleshooting Quick Reference

| Error | Solution |
|-------|----------|
| Worker service not accessible | Start: `cd worker-service && python -m uvicorn app.main:app --port 8001` |
| Database connection failed | Start: `docker-compose up -d postgres` |
| GitHub auth failed | Check `.env` has GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY, GITHUB_INSTALLATION_ID |
| services_count is 0 | Test repo needs Dockerfile, package.json, pyproject.toml, or go.mod |
| Ingestion timeout | Check worker logs, verify GitHub rate limits, try smaller repo |

## Manual Verification

After tests pass, verify in database:

```sql
-- Should show 2 ingestion snapshots
SELECT COUNT(*) FROM meta.architecture_snapshots 
WHERE repo = 'test-org/test-repo' AND event_type = 'ingestion';

-- Should show 2 policy finding snapshots
SELECT COUNT(*) FROM meta.architecture_snapshots 
WHERE repo = 'test-org/test-repo' AND event_type = 'policy_finding';

-- Should show nodes with valid_to set (if any were deleted)
SELECT COUNT(*) FROM meta.architecture_nodes 
WHERE repo = 'test-org/test-repo' AND valid_to IS NOT NULL;
```

## Integration Points

This test suite verifies the integration between:

1. **Ingestion Pipeline** → **Temporal Graph Store**
   - `IngestionPipeline._emit_completion_event()` triggers
   - `TemporalGraphStore.record_ingestion_snapshot()` records

2. **Policy Pipeline** → **Temporal Graph Store**
   - `PolicyPipeline._record_policy_temporal()` calls
   - `TemporalGraphStore.record_policy_event()` records

3. **Temporal Graph Store** → **Neo4j** (via gRPC)
   - `_query_current_nodes()` fetches from Neo4j
   - `_query_current_edges()` fetches from Neo4j
   - Falls back to PostgreSQL if Neo4j unavailable

4. **Temporal Graph Store** → **PostgreSQL**
   - Writes to `meta.architecture_snapshots`
   - Writes to `meta.architecture_nodes`
   - Queries for time travel functionality

## Next Steps

After all tests pass:

1. **Mark tasks complete** in `.kiro/specs/ka-chow-production-completion/tasks.md`:
   - [x] 14.3.1
   - [x] 14.3.2
   - [x] 14.3.3
   - [x] 14.3.4
   - [x] 14.3.5
   - [x] 14.3.6
   - [x] 14.3.7

2. **Proceed to Task 14.4**: Impact Analyzer Neo4j integration verification

3. **Optional**: Run tests in CI/CD (see guide for GitHub Actions example)

## Test Output Example

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

[... continues for all 7 tests ...]

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

## Support

For issues or questions:

1. Check `TASK_14_3_COMPLETE_GUIDE.md` for detailed troubleshooting
2. Review worker service logs for errors
3. Verify database schema is up to date
4. Check GitHub App permissions and rate limits

## Summary

This test suite provides:
- ✓ Complete automation of Task 14.3 verification
- ✓ Sequential test execution with dependency handling
- ✓ Detailed progress reporting and error messages
- ✓ Database verification at each step
- ✓ Integration testing across multiple components
- ✓ Time travel functionality validation
- ✓ Policy finding snapshot verification

Run `python test_task14_3_complete.py` to verify all temporal snapshot functionality is working correctly.
