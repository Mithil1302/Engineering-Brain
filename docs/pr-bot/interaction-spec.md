# PR Bot Interaction Spec

## Comment Structure
- Summary (overall status, risk level).
- Affected services/endpoints.
- Key findings (breaking changes, doc drift, impact) with citations (files/lines/spec refs).
- Suggestions/patches (when available) for doc stubs or config tweaks.

## Checks & Enforcement
- Map rule severity → check status (fail/warn/info).
- On fail: block merge; on warn: advisory.
- Updates: bot edits its own comment on rerun; avoids duplicates.

## Suggested Patches
- Allowed types initially: doc stub insertion, timeout/retry config tweaks.
- Format: unified diff attached to comment or via Check Run annotations.

## Permissions
- GitHub App scopes: Checks, Pull requests, Contents (read), Issues (comments), Metadata; write where needed for comments/checks.

## Rate & Rerun Behavior
- Re-run on new commits to PR; throttle comment updates to avoid spam.

## Event-Driven Delivery (implemented)
- Worker policy pipeline consumes `repo.events` for `pull_request/spec/schema/doc` events.
- Evaluations are emitted to `pr.checks` with fields:
	- `action`: `create_comment|update_comment|noop`
	- `comment_key`: stable key `repo:pr:rule-set`
	- `markdown_comment`, `findings`, `citations`, `check_annotations`, `suggested_patches`
- Anti-spam dedupe:
	- fingerprint-based dedupe state in `meta.pr_comment_state`
	- unchanged findings produce `noop` and suppress duplicate check emission
	- every run persisted in `meta.policy_check_runs` for auditability

## Multi-tenant GitHub Delivery (implemented)
- Incoming events can carry `tenant_id` and `installation_id` (or `tenant.{id,installation_id}`).
- Bridge resolves tenant installation context in this order:
	1. event installation fields
	2. `meta.tenant_installations` mapping by `(tenant_id, repo_full_name)` (fallback `repo_full_name='*'`)
	3. legacy static env fallback (`GITHUB_INSTALLATION_ID`) for backward compatibility
- Delivery and audit persistence now capture tenant scope (`tenant_id`, `installation_id`) in:
	- `meta.github_delivery_state`
	- `meta.github_delivery_attempts`
- Tenant mapping management API:
	- `POST /github/bridge/tenants/installations`
	- `GET /github/bridge/tenants/installations?tenant_id=...`

## Security & Hardening (implemented)
- Admin API protection:
	- Tenant mapping endpoints require admin token when `GITHUB_BRIDGE_ADMIN_TOKEN` is configured
	- Header options: `Authorization: Bearer <token>` or `X-Admin-Token: <token>`
- Webhook verification:
	- `POST /github/webhook`
	- Verifies `X-Hub-Signature-256` using `GITHUB_WEBHOOK_SECRET`
	- Handles `installation` and `installation_repositories` events to auto-register tenant/repo installation mappings
- Metadata protection:
	- Tenant installation `metadata` can be encrypted at rest using `TENANT_METADATA_ENCRYPTION_KEY` (Fernet)
- Tenant abuse controls:
	- Per-tenant rate limiting (`GITHUB_TENANT_RATE_LIMIT_PER_MINUTE`)
	- Per-tenant circuit breaker with threshold/cooldown:
		- `GITHUB_TENANT_CIRCUIT_BREAKER_FAILURE_THRESHOLD`
		- `GITHUB_TENANT_CIRCUIT_BREAKER_COOLDOWN_SEC`

## Open Items
- Exact markdown template; localization not required.
