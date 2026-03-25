from __future__ import annotations

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
                    (repo, plan_id, __import__("json").dumps(graph_payload)),
                )
            conn.commit()
    except Exception:
        return
