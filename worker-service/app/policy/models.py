from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Severity(str, Enum):
    HIGH = "high"
    MED = "med"
    LOW = "low"


class CheckStatus(str, Enum):
    FAIL = "fail"
    WARN = "warn"
    INFO = "info"
    PASS = "pass"


SEVERITY_TO_STATUS = {
    Severity.HIGH: CheckStatus.FAIL,
    Severity.MED: CheckStatus.WARN,
    Severity.LOW: CheckStatus.INFO,
}


class Citation(BaseModel):
    kind: str = Field(description="file|line|spec|entity|graph-path")
    reference: str
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    details: Optional[str] = None


class Finding(BaseModel):
    rule_id: str
    severity: Severity
    status: CheckStatus
    title: str
    description: str
    entity_refs: List[str] = Field(default_factory=list)
    evidence: List[Citation] = Field(default_factory=list)
    suggested_action: str
    detected_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    correlation_id: Optional[str] = None


class SuggestedPatch(BaseModel):
    patch_id: str
    patch_type: str = Field(description="doc_stub|config_tweak")
    file_path: str
    summary: str
    unified_diff: str
    citations: List[Citation] = Field(default_factory=list)


class RuleConfig(BaseModel):
    enabled: bool = True
    severity: Severity


class PolicyConfig(BaseModel):
    rule_pack: Optional[str] = Field(default=None, description="Policy pack id override, e.g. rules-v1")
    rules: Dict[str, RuleConfig] = Field(default_factory=dict)


class ChangedFile(BaseModel):
    path: str
    status: str
    patch: Optional[str] = None


class EndpointSpec(BaseModel):
    method: str
    path: str
    operation_id: Optional[str] = None
    owner: Optional[str] = None
    request_required_fields: List[str] = Field(default_factory=list)
    request_enum_fields: Dict[str, List[str]] = Field(default_factory=dict)
    response_fields: Dict[str, str] = Field(default_factory=dict)
    response_status_codes: List[str] = Field(default_factory=list)


class ServiceSpec(BaseModel):
    service_id: str
    endpoints: List[EndpointSpec] = Field(default_factory=list)


class ImpactEdge(BaseModel):
    edge_type: str
    src: str
    dst: str


class PolicyEvaluationRequest(BaseModel):
    repo: str
    pr_number: Optional[int] = None
    correlation_id: Optional[str] = None
    head_spec: ServiceSpec
    base_spec: Optional[ServiceSpec] = None
    changed_files: List[ChangedFile] = Field(default_factory=list)
    owners: Dict[str, str] = Field(default_factory=dict)
    docs_touched: List[str] = Field(default_factory=list)
    impact_edges: List[ImpactEdge] = Field(default_factory=list)
    config: Optional[PolicyConfig] = None


class PolicyEvaluationResponse(BaseModel):
    repo: str
    pr_number: Optional[int] = None
    summary_status: CheckStatus
    findings: List[Finding] = Field(default_factory=list)
    suggested_patches: List[SuggestedPatch] = Field(default_factory=list)
    citations: List[Citation] = Field(default_factory=list)
    markdown_comment: str
    check_annotations: List[Dict[str, Any]] = Field(default_factory=list)
