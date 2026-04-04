# REQUIRED CONFIGURATION - CRITICAL SETUP CHECKLIST

## ⚠️ CRITICAL: Missing Configuration Items

This document lists ALL API keys, secrets, tokens, and endpoints that MUST be configured for the system to work.

---

## 1. GITHUB APP CREDENTIALS (CRITICAL - REQUIRED)

### Location: `.env` file

These are **ALREADY CONFIGURED** in your `.env` file:

```bash
GITHUB_APP_ID=3141804
GITHUB_INSTALLATION_ID=117795165
GITHUB_WEBHOOK_SECRET=Mithil@1302
GITHUB_APP_PRIVATE_KEY_FILE=./eng-brain.2026-03-20.private-key.pem
```

### ⚠️ MISSING IN DOCKER-COMPOSE:

The `worker-service` in `docker-compose.yml` expects `GITHUB_APP_PRIVATE_KEY` as an **environment variable** (the actual key content), but you're providing it as a **file path**.

**YOU NEED TO ADD THIS TO `.env`:**

```bash
# Add the ACTUAL private key content (multi-line)
GITHUB_APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----
[YOUR FULL PRIVATE KEY CONTENT HERE - COPY FROM eng-brain.2026-03-20.private-key.pem]
-----END RSA PRIVATE KEY-----"
```

**OR** update `docker-compose.yml` worker-service to mount the file like agent-service does:

```yaml
worker-service:
  volumes:
    - ${GITHUB_APP_PRIVATE_KEY_FILE:-./eng-brain.2026-03-20.private-key.pem}:/run/secrets/github_app.pem:ro
  environment:
    GITHUB_APP_PRIVATE_KEY_PATH: /run/secrets/github_app.pem
```

---

## 2. GEMINI API KEY (CRITICAL - ALREADY CONFIGURED)

### Location: `.env` file

**STATUS: ✅ CONFIGURED**

```bash
GEMINI_API_KEY=your_gemini_api_key_here
```

### ⚠️ MISSING IN DOCKER-COMPOSE:

The `worker-service` in `docker-compose.yml` does NOT have `GEMINI_API_KEY` in its environment variables!

**YOU MUST ADD THIS TO `docker-compose.yml` under `worker-service` → `environment`:**

```yaml
worker-service:
  environment:
    # ... existing vars ...
    GEMINI_API_KEY: ${GEMINI_API_KEY}
```

---

## 3. SLACK CREDENTIALS (OPTIONAL - Currently Empty)

### Location: `.env` file

**STATUS: ⚠️ NOT CONFIGURED (Optional feature)**

If you want Slack integration to work, add these to `.env`:

```bash
SLACK_SIGNING_SECRET=your_slack_signing_secret_here
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token-here
```

**Current Status:** These are empty in docker-compose, so Slack adapter will log errors but won't crash the service.

---

## 4. DATABASE CREDENTIALS (CONFIGURED)

### Location: `.env` file

**STATUS: ✅ CONFIGURED**

```bash
POSTGRES_USER=brain
POSTGRES_PASSWORD=brain
POSTGRES_DB=brain
NEO4J_USER=neo4j
NEO4J_PASSWORD=testtest
```

These are correctly passed to docker-compose.

---

## 5. KAFKA CONFIGURATION (AUTO-CONFIGURED)

**STATUS: ✅ AUTO-CONFIGURED**

Kafka brokers are automatically set to `kafka:9092` in docker-compose. No action needed.

---

## 6. GRAPH SERVICE URL (AUTO-CONFIGURED)

**STATUS: ✅ AUTO-CONFIGURED**

Default: `graph-service:50051` - correctly configured in docker-compose.

---

## 7. SECURITY TOKENS (CONFIGURED)

### Location: `.env` file

**STATUS: ✅ CONFIGURED**

```bash
GITHUB_BRIDGE_ADMIN_TOKEN=MITHILPATEL
AUTH_CONTEXT_SIGNING_KEY=MITHILPATEL
POLICY_ADMIN_TOKEN=CHANGE_ME_WEEK1_ADMIN_TOKEN
TENANT_METADATA_ENCRYPTION_KEY=sVgkQX2XDFmBNncSEj1d_EurKL29e3WeyIcqZnUFxXI=
```

⚠️ **SECURITY WARNING:** These should be changed to strong random values in production!

---

## 8. OPENTELEMETRY ENDPOINT (OPTIONAL)

