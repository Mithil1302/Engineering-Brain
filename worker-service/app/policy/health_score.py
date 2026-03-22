from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

from .models import Finding, PolicyEvaluationRequest


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _grade(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def build_knowledge_health_score(
    *,
    request: PolicyEvaluationRequest,
    findings: List[Finding],
    merge_gate: Dict[str, object],
    doc_refresh_plan: Dict[str, object],
    weights: Dict[str, float] | None = None,
) -> Dict[str, object]:
    w = {
        "policy": 0.45,
        "docs": 0.35,
        "ownership": 0.20,
    }
    if weights:
        w.update(weights)

    # Normalize weights defensively.
    total_weight = sum(max(v, 0.0) for v in w.values()) or 1.0
    w = {k: max(v, 0.0) / total_weight for k, v in w.items()}

    fail_count = sum(1 for f in findings if str(f.status) == "CheckStatus.FAIL" or str(f.status) == "fail")
    warn_count = sum(1 for f in findings if str(f.status) == "CheckStatus.WARN" or str(f.status) == "warn")

    # Policy quality decreases with fails/warns.
    policy_score = _clamp(100 - (fail_count * 28) - (warn_count * 9))

    # Documentation health via doc refresh planner outcome.
    doc_decision = str(doc_refresh_plan.get("decision") or "not_needed")
    doc_finding_count = int(doc_refresh_plan.get("doc_finding_count") or 0)
    if doc_decision == "required":
        docs_score = _clamp(45 - (doc_finding_count * 8))
    elif doc_decision == "recommended":
        docs_score = _clamp(72 - (doc_finding_count * 5))
    elif doc_decision == "noop":
        docs_score = 90.0
    else:
        docs_score = 100.0

    # Ownership quality from owner-related findings.
    owner_missing_count = sum(1 for f in findings if f.rule_id == "DOC_DRIFT_MISSING_OWNER")
    ownership_score = _clamp(100 - (owner_missing_count * 25))

    total = _clamp(
        (policy_score * w["policy"])
        + (docs_score * w["docs"])
        + (ownership_score * w["ownership"])
    )

    blocked = str(merge_gate.get("decision") or "allow") == "block"
    if blocked:
        total = _clamp(total - 7)

    score = round(total, 2)
    return {
        "score": score,
        "grade": _grade(score),
        "blocked": blocked,
        "dimensions": {
            "policy": round(policy_score, 2),
            "docs": round(docs_score, 2),
            "ownership": round(ownership_score, 2),
        },
        "weights": w,
        "inputs": {
            "fail_count": fail_count,
            "warn_count": warn_count,
            "doc_decision": doc_decision,
            "doc_finding_count": doc_finding_count,
            "owner_missing_count": owner_missing_count,
            "repo": request.repo,
            "pr_number": request.pr_number,
        },
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
