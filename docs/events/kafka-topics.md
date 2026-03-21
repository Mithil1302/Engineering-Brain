# Kafka Topics & Event Model

## Topics
- **repo.events**: commit/PR/webhook-derived repo changes.
- **repo.events.dlq**: dead-letter queue for repo.events messages that fail processing after retry budget.
- **graph.updates**: emitted after graph mutations; can be consumed for projections/analytics.
- **analysis.jobs**: requests for drift/impact analysis, embedding refresh jobs.
- **pr.checks**: normalized PR policy check outputs with markdown comments, citations, annotations, and suggested patches.
- **agent.requests**: LLM/agent tasks with context references.
- **ci.events**: CI-related signals, test results, build status.

## General Conventions
- Serialization: JSON (optionally Avro later) with schema version field `schema_version`.
- Idempotency key per event type; correlation_id for tracing; produced_at timestamp.
- Partitioning: per-repo (hash of repo id) to preserve order for repo.events; corresponding partitions for downstream topics when order matters.
- DLQ: per topic (e.g., repo.events.dlq). Retry with exponential backoff; max attempts configurable.

## Producers/Consumers (initial)
- **repo.events**: produced by ingestion webhook listener; consumed by ingestion-service.
- **repo.events.dlq**: produced by ingestion-service on terminal processing failure; consumed by replay/ops workflows.
- **graph.updates**: produced by graph-service; consumed by analysis-service, projections.
- **analysis.jobs**: produced by ingestion-service or PR triggers; consumed by analysis/worker-service.
- **pr.checks**: produced by worker-service policy pipeline; consumed by PR bot/checks bridge for create/update comment actions.
- **agent.requests**: produced by analysis/PR bot; consumed by agent-service.
- **ci.events**: produced by CI bridge; consumed by analysis-service for test linkage.

## Retry & DLQ policy (ingestion-service)
- Retries use exponential backoff (`RETRY_BASE_DELAY_MS`, default 500 ms) for `MAX_PROCESS_RETRIES` attempts (default 3).
- If all retries fail, ingestion-service publishes a DLQ envelope with source metadata, error, and `payload_raw` to `repo.events.dlq`.
- Replay utility: `scripts/replay-dlq.ps1` re-publishes `payload_raw` into `repo.events`.

## Payload Schemas (summaries)
- See `docs/events/schemas/*.json` for detailed fields. Initial schema stubs to be added.

## Security/ACLs
- Auth required for producers/consumers; least privilege per topic.
- Size limits: large payloads (e.g., full specs) should be stored externally and referenced by URI where feasible.
