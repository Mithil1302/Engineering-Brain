# Stack Charter

## Runtime & Services
- **Polyglot:** Node/TypeScript for API layer, GitHub App, orchestration; Python for ML/LLM agents, parsing, embeddings.
- **Inter-service comms:** gRPC internally; REST externally.
- **Services (initial set):** api-gateway (Node), ingestion-service (Node), graph-service (Python), agent-service (Python), worker-service (Python).

## Data & Messaging
- **Graph:** Neo4j with temporal modeling (versioned edges: `valid_from`, `valid_to`; as-of queries; projections).
- **Vector:** Qdrant for ANN with payload filters; hybrid search.
- **Relational:** PostgreSQL for jobs, policies, audit logs, embeddings metadata (not vectors).
- **Messaging/Event backbone:** Kafka (NOT Redis). Topics: `repo.events`, `graph.updates`, `analysis.jobs`, `agent.requests`, `ci.events`. Replay required for timeline.

## LLM/Embeddings & Agents
- **LLM:** Google Gemini (1.5/2.0 subject to access).
- **Embeddings:** Vertex AI embedding models.
- **Agent framework:** LangGraph or custom orchestrator. Agents: Impact, Architecture, Doc, Self-healing. Each uses LLM + tools + graph queries + memory. Tool/function calling enabled for graph queries.

## PR Surface & Integrations
- **PR interface:** GitHub App (org-level). Capabilities: PR checks, inline comments, suggested patches/diffs, status enforcement.
- **Identity & auth:** GitHub App with least-privilege scopes; service-to-service auth via shared secrets/certs (TBD) and Kafka ACLs.

## Packaging & Deployment
- **Containers:** Docker.
- **Orchestration:** Kubernetes.
- **Runtime images:** Minimal base images per language; health/liveness probes required.

## Retrieval & Reasoning Path
- Hybrid retrieval: Qdrant ANN → Neo4j graph expansion → Gemini reasoning with citations.

## Observability
- **Logs:** Structured JSON.
- **Metrics:** Prometheus + Grafana.
- **Traces:** OpenTelemetry + Jaeger.

## Security & Compliance (baseline)
- Secrets management for GitHub App keys, DB/Kafka creds (store securely, rotate).
- Audit logging for graph mutations and agent actions.
- PII-aware ingestion toggles and retention windows to be defined in security policy.

## Rationale (condensed)
- Node: best GitHub ecosystem + async; Python: best AI/parsing.
- gRPC: low-latency internal calls.
- Neo4j: native graph + temporal modeling; Qdrant: fast ANN with payload filters.
- Kafka: replay, ordering, scalable ingestion for timeline feature.
- Gemini/Vertex: preferred LLM/embedding stack.
- K8s: standard for multi-service deployment.

## Approvals
- Owner: <to assign>
- Approved by: <to record>
- Date: <fill when approved>
