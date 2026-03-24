
from fastapi import APIRouter, Depends, HTTPException, status

from ..dependencies import (
    PG_CFG, auth_read_scoped, enforce_repo_scope, AuthContext,
    llm_client, embedding_store,
)

router = APIRouter()

from ..qa.models import QARequest, QAConversationRequest, QASearchRequest, QASearchResponse, QASearchResult
from ..qa.assistant import answer_question, answer_conversation, semantic_search


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
