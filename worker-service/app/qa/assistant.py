from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from .models import QACitation, QARequest, QAResponse


def _intent(q: str) -> str:
    ql = q.lower()
    if any(k in ql for k in ["waiver", "exception", "override"]):
        return "governance_waiver"
    if any(k in ql for k in ["merge", "block", "gate"]):
        return "merge_gate"
    if any(k in ql for k in ["doc", "rewrite", "adr"]):
        return "doc_automation"
    if any(k in ql for k in ["architecture", "scaffold", "design"]):
        return "architecture_plan"
    if any(k in ql for k in ["health", "score", "grade", "trend"]):
        return "knowledge_health"
    return "general_status"


def _db_conn(pg_cfg: Dict[str, Any]):
    return psycopg2.connect(**pg_cfg)


def _fetch_latest(cur, table: str, repo: Optional[str], pr_number: Optional[int], limit: int = 5):
    cur.execute(
        f"""
        SELECT *
        FROM {table}
        WHERE (%s IS NULL OR repo = %s)
          AND (%s IS NULL OR pr_number = %s)
        ORDER BY id DESC
        LIMIT %s
        """,
        (repo, repo, pr_number, pr_number, limit),
    )
    return [dict(r) for r in cur.fetchall()]


def answer_question(request: QARequest, pg_cfg: Dict[str, Any]) -> QAResponse:
    intent = _intent(request.question)

    with _db_conn(pg_cfg) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            policy_runs = _fetch_latest(cur, "meta.policy_check_runs", request.repo, request.pr_number, 3)
            doc_jobs = _fetch_latest(cur, "meta.doc_refresh_jobs", request.repo, request.pr_number, 3)
            rewrite_runs = _fetch_latest(cur, "meta.doc_rewrite_runs", request.repo, request.pr_number, 3)
            health = _fetch_latest(cur, "meta.knowledge_health_snapshots", request.repo, request.pr_number, 3)
            arch = _fetch_latest(cur, "meta.architecture_plan_runs", request.repo, request.pr_number, 3)
            waivers = _fetch_latest(cur, "meta.policy_waivers", request.repo, request.pr_number, 3)

    citations: List[QACitation] = []
    answer_lines: List[str] = []

    if intent == "architecture_plan":
        latest = arch[0] if arch else None
        if latest:
            answer_lines.append(f"Latest architecture plan: {latest.get('plan_id')} with status {latest.get('status')}.")
            answer_lines.append(f"Services proposed: {len(latest.get('services') or [])}; infra components: {len(latest.get('infrastructure') or [])}.")
            citations.append(QACitation(source="meta.architecture_plan_runs", reference=str(latest.get("id")), details="latest architecture plan run"))
        else:
            answer_lines.append("No architecture plans found for this scope.")

    elif intent == "governance_waiver":
        latest = waivers[0] if waivers else None
        if latest:
            answer_lines.append(f"Latest waiver status: {latest.get('status')} (requested by {latest.get('requested_by')}).")
            answer_lines.append(f"Expires at: {latest.get('expires_at')}.")
            citations.append(QACitation(source="meta.policy_waivers", reference=str(latest.get("id")), details="latest waiver"))
        else:
            answer_lines.append("No waiver records found for this scope.")

    elif intent == "merge_gate":
        latest = policy_runs[0] if policy_runs else None
        if latest:
            mg = latest.get("merge_gate") or {}
            answer_lines.append(f"Merge gate decision: {mg.get('decision', 'unknown')}.")
            answer_lines.append(f"Blocking rules: {', '.join(mg.get('blocking_rule_ids') or []) or 'none'}.")
            citations.append(QACitation(source="meta.policy_check_runs", reference=str(latest.get("id")), details="latest policy run"))
        else:
            answer_lines.append("No policy check runs found for this scope.")

    elif intent == "doc_automation":
        latest_doc = doc_jobs[0] if doc_jobs else None
        latest_rw = rewrite_runs[0] if rewrite_runs else None
        if latest_doc:
            answer_lines.append(f"Doc refresh decision: {latest_doc.get('decision')} (priority: {latest_doc.get('priority')}).")
            citations.append(QACitation(source="meta.doc_refresh_jobs", reference=str(latest_doc.get("id")), details="latest doc refresh job"))
        if latest_rw:
            answer_lines.append(f"Doc rewrite run status: {latest_rw.get('status')}.")
            citations.append(QACitation(source="meta.doc_rewrite_runs", reference=str(latest_rw.get("id")), details="latest rewrite run"))
        if not latest_doc and not latest_rw:
            answer_lines.append("No documentation automation runs found for this scope.")

    elif intent == "knowledge_health":
        latest = health[0] if health else None
        if latest:
            answer_lines.append(f"Knowledge health is {latest.get('score')} ({latest.get('grade')}).")
            answer_lines.append(f"Summary status: {latest.get('summary_status')}.")
            citations.append(QACitation(source="meta.knowledge_health_snapshots", reference=str(latest.get("id")), details="latest health snapshot"))
        else:
            answer_lines.append("No health snapshots found for this scope.")

    else:
        answer_lines.append("Current system status summary:")
        answer_lines.append(f"- policy runs: {len(policy_runs)}")
        answer_lines.append(f"- doc jobs: {len(doc_jobs)}")
        answer_lines.append(f"- rewrite runs: {len(rewrite_runs)}")
        answer_lines.append(f"- health snapshots: {len(health)}")
        answer_lines.append(f"- architecture plans: {len(arch)}")
        answer_lines.append(f"- waivers: {len(waivers)}")

    confidence = 0.86 if citations else 0.62
    evidence = {
        "policy_runs": policy_runs,
        "doc_refresh_jobs": doc_jobs,
        "doc_rewrite_runs": rewrite_runs,
        "health_snapshots": health,
        "architecture_plans": arch,
        "waivers": waivers,
        "channel": request.channel,
        "role": request.role,
    }

    return QAResponse(
        answer="\n".join(answer_lines),
        confidence=confidence,
        intent=intent,
        citations=citations,
        evidence=evidence,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
