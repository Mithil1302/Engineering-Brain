from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ArchitectureRequirement(BaseModel):
    requirement_text: str = Field(min_length=10)
    domain: Optional[str] = None
    non_functional: Dict[str, str] = Field(default_factory=dict)
    constraints: Dict[str, str] = Field(default_factory=dict)
    team: Optional[str] = None
    target_cloud: str = "generic"


class ConstraintType(str, Enum):
    TRAFFIC_RPM = "traffic_rpm"
    TEAM_SIZE = "team_size"
    LATENCY_SLA_MS = "latency_sla_ms"
    COMPLIANCE = "compliance"
    AVAILABILITY_SLA = "availability_sla"
    BUDGET_MONTHLY = "budget_monthly"
    GEO = "geo"
    DATA_RESIDENCY = "data_residency"
    TECH_PREFERENCE = "tech_preference"
    TECH_PROHIBITION = "tech_prohibition"
    TIMELINE = "timeline"
    UNKNOWN = "unknown"


class Constraint(BaseModel):
    type: ConstraintType
    value: Any
    confidence: float = Field(ge=0.0, le=1.0)
    source_span: str = ""
    normalized_value: Optional[Any] = None
    units: Optional[str] = None
    priority: float = Field(default=0.5, ge=0.0, le=1.0)


class ConflictSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Conflict(BaseModel):
    conflict_id: str
    constraint_a: Constraint
    constraint_b: Constraint
    severity: ConflictSeverity
    reason: str
    resolution_options: List[str] = Field(default_factory=list)


class AmbiguityItem(BaseModel):
    field: str
    score: float = Field(ge=0.0, le=1.0)
    reason: str
    suggested_question: Optional[str] = None


class AmbiguityReport(BaseModel):
    overall_score: float = Field(ge=0.0, le=1.0)
    items: List[AmbiguityItem] = Field(default_factory=list)


class ClarificationQuestion(BaseModel):
    question_id: str
    question: str
    priority: float = Field(ge=0.0, le=1.0)
    target_field: str
    reason: str


class ConstraintSet(BaseModel):
    constraints: List[Constraint] = Field(default_factory=list)
    conflicts: List[Conflict] = Field(default_factory=list)
    ambiguity_report: AmbiguityReport = Field(default_factory=lambda: AmbiguityReport(overall_score=0.0, items=[]))
    clarification_questions: List[ClarificationQuestion] = Field(default_factory=list)


class DecisionDimension(str, Enum):
    OPERATIONAL_COMPLEXITY = "operational_complexity"
    LEARNING_CURVE = "learning_curve"
    ECOSYSTEM_MATURITY = "ecosystem_maturity"
    HORIZONTAL_SCALABILITY = "horizontal_scalability"
    TEAM_FAMILIARITY = "team_familiarity"
    LATENCY_FIT = "latency_fit"
    COMPLIANCE_FIT = "compliance_fit"
    COST_EFFICIENCY = "cost_efficiency"


class CandidateScore(BaseModel):
    candidate: str
    category: str
    raw_scores: Dict[str, float] = Field(default_factory=dict)
    weighted_score: float = 0.0
    penalties: Dict[str, float] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)


class SensitivityDelta(BaseModel):
    candidate: str
    before: float
    after: float
    delta: float


class SensitivityAnalysis(BaseModel):
    changed_weights: Dict[str, float] = Field(default_factory=dict)
    deltas: List[SensitivityDelta] = Field(default_factory=list)
    winner_changed: bool = False


class StackDecisionResult(BaseModel):
    dimension_weights: Dict[str, float] = Field(default_factory=dict)
    candidate_scores: List[CandidateScore] = Field(default_factory=list)
    winner: Optional[CandidateScore] = None
    alternatives_ranked: List[str] = Field(default_factory=list)
    why: Dict[str, Any] = Field(default_factory=dict)
    sensitivity_analysis: Optional[SensitivityAnalysis] = None


class RationaleDecision(BaseModel):
    decision_id: str
    title: str
    decision: str
    driving_constraints: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    alternatives_considered: List[str] = Field(default_factory=list)
    impact_if_constraint_changes: List[str] = Field(default_factory=list)
    tradeoffs: List[str] = Field(default_factory=list)


class ADRDocument(BaseModel):
    adr_id: str
    title: str
    status: str = "proposed"
    context: str
    decision: str
    alternatives: List[str] = Field(default_factory=list)
    consequences: str
    risks: List[str] = Field(default_factory=list)
    rollback_notes: str = ""
    markdown: str


class BlueprintNode(BaseModel):
    node_id: str
    node_type: str
    label: str
    attributes: Dict[str, Any] = Field(default_factory=dict)


class BlueprintEdge(BaseModel):
    src: str
    dst: str
    edge_type: str
    attributes: Dict[str, Any] = Field(default_factory=dict)


class BlueprintGraph(BaseModel):
    nodes: List[BlueprintNode] = Field(default_factory=list)
    edges: List[BlueprintEdge] = Field(default_factory=list)


class ArchitectureDiff(BaseModel):
    changed_constraints: List[str] = Field(default_factory=list)
    affected_nodes: List[str] = Field(default_factory=list)
    added_decisions: List[str] = Field(default_factory=list)
    removed_decisions: List[str] = Field(default_factory=list)
    changed_decisions: List[str] = Field(default_factory=list)
    summary: str = ""


class RefinePlanRequest(BaseModel):
    repo: str
    base_plan_id: int
    requirement_delta: Optional[str] = None
    constraint_overrides: Dict[str, Any] = Field(default_factory=dict)
    correlation_id: Optional[str] = None


class RefinePlanResponse(BaseModel):
    repo: str
    base_plan_id: int
    new_plan_id: int
    diff: ArchitectureDiff
    plan: Dict[str, Any]


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
    extracted_constraints: ConstraintSet = Field(default_factory=ConstraintSet)
    intent_tags: List[str] = Field(default_factory=list)
    decisions: List[ArchitectureDecision] = Field(default_factory=list)
    rationale_decisions: List[RationaleDecision] = Field(default_factory=list)
    blueprint_graph: BlueprintGraph = Field(default_factory=BlueprintGraph)
    stack_decisions: Dict[str, StackDecisionResult] = Field(default_factory=dict)
    adrs: List[ADRDocument] = Field(default_factory=list)
    services: List[ServiceBlueprint] = Field(default_factory=list)
    infrastructure: List[InfrastructureBlueprint] = Field(default_factory=list)
    artifacts: List[ScaffoldArtifact] = Field(default_factory=list)
    produced_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ArchitecturePlanRequest(BaseModel):
    repo: str
    pr_number: Optional[int] = None
    correlation_id: Optional[str] = None
    requirement: ArchitectureRequirement
    constraints: Optional[List[str]] = None
    interactive: bool = False


class ArchitecturePlanResponse(BaseModel):
    repo: str
    pr_number: Optional[int] = None
    correlation_id: Optional[str] = None
    plan: ArchitecturePlan

PlanArtifact = ScaffoldArtifact
