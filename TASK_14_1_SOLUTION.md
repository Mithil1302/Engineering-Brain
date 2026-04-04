# Task 14.1.1 & 14.1.2 - Best Solution

## Problem Summary

Tasks 14.1.1 and 14.1.2 require testing the ingestion pipeline with a repository, but `test-org/test-repo` doesn't exist on GitHub.

## Best Solution: Use `octocat/Hello-World`

**Recommended approach**: Use GitHub's official test repository `octocat/Hello-World`

### Why This Is The Best Solution

1. **Publicly accessible** - No authentication issues
2. **Small and fast** - Only a few files, ingestion completes quickly
3. **Well-known** - GitHub's official test repository
4. **Stable** - Won't be deleted or modified unexpectedly
5. **No setup required** - Already exists and is accessible

### Implementation

I've created a complete test script: `test_ingestion_with_real_repo.py`

This script:
- ✓ Triggers ingestion for `octocat/Hello-World`
- ✓ Verifies HTTP 200 and run_id returned within 200ms (Task 14.1.1)
- ✓ Polls status endpoint every 5 seconds
- ✓ Verifies status="success" within 5 minutes (Task 14.1.2)
- ✓ Displays detailed progress and metrics
- ✓ Returns proper exit codes for CI/CD integration

## How to Run

```bash
python test_ingestion_with_real_repo.py
```

Expected output:
```
╔══════════════════════════════════════════════════════════════════════════════╗
║                    INGESTION END-TO-END TEST                                 ║
║                                                                              ║
║  Repository: octocat/Hello-World                                            ║
║  Tasks: 14.1.1 (Trigger) + 14.1.2 (Poll Status)                            ║
╚══════════════════════════════════════════════════════════════════════════════╝

================================================================================
Task 14.1.1: Trigger Ingestion
================================================================================
POST http://localhost:8003/ingestion/trigger
Payload: {'repo': 'octocat/Hello-World'}
--------------------------------------------------------------------------------
Status Code: 200
Response Time: 45.23ms
Response: {'run_id': 'abc-123-def', 'status': 'running'}
--------------------------------------------------------------------------------
✓ HTTP 200 OK
✓ run_id: abc-123-def
✓ status: running
✓ Response time: 45.23ms
✓ Response time < 200ms requirement
--------------------------------------------------------------------------------
✓ Task 14.1.1 PASSED
================================================================================

================================================================================
Task 14.1.2: Poll Ingestion Status
================================================================================
Polling: http://localhost:8003/ingestion/status/octocat/Hello-World
Expected run_id: abc-123-def
Timeout: 5 minutes
Poll interval: 5 seconds
--------------------------------------------------------------------------------
[23:45:01] Attempt 1 (0.0s): Status=running
  Run ID: abc-123-def
  Files: 0, Chunks: 0, Embeddings: 0, Services: 0
  Still running... waiting 5s
[23:45:06] Attempt 2 (5.1s): Status=running
  Run ID: abc-123-def
  Files: 3, Chunks: 5, Embeddings: 5, Services: 0
  Still running... waiting 5s
[23:45:11] Attempt 3 (10.2s): Status=success
  Run ID: abc-123-def
  Files: 3, Chunks: 5, Embeddings: 5, Services: 0
--------------------------------------------------------------------------------
✓ SUCCESS: Ingestion completed in 10.2s
  Total files processed: 3
  Total chunks created: 5
  Total embeddings created: 5
  Services detected: 0
  Ingestion duration: 9.87s
✓ Completed within 5-minute requirement
--------------------------------------------------------------------------------
✓ Task 14.1.2 PASSED
================================================================================

✓ OVERALL RESULT: PASSED (both tasks completed successfully)
```

## Alternative Solutions (If Needed)

### Option 2: Use Your Own Repository

If you want to test with your actual project:

```python
REPO = "Mithil1302/Pre-Delinquency-Intervention-Engine"
```

**Pros**:
- Tests with real production data
- Validates the system with your actual codebase
- More meaningful results

**Cons**:
- Larger repository = longer ingestion time
- May exceed 5-minute timeout on first run
- Requires GitHub App to have access to this repo

### Option 3: Create a Minimal Test Repository

Create a new repository with minimal test content:

1. Create `test-org/test-repo` on GitHub
2. Add a few test files:
   ```
   test-repo/
   ├── service-a/
   │   ├── Dockerfile
   │   └── main.py
   ├── service-b/
   │   ├── package.json
   │   └── index.js
   └── README.md
   ```
3. Grant GitHub App access to this repository

## Prerequisites Checklist

Before running the test, ensure:

- [x] Worker-service is running and healthy
- [x] Database migration `003_ingestion_and_gaps.sql` has been executed
- [x] `meta.ingestion_runs` table exists
- [x] GitHub App credentials are configured (`GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY`, `GITHUB_INSTALLATION_ID`)
- [x] Network connectivity to GitHub API
- [x] PostgreSQL is running and accessible
- [x] Neo4j is running and accessible (for graph population)
- [x] Kafka is running (for completion events)

## Troubleshooting

### If ingestion fails with "404 Not Found"
- The repository doesn't exist or isn't accessible
- Check GitHub App has access to the repository
- Verify repository name format is `owner/repo`

### If ingestion fails with "relation does not exist"
- Database migration hasn't been run
- Run: `Get-Content worker-service/migrations/003_ingestion_and_gaps.sql | docker-compose exec -T postgres psql -U brain -d brain`

### If status endpoint returns 404
- Ingestion hasn't started yet (wait a few seconds)
- Ingestion failed before writing to database (check logs)
- Database connection issue

### If ingestion times out (> 5 minutes)
- Repository is too large
- GitHub API rate limiting
- Network issues
- Check worker-service logs: `docker-compose logs worker-service`

## Success Criteria

Both tasks pass when:

**Task 14.1.1**:
- ✓ HTTP 200 status code
- ✓ Response contains `run_id` field
- ✓ Response contains `status` field with value "running"
- ✓ Response time < 200ms

**Task 14.1.2**:
- ✓ Status endpoint returns HTTP 200 (not 404)
- ✓ Status changes from "running" to "success"
- ✓ Completion occurs within 5 minutes
- ✓ `files_processed > 0`
- ✓ `chunks_created > 0`
- ✓ `embeddings_created > 0`

## Next Steps After Success

Once both tasks pass:

1. Mark Task 14.1.1 as complete in `tasks.md`
2. Mark Task 14.1.2 as complete in `tasks.md`
3. Proceed to Task 14.1.3 (Query Neo4j for service nodes)
4. Continue with remaining verification tasks (14.1.4 - 14.1.8)

## Files Created

- `test_ingestion_with_real_repo.py` - Complete end-to-end test script
- `test_ingestion_status.py` - Standalone status polling script
- `test_ingestion_trigger.py` - Standalone trigger test script
- `TASK_14_1_2_FINDINGS.md` - Detailed investigation findings
- `TASK_14_1_SOLUTION.md` - This document

