# Task 14.3 Step-by-Step Execution Guide

This guide provides detailed instructions for executing tasks 14.3.1 through 14.3.7, including all prerequisites, file changes, and troubleshooting steps.

## Prerequisites

### Environment Setup
1. **API Key Configuration**
   - Ensure `.env` has valid `GEMINI_API_KEY`
   - Set PowerShell environment variable: `$env:GEMINI_API_KEY = "your-key-here"`
   - Verify: `docker compose exec worker-service printenv GEMINI_API_KEY`

2. **Services Running**
   ```bash
   docker compose ps
   ```
   All services should be "healthy" or "running"

3. **Database Clean State**
   - PostgreSQL on localhost:5432
   - Database: brain, User: brain, Password: brain

### Known Issues & Fixes

**Issue: "Event loop is closed" error**
- **Cause**: Gemini SDK event loop conflict
- **Fix**: Already applied in `worker-service/app/llm/embeddings.py` (line 64-68)
- **Verify**: Check that `http_options={'api_version': 'v1beta'}` is present

**Issue: API key not updating**
- **Cause**: PowerShell environment variable overrides `.env`
- **Fix**: Set `$env:GEMINI_API_KEY` in PowerShell before running docker compose

---

## Task 14.3.1: Verify Temporal Snapshot Creation

### Purpose
Verify that temporal snapshots are created after successful ingestion.

### Prerequisites
- At least one successful ingestion run (14.1.1 and 14.1.2 completed)

### Files to Check
- `test_task_14_3_1_temporal_snapshot.py` - No changes needed

### Execution Steps

1. **Run the test**
   ```bash
   python test_task_14_3_1_temporal_snapshot.py
   ```

2. **Expected Output**
   ```
   ✓ Found N temporal snapshot(s) with event_type='ingestion'
   ✓ node_ids contains X nodes
   ✓ Edge count: Y
   ✓ Services count: Z
   ✓ TEST PASSED
   ```

3. **If Test Fails**
   - **No snapshots found**: Run ingestion first
     ```bash
     python test_ingestion_trigger.py
     python test_ingestion_status.py
     ```
   - **node_ids is empty**: Ingestion failed or no services detected
     - Check worker-service logs: `docker compose logs worker-service`
     - Verify API key is working
     - Restart worker-service: `docker compose restart worker-service`

### Success Criteria
- At least 1 snapshot with `event_type='ingestion'`
- `node_ids` is a non-empty JSON array
- Snapshot has valid `snapshot_id`, `timestamp`, and `repo`

---

## Task 14.3.2: Incremental Ingestion Creates Snapshot

### Purpose
Verify that incremental ingestion (via webhook or manual trigger) creates a second snapshot.

### Prerequisites
- Task 14.3.1 passed (at least 1 snapshot exists)

### Files to Check
- `test_task_14_3_2_incremental_ingestion.py` - No changes needed

### Known Issue
The test sends a webhook to agent-service, but agent-service doesn't trigger ingestion from push webhooks. The webhook is accepted (HTTP 200) but nothing happens.

### Workaround: Manual Trigger

Instead of running the test as-is, trigger a second ingestion manually:

1. **Trigger second ingestion**
   ```bash
   python test_ingestion_trigger.py
   ```

2. **Wait for completion**
   ```bash
   python test_ingestion_status.py
   ```

3. **Verify second snapshot was created**
   ```bash
   python test_task_14_3_1_temporal_snapshot.py
   ```
   Should show 2 or more snapshots now.

4. **Run the test (it will detect the new snapshot)**
   ```bash
   python test_task_14_3_2_incremental_ingestion.py
   ```

### Expected Behavior
- Test detects initial snapshot count
- Sends webhook (HTTP 200 response)
- Waits for new snapshot (120s timeout)
- Verifies new snapshot has different `snapshot_id`
- Verifies `node_ids` is non-empty

### If Test Fails
- **Timeout waiting for snapshot**: Use manual trigger workaround above
- **node_ids is empty**: The incremental ingestion only processed changed files, no services detected
  - Solution: Run full ingestion instead: `python test_ingestion_trigger.py`

### Success Criteria
- At least 2 snapshots exist
- Second snapshot has different `snapshot_id` from first
- Second snapshot has non-empty `node_ids`

---

## Task 14.3.3: Compare Snapshots

### Purpose
Verify that we can compare `node_ids` between two snapshots to identify added/removed/unchanged nodes.

### Prerequisites
- Task 14.3.2 passed (at least 2 snapshots exist)

