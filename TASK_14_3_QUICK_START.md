# Task 14.3 Quick Start

## TL;DR - Run This

```bash
# 1. Start services
docker-compose up -d postgres
cd worker-service && python -m uvicorn app.main:app --port 8001 &

# 2. Run tests
python test_task14_3_complete.py
```

## What You Need

✓ PostgreSQL running (port 5432)  
✓ Worker service running (port 8001)  
✓ GitHub App credentials in `.env`  
✓ Test repository accessible by your GitHub App  

## What Gets Tested

| Task | What It Does | Duration |
|------|--------------|----------|
| 14.3.1 | First ingestion → verify snapshot created | 1-5 min |
| 14.3.2 | Second ingestion → simulate file change | 1-5 min |
| 14.3.3 | Compare two snapshots → check differences | <1 sec |
| 14.3.4 | Simulate service deletion | <1 sec |
| 14.3.5 | Verify deleted nodes have valid_to set | <1 sec |
| 14.3.6 | Time travel query → get historical state | <1 sec |
| 14.3.7 | Policy finding snapshot → DOC_DRIFT test | <1 sec |

**Total Time**: ~2-10 minutes

## Expected Result

```
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

## Common Issues

### "Worker service is not accessible"
```bash
cd worker-service
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```

### "Ingestion failed: GitHub authentication failed"
Check `.env` has:
- `GITHUB_APP_ID`
- `GITHUB_APP_PRIVATE_KEY`
- `GITHUB_INSTALLATION_ID`

### "services_count is 0"
Your test repo needs at least one service directory with:
- `Dockerfile`, OR
- `package.json`, OR
- `pyproject.toml`, OR
- `go.mod`

## Quick Verification

After tests pass, check the database:

```sql
-- View all snapshots
SELECT event_type, COUNT(*) 
FROM meta.architecture_snapshots 
WHERE repo = 'test-org/test-repo'
GROUP BY event_type;

-- Should show:
-- ingestion      | 2
-- policy_finding | 2
```

## Files Created

- `test_task14_3_complete.py` - Main test script
- `TASK_14_3_COMPLETE_GUIDE.md` - Detailed guide
- `TASK_14_3_QUICK_START.md` - This file

## Next Steps

After all tests pass:
1. Mark tasks 14.3.1-14.3.7 complete in `tasks.md`
2. Move to Task 14.4 (Impact Analyzer Neo4j integration)

## Need Help?

See `TASK_14_3_COMPLETE_GUIDE.md` for:
- Detailed troubleshooting
- Manual verification queries
- CI/CD integration
- Individual test execution
