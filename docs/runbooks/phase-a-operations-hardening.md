# Week 3 Phase A Operations Hardening Runbook

## Scope
Production observability and failure handling for emit-retry and delivery paths.

## Incident 1: Failure Rate Spike
**Signal**
- `/policy/admin/emit-retry/alerts` → `alerts.failure_rate_spike.triggered = true`

**Immediate actions**
1. Open `/policy/admin/emit-retry/metrics?window_minutes=60` and capture `failure_rate_pct`.
2. Open `/policy/admin/emit-retry/overview?window_hours=24` and inspect `recent_job_errors`.
3. Validate broker and worker health (`/policy/pipeline/readiness`).

**Mitigation**
- Requeue quarantined poison-pill entries one-by-one after root-cause validation.
- If failures continue, pause upstream emission and isolate failing emit type from `recent_job_errors`.

**Exit criteria**
- `failure_rate_spike.triggered = false`
- `delivery_failures.triggered = false`

---

## Incident 2: Backlog Growth
**Signal**
- `/policy/admin/emit-retry/alerts` → `alerts.backlog_growth.triggered = true`

**Immediate actions**
1. Open `/policy/admin/emit-retry/metrics` and review `backlog.total`, `backlog.delta`, `backlog.oldest_age_sec`.
2. Verify worker loop is healthy from `/policy/pipeline/readiness`.
3. Verify Kafka and Postgres availability.

**Mitigation**
- Scale worker replicas (if available) or increase batch size temporarily.
- Prioritize stuck queued jobs by replaying dead-letter blockers first.

**Exit criteria**
- backlog delta normalizes (`backlog_growth.triggered = false`)
- oldest backlog age returns below threshold

---

## Incident 3: Delivery Failures / Poison-Pill Triage
**Signal**
- `/policy/admin/emit-retry/alerts` → `alerts.delivery_failures.triggered = true`
- Dead-letter list contains quarantined records.

**Immediate actions**
1. Open `/policy/admin/emit-retry/dead-letters?limit=50`.
2. Identify poison pill by `error`, `idempotency_key`, `attempts`.
3. Capture evidence (payload + error + timestamps).

**Replay workflow**
1. Requeue via `/policy/admin/emit-retry/dead-letters/{poison_id}/requeue`.
2. Verify poison pill status transitions to `requeued`.
3. Confirm job transitions out of `queued/processing` and alert clears.

**Exit criteria**
- Poison pill replayed end-to-end successfully
- `delivery_failures.triggered = false`

---

## Drill checklist (single session)
1. Simulate failures/backlog condition.
2. Confirm all 3 alerts trigger when thresholds are crossed.
3. Replay poison-pill item.
4. Recover and confirm all 3 alerts return to non-triggered state.

Validation script: `scripts/validate-week3-phasea-drill.py`
