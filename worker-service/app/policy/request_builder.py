"""
request_builder.py — Build a PolicyEvaluationRequest from a raw Kafka payload.

Pure data-transformation: no Kafka, no DB, no side-effects.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .models import (
    ChangedFile,
    EndpointSpec,
    ImpactEdge,
    PolicyEvaluationRequest,
    ServiceSpec,
)


def build_request(
    payload: Dict[str, Any],
    default_service_id: str = "unknown-service",
) -> Optional[PolicyEvaluationRequest]:
    """
    Parse a raw Kafka repo-event payload into a PolicyEvaluationRequest.

    Returns None if the payload does not contain enough information to
    construct a valid request (e.g. missing repo identifier).
    """
    repo = payload.get("repo") or {}
    repo_id = repo.get("full_name") or repo.get("name_with_owner") or repo.get("id")
    if not repo_id:
        return None

    changed_files = [
        ChangedFile(
            path=f.get("path", "unknown"),
            status=f.get("status", "modified"),
        )
        for f in payload.get("changed_files", [])
    ]

    policy_ctx = payload.get("policy_context") or {}

    # Build head spec from explicit context or infer from event type
    if policy_ctx.get("head_spec"):
        head_spec = ServiceSpec.model_validate(policy_ctx["head_spec"])
    else:
        inferred_endpoint = EndpointSpec(
            method="POST" if payload.get("event_type") == "pull_request" else "GET",
            path=f"/inferred/{payload.get('event_type', 'event')}",
            operation_id=f"inferred_{payload.get('event_type', 'event')}",
            owner=payload.get("owner") or None,
            request_required_fields=[],
            request_enum_fields={},
            response_fields={"status": "string"},
            response_status_codes=["200"],
        )
        head_spec = ServiceSpec(
            service_id=default_service_id,
            endpoints=[inferred_endpoint],
        )

    base_spec = None
    if policy_ctx.get("base_spec"):
        base_spec = ServiceSpec.model_validate(policy_ctx["base_spec"])

    impact_edges = []
    for edge in policy_ctx.get("impact_edges", []):
        try:
            impact_edges.append(ImpactEdge.model_validate(edge))
        except Exception:
            continue

    pr = payload.get("pull_request") or {}
    pr_number = pr.get("number")

    return PolicyEvaluationRequest(
        repo=repo_id,
        pr_number=pr_number,
        correlation_id=payload.get("correlation_id"),
        head_spec=head_spec,
        base_spec=base_spec,
        changed_files=changed_files,
        owners=policy_ctx.get("owners") or {},
        docs_touched=policy_ctx.get("docs_touched") or [],
        impact_edges=impact_edges,
        config=policy_ctx.get("config"),
    )
