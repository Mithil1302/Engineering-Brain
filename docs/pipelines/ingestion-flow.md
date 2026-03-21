# Ingestion Flow (Event-Driven)

## High-Level Sequence
1) Webhook/connector receives change (Git/PR, spec, schema, doc, incident) → normalizes payload → produces `repo.events` (idempotency_key, correlation_id).
2) ingestion-service consumes `repo.events`, parses/normalizes into graph mutations and emits to graph-service via gRPC (or internal call).
3) graph-service applies idempotent mutations in Neo4j; emits `graph.updates` to Kafka.
4) analysis-service consumes `graph.updates` (or `repo.events`) and enqueues `analysis.jobs` for drift/impact/embedding refresh.
5) worker/agent-service consumes `analysis.jobs` or `agent.requests` to perform evaluations/LLM tasks.
6) Results surface via PR bot (GitHub App), API, or dashboard.

## Reliability
- Idempotency: keys per event (commit SHA, spec hash, schema hash).
- Ordering: Kafka partitions per repo for `repo.events`; downstream topics mirror partitioning when order is needed.
- Retries: exponential backoff; max attempts configurable; DLQ per topic (e.g., `repo.events.dlq`).
- Poison pills: detect repeated failures, route to DLQ with error metadata.

## Phase 2.1 Hardening (implemented)
- Partition-key strategy hardened:
	- downstream events (`graph.updates`, `analysis.jobs`) are produced with explicit partition keys (`repo_id`/`correlation_id`).
	- ingestion consumer uses strict partition sequencing (`partitionsConsumedConcurrently: 1`) to preserve in-partition order.
- Safe dedupe policy:
	- `meta.processed_events` table tracks processed `event_key` idempotency values.
	- duplicate events are acknowledged and skipped without re-emitting downstream side effects.
- Poison-pill quarantine:
	- `meta.poison_pills` table stores failed payloads and metadata after retry exhaustion.
	- API endpoints:
		- `GET /poison-pills?status=quarantined&limit=50`
		- `POST /poison-pills/:id/requeue`
- Replay ergonomics:
	- `scripts/replay-dlq.ps1` (DLQ replay)
	- `scripts/replay-offset.ps1` (offset/partition-based replay windows)

## DLQ & Replay Operations
- Ingestion service retries failed `repo.events` with exponential backoff (`MAX_PROCESS_RETRIES`, `RETRY_BASE_DELAY_MS`).
- After max retries, failed events are published to `repo.events.dlq` with envelope fields:
	- `source.topic`, `source.partition`, `source.offset`
	- `attempts`, `error`, `payload_raw`, `correlation_id`, `idempotency_key`
- Replay utility:
	- `scripts/replay-dlq.ps1` reads `payload_raw` from DLQ messages and republishes into `repo.events`.
	- Supports `-DryRun` for inspection-only mode.

## Backpressure
- Consumer concurrency tuned per topic; bounded queues; visibility via lag metrics.

## Security
- Webhook signature verification; Kafka ACLs per topic; service-to-service auth on gRPC.

## Open Items
- Finalize gRPC contracts between ingestion-service and graph-service.
- Define DLQ processing policy (alerting, manual replay commands).
