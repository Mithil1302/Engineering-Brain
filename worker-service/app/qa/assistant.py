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
from .coreference import ConversationState
from .models import (
    QACitation,
    QARequest,
    QAResponse,
    SourceCitation,
)
from .session_store import get_session_store

log = logging.getLogger("ka-chow.qa")

# ---------------------------------------------------------------------------
# Intent classification — maps to evidence retrieval strategy
# ---------------------------------------------------------------------------

INTENT_TREE: dict[str, list[str]] = {
    "architecture": [
        "architecture.explain_service",
        "architecture.trace_dependency",
        "architecture.why_decision",
        "architecture.add_service",
        "architecture.compare_services",
    ],
    "impact": [
        "impact.deprecate_endpoint",
        "impact.change_schema",
        "impact.change_dependency",
    ],
    "policy_status": [
        "policy_status.pr_check",
        "policy_status.merge_gate",
        "policy_status.waiver_status",
    ],
    "doc_health": [
        "doc_health.missing_docs",
        "doc_health.stale_docs",
        "doc_health.coverage_score",
    ],
    "onboarding": [
        "onboarding.getting_started",
        "onboarding.find_owner",
        "onboarding.understand_flow",
    ],
    "health": ["health"],
    "waiver": ["waiver"],
    "general": ["general"],
}

INTENT_EVIDENCE_MAP = {
    # Coarse fallbacks (existing — unchanged)
    "policy_status": ["policy_runs", "merge_gates"],
    "doc_health": ["doc_rewrite_runs", "doc_refresh_jobs"],
    "architecture": ["architecture_plans", "graph_nodes"],
    "onboarding": ["onboarding_paths"],
    "impact": ["impact_edges", "graph_nodes"],
    "health": ["health_snapshots"],
    "waiver": ["waivers"],
    "general": ["policy_runs", "health_snapshots", "doc_rewrite_runs"],
    # Sub-intent entries (new — added for hierarchical classification)
    "architecture.explain_service": ["graph_nodes", "knowledge_chunks", "api_specs"],
    "architecture.trace_dependency": ["dependency_graph", "graph_nodes"],
    "architecture.why_decision": ["adrs", "knowledge_chunks"],
    "architecture.add_service": ["adrs", "scaffold_templates", "knowledge_chunks"],
    "architecture.compare_services": ["graph_nodes", "api_specs", "knowledge_chunks"],
    "impact.deprecate_endpoint": ["api_specs", "dependency_graph", "policy_runs"],
    "impact.change_schema": ["schema_registry", "dependency_graph"],
    "impact.change_dependency": ["dependency_graph", "knowledge_chunks"],
    "onboarding.getting_started": ["onboarding_paths", "knowledge_chunks"],
    "onboarding.find_owner": ["graph_nodes", "team_metadata"],
    "onboarding.understand_flow": ["knowledge_chunks", "api_specs", "dependency_graph"],
}


