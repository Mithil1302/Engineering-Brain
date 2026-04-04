"""
KA-CHOW Impact Analyzer — Graph-Based What-If Analysis.

Provides:
  1. Dependency graph traversal for impact propagation
  2. What-if analysis: simulate removing/changing an endpoint
  3. LLM-enhanced natural language impact explanations
  4. Failure cascade simulation via BFS on service graph
  5. Neo4j integration via gRPC with PostgreSQL fallback
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import grpc
import psycopg2
from psycopg2.extras import RealDictCursor

# Import generated protobuf stubs
from ..generated import services_pb2, services_pb2_grpc

from ..llm import get_llm_client
from ..llm.prompts import ImpactAnalysisPrompt

log = logging.getLogger("ka-chow.impact")


# ---------------------------------------------------------------------------
# Placeholder proto message classes (until QueryGraph is added to services.proto)
# ---------------------------------------------------------------------------

class QueryGraphRequest:
    """Placeholder for QueryGraphRequest proto message."""
    def __init__(self, cypher: str, params: dict):
        self.cypher = cypher
        self.params = params


class QueryGraphResponse:
    """Placeholder for QueryGraphResponse proto message."""
    def __init__(self, rows: list):
        self.rows = rows


# ---------------------------------------------------------------------------
# Impact Analyzer with Neo4j Integration
# ---------------------------------------------------------------------------

class ImpactAnalyzer:
    """
    Analyzes impact of changes using Neo4j graph data with PostgreSQL fallback.
    
    Features:
    - 60-second TTL cache for graph queries
    - Automatic fallback to PostgreSQL when Neo4j unavailable
    - Cache invalidation on repo ingestion completion
    """
    
    def __init__(self, graph_service_url: str, pg_cfg: dict):
        """
        Initialize Impact Analyzer with Neo4j gRPC client and PostgreSQL config.
        
        Args:
            graph_service_url: gRPC endpoint (e.g., "graph-service:50051")
            pg_cfg: PostgreSQL connection config for fallback queries
        """
        self.graph_service_url = graph_service_url
        self.pg_cfg = pg_cfg
        self._channel = grpc.aio.insecure_channel(graph_service_url)
        self._grpc_stub = services_pb2_grpc.GraphServiceStub(self._channel)
        self._cache: dict[str, tuple[Any, float]] = {}
        self._cache_ttl: int = 60
    
    async def _get_dependency_edges(self, repo: str) -> list[tuple[str, str, str]]:
        """
        Get dependency edges from Neo4j with cache and PostgreSQL fallback.
        
        Returns list of (source, target, type) tuples for BFS traversal.
        Cache key: f"edges:{repo}"
        """
        cache_key = f"edges:{repo}"
        
        # Check cache first
        if cache_key in self._cache:
            data, expiry = self._cache[cache_key]
            if time.time() < expiry:
                return data
        
        # Query Neo4j via gRPC
        cypher = "MATCH (s:Service {repo: $repo})-[r:DEPENDENCY]->(t:Service) RETURN s.service_name AS source, t.service_name AS target, r.dependency_type AS type"
        try:
            request = QueryGraphRequest(cypher=cypher, params={"repo": repo})
            response = await self._grpc_stub.QueryGraph(request, timeout=5.0)
            edges = [(row["source"], row["target"], row["type"]) for row in response.rows]
            self._cache[cache_key] = (edges, time.time() + self._cache_ttl)
            return edges
        except grpc.RpcError as e:
            log.warning(
                f"Neo4j _get_dependency_edges failed for {repo}, using PostgreSQL fallback: "
                f"{e.code()} {e.details()}"
            )
            return await self._get_dependency_edges_from_postgres(repo)
    
    async def _get_dependency_edges_from_postgres(self, repo: str) -> list[tuple[str, str, str]]:
        """
        PostgreSQL fallback for dependency edges.
        
        Queries meta.graph_nodes with self-join on depends_on property.
        Defaults type to "runtime" when NULL.
        """
        try:
            with psycopg2.connect(**self.pg_cfg) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT 
                            n1.label AS source,
                            n2.label AS target,
                            COALESCE(n1.properties->>'dependency_type', 'runtime') AS type
                        FROM meta.graph_nodes n1
                        JOIN meta.graph_nodes n2 
                            ON (n1.properties->>'depends_on') = n2.label
                        WHERE n1.repo = %s AND n2.repo = %s
                        """,
                        (repo, repo),
                    )
                    rows = cur.fetchall()
                    return [(row["source"], row["target"], row["type"]) for row in rows]
        except Exception as exc:
            log.error(f"PostgreSQL fallback failed for _get_dependency_edges: {exc}")
            return []
    
    async def _get_service_node(self, repo: str, service_name: str) -> dict | None:
        """
        Get service node from Neo4j with cache and PostgreSQL fallback.
        
        Cache key: f"service:{repo}:{service_name}"
        """
        cache_key = f"service:{repo}:{service_name}"
        
        # Check cache first
        if cache_key in self._cache:
            data, expiry = self._cache[cache_key]
            if time.time() < expiry:
                return data
        
        # Query Neo4j via gRPC
        cypher = "MATCH (s:Service {service_name: $name, repo: $repo}) RETURN s"
        try:
            request = QueryGraphRequest(
                cypher=cypher,
                params={"name": service_name, "repo": repo}
            )
            response = await self._grpc_stub.QueryGraph(request, timeout=5.0)
            node = response.rows[0]["s"] if response.rows else None
            self._cache[cache_key] = (node, time.time() + self._cache_ttl)
            return node
        except grpc.RpcError as e:
            log.warning(
                f"Neo4j _get_service_node failed for {repo}, using PostgreSQL fallback: "
                f"{e.code()} {e.details()}"
            )
            return await self._get_service_node_from_postgres(repo, service_name)
    
    async def _get_service_node_from_postgres(self, repo: str, service_name: str) -> dict | None:
        """PostgreSQL fallback for service node query."""
        try:
            with psycopg2.connect(**self.pg_cfg) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT properties
                        FROM meta.graph_nodes
                        WHERE repo = %s AND label = %s AND node_type = 'service'
                        LIMIT 1
                        """,
                        (repo, service_name),
                    )
                    row = cur.fetchone()
                    return dict(row["properties"]) if row else None
        except Exception as exc:
            log.error(f"PostgreSQL fallback failed for _get_service_node: {exc}")
            return None
    
    async def _get_api_nodes(self, repo: str, path_fragment: str) -> list[dict]:
        """
        Get API nodes matching path fragment from Neo4j with PostgreSQL fallback.
        
        No caching (query is parameterized by path_fragment).
        """
        cypher = "MATCH (a:API {repo: $repo}) WHERE a.path CONTAINS $path_fragment RETURN a"
        try:
            request = QueryGraphRequest(
                cypher=cypher,
                params={"repo": repo, "path_fragment": path_fragment}
            )
            response = await self._grpc_stub.QueryGraph(request, timeout=5.0)
            return [row["a"] for row in response.rows]
        except grpc.RpcError as e:
            log.warning(
                f"Neo4j _get_api_nodes failed for {repo}, using PostgreSQL fallback: "
                f"{e.code()} {e.details()}"
            )
            return await self._get_api_nodes_from_postgres(repo, path_fragment)
    
    async def _get_api_nodes_from_postgres(self, repo: str, path_fragment: str) -> list[dict]:
        """PostgreSQL fallback for API nodes query."""
        try:
            with psycopg2.connect(**self.pg_cfg) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT properties
                        FROM meta.graph_nodes
                        WHERE repo = %s 
                          AND node_type = 'api'
                          AND properties->>'path' LIKE %s
                        """,
                        (repo, f"%{path_fragment}%"),
                    )
                    rows = cur.fetchall()
                    return [dict(row["properties"]) for row in rows]
        except Exception as exc:
            log.error(f"PostgreSQL fallback failed for _get_api_nodes: {exc}")
            return []
    
    async def get_dependency_graph(self, repo: str) -> dict[str, Any]:
        """
        Get full dependency graph for repo from Neo4j.
        
        Uses 10s timeout (longer than other queries).
        Returns dict with nodes and edges lists.
        """
        cypher = "MATCH (n)-[r]->(m) WHERE n.repo = $repo RETURN n, r, m"
        try:
            request = QueryGraphRequest(cypher=cypher, params={"repo": repo})
            response = await self._grpc_stub.QueryGraph(request, timeout=10.0)
            
            nodes = {}
            edges = []
            
            for row in response.rows:
                n = row["n"]
                m = row["m"]
                r = row["r"]
                
                # Add nodes (deduplicate by node_id)
                if n.get("node_id") and n["node_id"] not in nodes:
                    nodes[n["node_id"]] = n
                if m.get("node_id") and m["node_id"] not in nodes:
                    nodes[m["node_id"]] = m
                
                # Add edge
                edges.append({
                    "source": n.get("service_name") or n.get("node_id"),
                    "target": m.get("service_name") or m.get("node_id"),
                    "type": r.get("edge_type", "unknown"),
                })
            
            return {
                "nodes": list(nodes.values()),
                "edges": edges,
            }
        except grpc.RpcError as e:
            log.warning(
                f"Neo4j get_dependency_graph failed for {repo}, using PostgreSQL fallback: "
                f"{e.code()} {e.details()}"
            )
            return await self._get_dependency_graph_from_postgres(repo)
    
    async def _get_dependency_graph_from_postgres(self, repo: str) -> dict[str, Any]:
        """PostgreSQL fallback for full dependency graph."""
        try:
            with psycopg2.connect(**self.pg_cfg) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # Get all nodes
                    cur.execute(
                        """
                        SELECT node_id, node_type, label, properties
                        FROM meta.graph_nodes
                        WHERE repo = %s
                        """,
                        (repo,),
                    )
                    nodes = [dict(row) for row in cur.fetchall()]
                    
                    # Build edges from depends_on properties
                    edges = []
                    for node in nodes:
                        depends_on = node.get("properties", {}).get("depends_on")
                        if depends_on:
                            edges.append({
                                "source": node["label"],
                                "target": depends_on,
                                "type": "runtime",
                            })
                    
                    return {"nodes": nodes, "edges": edges}
        except Exception as exc:
            log.error(f"PostgreSQL fallback failed for get_dependency_graph: {exc}")
            return {"nodes": [], "edges": []}
    
    def invalidate_cache(self, repo: str) -> None:
        """
        Invalidate all cache entries for a repo.
        
        Deletes keys matching f":{repo}:" or ending with f":{repo}".
        Logs INFO with count of deleted entries.
        """
        keys_to_delete = [
            key for key in self._cache.keys()
            if f":{repo}:" in key or key.endswith(f":{repo}")
        ]
        
        for key in keys_to_delete:
            del self._cache[key]
        
        log.info(f"Invalidated {len(keys_to_delete)} cache entries for repo {repo}")
    
    async def analyze_impact(
        self,
        *,
        change_description: str,
        repo: str,
        service_id: Optional[str] = None,
        endpoint: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Analyze the impact of a proposed change using Neo4j graph data.
        
        Uses graph data + LLM to explain downstream impact.
        """
        # Step 1: Get dependency edges from Neo4j
        edges = await self._get_dependency_edges(repo)
        
        # Step 2: Build impacted entities list
        impacted = await self._propagate_impact(
            repo=repo,
            edges=edges,
            service_id=service_id,
            endpoint=endpoint,
        )
        
        # Step 3: Build dependency paths
        paths = self._build_dependency_paths(edges, service_id)
        
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
        
        analysis["dependency_graph"] = {"edges": edges}
        analysis["raw_impacted"] = impacted
        analysis["dependency_paths"] = paths
        
        return analysis
    
    async def simulate_failure_cascade(
        self,
        *,
        failing_service: str,
        repo: str,
    ) -> Dict[str, Any]:
        """
        Simulate a failure cascade using Neo4j dependency edges.
        
        Uses BFS on the dependency graph from Neo4j.
        """
        edges = await self._get_dependency_edges(repo)
        
        # Build adjacency list from edges
        graph: Dict[str, List[str]] = {}
        all_services = set()
        for source, target, _ in edges:
            graph.setdefault(source, []).append(target)
            all_services.add(source)
            all_services.add(target)
        
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
                    "total_services": len(all_services),
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
            "total_services": len(all_services),
            "blast_radius_pct": round(
                len(cascade_order) / max(len(all_services), 1) * 100, 1
            ),
            "explanation": explanation,
        }
    
    async def _propagate_impact(
        self,
        repo: str,
        edges: list[tuple[str, str, str]],
        service_id: Optional[str],
        endpoint: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Build list of impacted entities from dependency edges."""
        impacted = []
        
        # Build set of services that depend on the changed service
        dependent_services = set()
        for source, target, _ in edges:
            if service_id and target == service_id:
                dependent_services.add(source)
        
        # For each dependent service, check if it uses the endpoint
        for svc_name in dependent_services:
            if endpoint:
                # Check if service has API nodes that match the endpoint
                api_nodes = await self._get_api_nodes(repo, endpoint)
                if any(node.get("service_name") == svc_name for node in api_nodes):
                    impacted.append({
                        "entity": svc_name,
                        "type": "service",
                        "reason": f"Consumes endpoint {endpoint}",
                        "severity": "high",
                    })
                    continue
            
            impacted.append({
                "entity": svc_name,
                "type": "service",
                "reason": f"Depends on {service_id}",
                "severity": "medium",
            })
        
        return impacted
    
    def _build_dependency_paths(
        self,
        edges: list[tuple[str, str, str]],
        service_id: Optional[str],
    ) -> List[str]:
        """Build human-readable dependency path descriptions."""
        paths = []
        
        # Group by source service
        by_source: dict[str, list[str]] = {}
        for source, target, dep_type in edges:
            by_source.setdefault(source, []).append(f"{target} ({dep_type})")
        
        for source, targets in by_source.items():
            paths.append(f"{source} → {', '.join(targets)}")
        
        if not paths:
            paths.append("No dependency data available yet. Run ingestion to populate the graph.")
        
        return paths


# ---------------------------------------------------------------------------
# Legacy function wrappers for backward compatibility
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
    Legacy wrapper for analyze_impact.
    
    NOTE: This is synchronous and doesn't use Neo4j.
    New code should use ImpactAnalyzer class directly.
    """
    # Fallback to old PostgreSQL-only implementation
    deps = _query_dependencies_from_db(pg_cfg, repo, service_id)
    impacted = _propagate_impact_legacy(deps, service_id, endpoint)
    paths = _build_dependency_paths_legacy(deps, service_id)
    
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
    Legacy wrapper for simulate_failure_cascade.
    
    NOTE: This is synchronous and doesn't use Neo4j.
    New code should use ImpactAnalyzer class directly.
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
    """
    Legacy wrapper for get_dependency_graph.
    
    NOTE: This is synchronous and doesn't use Neo4j.
    New code should use ImpactAnalyzer class directly.
    """
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
# Legacy internal helpers
# ---------------------------------------------------------------------------

def _query_dependencies_from_db(
    pg_cfg: Dict[str, Any],
    repo: str,
    service_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Query dependency information from PostgreSQL.
    (Legacy implementation for backward compatibility.)
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


def _propagate_impact_legacy(
    deps: Dict[str, Any],
    service_id: Optional[str],
    endpoint: Optional[str],
) -> List[Dict[str, Any]]:
    """Build list of impacted entities from dependency data (legacy)."""
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


def _build_dependency_paths_legacy(
    deps: Dict[str, Any],
    service_id: Optional[str],
) -> List[str]:
    """Build human-readable dependency path descriptions (legacy)."""
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
