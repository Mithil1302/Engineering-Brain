
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..dependencies import (
    PG_CFG, auth_read_scoped, enforce_repo_scope, AuthContext,
    llm_client, embedding_store,
)
from ..llm import get_llm_client

router = APIRouter()

from ..qa.models import QARequest, QAConversationRequest, QASearchRequest, QASearchResponse, QASearchResult
from ..qa.assistant import answer_question, answer_conversation, semantic_search
from ..qa.gap_detector import GapDetector


@router.post("/assistant/ask")
def assistant_ask(request: QARequest, auth: AuthContext = Depends(auth_read_scoped)):
    """Single-turn Q&A with LLM RAG pipeline."""
    if not request.repo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="repo is required")
    enforce_repo_scope(auth, request.repo)
    return answer_question(request, PG_CFG, embedding_store=embedding_store).model_dump()


@router.post("/assistant/conversation")
def assistant_conversation(
    request: QAConversationRequest,
    auth: AuthContext = Depends(auth_read_scoped),
):
    """Multi-turn conversation with context-aware follow-ups."""
    if not request.repo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="repo is required")
    enforce_repo_scope(auth, request.repo)
    return answer_conversation(
        question=request.question,
        history=request.history,
        repo=request.repo,
        pg_cfg=PG_CFG,
        session_id=request.conversation_id,
    ).model_dump()


@router.post("/assistant/search")
def assistant_search(
    request: QASearchRequest,
    auth: AuthContext = Depends(auth_read_scoped),
):
    """Semantic search over the knowledge base embeddings."""
    if not request.repo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="repo is required")
    enforce_repo_scope(auth, request.repo)
    results = semantic_search(
        request.query,
        embedding_store,
        source_types=request.source_types,
        top_k=request.top_k,
    )
    return QASearchResponse(
        results=[QASearchResult(**r) for r in results],
        query=request.query,
        total=len(results),
    ).model_dump()


@router.get("/assistant/health")
def assistant_health(auth: AuthContext = Depends(auth_read_scoped)):
    """LLM and embedding health status."""
    return {
        "llm": llm_client.health(),
        "embeddings": embedding_store.count() if embedding_store else 0,
    }


@router.get("/qa/gaps")
def get_documentation_gaps(
    repo: str,
    days: int = Query(default=7, ge=1, le=365),
    auth: AuthContext = Depends(auth_read_scoped),
):
    """Detect documentation gaps by analyzing QA event logs.
    
    Args:
        repo: Repository name to analyze
        days: Number of days to look back (1-365, default 7)
        auth: Authentication context
        
    Returns:
        GapReport with detected gaps, service grouping, and documentation debt score
    """
    if not repo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="repo is required")
    enforce_repo_scope(auth, repo)
    
    # Instantiate per request to avoid stale connections
    detector = GapDetector(PG_CFG, get_llm_client())
    report = detector.generate_gap_report(repo, lookback_days=days)
    
    return {
        "repo": report.repo,
        "generated_at": report.generated_at.isoformat(),
        "total_gaps": report.total_gaps,
        "gaps_by_service": {
            service: [
                {
                    "question_sample": gap.question_sample,
                    "intent": gap.intent,
                    "frequency": gap.frequency,
                    "avg_confidence": gap.avg_confidence,
                    "suggested_doc_title": gap.suggested_doc_title,
                    "suggested_doc_location": gap.suggested_doc_location,
                    "gap_severity": gap.gap_severity,
                }
                for gap in gaps
            ]
            for service, gaps in report.gaps_by_service.items()
        },
        "top_gaps": [
            {
                "question_sample": gap.question_sample,
                "intent": gap.intent,
                "frequency": gap.frequency,
                "avg_confidence": gap.avg_confidence,
                "suggested_doc_title": gap.suggested_doc_title,
                "suggested_doc_location": gap.suggested_doc_location,
                "gap_severity": gap.gap_severity,
            }
            for gap in report.top_gaps
        ],
        "documentation_debt_score": report.documentation_debt_score,
    }