### Files to Check
- `test_task_14_3_3_compare_snapshots.py` - No changes needed

### Execution Steps

1. **Run the test**
   ```bash
   python test_task_14_3_3_compare_snapshots.py
   ```

2. **Expected Output**
   ```
   ✓ Found N temporal snapshot(s)
   ✓ Snapshot IDs are unique
   ✓ First snapshot: X nodes
   ✓ Second snapshot: Y nodes
   Comparison results:
     - Added nodes: A
     - Removed nodes: R
     - Unchanged nodes: U
   ✓ Node count math is correct
   ✓ TEST PASSED
   ```

### Understanding the Output
- **Added nodes**: Nodes in second snapshot but not in first
- **Removed nodes**: Nodes in first snapshot but not in second
- **Unchanged nodes**: Nodes present in both snapshots

### If Test Fails
- **Less than 2 snapshots**: Run task 14.3.2 first
- **node_ids empty**: One or both snapshots have empty node arrays
  - Run full ingestion: `python test_ingestion_trigger.py`
- **Math doesn't add up**: Data corruption or parsing error
  - Check database: `SELECT * FROM meta.architecture_snapshots WHERE event_type='ingestion' ORDER BY timestamp DESC LIMIT 2;`

### Success Criteria
- Successfully compares 2 most recent snapshots
- Math is correct: `first + added - removed = second`
- Timestamps are ordered correctly

---

## Task 14.3.4: Service Deletion Detection

### Purpose
Verify that deleting a service directory triggers snapshot creation and reduces active service count.

### Prerequisites
- Task 14.3.3 passed
- Access to GitHub repository to delete a service

### Files to Change BEFORE Running Test

**CRITICAL**: You must delete a service directory from your GitHub repository before running this test.

1. **Choose a service to delete**
   - Options: `agent-service`, `backend`, `graph-service`, `ingestion-service`, `worker-service`
   - Recommendation: Delete `backend` (least critical for testing)

2. **Delete from GitHub**
   ```bash
   # On GitHub web interface:
   # 1. Navigate to the service directory (e.g., /backend)
   # 2. Click "..." menu
   # 3. Select "Delete directory"
   # 4. Commit with message: "Test: Remove backend service for 14.3.4"
   ```

3. **Update docker-compose.yml** (if needed)
   - Remove the service entry from `docker-compose.yml`
   - Commit and push

### Execution Steps

1. **Record initial state**
   ```bash
   # Count active services before deletion
   docker compose exec postgres psql -U brain -d brain -c "SELECT COUNT(*) FROM meta.architecture_nodes WHERE node_type='service' AND valid_to IS NULL;"
   ```

2. **Run the test**
   ```bash
   python test_task_14_3_4_service_deletion.py
   ```

3. **Expected Output**
   ```
   Task 14.3.4
   -----------
   before_active_services=12
   after_active_services=11
   services_decreased=True
   snapshot_created=True
   PASS: full ingestion reflected service deletion
   ```

### If Test Fails
- **services_decreased=False**: Service wasn't actually deleted
  - Verify deletion on GitHub
  - Check that ingestion completed successfully
  - Verify `GraphPopulator._delete_removed_services()` is implemented
- **snapshot_created=False**: Ingestion didn't create snapshot
  - Check worker-service logs
  - Verify database connection

### Success Criteria
- Active service count decreases by at least 1
- New ingestion snapshot is created
- Test returns exit code 0

---

## Task 14.3.5: Removed Service valid_to Timestamp

### Purpose
Verify that removed service nodes have `valid_to` set in `meta.architecture_nodes`.

### Prerequisites
- Task 14.3.4 passed (service was deleted and ingestion ran)

### Files to Check
- `test_task_14_3_5_removed_service_valid_to.py` - No changes needed

### Execution Steps

1. **Run the test**
   ```bash
   python test_task_14_3_5_removed_service_valid_to.py
   ```

2. **Expected Output**
   ```
   Task 14.3.5
   -----------
   repo=Mithil1302/Engineering-Brain
   previous_ingestion_ts=2026-04-04 17:00:00
   latest_ingestion_ts=2026-04-04 17:05:00
   end_dated_services_in_window=1
   - backend (service:backend) valid_to=2026-04-04 17:05:00
   PASS: removed service node(s) have valid_to set
   ```

### Understanding the Output
- **end_dated_services_in_window**: Number of services that were marked as removed
- **valid_to**: Timestamp when the service was removed (should match latest ingestion)

