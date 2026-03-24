# Week 3 Phase A Alert Rules (Operations Hardening)

This document defines the runtime alert signals for the emit-retry pipeline.

## Alert 1: Failure Rate Spike
- **Signal:** `failure_rate_spike`
- **Source:** `GET /policy/admin/emit-retry/alerts`
- **Condition:**
  - `failure_rate_pct >= POLICY_ALERT_FAILURE_RATE_THRESHOLD_PCT`
  - and at least 3 terminal events in window (`completed + dead_letter >= 3`)
- **Default threshold:** `20%`
- **Severity:** high

## Alert 2: Backlog Growth
- **Signal:** `backlog_growth`
- **Source:** `GET /policy/admin/emit-retry/alerts`
- **Condition (either):**
  - `backlog_delta >= POLICY_ALERT_BACKLOG_GROWTH_DELTA`
  - OR (`backlog_total >= POLICY_ALERT_BACKLOG_THRESHOLD` AND `oldest_backlog_age_sec >= POLICY_ALERT_BACKLOG_OLDEST_AGE_SEC`)
- **Default thresholds:**
  - backlog total: `20`
  - backlog delta: `10`
  - oldest age: `300 sec`
- **Severity:** medium/high

## Alert 3: Delivery Failures
- **Signal:** `delivery_failures`
- **Source:** `GET /policy/admin/emit-retry/alerts`
- **Condition:**
  - `delivery_failures_window >= POLICY_ALERT_DELIVERY_FAILURES_THRESHOLD`
- **Default threshold:** `3`
- **Severity:** high

## Operator Checks
- Metrics snapshot endpoint: `GET /policy/admin/emit-retry/metrics`
- Alerts endpoint: `GET /policy/admin/emit-retry/alerts`
- Replay endpoint: `POST /policy/admin/emit-retry/dead-letters/{poison_id}/requeue`
