from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List

from .models import CheckStatus, Finding


def build_merge_gate_decision(
    findings: List[Finding],
    *,
    rule_set: str,
    fail_blocks_merge: bool = True,
    warn_blocks_merge: bool = False,
) -> Dict[str, object]:
    by_status = Counter([f.status for f in findings])

    has_fail = by_status.get(CheckStatus.FAIL, 0) > 0
    has_warn = by_status.get(CheckStatus.WARN, 0) > 0

    if fail_blocks_merge and has_fail:
        decision = "block"
    elif warn_blocks_merge and has_warn:
        decision = "block"
    elif has_warn:
        decision = "allow_with_warnings"
    else:
        decision = "allow"

    blocking_findings = [f for f in findings if f.status == CheckStatus.FAIL]
    if warn_blocks_merge:
        blocking_findings.extend([f for f in findings if f.status == CheckStatus.WARN])

    blocking_rule_ids = sorted({f.rule_id for f in blocking_findings})
    blocking_entities = sorted({e for f in blocking_findings for e in f.entity_refs})

    reasons = []
    if decision == "block":
        reasons.append("One or more blocking policy findings were detected.")
    elif decision == "allow_with_warnings":
        reasons.append("No blocking findings, but warning-level findings require review.")
    else:
        reasons.append("No blocking findings detected.")

    return {
        "decision": decision,
        "rule_set": rule_set,
        "counts": {
            "fail": by_status.get(CheckStatus.FAIL, 0),
            "warn": by_status.get(CheckStatus.WARN, 0),
            "info": by_status.get(CheckStatus.INFO, 0),
            "pass": by_status.get(CheckStatus.PASS, 0),
        },
        "blocking_rule_ids": blocking_rule_ids,
        "blocking_entities": blocking_entities,
        "reasons": reasons,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