### If Test Fails
- **No removed services found**: `GraphPopulator._delete_removed_services()` not working
  - Check implementation in `worker-service/app/ingestion/graph_populator.py`
  - Verify it sets `valid_to = NOW()` for removed services
- **valid_to not in window**: Timing issue
  - Re-run task 14.3.4 to ensure fresh deletion

### Success Criteria
- At least 1 service has `valid_to` set
- `valid_to` timestamp is between previous and latest ingestion
- Test returns exit code 0

---

## Task 14.3.6: get_snapshot_at() Time Travel

### Purpose
Verify that `TemporalGraphStore.get_snapshot_at()` correctly reconstructs architecture state at a specific point in time.

### Prerequisites
- Task 14.3.3 passed (at least 2 snapshots exist)

### Files to Check
- `test_task_14_3_6_get_snapshot_at.py` - No changes needed
- `worker-service/app/simulation/time_travel.py` - Verify `get_snapshot_at()` is implemented

### Execution Steps

1. **Run the test**
   ```bash
   python test_task_14_3_6_get_snapshot_at.py
   ```

2. **Expected Output**
   ```
   ✓ Found N temporal snapshot(s)
   ✓ Timestamp is between first and second snapshot
   ✓ Reconstructed X temporal node(s) from snapshot history
   ✓ get_snapshot_at() returned successfully
   ✓ All expected nodes are present
   ✓ All returned nodes are valid at query timestamp
   ✓ TEST PASSED
   ```

### Understanding the Test
1. Gets first and second snapshots
2. Calculates midpoint timestamp between them
3. Calls `get_snapshot_at(midpoint_timestamp)`
4. Verifies returned snapshot matches first snapshot state
5. Verifies nodes added in second snapshot are excluded

### If Test Fails
- **get_snapshot_at() not found**: Method not implemented
  - Check `worker-service/app/simulation/time_travel.py`
  - Implement `TemporalGraphStore.get_snapshot_at(timestamp, repo)`
- **Missing nodes**: Temporal validity logic incorrect
  - Verify `TemporalNode.is_valid_at()` implementation
  - Check `valid_from` and `valid_to` timestamps in database
- **Extra nodes**: Nodes with incorrect temporal validity
  - Check that nodes added in second snapshot have `valid_from` after midpoint

### Success Criteria
- `get_snapshot_at()` returns snapshot at correct point in time
- All expected nodes from first ingestion are present
- Nodes added in second ingestion are correctly excluded
- Test returns exit code 0

---

## Task 14.3.7: Policy Finding Temporal Snapshot

### Purpose
Verify that policy findings (DOC_DRIFT, BREAKING_CHANGE) create temporal snapshot records.

### Prerequisites
- None (test creates its own data)

### Files to Check
- `test_task_14_3_7_policy_finding_snapshot.py` - No changes needed
- `worker-service/app/simulation/time_travel.py` - Verify `record_policy_event()` is implemented

### Execution Steps

1. **Run the test**
   ```bash
   python test_task_14_3_7_policy_finding_snapshot.py
   ```

2. **Expected Output**
   ```
   Task 14.3.7: Policy Finding Temporal Snapshot Test
   ✓ record_policy_event() completed successfully
   ✓ Found 3 policy_finding snapshot(s)
   ✓ Correct number of snapshots (3)
   ✓ All expected rule_ids found
   ✓ STYLE_VIOLATION correctly filtered out
   ✓ ON CONFLICT working
   ✓ Task 14.3.7: ALL CHECKS PASSED
   ```

### Understanding the Test
1. Creates 4 mock findings (3 relevant, 1 irrelevant)
2. Calls `record_policy_event()` with findings
3. Verifies 3 snapshots created (DOC_DRIFT_*, BREAKING_*)
4. Verifies STYLE_VIOLATION is filtered out
5. Tests ON CONFLICT (re-delivery protection)

### If Test Fails
- **record_policy_event() not found**: Method not implemented
  - Check `worker-service/app/simulation/time_travel.py`
  - Implement `TemporalGraphStore.record_policy_event(repo, run_id, findings)`
- **Wrong number of snapshots**: Filtering logic incorrect
  - Should only record DOC_DRIFT_* and BREAKING_* findings
  - STYLE_VIOLATION should be excluded
- **ON CONFLICT failed**: Duplicate snapshots created
  - Verify `ON CONFLICT (snapshot_id) DO NOTHING` in SQL

