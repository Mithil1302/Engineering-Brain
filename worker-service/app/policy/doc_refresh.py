from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Set

from .models import Finding, PolicyEvaluationRequest, SuggestedPatch

DOC_DRIFT_RULE_IDS = {
    "DOC_DRIFT_ENDPOINT_CHANGED_NO_DOC",
    "DOC_DRIFT_MISSING_OWNER",
}


def build_doc_refresh_plan(
    *,
    request: PolicyEvaluationRequest,
    findings: List[Finding],
    suggested_patches: List[SuggestedPatch],
    merge_gate: Dict[str, object],
    action: str,
) -> Dict[str, object]:
    doc_findings = [f for f in findings if f.rule_id in DOC_DRIFT_RULE_IDS]
    doc_patches = [p for p in suggested_patches if p.patch_type == "doc_stub"]

    target_files: Set[str] = set()
    for f in doc_findings:
        for c in f.evidence:
            if c.kind == "file" and c.reference:
                target_files.add(c.reference)

    for p in doc_patches:
        target_files.add(p.file_path)

    if not target_files and doc_findings:
        target_files.add("docs/changes/pr-notes.md")

    decision = "not_needed"
    if action == "noop":
        decision = "noop"
    elif doc_findings:
        if merge_gate.get("decision") == "block":
            decision = "required"
        else:
            decision = "recommended"

    priority = "low"
    if decision == "required":
        priority = "high"
    elif decision == "recommended":
        priority = "med"

    return {
        "decision": decision,
        "priority": priority,
        "rule_set": merge_gate.get("rule_set"),
        "reason": "Documentation drift findings detected" if doc_findings else "No documentation refresh needed",
        "target_files": sorted(target_files),
        "doc_finding_count": len(doc_findings),
        "doc_patch_count": len(doc_patches),
        "patches": [p.model_dump() for p in doc_patches],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "should_emit": decision in {"required", "recommended"},
        "repo": request.repo,
        "pr_number": request.pr_number,
    }
