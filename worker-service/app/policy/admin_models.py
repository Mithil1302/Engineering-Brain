from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class PolicyTemplateUpsertRequest(BaseModel):
    template_name: str
    scope_type: str = Field(description="org|team|repo")
    scope_value: str
    rule_pack: Optional[str] = None
    rules: dict = Field(default_factory=dict)
    fail_blocks_merge: bool = True
    warn_blocks_merge: bool = False
    no_docs_no_merge: bool = False
    metadata: dict = Field(default_factory=dict)
    enabled: bool = True
    priority: int = 100


class WaiverRequest(BaseModel):
    repo: str
    pr_number: int
    rule_set: str = "rules-v1"
    requested_by: str
    requested_role: str
    reason: str
    expires_at: str
    required_approvals: int = 1
    approval_chain: list[str] = Field(default_factory=list)
    scope: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)


class WaiverDecisionRequest(BaseModel):
    decision: str = Field(description="approve|reject")
    approver: str
    approver_role: str
    notes: Optional[str] = None


class RetryDeadLetterRequeueRequest(BaseModel):
    reset_attempt: bool = True