**STATUS: ⚠️ COMMENTED OUT (Optional)**

If you want observability/tracing, uncomment in `.env`:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://host.docker.internal:4318
```

Currently commented out, so telemetry will fail silently (non-critical).

---

## IMMEDIATE ACTION REQUIRED

### 🔴 CRITICAL FIX #1: Add GEMINI_API_KEY to worker-service

**File:** `docker-compose.yml`

**Line:** Under `worker-service` → `environment`, add:

```yaml
GEMINI_API_KEY: ${GEMINI_API_KEY}
```

### 🔴 CRITICAL FIX #2: Fix GitHub Private Key for worker-service

**Option A (Recommended):** Mount the file like agent-service does

**File:** `docker-compose.yml`

Add under `worker-service`:

```yaml
volumes:
  - ${GITHUB_APP_PRIVATE_KEY_FILE:-./eng-brain.2026-03-20.private-key.pem}:/run/secrets/github_app.pem:ro
environment:
  GITHUB_APP_PRIVATE_KEY_PATH: /run/secrets/github_app.pem
```

**AND** update `worker-service/app/dependencies.py` line 91:

```python
# Change from:
private_key=os.getenv("GITHUB_APP_PRIVATE_KEY", ""),

# To:
private_key_path=os.getenv("GITHUB_APP_PRIVATE_KEY_PATH", ""),
# Then read the file content in the code
```

**Option B:** Add the full private key content to `.env`

Copy the entire content of `eng-brain.2026-03-20.private-key.pem` and add to `.env`:

```bash
GITHUB_APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----
[PASTE FULL KEY HERE]
-----END RSA PRIVATE KEY-----"
```

---

## VALIDATION CHECKLIST

After making the fixes above, verify:

- [ ] `GEMINI_API_KEY` is in `.env` ✅ (Already there)
- [ ] `GEMINI_API_KEY` is in `docker-compose.yml` worker-service environment ❌ (NEEDS TO BE ADDED)
- [ ] `GITHUB_APP_PRIVATE_KEY` or `GITHUB_APP_PRIVATE_KEY_PATH` is properly configured ❌ (NEEDS FIX)
- [ ] GitHub App credentials are in `.env` ✅ (Already there)
- [ ] Database credentials are in `.env` ✅ (Already there)
- [ ] Private key file `eng-brain.2026-03-20.private-key.pem` exists in root directory ✅ (Confirmed)

---

## FILES THAT NEED MODIFICATION

### 1. `docker-compose.yml`

Add to `worker-service` → `environment`:

```yaml
GEMINI_API_KEY: ${GEMINI_API_KEY}
```

Add to `worker-service` → `volumes`:

```yaml
- ${GITHUB_APP_PRIVATE_KEY_FILE:-./eng-brain.2026-03-20.private-key.pem}:/run/secrets/github_app.pem:ro
```

Add to `worker-service` → `environment`:

```yaml
GITHUB_APP_PRIVATE_KEY_PATH: /run/secrets/github_app.pem
```

### 2. `worker-service/app/dependencies.py`

Update the `GitHubRepoCrawler` initialization (around line 90-92):

```python
# Current code reads from environment variable:
private_key=os.getenv("GITHUB_APP_PRIVATE_KEY", ""),

# Change to read from file:
private_key_path = os.getenv("GITHUB_APP_PRIVATE_KEY_PATH", "")
with open(private_key_path, 'r') as f:
    private_key = f.read()

crawler = GitHubRepoCrawler(
    app_id=os.getenv("GITHUB_APP_ID", ""),
    private_key=private_key,  # Now contains the file content
    installation_id=os.getenv("GITHUB_INSTALLATION_ID", ""),
    max_concurrent=int(os.getenv("INGESTION_MAX_CONCURRENT_FETCHES", "10")),
    max_file_size_kb=int(os.getenv("INGESTION_MAX_FILE_SIZE_KB", "500")),
)
```

---

## SUMMARY

**Total Critical Issues: 2**

1. ❌ `GEMINI_API_KEY` missing from worker-service docker-compose environment
2. ❌ `GITHUB_APP_PRIVATE_KEY` not properly configured for worker-service

**Total Optional Issues: 2**

1. ⚠️ Slack credentials not configured (feature won't work but won't crash)
2. ⚠️ OpenTelemetry endpoint commented out (no observability but won't crash)

**Fix these 2 critical issues and your system should start working!**
