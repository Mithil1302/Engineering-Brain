# Connector Contracts (Ingestion Inputs)

## Git / PR
- Payload: repo id/url, commit SHA or PR number, head SHA, changed files (paths, status, patches/URLs), author, timestamps.
- Idempotency: commit SHA or (PR number + head SHA).
- Auth: GitHub App webhook signature verification.
- Filters: ignore binary/large files by pattern; include only whitelisted dirs optionally.

## OpenAPI / AsyncAPI
- Accepted: JSON/YAML; must include version, servers, paths/channels, components/schemas.
- Versioning: spec_hash (content hash). Store raw spec in object storage if large.
- Location: repo path or URL; include commit SHA reference.

## DB Schema (initial: Postgres)
- Snapshot fields: tables (name, schema), columns (name, type, nullable, default), PK/FK, indexes.
- Hashing: per table + global schema hash. Idempotency via schema hash.
- Auth: read-only DB creds.

## Docs / ADRs (Markdown)
- Expect optional frontmatter: title, date, status, decision, context, consequences, tags, related opIds/services.
- Parse headings and links; link by opId tags when present.

## Incidents / Tickets
- Minimal JSON/CSV: id, title, severity, status, opened_at, closed_at?, impacted_services, summary, links.

## Size & Storage
- Large blobs (full specs, schema dumps) may be stored externally; events carry URIs + hashes.

## Event Emission
- Each connector emits normalized events with: schema_version, idempotency_key, correlation_id, produced_at.
