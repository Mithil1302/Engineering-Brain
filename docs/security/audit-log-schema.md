# Audit Log Schema

## Fields
- `timestamp`
- `actor` (service/user/app id)
- `action` (graph_mutation | agent_action | suggestion_created | suggestion_applied)
- `entities` (list of graph entity refs: service/endpoint/model/test/doc)
- `correlation_id`
- `request_id`
- `result` (success/failure + error if any)
- `metadata` (rule_id, severity, commit/pr refs where applicable)

## Storage
- Postgres table with indexing on timestamp, actor, action, correlation_id.
