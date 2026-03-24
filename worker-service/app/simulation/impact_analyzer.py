"""
KA-CHOW Impact Analyzer — Graph-Based What-If Analysis.

Provides:
  1. Dependency graph traversal for impact propagation
  2. What-if analysis: simulate removing/changing an endpoint
  3. LLM-enhanced natural language impact explanations
  4. Failure cascade simulation via BFS on service graph
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from ..llm import get_llm_client
from ..llm.prompts import ImpactAnalysisPrompt

log = logging.getLogger("ka-chow.impact")


# ---------------------------------------------------------------------------
# Graph querying (via Neo4j through the graph-service gRPC)
# ---------------------------------------------------------------------------

def _query_dependencies_from_db(
    pg_cfg: Dict[str, Any],
    repo: str,
    service_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Query dependency information from PostgreSQL.
    (In production, this would query Neo4j graph-service via gRPC.)
    """
    import psycopg2
    from psycopg2.extras import RealDictCursor

    dependencies: Dict[str, Any] = {
        "services": [],
        "endpoints": [],
        "edges": [],
    }

    try:
        with psycopg2.connect(**pg_cfg) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get recent policy runs with their specs for dependency info
                cur.execute(
                    """
                    SELECT DISTINCT repo, head_spec, base_spec
                    FROM meta.policy_check_runs
                    WHERE repo = %s
                    ORDER BY id DESC
                    LIMIT 10
                    """,
                    (repo,),
                )
                for row in cur.fetchall():
                    head = row.get("head_spec") or {}
                    if isinstance(head, str):
                        head = json.loads(head)
                    if head.get("service_id"):
                        services_set = {s["name"] for s in dependencies["services"]}
                        if head["service_id"] not in services_set:
                            dependencies["services"].append({
                                "name": head["service_id"],
                                "endpoints": [
                                    {
                                        "method": ep.get("method"),
                                        "path": ep.get("path"),
                                        "operation_id": ep.get("operation_id"),
                                    }
                                    for ep in (head.get("endpoints") or [])
                                ],
                            })

                # Get health data for services
                cur.execute(
                    """
                    SELECT repo, score::float8 AS score, grade, dimensions
                    FROM meta.knowledge_health_snapshots
                    WHERE repo = %s
                    ORDER BY id DESC LIMIT 1
                    """,
                    (repo,),
                )
                health = cur.fetchone()
                if health:
                    dependencies["health"] = dict(health)

    except Exception as exc:
        log.warning("Dependency query failed: %s", exc)

    return dependencies


# ---------------------------------------------------------------------------
# Impact analysis
# ---------------------------------------------------------------------------

