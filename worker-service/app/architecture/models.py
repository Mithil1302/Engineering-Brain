from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ArchitectureRequirement(BaseModel):
    requirement_text: str = Field(min_length=10)
    domain: Optional[str] = None
    non_functional: Dict[str, str] = Field(default_factory=dict)
    constraints: Dict[str, str] = Field(default_factory=dict)
    team: Optional[str] = None
    target_cloud: str = "generic"


class ArchitectureDecision(BaseModel):
    title: str
    rationale: str
    tradeoffs: List[str] = Field(default_factory=list)


class ServiceBlueprint(BaseModel):
    name: str
    role: str
    language: str
    runtime: str
    interfaces: List[str] = Field(default_factory=list)


class InfrastructureBlueprint(BaseModel):
    resource: str
    purpose: str
    sku: Optional[str] = None


class ScaffoldArtifact(BaseModel):
    file_path: str
    content: str
    content_type: str = "text/plain"


class ArchitecturePlan(BaseModel):
    plan_id: str
    requirement: ArchitectureRequirement
    intent_tags: List[str] = Field(default_factory=list)
    decisions: List[ArchitectureDecision] = Field(default_factory=list)
    services: List[ServiceBlueprint] = Field(default_factory=list)
    infrastructure: List[InfrastructureBlueprint] = Field(default_factory=list)
    artifacts: List[ScaffoldArtifact] = Field(default_factory=list)
    produced_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ArchitecturePlanRequest(BaseModel):
    repo: str
    pr_number: Optional[int] = None
    correlation_id: Optional[str] = None
    requirement: ArchitectureRequirement


class ArchitecturePlanResponse(BaseModel):
    repo: str
    pr_number: Optional[int] = None
    correlation_id: Optional[str] = None
    plan: ArchitecturePlan

PlanArtifact = ScaffoldArtifact
