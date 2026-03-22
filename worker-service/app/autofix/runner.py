from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List


def build_autofix_workflow(
    *,
    repo: str,
    pr_number: int | None,
    findings: List[Dict[str, Any]],
    doc_refresh_plan: Dict[str, Any],
) -> Dict[str, Any]:
    jobs: List[Dict[str, Any]] = []

    for f in findings:
        rid = f.get("rule_id")
        if rid in {"DOC_DRIFT_ENDPOINT_CHANGED_NO_DOC", "DOC_DRIFT_MISSING_OWNER"}:
            jobs.append(
                {
                    "job_type": "doc_fix",
                    "rule_id": rid,
                    "action": "apply_doc_rewrite_bundle",
                    "status": "queued",
                }
            )
        elif str(f.get("status")) in {"fail", "CheckStatus.FAIL"}:
            jobs.append(
                {
                    "job_type": "contract_fix",
                    "rule_id": rid,
                    "action": "propose_contract_migration_patch",
                    "status": "queued",
                }
            )

    if not jobs and doc_refresh_plan.get("should_emit"):
        jobs.append(
            {
                "job_type": "doc_fix",
                "rule_id": "DOC_AUTOMATION",
                "action": "apply_doc_rewrite_bundle",
                "status": "queued",
            }
        )

    return {
        "repo": repo,
        "pr_number": pr_number,
        "status": "queued" if jobs else "noop",
        "jobs": jobs,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
