from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class QARequest(BaseModel):
    question: str = Field(min_length=5)
    repo: Optional[str] = None
    pr_number: Optional[int] = None
    role: Optional[str] = None
    channel: Optional[str] = Field(default="web", description="web|chat|api|cli")


class QACitation(BaseModel):
    source: str
    reference: str
    details: Optional[str] = None


class QAResponse(BaseModel):
    answer: str
    confidence: float
    intent: str
    citations: List[QACitation] = Field(default_factory=list)
    evidence: Dict[str, Any] = Field(default_factory=dict)
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
