from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from psycopg2.extras import RealDictCursor


def build_architecture_explorer(
    *,
    repo: str,
    pr_number: Optional[int],
    db_conn_factory: Callable[[], Any],
    ensure_arch_schema: Callable[[], None],
) -> Dict[str, Any]:
    ensure_arch_schema()

    with db_conn_factory() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT *
                FROM meta.architecture_plan_runs
                WHERE repo = %s
                  AND (%s IS NULL OR pr_number = %s)
                ORDER BY id DESC
                LIMIT 1
                """,
                (repo, pr_number, pr_number),
            )
            row = cur.fetchone()

    if row is None:
        return {
            "repo": repo,
            "pr_number": pr_number,
            "has_plan": False,
            "message": "No architecture plan found for the selected scope.",
            "graph": {"nodes": [], "edges": []},
        }

    latest = dict(row)
    services = latest.get("services") or []
    infrastructure = latest.get("infrastructure") or []

    nodes = []
    edges = []
    node_ids = set()

    def _add_node(node_id: str, label: str, node_type: str, meta: Optional[dict] = None):
        if node_id in node_ids:
            return
        node_ids.add(node_id)
        nodes.append({"id": node_id, "label": label, "type": node_type, "meta": meta or {}})

    _add_node(f"repo:{repo}", repo, "repo", {"pr_number": latest.get("pr_number")})

    for svc in services:
        name = str((svc or {}).get("name") or "unknown-service")
        svc_id = f"service:{name}"
        _add_node(
            svc_id,
            name,
            "service",
            {
                "role": (svc or {}).get("role"),
                "language": (svc or {}).get("language"),
                "runtime": (svc or {}).get("runtime"),
                "interfaces": (svc or {}).get("interfaces") or [],
            },
        )
        edges.append({"from": f"repo:{repo}", "to": svc_id, "kind": "contains"})

    for infra in infrastructure:
        resource = str((infra or {}).get("resource") or "unknown-resource")
        infra_id = f"infra:{resource}"
        _add_node(
            infra_id,
            resource,
            "infrastructure",
            {
                "purpose": (infra or {}).get("purpose"),
                "sku": (infra or {}).get("sku"),
            },
        )
        edges.append({"from": f"repo:{repo}", "to": infra_id, "kind": "provisions"})

    known_service_names = {str((s or {}).get("name") or "") for s in services}
    for svc in services:
        svc_name = str((svc or {}).get("name") or "unknown-service")
        svc_id = f"service:{svc_name}"
        interfaces = (svc or {}).get("interfaces") or []
        for idx, api in enumerate(interfaces):
            api_text = str(api)
            api_id = f"api:{svc_name}:{idx}"
            _add_node(api_id, api_text, "api", {"service": svc_name})
            edges.append({"from": svc_id, "to": api_id, "kind": "exposes"})

            lower_api = api_text.lower()
            if lower_api.startswith("kafka:") or lower_api.startswith("queue:"):
                topic = api_text.split(":", 1)[1] if ":" in api_text else api_text
                dep_id = f"event:{topic}"
                _add_node(dep_id, topic, "dependency", {"protocol": "event"})
                edges.append({"from": svc_id, "to": dep_id, "kind": "depends_on"})
            if lower_api.startswith("http:"):
                edges.append({"from": svc_id, "to": api_id, "kind": "http"})

        for candidate in known_service_names:
            if candidate and candidate != svc_name:
                normalized = candidate.lower()
                if any(normalized in str(itf).lower() for itf in interfaces):
                    edges.append({"from": svc_id, "to": f"service:{candidate}", "kind": "depends_on"})

    return {
        "repo": repo,
        "pr_number": latest.get("pr_number"),
        "has_plan": True,
        "plan": {
            "id": latest.get("plan_id"),
            "status": latest.get("status"),
            "created_at": latest.get("created_at"),
            "intent_tags": latest.get("intent_tags") or [],
            "decisions": latest.get("decisions") or [],
            "requirement": latest.get("requirement") or {},
        },
        "graph": {
            "nodes": nodes,
            "edges": edges,
        },
    }