def _classify_intent(question: str, repo: str) -> Dict[str, Any]:
    """
    Two-stage intent classification.
    Stage 1: coarse classification (existing behavior preserved).
    Stage 2: sub-intent via constrained JSON (only when multiple candidates).
    Falls back silently to coarse intent on sub-classification failure.
    """
    # Stage 1: coarse classification (existing behavior — unchanged)
    coarse_result = None
    try:
        llm = get_llm_client()
        result = llm.generate_json(
            QAIntentClassifierPrompt.user_prompt(question, repo),
            system_prompt=QAIntentClassifierPrompt.system_prompt,
            json_schema=QAIntentClassifierPrompt.response_schema(),
            temperature=0.1,
        )
        if isinstance(result, dict) and "intent" in result:
            coarse_result = result
    except Exception as exc:
        log.warning("LLM intent classification failed, falling back: %s", exc)

    # Fallback: keyword-based classification (kept for resilience)
    if coarse_result is None:
        q = question.lower()
        if any(w in q for w in ("policy", "check", "pr", "merge", "gate", "block")):
            coarse_result = {"intent": "policy_status", "confidence": 0.5, "reasoning": "keyword_fallback"}
        elif any(w in q for w in ("doc", "documentation", "drift", "stale")):
            coarse_result = {"intent": "doc_health", "confidence": 0.5, "reasoning": "keyword_fallback"}
        elif any(w in q for w in ("health", "score", "grade", "trend")):
            coarse_result = {"intent": "health", "confidence": 0.5, "reasoning": "keyword_fallback"}
        elif any(w in q for w in ("waiver", "exempt", "approval")):
            coarse_result = {"intent": "waiver", "confidence": 0.5, "reasoning": "keyword_fallback"}
        elif any(w in q for w in ("architecture", "design", "service", "endpoint")):
            coarse_result = {"intent": "architecture", "confidence": 0.5, "reasoning": "keyword_fallback"}
        elif any(w in q for w in ("impact", "what-if", "change", "break")):
            coarse_result = {"intent": "impact", "confidence": 0.5, "reasoning": "keyword_fallback"}
        elif any(w in q for w in ("onboard", "learn", "start", "new")):
            coarse_result = {"intent": "onboarding", "confidence": 0.5, "reasoning": "keyword_fallback"}
        else:
            coarse_result = {"intent": "general", "confidence": 0.3, "reasoning": "no_match_fallback"}

    # Extract coarse intent and confidence for Stage 2
    coarse_intent = coarse_result.get("intent", "general")
    base_confidence = coarse_result.get("confidence", 0.5)

    # Stage 2: sub-intent classification (only when multiple candidates exist)
    candidates = INTENT_TREE.get(coarse_intent, [coarse_intent])
    if len(candidates) <= 1:
        return coarse_result

    # Import SubIntentClassifierPrompt here to avoid circular dependency
    try:
        from ..llm.prompts import SubIntentClassifierPrompt
        
        llm = get_llm_client()
        sub_result = llm.generate_json(
            SubIntentClassifierPrompt.user_prompt(question, coarse_intent, candidates),
            system_prompt=SubIntentClassifierPrompt.system_prompt,
            json_schema=SubIntentClassifierPrompt.response_schema(candidates),
            temperature=0.1,
        )
        sub_intent = sub_result.get("sub_intent", coarse_intent)
        
        # Validate returned sub_intent is in candidates
        if sub_intent not in candidates:
            log.warning(
                f"Sub-intent '{sub_intent}' not in candidates {candidates}, "
                f"falling back to coarse intent '{coarse_intent}'"
            )
            return {"intent": coarse_intent, "confidence": base_confidence}
        
        return {
            "intent": sub_intent,
            "confidence": base_confidence,
            "reasoning": f"coarse={coarse_intent}, sub={sub_intent}",
        }
    except Exception:
        # Silent fallback: return coarse intent without logging
        return {"intent": coarse_intent, "confidence": base_confidence}


# ---------------------------------------------------------------------------
# Evidence gathering from PostgreSQL
# ---------------------------------------------------------------------------

