# Task 14.1.2 Fix Summary

## Problem
The ingestion test was failing with 404 errors when polling the status endpoint. The root cause was that the GitHub crawler couldn't authenticate to access the private repository `Mithil1302/Engineering-Brain`.

## Root Cause
The `.env` file had `GITHUB_APP_PRIVATE_KEY_FILE` but the code was looking for `GITHUB_APP_PRIVATE_KEY_PATH`. The docker-compose.yml was correctly configured to mount the private key file to `/run/secrets/github_app.pem` inside the container, but the environment variable name mismatch prevented the crawler from finding it.

## Fix Applied
Added `GITHUB_APP_PRIVATE_KEY_PATH` to `.env`:
```
GITHUB_APP_PRIVATE_KEY_FILE=./eng-brain.2026-03-20.private-key.pem
GITHUB_APP_PRIVATE_KEY_PATH=./eng-brain.2026-03-20.private-key.pem
```

The docker-compose.yml already had the correct configuration:
- Volume mount: `${GITHUB_APP_PRIVATE_KEY_FILE}:/run/secrets/github_app.pem:ro`
- Environment variable: `GITHUB_APP_PRIVATE_KEY_PATH: /run/secrets/github_app.pem`

## Verification
1. Private key file exists: ✓
2. File is mounted in container: ✓ (`/run/secrets/github_app.pem`)
3. File is readable: ✓
4. Worker service restarted: ✓

## Next Steps
Run the test script to verify the fix:
```bash
python test_ingestion_1min.py
```

The test should now:
1. Successfully trigger ingestion (Task 14.1.1)
2. Poll the status endpoint and see the ingestion progress (Task 14.1.2)
3. Eventually show status="success" or status="failed" with error details

## Expected Behavior
- The crawler will now authenticate with GitHub using the App credentials
- It will fetch files from `Mithil1302/Engineering-Brain`
- The ingestion pipeline will process the files
- The status endpoint will return the ingestion progress
- The test will pass when status changes to "success"