def analyze_impact(
    *,
    change_description: str,
    repo: str,
    service_id: Optional[str] = None,
    endpoint: Optional[str] = None,
    pg_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Analyze the impact of a proposed change.

    Uses graph data + LLM to explain downstream impact.
    """
    # Step 1: Query dependency graph
    deps = _query_dependencies_from_db(pg_cfg, repo, service_id)

    # Step 2: Build impacted entities list
    impacted = _propagate_impact(
        deps,
        service_id=service_id,
        endpoint=endpoint,
    )

    # Step 3: Build dependency paths
    paths = _build_dependency_paths(deps, service_id)

    # Step 4: LLM explanation
    llm = get_llm_client()
    prompt = ImpactAnalysisPrompt.user_prompt(
        change_description=change_description,
        impacted_entities=impacted,
        dependency_paths=paths,
    )

    try:
        resp = llm.generate(
            prompt,
            system_prompt=ImpactAnalysisPrompt.system_prompt,
            json_mode=True,
            json_schema=ImpactAnalysisPrompt.response_schema(),
            temperature=0.3,
        )
        analysis = resp.as_json()
        if not isinstance(analysis, dict):
            analysis = {
                "summary": str(analysis),
                "blast_radius": "unknown",
                "overall_risk": "unknown",
                "impacted_services": [],
            }
    except Exception as exc:
        log.error("LLM impact analysis failed: %s", exc)
        analysis = {
            "summary": f"Impact analysis generation failed: {exc}",
            "blast_radius": "unknown",
            "overall_risk": "unknown",
            "impacted_services": [],
        }

    analysis["dependency_graph"] = deps
    analysis["raw_impacted"] = impacted
    analysis["dependency_paths"] = paths

    return analysis


def simulate_failure_cascade(
    *,
    failing_service: str,
    repo: str,
    pg_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Simulate a failure cascade: if service X goes down, what else breaks?
    Uses BFS on the dependency graph.
    """
    deps = _query_dependencies_from_db(pg_cfg, repo)
    services = deps.get("services", [])
    edges = deps.get("edges", [])

    # Build adjacency list from edges
    graph: Dict[str, List[str]] = {}
    for edge in edges:
        src = edge.get("from", "")
        dst = edge.get("to", "")
        if src:
            graph.setdefault(src, []).append(dst)

    # BFS from failing service
    visited = set()
    queue = [failing_service]
    cascade_order = []

    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        cascade_order.append(current)
        for neighbor in graph.get(current, []):
            if neighbor not in visited:
                queue.append(neighbor)

    # Remove the initial failing service from cascade
    cascade_order = cascade_order[1:] if cascade_order else []

    # Get LLM explanation
    try:
        llm = get_llm_client()
        resp = llm.generate_json(
            json.dumps({
                "failing_service": failing_service,
                "cascade_order": cascade_order,
                "total_services": len(services),
                "task": "Explain the failure cascade and recommend mitigation strategies.",
            }),
            system_prompt=(
                "You are a site reliability engineer analyzing a failure cascade. "
                "Explain what happens when each service fails and suggest circuit breakers, "
                "fallbacks, and graceful degradation strategies."
            ),
        )
        explanation = resp if isinstance(resp, dict) else {"explanation": str(resp)}
    except Exception:
        explanation = {"explanation": "LLM explanation unavailable"}

    return {
        "failing_service": failing_service,
        "cascade_order": cascade_order,
        "affected_count": len(cascade_order),
        "total_services": len(services),
        "blast_radius_pct": round(
            len(cascade_order) / max(len(services), 1) * 100, 1
        ),
        "explanation": explanation,
    }


def get_dependency_graph(
    repo: str,
    pg_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    """Return the service dependency graph."""
    deps = _query_dependencies_from_db(pg_cfg, repo)
    return {
        "repo": repo,
        "services": deps.get("services", []),
        "edges": deps.get("edges", []),
        "health": deps.get("health"),
        "node_count": len(deps.get("services", [])),
        "edge_count": len(deps.get("edges", [])),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _propagate_impact(
    deps: Dict[str, Any],
    service_id: Optional[str],
    endpoint: Optional[str],
) -> List[Dict[str, Any]]:
    """Build list of impacted entities from dependency data."""
    impacted = []
    services = deps.get("services", [])

    for svc in services:
        svc_name = svc.get("name", "")
        if service_id and svc_name == service_id:
            continue  # skip the service being changed

        # Check if any endpoints overlap
        for ep in svc.get("endpoints", []):
            if endpoint and ep.get("path") == endpoint:
                impacted.append({
                    "entity": svc_name,
                    "type": "service",
                    "reason": f"Consumes endpoint {endpoint}",
                    "severity": "high",
                })
                break
        else:
            impacted.append({
                "entity": svc_name,
                "type": "service",
                "reason": "In the same service mesh",
                "severity": "low",
            })

    return impacted


def _build_dependency_paths(
    deps: Dict[str, Any],
    service_id: Optional[str],
) -> List[str]:
    """Build human-readable dependency path descriptions."""
    paths = []
    services = deps.get("services", [])

    for svc in services:
        svc_name = svc.get("name", "")
        endpoints = svc.get("endpoints", [])
        ep_count = len(endpoints)
        paths.append(f"{svc_name} ({ep_count} endpoints)")

    if not paths:
        paths.append("No dependency data available yet. Run a policy check to populate the graph.")

    return paths
