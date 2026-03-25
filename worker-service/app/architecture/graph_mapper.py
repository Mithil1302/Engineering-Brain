from __future__ import annotations

import json
from typing import Any, Dict, List


def blueprint_to_graph_mutations(
    *,
    repo: str,
    plan_id: int,
    plan: Dict[str, Any],
    rationale_decisions: List[Dict[str, Any]],
    adrs: List[Dict[str, Any]],
    constraints: Dict[str, Any],
) -> List[Dict[str, Any]]:
    now_payload = {"repo": repo, "plan_id": plan_id}
    mutations: List[Dict[str, Any]] = []

    repo_id = f"repo:{repo}"
    mutations.append(
        {
            "type": "create_node",
            "entity_kind": "repo",
            "entity_id": repo_id,
            "payload_json": json.dumps(now_payload),
            "valid_from": "",
            "valid_to": "",
        }
    )

    for svc in (plan.get("services") or []):
        name = str((svc or {}).get("name") or "unknown-service")
        sid = f"service:{repo}:{name}"
        mutations.append(
            {
                "type": "create_node",
                "entity_kind": "service",
                "entity_id": sid,
                "payload_json": json.dumps({"name": name, "repo": repo, "plan_id": plan_id, **(svc or {})}),
                "valid_from": "",
                "valid_to": "",
            }
        )

    for d in rationale_decisions:
        did = str(d.get("decision_id") or "decision")
        node_id = f"decision:{repo}:{plan_id}:{did}"
        mutations.append(
            {
                "type": "create_node",
                "entity_kind": "decision",
                "entity_id": node_id,
                "payload_json": json.dumps({"repo": repo, "plan_id": plan_id, **d}),
                "valid_from": "",
                "valid_to": "",
            }
        )

    for adr in adrs:
        aid = str(adr.get("adr_id") or "adr")
        node_id = f"adr:{repo}:{plan_id}:{aid}"
        mutations.append(
            {
                "type": "create_node",
                "entity_kind": "adr",
                "entity_id": node_id,
                "payload_json": json.dumps({"repo": repo, "plan_id": plan_id, **adr}),
                "valid_from": "",
                "valid_to": "",
            }
        )

    for idx, c in enumerate((constraints.get("constraints") or []), start=1):
        cid = f"constraint:{repo}:{plan_id}:{idx}"
        mutations.append(
            {
                "type": "create_node",
                "entity_kind": "constraint",
                "entity_id": cid,
                "payload_json": json.dumps({"repo": repo, "plan_id": plan_id, **c}),
                "valid_from": "",
                "valid_to": "",
            }
        )

    return mutations


def propose_reuse_candidates(*, repo: str, bounded_context: str, known_services: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    context_norm = (bounded_context or "").strip().lower()
    if not context_norm:
        return []

    out: List[Dict[str, Any]] = []
    for svc in known_services:
        name = str(svc.get("name") or "")
        role = str(svc.get("responsibility") or svc.get("role") or "")
        blob = f"{name} {role}".lower()
        if context_norm in blob or any(token in blob for token in context_norm.split() if len(token) > 3):
            out.append(
                {
                    "service": name,
                    "reason": "Existing bounded context overlap detected",
                    "recommendation": "extend_existing_service",
                }
            )
    return out
