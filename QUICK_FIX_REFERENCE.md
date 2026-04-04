# QUICK FIX REFERENCE - Copy & Paste Ready

## 🔴 FIX #1: Add GEMINI_API_KEY to docker-compose.yml

**File:** `docker-compose.yml`
**Location:** Line ~275 (in worker-service → environment section)

**Add this line:**
```yaml
    GEMINI_API_KEY: ${GEMINI_API_KEY}
```

**Full context (add the marked line):**
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

## 🔴 FIX #2: Add GitHub Private Key File Mount

**File:** `docker-compose.yml`
**Location:** In worker-service section, after environment, before ports

**Add these lines:**
```yaml
    volumes:
      - ${GITHUB_APP_PRIVATE_KEY_FILE:-./eng-brain.2026-03-20.private-key.pem}:/run/secrets/github_app.pem:ro
```

**And add this to environment section:**
```yaml
      GITHUB_APP_PRIVATE_KEY_PATH: /run/secrets/github_app.pem
```

**Full context:**
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
      # ... all other environment vars ...
      GEMINI_API_KEY: ${GEMINI_API_KEY}
      GITHUB_APP_PRIVATE_KEY_PATH: /run/secrets/github_app.pem  # <--- ADD THIS
    volumes:  # <--- ADD THIS ENTIRE SECTION
      - ${GITHUB_APP_PRIVATE_KEY_FILE:-./eng-brain.2026-03-20.private-key.pem}:/run/secrets/github_app.pem:ro
    ports:
      - "8003:8003"
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8003/healthz').status==200 else 1)\""]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 20s
```

---

## 🔴 FIX #3: Update dependencies.py to Read Private Key from File

**File:** `worker-service/app/dependencies.py`
**Location:** Around line 88-95 (in get_ingestion_pipeline function)

**Replace this code:**
```python
        crawler = GitHubRepoCrawler(
            app_id=os.getenv("GITHUB_APP_ID", ""),
            private_key=os.getenv("GITHUB_APP_PRIVATE_KEY", ""),
            installation_id=os.getenv("GITHUB_INSTALLATION_ID", ""),
            max_concurrent=int(os.getenv("INGESTION_MAX_CONCURRENT_FETCHES", "10")),
            max_file_size_kb=int(os.getenv("INGESTION_MAX_FILE_SIZE_KB", "500")),
        )
```

**With this code:**
```python
        # Read private key from file (with fallback to env var)
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

---

## ✅ After Making Changes

**Run these commands:**

```bash
# Rebuild worker-service
docker-compose build worker-service

# Restart all services
docker-compose down
docker-compose up -d

# Wait 30 seconds for services to start
sleep 30

# Check if worker-service is running
docker-compose ps worker-service

# Check logs for errors
docker-compose logs worker-service --tail 50

# Test the endpoint
python test_ingestion_trigger.py
```

---

## 📝 Summary

**Files to Edit:** 2
1. `docker-compose.yml` - Add 3 lines
2. `worker-service/app/dependencies.py` - Replace 6 lines with 13 lines

**Time Required:** 5 minutes

**Result:** worker-service will start successfully and ingestion endpoint will work.
