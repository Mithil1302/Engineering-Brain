from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import List

from .models import (
    ArchitectureDecision,
    ArchitecturePlan,
    ArchitecturePlanRequest,
    InfrastructureBlueprint,
    ScaffoldArtifact,
    ServiceBlueprint,
)


def _tags(text: str) -> List[str]:
    t = text.lower()
    tags = []
    mapping = {
        "api": ["api", "rest", "graphql", "endpoint"],
        "event_driven": ["event", "queue", "stream", "kafka"],
        "batch": ["batch", "schedule", "cron"],
        "ui": ["dashboard", "frontend", "ui", "portal"],
        "ml": ["model", "ml", "inference", "prediction"],
        "compliance": ["audit", "compliance", "governance", "policy"],
    }
    for tag, keys in mapping.items():
        if any(k in t for k in keys):
            tags.append(tag)
    return sorted(set(tags))


def _stable_plan_id(request: ArchitecturePlanRequest, tags: List[str]) -> str:
    seed = json.dumps(
        {
            "repo": request.repo,
            "pr": request.pr_number,
            "req": request.requirement.requirement_text,
            "tags": tags,
            "ts": datetime.now(timezone.utc).strftime("%Y%m%d"),
        },
        sort_keys=True,
    )
    return "arch-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def generate_architecture_plan(request: ArchitecturePlanRequest) -> ArchitecturePlan:
    req = request.requirement
    tags = _tags(req.requirement_text)

    decisions: List[ArchitectureDecision] = [
        ArchitectureDecision(
            title="Bounded service decomposition",
            rationale="Split responsibilities by domain capability to reduce coupling and improve deployability.",
            tradeoffs=["More service boundaries increase operational overhead", "Requires stronger contract governance"],
        )
    ]

    services: List[ServiceBlueprint] = [
        ServiceBlueprint(
            name="policy-worker",
            role="asynchronous policy and governance processing",
            language="python",
            runtime="container",
            interfaces=["kafka:repo.events", "kafka:pr.checks"],
        )
    ]

    infra: List[InfrastructureBlueprint] = [
        InfrastructureBlueprint(resource="kafka", purpose="event ingestion and orchestration", sku="standard"),
        InfrastructureBlueprint(resource="postgres", purpose="state, audit and run snapshots", sku="general-purpose"),
    ]

    if "api" in tags:
        services.append(
            ServiceBlueprint(
                name="gateway-api",
                role="public synchronous API facade",
                language="python",
                runtime="container",
                interfaces=["http:/architecture/plan", "http:/policy/dashboard/*"],
            )
        )
        decisions.append(
            ArchitectureDecision(
                title="API facade for orchestration entry",
                rationale="Expose strongly typed endpoints for architecture planning and governance operations.",
                tradeoffs=["Requires API versioning", "Needs authz model from day one"],
            )
        )

    if "event_driven" in tags:
        infra.append(InfrastructureBlueprint(resource="event-topics", purpose="routing async workflows", sku="partitioned"))
        decisions.append(
            ArchitectureDecision(
                title="Event-first orchestration",
                rationale="Drive long-running tasks by durable events for resilience and replayability.",
                tradeoffs=["Eventual consistency", "Operational observability complexity"],
            )
        )

    if "ui" in tags:
        services.append(
            ServiceBlueprint(
                name="knowledge-dashboard-ui",
                role="interactive health and workflow visualization",
                language="html/js",
                runtime="static",
                interfaces=["http:/policy/dashboard/ui", "http:/policy/dashboard/*"],
            )
        )

    if "compliance" in tags:
        decisions.append(
            ArchitectureDecision(
                title="Governance enforcement with waiver chain",
                rationale="Combine policy templates with formal waivers to maintain controls while enabling controlled exceptions.",
                tradeoffs=["Approval latency", "Requires strict audit data quality"],
            )
        )

    artifacts = [
        ScaffoldArtifact(
            file_path="architecture/decisions/ADR-0001-service-boundaries.md",
            content=(
                "# ADR-0001: Service Boundaries\n\n"
                "- Decision: Bounded service decomposition\n"
                "- Rationale: Improve deployability and separation of concerns\n"
            ),
            content_type="text/markdown",
        ),
        ScaffoldArtifact(
            file_path="infrastructure/scaffold/stack.summary.json",
            content=json.dumps(
                {
                    "services": [s.model_dump() for s in services],
                    "infrastructure": [i.model_dump() for i in infra],
                },
                indent=2,
            ),
            content_type="application/json",
        ),
    ]

    return ArchitecturePlan(
        plan_id=_stable_plan_id(request, tags),
        requirement=req,
        intent_tags=tags,
        decisions=decisions,
        services=services,
        infrastructure=infra,
        artifacts=artifacts,
    )
