# Hybrid Retrieval Plan

## Chunking & Metadata
- Chunk sources: code, specs (OpenAPI/AsyncAPI), docs/ADRs, DB schema exports.
- Chunk size/overlap: to be tuned; include source offsets (path, line ranges) or opId/schema hash.
- Metadata (stored in Postgres): chunk_id, source_type, repo, path, line_range, opId, entity_refs (service/endpoint/model), hash, timestamp, tags.
- Re-embed when content hash changes.

## Storage
- Vectors: Qdrant collections with payload filters (repo, service, opId, type).
- Metadata: Postgres tables linking chunk_id ↔ entity refs ↔ hashes.

## Query Pipeline
1) User query → embed with Gemini embeddings.
2) Qdrant ANN search with filters (repo/service/opId/type).
3) Expand via graph: use matched entities to traverse Neo4j (services, endpoints, dependencies, docs, tests).
4) Compose context with citations (files/lines/specs).
5) Gemini reasoning over curated context → answer with citations.

## Filters & Controls
- Filters: repo, service, file extension, opId, environment.
- Limits: top-k from ANN; cap total tokens for context.

## Performance
- Target p99 latency: to be set; ANN + graph expansion should fit budget.

## Open Items
- Exact chunk sizes and overlap.
- Qdrant collection schemas and payload index choices.
- Context assembly ordering heuristic.
