# Self-Healing Policy (Controlled)

## Allowed Auto-Fixes (initial)
- Add/update client timeout/retry configuration (non-code logic changes).
- Generate doc stub for new/changed endpoint.
- Generate minimal ADR skeleton for breaking change note.

## Modes
- Default: suggest-only (no auto-apply). Requires human approval.
- Gated apply: optional toggle per repo/service; still requires explicit approval.

## Safety Limits
- Scope: only allowed paths (docs/, config/). No application logic changes.
- Max diff size: small (TBD lines/files threshold).
- Preconditions: clean lint/tests optional gate.

## Audit & Traceability
- Log every suggestion with rule trigger, evidence, target entities, timestamp, correlation_id.

## Open Items
- Exact thresholds for diff size and approval workflow.
