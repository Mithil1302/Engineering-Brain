from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class QARequest(BaseModel):
    question: str = Field(min_length=3)
    repo: Optional[str] = None
    pr_number: Optional[int] = None
    role: Optional[str] = None
    channel: Optional[str] = Field(default="web", description="web|chat|api|cli")


class QAConversationRequest(BaseModel):
    """Multi-turn conversation request."""
    question: str = Field(min_length=3)
    repo: Optional[str] = None
    pr_number: Optional[int] = None
    role: Optional[str] = None
    conversation_id: Optional[str] = None
    history: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Previous turns: [{'role': 'user'|'assistant', 'content': '...'}]",
    )


class SourceCitation(BaseModel):
    """Attribution for a claim in the answer."""
    source_ref: str
    source_type: str = Field(description="policy_run|doc|graph_node|health_snapshot|waiver|code")
    relevance: str = Field(default="direct", description="direct|supporting|background")
    chunk_preview: Optional[str] = None


class QACitation(BaseModel):
    source: str
    reference: str
    details: Optional[str] = None


class QAResponse(BaseModel):
    answer: str
    confidence: float
    intent: str
    original_question: str
    rewritten_question: str | None = None
    citations: List[QACitation] = Field(default_factory=list)
    source_citations: List[SourceCitation] = Field(default_factory=list)
    source_breakdown: Dict[str, int] = Field(default_factory=dict)
    evidence_policy: str = Field(default="citations_required")
    evidence: Dict[str, Any] = Field(default_factory=dict)
    follow_up_questions: List[str] = Field(default_factory=list)
    chain_steps: List[Dict[str, Any]] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class QASearchRequest(BaseModel):
    """Semantic search over the knowledge base."""
    query: str = Field(min_length=3)
    repo: Optional[str] = None
    source_types: Optional[List[str]] = None
    top_k: int = Field(default=10, ge=1, le=50)


class QASearchResult(BaseModel):
    """One search hit."""
    chunk_id: int
    source_type: str
    source_ref: str
    chunk_text: str
    score: float
    metadata: Dict[str, Any] = Field(default_factory=dict)


class QASearchResponse(BaseModel):
    results: List[QASearchResult] = Field(default_factory=list)
    query: str
    total: int = 0
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
