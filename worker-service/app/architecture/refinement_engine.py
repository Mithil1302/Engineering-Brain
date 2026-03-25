from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .models import ArchitectureDiff


def _service_name_set(plan: Dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for s in (plan.get("services") or []):
        name = str((s or {}).get("name") or "").strip()
        if name:
            out.add(name)
    return out


def compute_plan_diff(base_plan: Dict[str, Any], new_plan: Dict[str, Any], changed_constraints: List[str]) -> ArchitectureDiff:
    base_services = _service_name_set(base_plan)
    new_services = _service_name_set(new_plan)

    added_services = sorted(list(new_services - base_services))
    removed_services = sorted(list(base_services - new_services))
    common_services = sorted(list(new_services & base_services))

    base_decisions = {d.get("decision_id") for d in (base_plan.get("rationale_decisions") or []) if isinstance(d, dict)}
    new_decisions = {d.get("decision_id") for d in (new_plan.get("rationale_decisions") or []) if isinstance(d, dict)}

    added_decisions = sorted([x for x in (new_decisions - base_decisions) if x])
    removed_decisions = sorted([x for x in (base_decisions - new_decisions) if x])

    changed_decisions: List[str] = []
    base_map = {d.get("decision_id"): d for d in (base_plan.get("rationale_decisions") or []) if isinstance(d, dict)}
    new_map = {d.get("decision_id"): d for d in (new_plan.get("rationale_decisions") or []) if isinstance(d, dict)}
    for k in (base_decisions & new_decisions):
        if base_map.get(k) != new_map.get(k):
            changed_decisions.append(k)

    affected_nodes = [f"service:{s}" for s in sorted(set(added_services + removed_services + common_services[:3]))]
    summary = (
        f"Added services: {len(added_services)}, removed services: {len(removed_services)}, "
        f"decision delta: +{len(added_decisions)} / -{len(removed_decisions)} / ~{len(changed_decisions)}"
    )

    return ArchitectureDiff(
        changed_constraints=changed_constraints,
        affected_nodes=affected_nodes,
        added_decisions=added_decisions,
        removed_decisions=removed_decisions,
        changed_decisions=sorted(changed_decisions),
        summary=summary,
    )


def build_partial_regeneration_plan(diff: ArchitectureDiff) -> Dict[str, Any]:
    scope = "partial"
    if len(diff.affected_nodes) > 12 or len(diff.changed_constraints) > 6:
        scope = "full"

    return {
        "regeneration_scope": scope,
        "affected_nodes": diff.affected_nodes,
        "steps": [
            "Recompute tech-stack scores for impacted domains",
            "Regenerate impacted service contracts (OpenAPI/gRPC)",
            "Regenerate ADR sections tied to changed constraints",
            "Update only affected manifests and service stubs",
        ],
    }


def apply_constraint_overrides(requirement_text: str, overrides: Dict[str, Any]) -> str:
    if not overrides:
        return requirement_text
    lines = [requirement_text.strip(), "", "Constraint overrides:"]
    for k, v in overrides.items():
        lines.append(f"- {k}: {v}")
    return "\n".join(lines)
