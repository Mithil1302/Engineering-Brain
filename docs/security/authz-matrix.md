# Week 1 AuthZ Matrix

## Claims Contract
Protected endpoints require authenticated claims context provided through either:

- `X-Auth-Context` (JSON string with `subject`, `role`, `tenant_id`, `repo_scope[]`) and optional `X-Auth-Signature` (HMAC SHA-256)
- OR split headers: `X-Auth-Subject`, `X-Auth-Role`, `X-Auth-Tenant-Id`, `X-Auth-Repo-Scope`
- OR bootstrap `X-Admin-Token` / `Authorization: Bearer <admin-token>` (maps to `platform-admin`, wildcard scope)

When `AUTH_CONTEXT_SIGNING_KEY` is configured, signature is required for claims mode.

## Roles

- `platform-admin`
- `security-admin`
- `platform-lead`
- `architect`
- `developer`
- `sre`

## Endpoint Authorization

| Endpoint Group | Allowed Roles | Repo Scope Enforcement |
|---|---|---|
| `/policy/admin/*` | `platform-admin`, `security-admin` | if repo present in operation |
| `/policy/pipeline/health` | `platform-admin`, `security-admin` | n/a |
| `/policy/dashboard/*` data endpoints | all read roles | required `repo` + in `repo_scope` |
| `/policy/dashboard/ui` | all read roles | role only |
| `/architecture/plan` | admin + `platform-lead`, `architect` | `request.repo` in `repo_scope` |
| `/architecture/plans` | admin + `platform-lead`, `architect` | required `repo` + scope check |
| `/assistant/ask` | all read roles | required `request.repo` + scope check |
| `/onboarding/path` | all read roles | required `repo` + scope check |
| `/simulation/time-travel` | admin + `platform-lead`, `architect` | required `repo` + scope check |
| `/autofix/run` | admin + `platform-lead`, `architect` | required `repo` + scope check |
| `/policy/evaluate` | all read roles | required `request.repo` + scope check |

## Audit Requirements

- Every denied authorization attempt is logged as `authz_denied` in `meta.audit_logs`
- Privileged mutation events log actor, role, tenant, correlation/request IDs, and target entities
- Audit sink failures must not break API request flow