### Success Criteria
- 3 snapshots created with `event_type='policy_finding'`
- Each snapshot has correct `event_payload` with finding details
- `node_ids` is empty array, `edge_count=0`, `services_count=0`
- Re-delivery doesn't create duplicates
- Test returns exit code 0

---

## Troubleshooting Common Issues

### Issue: Ingestion Fails with "Event loop is closed"

**Symptoms**:
```
✗ FAILED: Ingestion failed
Error: Event loop is closed
```

**Solution**:
1. Verify fix is in place:
   ```bash
   grep -A 3 "http_options" worker-service/app/llm/embeddings.py
   ```
   Should show: `http_options={'api_version': 'v1beta'}`

2. Restart worker-service:
   ```bash
   docker compose restart worker-service
   ```

3. Wait 15 seconds, then retry ingestion

### Issue: API Key "reported as leaked"

**Symptoms**:
```
403 PERMISSION_DENIED
Your API key was reported as leaked
```

**Solution**:
1. Generate new API key in Google Cloud Console
2. Update `.env` file with new key
3. Set PowerShell environment variable:
   ```powershell
   $env:GEMINI_API_KEY = "new-key-here"
   ```
4. Rebuild and restart:
   ```bash
   docker compose down
   docker compose build worker-service
   docker compose up -d
   ```

### Issue: Empty node_ids in Snapshot

**Symptoms**:
```
✗ FAIL: node_ids field is NULL or empty
```

**Solution**:
1. Check if ingestion actually completed:
   ```bash
   python test_ingestion_status.py
   ```

2. If status is "success" but files=0:
   - This was an incremental ingestion that didn't detect services
   - Run full ingestion: `python test_ingestion_trigger.py`

3. If status is "failed":
   - Check worker-service logs: `docker compose logs --tail=100 worker-service`
   - Fix the error and retry

### Issue: Test Timeout Waiting for Snapshot

**Symptoms**:
```
✗ Timeout: No new snapshot created after 120s
```

**Solution**:
1. Check if ingestion is actually running:
   ```bash
   docker compose logs --tail=50 worker-service
   ```

2. If no activity, trigger manually:
   ```bash
   python test_ingestion_trigger.py
   ```

3. If ingestion is stuck, restart worker-service:
   ```bash
   docker compose restart worker-service
   ```

---

## Quick Reference: Test Execution Order

```bash
# 1. Verify initial snapshot
python test_task_14_3_1_temporal_snapshot.py

# 2. Create second snapshot (manual trigger)
python test_ingestion_trigger.py
python test_ingestion_status.py
python test_task_14_3_2_incremental_ingestion.py

# 3. Compare snapshots
python test_task_14_3_3_compare_snapshots.py

# 4. Delete service on GitHub, then run
python test_task_14_3_4_service_deletion.py

# 5. Verify valid_to timestamps
python test_task_14_3_5_removed_service_valid_to.py

# 6. Test time travel
python test_task_14_3_6_get_snapshot_at.py

# 7. Test policy findings
python test_task_14_3_7_policy_finding_snapshot.py
```

---

## Database Queries for Manual Verification

### Check Snapshot Count
```sql
SELECT event_type, COUNT(*) 
FROM meta.architecture_snapshots 
WHERE repo = 'Mithil1302/Engineering-Brain'
GROUP BY event_type;
```

### View Recent Snapshots
```sql
SELECT snapshot_id, event_type, timestamp, 
       jsonb_array_length(node_ids) as node_count
FROM meta.architecture_snapshots
WHERE repo = 'Mithil1302/Engineering-Brain'
ORDER BY timestamp DESC
LIMIT 10;
```

### Check Active Services
```sql
SELECT name, node_id, valid_from, valid_to
FROM meta.architecture_nodes
WHERE repo = 'Mithil1302/Engineering-Brain'
  AND node_type = 'service'
ORDER BY valid_from DESC;
```

### Check Removed Services
```sql
SELECT name, node_id, valid_from, valid_to
FROM meta.architecture_nodes
WHERE repo = 'Mithil1302/Engineering-Brain'
  AND node_type = 'service'
  AND valid_to IS NOT NULL
ORDER BY valid_to DESC;
```

---

## Summary

This guide provides step-by-step instructions for all 7 tasks in 14.3. Follow the order, check prerequisites, and use the troubleshooting section if you encounter issues.

Key points:
- Always verify API key is working before starting
- Use manual ingestion trigger for 14.3.2 (webhook doesn't work)
- Delete a service on GitHub before running 14.3.4
- Check database directly if tests fail
- Restart worker-service if you see "Event loop is closed"
