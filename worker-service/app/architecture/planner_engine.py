from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..llm import get_llm_client
from ..llm.prompts import ArchitecturePlannerPrompt
from .contract_generator import generate_grpc_contracts, generate_openapi_contracts
from .graph_integration import fetch_existing_services, persist_graph_projection
from .graph_mapper import blueprint_to_graph_mutations, propose_reuse_candidates
from .intent_parser import extract_constraints
from .rationale_tracer import build_adr_bundle, build_rationale_decisions, build_traceability_map
from .scaffold_guardrails import evaluate_scaffold_guardrails
from .tech_stack_engine import run_stack_decision_engine


def _build_blueprint_graph(plan: Dict[str, Any]) -> Dict[str, Any]:
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    for svc in plan.get("services", []) or []:
        name = str((svc or {}).get("name") or "service")
        sid = f"service:{name}"
        nodes.append({"node_id": sid, "node_type": "service", "label": name, "attributes": dict(svc or {})})
        for dep in (svc or {}).get("depends_on", []) or []:
            edges.append({"src": sid, "dst": f"service:{dep}", "edge_type": "depends_on", "attributes": {}})
    return {"nodes": nodes, "edges": edges}


def run_advanced_architecture_pipeline(
    *,
    requirement: str,
    repo: str,
    pr_number: Optional[int],
    pg_cfg: Dict[str, Any],
    constraints: Optional[List[str]] = None,
) -> Dict[str, Any]:
    llm = get_llm_client()

    combined_requirement = requirement
    if constraints:
        combined_requirement = requirement + "\n\nAdditional constraints:\n" + "\n".join(f"- {c}" for c in constraints)

    extracted = extract_constraints(combined_requirement)
    stack_decisions = run_stack_decision_engine(extracted)

    # Reuse proposal from historical plans
    existing_services = fetch_existing_services(pg_cfg, repo)
    reuse_candidates = propose_reuse_candidates(
        repo=repo,
        bounded_context=combined_requirement,
        known_services=existing_services,
    )

    planner_prompt = ArchitecturePlannerPrompt.user_prompt(
        requirement=combined_requirement,
        system_context={"existing_services": existing_services[:20], "reuse_candidates": reuse_candidates},
        constraints=constraints,
    )

    try:
        llm_resp = llm.generate(
            planner_prompt,
            system_prompt=ArchitecturePlannerPrompt.system_prompt,
            json_mode=True,
            json_schema=ArchitecturePlannerPrompt.response_schema(),
            temperature=0.35,
            use_cache=False,
        )
        plan = llm_resp.as_json()
        if not isinstance(plan, dict):
            plan = {"title": "Generated Plan", "summary": str(plan), "services": [], "adrs": [], "risks": []}
        llm_model = llm_resp.model
        llm_tokens = llm_resp.input_tokens + llm_resp.output_tokens
        llm_latency_ms = llm_resp.latency_ms
    except Exception as exc:
        plan = {
            "title": "Plan Generation Failed",
            "summary": f"LLM call failed: {exc}",
            "services": [],
            "adrs": [],
            "risks": [{"description": str(exc), "severity": "high", "mitigation": "Retry with clarified constraints."}],
        }
        llm_model = "error"
        llm_tokens = 0
        llm_latency_ms = 0.0

    blueprint_graph = _build_blueprint_graph(plan)
    rationale = build_rationale_decisions(plan, extracted, {k: v.model_dump() for k, v in stack_decisions.items()})
    adrs = build_adr_bundle(rationale, combined_requirement)
    traceability = build_traceability_map(rationale, extracted)

    contracts = {}
    contracts.update(generate_openapi_contracts(plan))
    contracts.update(generate_grpc_contracts(plan))

    guardrails = evaluate_scaffold_guardrails(
        plan=plan,
        extracted_constraints=extracted.model_dump(),
    )

    result = {
        **plan,
        "extracted_constraints": extracted.model_dump(),
        "stack_decisions": {k: v.model_dump() for k, v in stack_decisions.items()},
        "blueprint_graph": blueprint_graph,
        "rationale_decisions": [r.model_dump() for r in rationale],
        "adrs": [a.model_dump() for a in adrs],
        "traceability_map": traceability,
        "contract_artifacts": contracts,
        "guardrail_warnings": guardrails,
        "reuse_candidates": reuse_candidates,
        "_meta": {
            "llm_model": llm_model,
            "llm_tokens": llm_tokens,
            "llm_latency_ms": llm_latency_ms,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "repo": repo,
            "pr_number": pr_number,
        },
    }

    # produce graph projection payload for persistence hooks
    result["graph_mutations"] = blueprint_to_graph_mutations(
        repo=repo,
        plan_id=-1,
        plan=result,
        rationale_decisions=result["rationale_decisions"],
        adrs=result["adrs"],
        constraints=result["extracted_constraints"],
    )

    return result


def persist_advanced_graph_projection(pg_cfg: Dict[str, Any], repo: str, plan_id: int, plan_payload: Dict[str, Any]) -> None:
    graph_payload = {
        "nodes": (plan_payload.get("blueprint_graph") or {}).get("nodes", []),
        "edges": (plan_payload.get("blueprint_graph") or {}).get("edges", []),
        "rationale": plan_payload.get("rationale_decisions", []),
        "adrs": plan_payload.get("adrs", []),
    }
    persist_graph_projection(pg_cfg, repo, plan_id, graph_payload)
