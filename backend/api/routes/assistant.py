"""
routes/assistant.py — Intent-first Q&A, multi-turn conversation, semantic search.

Proxies to worker-service /assistant/* routes.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from ..config import WORKER_SERVICE_URL
from ..proxy import forward_request

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/ask")
async def assistant_ask(request: Request):
    """Single-turn Q&A with RAG pipeline and citations."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/assistant/ask")


@router.post("/conversation")
async def assistant_conversation(request: Request):
    """Multi-turn conversation with context-aware follow-ups."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/assistant/conversation")


@router.post("/search")
async def assistant_search(request: Request):
    """Semantic search over the knowledge base embeddings."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/assistant/search")


@router.get("/health")
async def assistant_health(request: Request):
    """LLM and embedding client health status."""
    return await forward_request(request, base_url=WORKER_SERVICE_URL, path="/assistant/health")
