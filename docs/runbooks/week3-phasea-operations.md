# Runbook — Week 3 Phase A Operations Hardening

## Scope
Covers top 3 incident types for emit-retry operations with alerting, triage, replay, and recovery validation.

## Incident 1 — Failure Rate Spike
**Alert signal:** `failure_rate_spike`

### Symptoms
- Increased `dead_letter` jobs in `meta.jobs`
- `failure_rate_pct` elevated in `/policy/admin/emit-retry/metrics`

### Triage
1. Call `/policy/admin/emit-retry/alerts?repo=<repo>&window_minutes=60`.
2. Call `/policy/admin/emit-retry/metrics?repo=<repo>&window_minutes=60`.
3. Inspect recent job errors and dead-letter payloads:
   - `/policy/admin/emit-retry/overview?repo=<repo>&window_hours=24`
   - `/policy/admin/emit-retry/dead-letters?limit=100`

### Recovery
1. Fix producer/downstream failure root cause.
2. Requeue quarantined poison pills via tooling (UI or API).
3. Confirm `failure_rate_spike.triggered == false`.

---

## Incident 2 — Backlog Growth
**Alert signal:** `backlog_growth`

### Symptoms
- `queued + processing` rising
- `oldest_backlog_age_sec` increasing

### Triage
1. Query `/policy/admin/emit-retry/metrics?repo=<repo>&window_minutes=60`.
2. Verify worker health and readiness at `/policy/pipeline/health`.
3. Check Kafka and DB readiness booleans under health response.

### Recovery
1. Unblock dependencies (Kafka, DB, downstream service).
2. Scale worker/reduce producer pressure if needed.
3. Confirm backlog total and age return below thresholds.

---

## Incident 3 — Delivery Failures / Poison Pill
**Alert signal:** `delivery_failures`

### Symptoms
- Rising dead-letter count in time window
- Quarantined poison pills in `meta.poison_pills`

### Triage
1. List dead-letters: `/policy/admin/emit-retry/dead-letters?limit=100`.
2. Inspect failed payload and `error` field.
3. Determine if safe replay is possible.

### Replay Workflow (End-to-End)
1. Requeue: `POST /policy/admin/emit-retry/dead-letters/{poison_id}/requeue` with `{ "reset_attempt": true }`.
2. Verify poison status becomes `requeued`.
3. Verify corresponding retry job returns to `queued/processing/completed`.

### Recovery Validation
- `delivery_failures.triggered == false`
- `failure_rate_spike.triggered == false`
- backlog back to steady state

---

## Tested Drill
Use `scripts/validate-week3-phasea-drill.py` to simulate:
1. failure + backlog conditions
2. alert trigger confirmation
3. poison-pill replay
4. recovery confirmation
