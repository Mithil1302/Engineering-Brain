# Execution Sequencing (Phases)

## Phase 1: Foundation
- Provision Kafka, Neo4j, Qdrant, Postgres; create topics.
- Service scaffolds (api-gateway, ingestion, graph, agent, worker); common gRPC IDL; REST surface stub.
- GitHub App skeleton with webhook handling.
- Basic observability wiring (logging/tracing/metrics stubs).
	- STATUS: infra compose + service scaffolds created with health endpoints and Dockerfiles.
	- Mesh check endpoint added in api-gateway to verify Kafka/Neo4j/Qdrant/Postgres and peer services reachability.
	- Next: generate gRPC stubs (Node/Python) from proto and wire a health RPC.
	- STATUS: HealthService RPC added; graph-service serves gRPC health; api-gateway calls it in /mesh. Proto tooling docs added. Python + Node stubs generated and committed (Node generated via space-free temp path due Windows path limitation).
	- OTel scaffolds added to services (deps + init hooks); exporter endpoint configurable via env.
	- Kafka topic bootstrap script wired via kafka-init service; Postgres bootstrap SQL wired via docker-entrypoint init mount.
	- Startup hardening completed: compose healthchecks + condition-based dependencies added; deterministic smoke script (`scripts/smoke.ps1`) validates health, mesh, Kafka topics, and Postgres bootstrap tables.

## Phase 2: Graph & Ingestion
- Implement graph schema, constraints, and helper queries.
- Implement ingestion-service normalization; graph-service mutations; emit graph.updates.
- DLQ/retry/backoff; ordering per repo partitions.
	- STATUS: Implemented advanced ingestion loop (`repo.events` consumer) with gRPC mutation dispatch to GraphService and downstream fan-out to `graph.updates` + `analysis.jobs`.
	- STATUS: GraphService now validates mutation envelopes, persists idempotent mutation batches/records in Neo4j, and exposes readiness via gRPC Health + `/healthz`.
	- STATUS: Verified end-to-end by publishing realistic `repo.events` payloads and confirming produced topic events + Neo4j persisted counts.
	- STATUS: Added DLQ retry pipeline (`repo.events.dlq`) with replay utility (`scripts/replay-dlq.ps1`) for operational recovery.
	- STATUS: Phase 2.1 hardening done: DB-backed dedupe policy, partition-key ordering strategy, poison-pill quarantine APIs, and offset replay tooling (`scripts/replay-offset.ps1`).
	- STATUS: Added pro-level resiliency in ingestion: exponential retry/backoff, terminal DLQ handoff to `repo.events.dlq`, and replay utility (`scripts/replay-dlq.ps1`).

## Phase 3: Policies & PR Checks
- Implement breaking-change/doc-drift/missing-owner rules; impact traversal.
- PR bot check + comment with citations; suggested patches for docs/config.
	- STATUS: Policy engine implemented in worker-service with breaking-change, doc-drift, missing-owner, and impact propagation evaluators.
	- STATUS: PR check markdown/comment payload generation with citations and suggested patches implemented.
	- STATUS: Event-driven PR checks pipeline wired: consumes `repo.events`, emits `pr.checks`, persists run history, and applies anti-spam dedupe/update semantics.

## Phase 4: Retrieval & Agents
- Chunking + embeddings pipeline to Qdrant; metadata in Postgres.
- Hybrid query path (Qdrant → Neo4j expansion → Gemini reasoning).
- Agents (Impact, Architecture, Doc, Self-healing in suggest-only).

## Phase 5: Health & Onboarding
- Health score computation; onboarding briefs generation.

## Phase 6: Hardening
- Load/chaos tests; tighten policies; finalize dashboards and runbooks.

## Done-ness Criteria
- Each phase must meet verification steps defined in the main plan before advancing.
