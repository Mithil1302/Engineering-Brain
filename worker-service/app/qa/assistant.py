"""
KA-CHOW Intent-First Q&A Assistant — LLM-Powered RAG Implementation.

Replaces the keyword-based classifier with:
  1. LLM intent classification (Gemini)
  2. Vector retrieval from pgvector embedding store
  3. DB evidence gathering (policy runs, health, waivers, docs)
  4. RAG answer generation with citations
  5. Multi-turn conversation support
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from ..llm import get_llm_client, get_embedding_client
from ..llm.chains import RAGChain
from ..llm.embeddings import EmbeddingStore
from ..llm.prompts import QAIntentClassifierPrompt, QAAnswerPrompt
from .models import (
    QACitation,
    QARequest,
    QAResponse,
    SourceCitation,
)

log = logging.getLogger("ka-chow.qa")

# ---------------------------------------------------------------------------
# Intent classification — maps to evidence retrieval strategy
# ---------------------------------------------------------------------------

INTENT_EVIDENCE_MAP = {
    "policy_status": ["policy_runs", "merge_gates"],
    "doc_health": ["doc_rewrite_runs", "doc_refresh_jobs"],
    "architecture": ["architecture_plans", "graph_nodes"],
    "onboarding": ["onboarding_paths"],
    "impact": ["impact_edges", "graph_nodes"],
    "health": ["health_snapshots"],
    "waiver": ["waivers"],
    "general": ["policy_runs", "health_snapshots", "doc_rewrite_runs"],
}


def _classify_intent(question: str, repo: str) -> Dict[str, Any]:
    """
    Use LLM to classify the user's question into an intent.
    Falls back to 'general' on LLM failure.
    """
    try:
        llm = get_llm_client()
        result = llm.generate_json(
            QAIntentClassifierPrompt.user_prompt(question, repo),
            system_prompt=QAIntentClassifierPrompt.system_prompt,
            json_schema=QAIntentClassifierPrompt.response_schema(),
            temperature=0.1,
        )
        if isinstance(result, dict) and "intent" in result:
            return result
    except Exception as exc:
        log.warning("LLM intent classification failed, falling back: %s", exc)

    # Fallback: keyword-based classification (kept for resilience)
    q = question.lower()
    if any(w in q for w in ("policy", "check", "pr", "merge", "gate", "block")):
        return {"intent": "policy_status", "confidence": 0.5, "reasoning": "keyword_fallback"}
    if any(w in q for w in ("doc", "documentation", "drift", "stale")):
        return {"intent": "doc_health", "confidence": 0.5, "reasoning": "keyword_fallback"}
    if any(w in q for w in ("health", "score", "grade", "trend")):
        return {"intent": "health", "confidence": 0.5, "reasoning": "keyword_fallback"}
    if any(w in q for w in ("waiver", "exempt", "approval")):
        return {"intent": "waiver", "confidence": 0.5, "reasoning": "keyword_fallback"}
    if any(w in q for w in ("architecture", "design", "service", "endpoint")):
        return {"intent": "architecture", "confidence": 0.5, "reasoning": "keyword_fallback"}
    if any(w in q for w in ("impact", "what-if", "change", "break")):
        return {"intent": "impact", "confidence": 0.5, "reasoning": "keyword_fallback"}
    if any(w in q for w in ("onboard", "learn", "start", "new")):
        return {"intent": "onboarding", "confidence": 0.5, "reasoning": "keyword_fallback"}
    return {"intent": "general", "confidence": 0.3, "reasoning": "no_match_fallback"}


# ---------------------------------------------------------------------------
# Evidence gathering from PostgreSQL
# ---------------------------------------------------------------------------

def _gather_evidence(
    pg_cfg: Dict[str, Any],
    *,
    repo: Optional[str],
    pr_number: Optional[int],
    intent: str,
) -> Dict[str, Any]:
    """
    Query the database for relevant evidence based on intent.
    Returns a dict with lists of relevant records.
    """
    evidence: Dict[str, Any] = {}
    evidence_types = INTENT_EVIDENCE_MAP.get(intent, INTENT_EVIDENCE_MAP["general"])

    try:
        with psycopg2.connect(**pg_cfg) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if "policy_runs" in evidence_types:
                    cur.execute(
                        """
                        SELECT id, repo, pr_number, summary_status, action,
                               merge_gate, created_at
                        FROM meta.policy_check_runs
                        WHERE (%s IS NULL OR repo = %s)
                          AND (%s IS NULL OR pr_number = %s)
                        ORDER BY id DESC LIMIT 10
                        """,
                        (repo, repo, pr_number, pr_number),
                    )
                    evidence["policy_runs"] = [dict(r) for r in cur.fetchall()]

                if "health_snapshots" in evidence_types:
                    cur.execute(
                        """
                        SELECT id, repo, pr_number, score::float8 AS score, grade,
                               summary_status, created_at
                        FROM meta.knowledge_health_snapshots
                        WHERE (%s IS NULL OR repo = %s)
                          AND (%s IS NULL OR pr_number = %s)
                        ORDER BY id DESC LIMIT 10
                        """,
                        (repo, repo, pr_number, pr_number),
                    )
                    evidence["health_snapshots"] = [dict(r) for r in cur.fetchall()]

                if "waivers" in evidence_types:
                    cur.execute(
                        """
                        SELECT id, repo, pr_number, rule_set, status,
                               requested_by, reason, expires_at, created_at
                        FROM meta.policy_waivers
                        WHERE (%s IS NULL OR repo = %s)
                          AND (%s IS NULL OR pr_number = %s)
                        ORDER BY id DESC LIMIT 10
                        """,
                        (repo, repo, pr_number, pr_number),
                    )
                    evidence["waivers"] = [dict(r) for r in cur.fetchall()]

                if "doc_rewrite_runs" in evidence_types:
                    cur.execute(
                        """
                        SELECT id, repo, pr_number, status, reason,
                               quality_gate_score, created_at
                        FROM meta.doc_rewrite_runs
                        WHERE (%s IS NULL OR repo = %s)
                          AND (%s IS NULL OR pr_number = %s)
                        ORDER BY id DESC LIMIT 10
                        """,
                        (repo, repo, pr_number, pr_number),
                    )
                    evidence["doc_rewrite_runs"] = [dict(r) for r in cur.fetchall()]

                if "doc_refresh_jobs" in evidence_types:
                    cur.execute(
                        """
                        SELECT id, repo, pr_number, decision, priority,
                               plan, created_at
                        FROM meta.doc_refresh_jobs
                        WHERE (%s IS NULL OR repo = %s)
                          AND (%s IS NULL OR pr_number = %s)
                        ORDER BY id DESC LIMIT 10
                        """,
                        (repo, repo, pr_number, pr_number),
                    )
                    evidence["doc_refresh_jobs"] = [dict(r) for r in cur.fetchall()]

                if "merge_gates" in evidence_types:
                    cur.execute(
                        """
                        SELECT id, repo, pr_number, merge_gate, created_at
                        FROM meta.policy_check_runs
                        WHERE (%s IS NULL OR repo = %s)
                          AND (%s IS NULL OR pr_number = %s)
                          AND merge_gate IS NOT NULL
                        ORDER BY id DESC LIMIT 5
                        """,
                        (repo, repo, pr_number, pr_number),
                    )
                    evidence["merge_gates"] = [dict(r) for r in cur.fetchall()]

    except Exception as exc:
        log.warning("Evidence gathering failed (tables may not exist yet): %s", exc)

    # Serialize datetimes for JSON
    for key, records in evidence.items():
        for record in records:
            for k, v in record.items():
                if isinstance(v, datetime):
                    record[k] = v.isoformat()

    return evidence


# ---------------------------------------------------------------------------
# RAG-powered answer generation
# ---------------------------------------------------------------------------

def _generate_answer_with_rag(
    question: str,
    evidence: Dict[str, Any],
    embedding_store: Optional[EmbeddingStore],
) -> Dict[str, Any]:
    """
    Full RAG pipeline:
      1. Retrieve relevant chunks from pgvector
      2. Combine with DB evidence
      3. Generate answer with LLM

    Returns the parsed LLM JSON response.
    """
    llm = get_llm_client()

    # Try RAG chain if embedding store is available
    if embedding_store:
        try:
            chain = RAGChain(llm=llm, store=embedding_store, top_k=8, rerank=True, rerank_top_k=5)
            result = chain.run(question, evidence=evidence)
            if result.output and isinstance(result.output, dict):
                result.output["_chain_steps"] = [
                    {
                        "name": s.step_name,
                        "latency_ms": s.latency_ms,
                        "tokens": s.tokens_used,
                    }
                    for s in result.steps
                ]
                return result.output
        except Exception as exc:
            log.warning("RAG chain failed, falling back to direct LLM: %s", exc)

    # Fallback: direct LLM call without vector retrieval
    try:
        user_prompt = QAAnswerPrompt.user_prompt(
            question=question,
            context_chunks=[],
            evidence=evidence,
        )
        resp = llm.generate_json(
            user_prompt,
            system_prompt=QAAnswerPrompt.system_prompt,
            json_schema=QAAnswerPrompt.response_schema(),
        )
        return resp if isinstance(resp, dict) else {"answer": str(resp), "confidence": 0.3, "citations": []}
    except Exception as exc:
        log.error("Direct LLM answer generation failed: %s", exc)
        return _fallback_template_answer(question, evidence)


def _fallback_template_answer(
    question: str, evidence: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Last-resort: template-based answer when LLM is unavailable.
    This ensures the endpoint never fully breaks.
    """
    parts = []

    policy_runs = evidence.get("policy_runs", [])
    if policy_runs:
        latest = policy_runs[0]
        parts.append(
            f"Latest policy check: **{latest.get('summary_status', 'unknown')}** "
            f"(repo: {latest.get('repo')}, PR #{latest.get('pr_number')})"
        )

    health = evidence.get("health_snapshots", [])
    if health:
        latest = health[0]
        parts.append(
            f"Health score: **{latest.get('score', 'N/A')}** "
            f"(grade: {latest.get('grade', 'N/A')})"
        )

    waivers = evidence.get("waivers", [])
    if waivers:
        active = [w for w in waivers if w.get("status") == "approved"]
        parts.append(f"Active waivers: **{len(active)}**")

    if not parts:
        parts.append(
            "I don't have enough data to answer this question. "
            "Try running a policy check first to populate the knowledge base."
        )

    return {
        "answer": "\n\n".join(parts),
        "confidence": 0.2,
        "citations": [],
        "follow_up_questions": [
            "What is the current health score?",
            "Are there any active policy waivers?",
            "Show me the latest policy check results.",
        ],
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def answer_question(
    request: QARequest,
    pg_cfg: Dict[str, Any],
    *,
    embedding_store: Optional[EmbeddingStore] = None,
) -> QAResponse:
    """
    Main entry point: classify intent → gather evidence → RAG answer.

    Returns a QAResponse with natural-language answer, confidence, citations.
    """
    repo = (request.repo or "").strip() or None
    pr_number = request.pr_number

    # --- Step 1: Intent classification ---
    intent_result = _classify_intent(request.question, repo or "")
    intent = str(intent_result.get("intent", "general"))

    # --- Step 2: Gather DB evidence ---
    evidence = _gather_evidence(pg_cfg, repo=repo, pr_number=pr_number, intent=intent)

    # --- Step 3: RAG answer generation ---
    answer_result = _generate_answer_with_rag(
        request.question, evidence, embedding_store
    )

    # --- Build response ---
    raw_citations = answer_result.get("citations", [])
    source_citations = []
    legacy_citations = []

    for c in raw_citations:
        if isinstance(c, dict):
            source_citations.append(SourceCitation(
                source_ref=c.get("source_ref", "unknown"),
                source_type=c.get("source_type", "unknown"),
                relevance=c.get("relevance", "direct"),
            ))
            legacy_citations.append(QACitation(
                source=c.get("source_type", "db"),
                reference=c.get("source_ref", ""),
                details=c.get("relevance"),
            ))

    # Source breakdown: count citations per source_type
    source_breakdown: Dict[str, int] = {}
    for sc in source_citations:
        source_breakdown[sc.source_type] = source_breakdown.get(sc.source_type, 0) + 1
    for key, records in evidence.items():
        if key not in source_breakdown and records:
            source_breakdown[key] = len(records)

    chain_steps = answer_result.get("_chain_steps", [])

    return QAResponse(
        answer=answer_result.get("answer", "No answer available."),
        confidence=float(answer_result.get("confidence", 0.0)),
        intent=intent,
        citations=legacy_citations,
        source_citations=source_citations,
        source_breakdown=source_breakdown,
        evidence_policy="citations_required",
        evidence=evidence,
        follow_up_questions=answer_result.get("follow_up_questions", []),
        chain_steps=chain_steps,
    )


def answer_conversation(
    question: str,
    history: List[Dict[str, str]],
    repo: Optional[str],
    pg_cfg: Dict[str, Any],
) -> QAResponse:
    """
    Multi-turn conversation: uses conversation history for context-aware answers.
    """
    llm = get_llm_client()

    # Build message list with history
    messages = []
    for msg in history[-10:]:  # keep last 10 turns
        messages.append(msg)
    messages.append({"role": "user", "content": question})

    # Gather evidence for the latest question
    intent_result = _classify_intent(question, repo or "")
    intent = str(intent_result.get("intent", "general"))
    evidence = _gather_evidence(pg_cfg, repo=repo, pr_number=None, intent=intent)

    # Add evidence as context in the system prompt
    system = (
        QAAnswerPrompt.system_prompt
        + f"\n\nDatabase evidence:\n{json.dumps(evidence, default=str)[:4000]}"
    )

    try:
        resp = llm.multi_turn(
            messages,
            system_prompt=system,
            json_mode=True,
            temperature=0.3,
        )
        result = resp.as_json()
        if isinstance(result, dict):
            answer = result.get("answer", resp.text)
            confidence = float(result.get("confidence", 0.5))
            follow_ups = result.get("follow_up_questions", [])
        else:
            answer = resp.text
            confidence = 0.5
            follow_ups = []
    except Exception as exc:
        log.error("Multi-turn Q&A failed: %s", exc)
        answer = f"I encountered an error: {exc}"
        confidence = 0.0
        follow_ups = []

    return QAResponse(
        answer=answer,
        confidence=confidence,
        intent=intent,
        evidence=evidence,
        follow_up_questions=follow_ups,
    )


def semantic_search(
    query: str,
    embedding_store: EmbeddingStore,
    *,
    source_types: Optional[List[str]] = None,
    top_k: int = 10,
) -> List[Dict[str, Any]]:
    """
    Direct semantic search over the embedding store.
    Returns ranked chunks without LLM generation.
    """
    results = embedding_store.search(
        query, top_k=top_k, source_types=source_types
    )
    return [
        {
            "chunk_id": r.chunk_id,
            "source_type": r.source_type,
            "source_ref": r.source_ref,
            "chunk_text": r.chunk_text,
            "score": round(r.score, 4),
            "metadata": r.metadata,
        }
        for r in results
    ]
