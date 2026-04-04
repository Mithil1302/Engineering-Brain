# 🔴 CRITICAL FIXES NEEDED - DO THESE NOW

## Issue Summary

Your worker-service container is failing to start because of **2 CRITICAL missing environment variables**.

---

## FIX #1: Add GEMINI_API_KEY to worker-service

### Problem
The code in `worker-service/app/llm/__init__.py` tries to read `GEMINI_API_KEY` from environment, but it's NOT in the docker-compose.yml for worker-service.

### Solution

**Edit `docker-compose.yml`**

Find the `worker-service` section (around line 243) and add `GEMINI_API_KEY` to the environment:

```yaml
worker-service:
  build: ./worker-service
  depends_on:
    kafka:
      condition: service_healthy
    kafka-init:
      condition: service_completed_successfully
    graph-service:
      condition: service_healthy
  environment:
    PORT: 8003
    OTEL_EXPORTER_OTLP_ENDPOINT: ${OTEL_EXPORTER_OTLP_ENDPOINT:-http://host.docker.internal:4318}
    POLICY_PIPELINE_ENABLED: "true"
    POLICY_INPUT_TOPIC: repo.events
    POLICY_OUTPUT_TOPIC: pr.checks
    POLICY_CONSUMER_GROUP: worker-policy-checks-v1
    POLICY_RULE_SET: rules-v1
    POLICY_DEFAULT_SERVICE_ID: unknown-service
    KAFKA_BROKERS: kafka:9092
    POSTGRES_HOST: postgres
    POSTGRES_PORT: 5432
    POSTGRES_USER: ${POSTGRES_USER:-brain}
    POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-brain}
    POSTGRES_DB: ${POSTGRES_DB:-brain}
    GITHUB_APP_ID: ${GITHUB_APP_ID:-}
    GITHUB_APP_PRIVATE_KEY: ${GITHUB_APP_PRIVATE_KEY:-}
    GITHUB_INSTALLATION_ID: ${GITHUB_INSTALLATION_ID:-}
    INGESTION_MAX_CONCURRENT_FETCHES: ${INGESTION_MAX_CONCURRENT_FETCHES:-10}
    INGESTION_MAX_FILE_SIZE_KB: ${INGESTION_MAX_FILE_SIZE_KB:-500}
    INGESTION_BATCH_SIZE: ${INGESTION_BATCH_SIZE:-50}
    GRAPH_SERVICE_URL: ${GRAPH_SERVICE_URL:-graph-service:50051}
    SLACK_SIGNING_SECRET: ${SLACK_SIGNING_SECRET:-}
    SLACK_BOT_TOKEN: ${SLACK_BOT_TOKEN:-}
    GEMINI_API_KEY: ${GEMINI_API_KEY}  # <--- ADD THIS LINE
```

---

## FIX #2: Fix GitHub Private Key Configuration

### Problem
The code expects `GITHUB_APP_PRIVATE_KEY` as a string in environment variable, but you have it as a file. The agent-service correctly mounts the file, but worker-service doesn't.

### Solution Option A (RECOMMENDED - Consistent with agent-service)

**Step 1: Edit `docker-compose.yml`**

Add volumes section to worker-service (after the environment section):

```yaml
worker-service:
  build: ./worker-service
  # ... existing config ...
  environment:
    # ... all existing environment vars ...
    GITHUB_APP_PRIVATE_KEY_PATH: /run/secrets/github_app.pem  # <--- ADD THIS
  volumes:  # <--- ADD THIS ENTIRE SECTION
    - ${GITHUB_APP_PRIVATE_KEY_FILE:-./eng-brain.2026-03-20.private-key.pem}:/run/secrets/github_app.pem:ro
  ports:
    - "8003:8003"
```

**Step 2: Edit `worker-service/app/dependencies.py`**

Find the GitHubRepoCrawler initialization (around line 90-95) and change it:

