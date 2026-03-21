# Policy Rules v1 (Drift & Impact)

## Breaking-Change Rules (OpenAPI)
- Path/method removal → severity: high.
- Request schema tightening (new required field, enum shrink) → severity: high/med depending on context.
- Response schema breaking (removal, type change) → severity: high.
- Status code removal → severity: med.

## Doc Drift Rules
- Endpoint added/changed without corresponding doc/ADR update (spec hash mismatch) → severity: med.
- Missing owner metadata for service/endpoint → severity: med.

## Impact Propagation
- Given endpoint/model change: traverse client-consumes, service-calls-service, test-covers, doc-documents, message produced/consumed edges (as-of time) to list affected services, files, tests.

## Findings Schema (normalized)
- rule_id, severity, entity_refs (service/endpoint/model/test/doc), evidence (paths/lines/spec refs), suggested_action, detected_at, correlation_id.

## Config
- Enable/disable per rule; map severity to PR check status (fail/warn/info); thresholds per repo/service.

## Open Items
- Exact enum mapping for severities and statuses.
- Additional rules for AsyncAPI/message schemas.