def _get_known_services(repo: str, pg_cfg: Dict[str, Any]) -> list[str]:
    """
    Fetch known service names from meta.graph_nodes for coreference resolution.
    
    This is separate from any gRPC call and queries the PostgreSQL mirror table
    populated by the ingestion pipeline.
    
    Args:
        repo: Repository name to filter services
        pg_cfg: PostgreSQL connection configuration
        
    Returns:
        List of service names (labels) from the graph_nodes table
    """
    if not repo:
        return []
    
    try:
        with psycopg2.connect(**pg_cfg) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT DISTINCT label
                    FROM meta.graph_nodes
                    WHERE repo = %s AND node_type = 'service'
                    ORDER BY label
                    """,
                    (repo,),
                )
                rows = cur.fetchall()
                return [row["label"] for row in rows if row.get("label")]
    except Exception as exc:
        log.warning("Failed to fetch known services for repo %s: %s", repo, exc)
        return []


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
    
    # Check full dot-notation intent first (e.g., "architecture.trace_dependency")
    evidence_types = INTENT_EVIDENCE_MAP.get(intent)
    
    # If not found, fall back to coarse intent (e.g., "architecture")
    if evidence_types is None and "." in intent:
        coarse_intent = intent.split(".")[0]
        evidence_types = INTENT_EVIDENCE_MAP.get(coarse_intent)
    
    # Final fallback to "general"
    if evidence_types is None:
        evidence_types = INTENT_EVIDENCE_MAP["general"]

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
    pg_cfg: Optional[Dict[str, Any]] = None,
    intent: str = "general",
    session_id: str = "",
    repo: str = "",
    tone_instruction: str = "",
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
            chain = RAGChain(llm=llm, store=embedding_store, top_k=8, rerank_top_k=5, pg_cfg=pg_cfg)
            result = chain.run(
                question,
                evidence=evidence,
                intent=intent,
                session_id=session_id,
                repo=repo,
                tone_instruction=tone_instruction,
            )
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
        # Build system prompt with tone instruction
        system_prompt = QAAnswerPrompt.build_system_prompt(tone_instruction)
        resp = llm.generate_json(
            user_prompt,
            system_prompt=system_prompt,
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
    channel: str = "api",
) -> QAResponse:
    """
    Main entry point: classify intent → gather evidence → RAG answer.

    Returns a QAResponse with natural-language answer, confidence, citations.
    """
    from ..adapters.channel_formatter import ChannelFormatter
    
    repo = (request.repo or "").strip() or None
    pr_number = request.pr_number
    
    # Initialize channel formatter
    formatter = ChannelFormatter()
    
    # Get tone instruction BEFORE calling RAG chain
    tone_instruction = formatter.get_tone_instruction(channel)

    # --- Step 1: Intent classification ---
    intent_result = _classify_intent(request.question, repo or "")
    intent = str(intent_result.get("intent", "general"))

    # --- Step 2: Gather DB evidence ---
    evidence = _gather_evidence(pg_cfg, repo=repo, pr_number=pr_number, intent=intent)

    # --- Step 3: RAG answer generation with tone instruction ---
    answer_result = _generate_answer_with_rag(
        request.question, evidence, embedding_store, pg_cfg,
        intent=intent, session_id=getattr(request, 'session_id', ''), repo=repo or "",
        tone_instruction=tone_instruction,
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

    response = QAResponse(
        answer=answer_result.get("answer", "No answer available."),
        confidence=float(answer_result.get("confidence", 0.0)),
        intent=intent,
        original_question=request.question,
        citations=legacy_citations,
        source_citations=source_citations,
        source_breakdown=source_breakdown,
        evidence_policy="citations_required",
        evidence=evidence,
        follow_up_questions=answer_result.get("follow_up_questions", []),
        chain_steps=chain_steps,
    )
    
    # Format response for channel as the LAST step
    response = formatter.format_response(response, channel)
    
    return response


def answer_conversation(
    question: str,
    history: List[Dict[str, str]],
    repo: Optional[str],
    pg_cfg: Dict[str, Any],
    session_id: Optional[str] = None,
    channel: str = "api",
) -> QAResponse:
    """
    Multi-turn conversation: uses conversation history for context-aware answers.
    """
    from ..adapters.channel_formatter import ChannelFormatter
    
    # Initialize channel formatter
    formatter = ChannelFormatter()
    
    # Get tone instruction BEFORE generation
    tone_instruction = formatter.get_tone_instruction(channel)
    
    # Load ConversationState from session store
    session_store = get_session_store()
    raw_state = session_store.get(session_id, "conversation_state") if session_id else None
    state = ConversationState.from_dict(raw_state) if raw_state else ConversationState()
    
    # Get known services for coreference resolution
    known_services = _get_known_services(repo or "", pg_cfg)
    
    # Resolve coreferences BEFORE anything else
    rewritten_question = state.resolve_references(question)
    if rewritten_question != question:
        log.debug(f"Coreference resolved: '{question}' → '{rewritten_question}'")
    
    llm = get_llm_client()

    # Build message list with history
    messages = []
    for msg in history[-10:]:  # keep last 10 turns
        messages.append(msg)
    # Store original question in conversation history (what user actually typed)
    # but use rewritten question for intent classification and evidence gathering
    messages.append({"role": "user", "content": question})

    # Gather evidence for the latest question
    intent_result = _classify_intent(rewritten_question, repo or "")
    intent = str(intent_result.get("intent", "general"))
    evidence = _gather_evidence(pg_cfg, repo=repo, pr_number=None, intent=intent)

    # Add evidence as context in the system prompt with tone instruction
    system = (
        QAAnswerPrompt.build_system_prompt(tone_instruction)
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

    # Update conversation state with ORIGINAL question (not rewritten)
    state.update(question, answer, known_services)
    
    # Persist updated state to session store
    if session_id:
        session_store.set(session_id, "conversation_state", state.to_dict())

    response = QAResponse(
        answer=answer,
        confidence=confidence,
        intent=intent,
        original_question=question,
        rewritten_question=rewritten_question if rewritten_question != question else None,
        evidence=evidence,
        follow_up_questions=follow_ups,
    )
    
    # Format response for channel as the LAST step (after ConversationState update)
    response = formatter.format_response(response, channel)
    
    return response


async def stream_answer(
    question: str,
    repo: str,
    session_id: str,
    pg_cfg: Dict[str, Any],
    *,
    embedding_store: Optional[EmbeddingStore] = None,
    tone_instruction: str = "",
    channel: str = "api",
):
    """
    Stream answer generation using LLM streaming.
    
    Yields text chunks as they arrive from the model, then stores the final
    QAResponse in the session store for later retrieval.
    
    Args:
        question: User's question
        repo: Repository name
        session_id: Session identifier for storing the response
        pg_cfg: PostgreSQL configuration
        embedding_store: Optional embedding store for RAG
        tone_instruction: Optional tone instruction for the LLM
        channel: Delivery channel (api, cli, slack, web)
        
    Yields:
        Text chunks from the streaming LLM response
    """
    from ..adapters.channel_formatter import ChannelFormatter
    
    # Initialize channel formatter
    formatter = ChannelFormatter()
    
    # Get tone instruction if not provided
    if not tone_instruction:
        tone_instruction = formatter.get_tone_instruction(channel)
    
    # --- Step 1: Intent classification ---
    intent_result = _classify_intent(question, repo or "")
    intent = str(intent_result.get("intent", "general"))
    
    # --- Step 2: Gather DB evidence ---
    evidence = _gather_evidence(pg_cfg, repo=repo, pr_number=None, intent=intent)
    
    # --- Step 3: Retrieve relevant chunks if embedding store available ---
    context_chunks = []
    if embedding_store:
        try:
            results = embedding_store.search(question, top_k=8)
            context_chunks = [
                {
                    "content": r.chunk_text,
                    "source_ref": r.source_ref,
                    "source_type": r.source_type,
                    "score": r.score,
                }
                for r in results
            ]
        except Exception as exc:
            log.warning("Chunk retrieval failed during streaming: %s", exc)
    
    # --- Step 4: Build prompt ---
    from ..llm.prompts import QAAnswerPrompt
    
    user_prompt = QAAnswerPrompt.user_prompt(
        question=question,
        context_chunks=context_chunks,
        evidence=evidence,
    )
    system_prompt = QAAnswerPrompt.build_system_prompt(tone_instruction)
    
    # --- Step 5: Stream the answer ---
    llm = get_llm_client()
    full_text = []
    
    try:
        for chunk in llm.generate_streaming(
            user_prompt,
            system_prompt=system_prompt,
            temperature=0.3,
        ):
            full_text.append(chunk)
            yield chunk
    except Exception as exc:
        error_msg = f"Streaming failed: {exc}"
        log.error(error_msg)
        yield error_msg
        full_text.append(error_msg)
    
    # --- Step 6: Store final response in session store ---
    final_answer = "".join(full_text)
    
    # Build citations from context chunks
    source_citations = []
    for chunk in context_chunks[:5]:  # Top 5 chunks
        source_citations.append(SourceCitation(
            source_ref=chunk["source_ref"],
            source_type=chunk["source_type"],
            relevance="direct",
        ))
    
    # Build source breakdown
    source_breakdown: Dict[str, int] = {}
    for sc in source_citations:
        source_breakdown[sc.source_type] = source_breakdown.get(sc.source_type, 0) + 1
    for key, records in evidence.items():
        if key not in source_breakdown and records:
            source_breakdown[key] = len(records)
    
    # Create QAResponse
    response = QAResponse(
        answer=final_answer,
        confidence=0.7,  # Default confidence for streaming
        intent=intent,
        original_question=question,
        source_citations=source_citations,
        source_breakdown=source_breakdown,
        evidence_policy="citations_required",
        evidence=evidence,
        follow_up_questions=[],  # Could be extracted from final answer if needed
    )
    
    # Format response for channel
    response = formatter.format_response(response, channel)
    
    # Store in session store
    session_store = get_session_store()
    session_store.set(session_id, "last_response", response.model_dump())


def get_last_response(session_id: str) -> Optional[QAResponse]:
    """
    Retrieve the last QAResponse from the session store.
    
    Args:
        session_id: Session identifier
        
    Returns:
        QAResponse if found, None otherwise
    """
    session_store = get_session_store()
    response_dict = session_store.get(session_id, "last_response")
    
    if response_dict:
        try:
            return QAResponse(**response_dict)
        except Exception as exc:
            log.warning("Failed to deserialize last_response for session %s: %s", session_id, exc)
            return None
    
    return None


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