```python
# BEFORE (current code):
crawler = GitHubRepoCrawler(
    app_id=os.getenv("GITHUB_APP_ID", ""),
    private_key=os.getenv("GITHUB_APP_PRIVATE_KEY", ""),
    installation_id=os.getenv("GITHUB_INSTALLATION_ID", ""),
    max_concurrent=int(os.getenv("INGESTION_MAX_CONCURRENT_FETCHES", "10")),
    max_file_size_kb=int(os.getenv("INGESTION_MAX_FILE_SIZE_KB", "500")),
)

# AFTER (new code):
# Read private key from file
private_key_path = os.getenv("GITHUB_APP_PRIVATE_KEY_PATH", "")
if private_key_path and os.path.exists(private_key_path):
    with open(private_key_path, 'r') as f:
        private_key = f.read()
else:
    # Fallback to environment variable
    private_key = os.getenv("GITHUB_APP_PRIVATE_KEY", "")

crawler = GitHubRepoCrawler(
    app_id=os.getenv("GITHUB_APP_ID", ""),
    private_key=private_key,
    installation_id=os.getenv("GITHUB_INSTALLATION_ID", ""),
    max_concurrent=int(os.getenv("INGESTION_MAX_CONCURRENT_FETCHES", "10")),
    max_file_size_kb=int(os.getenv("INGESTION_MAX_FILE_SIZE_KB", "500")),
)
```

### Solution Option B (Quick but less secure)

Add the full private key content to `.env` file:

```bash
# Copy the entire content of eng-brain.2026-03-20.private-key.pem
GITHUB_APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----
[PASTE YOUR FULL PRIVATE KEY HERE - ALL LINES]
-----END RSA PRIVATE KEY-----"
```

⚠️ **Warning:** This puts your private key in the .env file which is less secure. Option A is better.

---

## After Making These Changes

1. **Rebuild the worker-service image:**
   ```bash
   docker-compose build worker-service
   ```

2. **Restart all services:**
   ```bash
   docker-compose down
   docker-compose up -d
   ```

3. **Check if worker-service starts successfully:**
   ```bash
   docker-compose ps worker-service
   docker-compose logs worker-service --tail 50
   ```

4. **Test the ingestion endpoint:**
   ```bash
   python test_ingestion_trigger.py
   ```

---

## Verification Checklist

After making the fixes:

- [ ] Added `GEMINI_API_KEY: ${GEMINI_API_KEY}` to worker-service environment in docker-compose.yml
- [ ] Added `GITHUB_APP_PRIVATE_KEY_PATH` and volumes to worker-service in docker-compose.yml
- [ ] Updated `worker-service/app/dependencies.py` to read private key from file
- [ ] Rebuilt worker-service: `docker-compose build worker-service`
- [ ] Restarted services: `docker-compose up -d`
- [ ] Verified worker-service is running: `docker ps | grep worker-service`
- [ ] Checked logs for errors: `docker-compose logs worker-service --tail 50`
- [ ] Tested endpoint: `python test_ingestion_trigger.py`

---

## Expected Result

After these fixes, you should see:

```
Testing: POST http://localhost:8003/ingestion/trigger
Payload: {
  "repo": "test-org/test-repo"
}
------------------------------------------------------------
Status Code: 200
Response Time: XX.XXms
Response Body: {
  "run_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "status": "running"
}
------------------------------------------------------------
✓ HTTP 200 OK
✓ run_id present: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
✓ status present: running
✓ Response time XX.XXms < 200ms
------------------------------------------------------------
✓ Task 14.1.1 PASSED
```

---

## If You Still Have Issues

Check these:

1. **Database migration not run:**
   ```bash
   docker-compose exec worker-service python -c "import psycopg2; conn = psycopg2.connect(host='postgres', user='brain', password='brain', dbname='brain'); cur = conn.cursor(); cur.execute('SELECT * FROM meta.ingestion_runs LIMIT 1'); print('Table exists')"
   ```

2. **Kafka not ready:**
   ```bash
   docker-compose ps kafka
   ```

3. **Neo4j not ready:**
   ```bash
   docker-compose ps neo4j
   ```

4. **Check full logs:**
   ```bash
   docker-compose logs worker-service | grep -i error
   ```
