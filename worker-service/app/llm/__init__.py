"""
KA-CHOW LLM Integration Layer – singleton factories.

Usage:
    from app.llm import get_llm_client, get_embedding_client
    llm = get_llm_client()
    emb = get_embedding_client()
"""
from __future__ import annotations

import os
import threading
from typing import Optional

from .client import LLMClient
from .embeddings import EmbeddingClient

_lock = threading.Lock()
_llm_instance: Optional[LLMClient] = None
_emb_instance: Optional[EmbeddingClient] = None


def get_llm_client() -> LLMClient:
    """Return a process-wide singleton LLMClient, created lazily."""
    global _llm_instance
    if _llm_instance is not None:
        return _llm_instance
    with _lock:
        if _llm_instance is not None:
            return _llm_instance
        _llm_instance = LLMClient(
            api_key=os.getenv("GEMINI_API_KEY", ""),
            model=os.getenv("LLM_MODEL", "gemini-2.0-flash"),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.3")),
            max_output_tokens=int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "8192")),
        )
        return _llm_instance


def get_embedding_client() -> EmbeddingClient:
    """Return a process-wide singleton EmbeddingClient, created lazily."""
    global _emb_instance
    if _emb_instance is not None:
        return _emb_instance
    with _lock:
        if _emb_instance is not None:
            return _emb_instance
        _emb_instance = EmbeddingClient(
            api_key=os.getenv("GEMINI_API_KEY", ""),
            model=os.getenv("EMBEDDING_MODEL", "text-embedding-004"),
        )
        return _emb_instance
