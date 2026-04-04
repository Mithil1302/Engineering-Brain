from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List

import psycopg2
from psycopg2.extras import RealDictCursor


def fetch_existing_services(pg_cfg: Dict[str, Any], repo: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        with psycopg2.connect(**pg_cfg) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT plan
                    FROM meta.architecture_plan_runs
                    WHERE repo = %s
                    ORDER BY id DESC
                    LIMIT 20
                    """,
                    (repo,),
                )
                for r in cur.fetchall():
                    plan = r.get("plan") or {}
                    if isinstance(plan, dict):
                        rows.extend(plan.get("services") or [])
    except Exception:
        return []
    return rows


def persist_graph_projection(pg_cfg: Dict[str, Any], repo: str, plan_id: int, graph_payload: Dict[str, Any]) -> None:
    try:
        with psycopg2.connect(**pg_cfg) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE SCHEMA IF NOT EXISTS meta;
                    CREATE TABLE IF NOT EXISTS meta.architecture_graph_projection (
                        id BIGSERIAL PRIMARY KEY,
                        repo TEXT NOT NULL,
                        plan_id BIGINT NOT NULL,
                        graph JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                    """
                )
                cur.execute(
                    "INSERT INTO meta.architecture_graph_projection (repo, plan_id, graph) VALUES (%s,%s,%s::jsonb)",
                    (repo, plan_id, json.dumps(graph_payload)),
                )
            conn.commit()
    except Exception:
        return


def persist_autofix_graph_node(
    neo4j_driver: Any,
    *,
    fix_id: int,
    repo: str,
    finding_id: str,
    fix_type: str,
    graph_node_ids: List[str],
    pr_url: str,
    confidence: float,
) -> None:
    """
    Write an AutofixRun node into Neo4j and create FIXES relationships
    to each affected entity node. This is the traceability link that
    satisfies the spec requirement: every fix is traced back to the
    corresponding node in the knowledge graph.

    Node schema:
        (:AutofixRun {
            id, repo, finding_id, fix_type, pr_url,
            confidence, created_at
        })

    Edges:
        (:AutofixRun)-[:FIXES]->(:Entity {id: graph_node_id})

    The target entity nodes are MERGED (created if absent) so the
    relationship is always established even if the entity was not yet
    ingested via the normal mutation pipeline.
    """
    if neo4j_driver is None:
        return

    now = datetime.now(timezone.utc).isoformat()
    autofix_node_id = f"autofix:{repo}:{fix_id}"

    try:
        with neo4j_driver.session() as session:
            # Upsert the AutofixRun node
            session.run(
                """
                MERGE (a:AutofixRun {id: $autofix_id})
                SET a.fix_id       = $fix_id,
                    a.repo         = $repo,
                    a.finding_id   = $finding_id,
                    a.fix_type     = $fix_type,
                    a.pr_url       = $pr_url,
                    a.confidence   = $confidence,
                    a.created_at   = datetime($created_at)
                """,
                autofix_id=autofix_node_id,
                fix_id=fix_id,
                repo=repo,
                finding_id=finding_id,
                fix_type=fix_type,
                pr_url=pr_url or "",
                confidence=confidence,
                created_at=now,
            )

            # Create FIXES edges to each affected graph entity
            for node_id in graph_node_ids:
                # Determine label from node_id prefix (service:, endpoint:, etc.)
                label = _label_from_node_id(node_id)
                session.run(
                    f"""
                    MERGE (e:{label} {{id: $entity_id}})
                    ON CREATE SET e.created_at = datetime($now)
                    WITH e
                    MATCH (a:AutofixRun {{id: $autofix_id}})
                    MERGE (a)-[:FIXES]->(e)
                    """,
                    entity_id=node_id,
                    autofix_id=autofix_node_id,
                    now=now,
                )
    except Exception:
        # Graph traceability is best-effort — never block the fix flow
        return


def _label_from_node_id(node_id: str) -> str:
    """Derive a Neo4j label from the node_id prefix convention."""
    prefix_map = {
        "service:": "Service",
        "endpoint:": "Endpoint",
        "decision:": "Decision",
        "adr:": "ADR",
        "constraint:": "Constraint",
        "autofix:": "AutofixRun",
        "repo:": "Repo",
        "file:": "File",
    }
    for prefix, label in prefix_map.items():
        if node_id.startswith(prefix):
            return label
    return "Entity"
