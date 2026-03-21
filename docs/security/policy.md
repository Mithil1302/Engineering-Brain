# Security & Compliance Policy (Baseline)

## Secrets
- Store GitHub App keys, DB creds, Kafka creds securely (vault/secret manager). Rotate periodically.

## Permissions
- GitHub App least-privilege scopes: Checks, PRs, Contents (read), Issues (comments), Metadata.
- Kafka ACLs per topic; DB users with least privileges (read/write as needed; no superuser).

## Data Retention
- Define retention for raw artifacts/specs/logs; enable purge for PII on request.
- PII-aware ingestion toggles; avoid storing sensitive data when not needed.

## Audit Logging
- Record graph mutations, agent actions, suggested fixes with actor, timestamp, correlation_id, entities affected.

## Network/Transport
- TLS for all services and Kafka/DB connections.

## Open Items
- Select secret manager; define concrete retention periods and purge process.
