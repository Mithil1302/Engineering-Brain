"""
Multi-step reasoning chains for KA-CHOW.

Provides composable patterns:
  - RAGChain        — retrieve → rank → generate (the workhorse)
  - ReasoningChain  — multi-step LLM calls with context accumulation
  - CodeAnalysisChain — specialized for code understanding
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .client import LLMClient, LLMResponse
from .embeddings import EmbeddingStore, SearchResult
from .prompts import QAAnswerPrompt

log = logging.getLogger("ka-chow.chains")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ChainStep:
    """One step in a reasoning chain."""
    step_name: str
    input_summary: str
    output_summary: str
    latency_ms: float = 0.0
    tokens_used: int = 0


@dataclass
class ChainResult:
    """Final output of a chain execution."""
    output: Any
    steps: List[ChainStep] = field(default_factory=list)
    total_latency_ms: float = 0.0
    total_tokens: int = 0
    success: bool = True
    error: Optional[str] = None


@dataclass
class ChunkResult:
    """A retrieved and scored chunk for RAG pipeline with freshness scoring."""
    chunk_id: int
    content: str
    source_ref: str
    source_type: str
    score: float            # raw vector similarity score
    rerank_score: float     # LLM rerank score (0.0-1.0)
    metadata: Dict[str, Any]
    freshness_score: float = 1.0  # recency multiplier (1.2 for <7d, 1.1 for <30d, 1.0 for <90d, 0.9 for older)
    final_score: float = 0.0      # weighted combination: (rerank_score * 0.7) + (freshness_score * 0.3)


# ---------------------------------------------------------------------------
# RAG Chain — Retrieve → Rank → Generate
# ---------------------------------------------------------------------------

class RAGChain:
    """
    Retrieval-Augmented Generation chain.

    Flow:
        1. Embed the query
        2. Retrieve top-K similar chunks from pgvector
        3. Re-rank chunks using an LLM scoring pass (optional)
        4. Generate final answer using retrieved context

    Usage:
        chain = RAGChain(llm=llm_client, store=embedding_store)
        result = chain.run("What is the health score for repo X?", evidence={...})
    """

    def __init__(
        self,
        *,
        llm: LLMClient,
        store: EmbeddingStore,
        top_k: int = 10,
        rerank_top_k: int = 5,
        score_threshold: float = 0.3,
        pg_cfg: Optional[Dict[str, Any]] = None,
    ):
        self._llm = llm
        self._store = store
        self._top_k = top_k
        self._rerank_top_k = rerank_top_k
        self.score_threshold = score_threshold
        self._pg_cfg = pg_cfg

    def run(
        self,
        query: str,
        *,
        evidence: Optional[Dict[str, Any]] = None,
        source_types: Optional[List[str]] = None,
        system_prompt: Optional[str] = None,
        intent: str = "general",
        session_id: str = "",
        repo: str = "",
        tone_instruction: str = "",
    ) -> ChainResult:
        """Execute the full RAG pipeline."""
        steps: List[ChainStep] = []
        t_start = time.monotonic()

        # --- Step 1: Retrieve -----------------------------------------------
        t0 = time.monotonic()
        try:
            results = self._store.search(
                query, top_k=self._top_k, source_types=source_types
            )
        except Exception as exc:
            log.warning("RAG retrieval failed: %s", exc)
            results = []

        steps.append(ChainStep(
            step_name="retrieve",
            input_summary=f"query='{query[:80]}...' top_k={self._top_k}",
            output_summary=f"retrieved {len(results)} chunks",
            latency_ms=round((time.monotonic() - t0) * 1000, 1),
        ))

        # --- Step 2: Re-rank ------------------------------------------------
        t0 = time.monotonic()
        results = self._rerank_chunks(query, results)
        steps.append(ChainStep(
            step_name="rerank",
            input_summary=f"ranking {len(results)} chunks",
            output_summary=f"kept top {min(len(results), self._rerank_top_k)}",
            latency_ms=round((time.monotonic() - t0) * 1000, 1),
        ))
        results = results[: self._rerank_top_k]

        # --- Step 2.5: Apply freshness scoring ------------------------------
        t0 = time.monotonic()
        scored = self._apply_freshness_scoring(results)
        steps.append(ChainStep(
            step_name="freshness_score",
            input_summary=f"scoring {len(scored)} chunks",
            output_summary=f"scores range [{scored[-1].final_score:.2f}, {scored[0].final_score:.2f}]" if scored else "no chunks",
            latency_ms=round((time.monotonic() - t0) * 1000, 1),
        ))

        # --- Step 2.6: Apply threshold filtering ----------------------------
        # Filter by final_score threshold, then ensure minimum of 3 chunks
        filtered = [c for c in scored if c.final_score >= self.score_threshold]
        if len(filtered) < 3:
            filtered = scored[:3]
        results = filtered

        # --- Step 3: Generate answer ----------------------------------------
        t0 = time.monotonic()
        context_chunks = [
            {
                "source": r.source_ref,
                "source_type": r.source_type,
                "text": r.chunk_text[:1500],
                "score": round(r.score, 3),
            }
            for r in results
        ]

        prompt_cls = QAAnswerPrompt
        user_prompt = prompt_cls.user_prompt(
            question=query,
            context_chunks=context_chunks,
            evidence=evidence or {},
        )

        # Build system prompt with tone instruction
        final_system_prompt = system_prompt or prompt_cls.build_system_prompt(tone_instruction)

        try:
            llm_resp = self._llm.generate(
                user_prompt,
                system_prompt=final_system_prompt,
                json_mode=True,
                json_schema=prompt_cls.response_schema(),
                use_cache=False,  # answers are context-dependent
            )
            output = llm_resp.as_json()
            tokens = llm_resp.input_tokens + llm_resp.output_tokens
        except Exception as exc:
            log.error("RAG generation failed: %s", exc)
            output = {
                "answer": f"I couldn't generate an answer: {exc}",
                "confidence": 0.0,
                "citations": [],
            }
            tokens = 0

        steps.append(ChainStep(
            step_name="generate",
            input_summary=f"context_chunks={len(context_chunks)}",
            output_summary=f"answer_length={len(str(output))}",
            latency_ms=round((time.monotonic() - t0) * 1000, 1),
            tokens_used=tokens,
        ))

        total_ms = round((time.monotonic() - t_start) * 1000, 1)
        total_tok = sum(s.tokens_used for s in steps)

        # Log QA event (non-blocking)
        self._log_qa_event(
            question=query,
            intent=intent,
            session_id=session_id,
            repo=repo,
            chunk_count=len(filtered),
            top_chunk_source=filtered[0].source_ref if filtered else None,
            had_rag_results=len(filtered) > 0,
            confidence=float(output.get("confidence", 0.0)),
        )

        return ChainResult(
            output=output,
            steps=steps,
            total_latency_ms=total_ms,
            total_tokens=total_tok,
        )

    def _rerank_chunks(
        self, query: str, chunks: List[SearchResult]
    ) -> List[SearchResult]:
        """Use LLM to re-score chunks by relevance to query."""
        chunk_summaries = []
        for i, c in enumerate(chunks[:20]):
            chunk_summaries.append(
                f"[{i}] ({c.source_type}:{c.source_ref}) {c.chunk_text[:300]}"
            )

        rerank_prompt = (
            f"Query: {query}\n\n"
            "Rank the following text chunks by relevance to the query. "
            "Return a JSON array of indices ordered from most to least relevant.\n\n"
            + "\n".join(chunk_summaries)
        )

        try:
            resp = self._llm.generate_json(
                rerank_prompt,
                system_prompt="You are a search relevance ranker. Return only a JSON array of integer indices.",
                temperature=0.0,
            )
            if isinstance(resp, list):
                reranked = []
                for rank_position, idx in enumerate(resp):
                    if isinstance(idx, int) and 0 <= idx < len(chunks):
                        chunk = chunks[idx]
                        # Set rerank_score based on position: 1.0 for first, decreasing linearly
                        chunk.rerank_score = 1.0 - (rank_position / max(len(resp), 1))
                        reranked.append(chunk)
                if reranked:
                    return reranked
        except Exception:
            pass
        
        # Fallback: use original order and set rerank_score = score
        for chunk in chunks:
            chunk.rerank_score = chunk.score
        return chunks

    def _apply_freshness_scoring(self, chunks: List[SearchResult]) -> List[SearchResult]:
        """
        Compute freshness_score per chunk and calculate final_score.
        
        Freshness: 1.2 (≤7d), 1.1 (≤30d), 1.0 (≤90d), 0.9 (>90d).
        Final: (rerank_score * 0.7) + (freshness_score * 0.3).
        
        Sorts descending by final_score.
        """
        from datetime import datetime, timezone
        
        now = datetime.now(timezone.utc)
        
        for chunk in chunks:
            # Extract last_modified from metadata
            last_modified = chunk.metadata.get("last_modified")
            
            if last_modified is None:
                # No timestamp available, use neutral score
                chunk.freshness_score = 1.0
            else:
                # Handle both string ISO format and datetime objects
                if isinstance(last_modified, str):
                    last_modified = datetime.fromisoformat(last_modified)
                
                # Handle timezone-naive datetimes
                if last_modified.tzinfo is None:
                    last_modified = last_modified.replace(tzinfo=timezone.utc)
                
                # Compute age in days
                age_days = (now - last_modified).days
                
                # Apply freshness thresholds (inclusive on lower bound)
                if age_days <= 7:
                    chunk.freshness_score = 1.2
                elif age_days <= 30:
                    chunk.freshness_score = 1.1
                elif age_days <= 90:
                    chunk.freshness_score = 1.0
                else:  # age_days > 90
                    chunk.freshness_score = 0.9
            
            # Compute final weighted score
            chunk.final_score = (chunk.rerank_score * 0.7) + (chunk.freshness_score * 0.3)
        
        # Sort descending by final_score
        scored = sorted(chunks, key=lambda c: c.final_score, reverse=True)
        
        return scored

    def _log_qa_event(
        self,
        question: str,
        intent: str,
        session_id: str,
        repo: str,
        chunk_count: int,
        top_chunk_source: Optional[str],
        had_rag_results: bool,
        confidence: float,
    ) -> None:
        """
        Non-blocking INSERT to meta.qa_event_log.
        Failure is logged at WARNING level and never surfaces to the caller.
        """
        if not self._pg_cfg:
            return  # No database config, skip logging
        
        try:
            import psycopg2
            
            # Parse sub_intent from dot-notation
            parts = intent.split(".", 1)
            coarse = parts[0]
            sub = parts[1] if len(parts) > 1 else None
            
            with psycopg2.connect(**self._pg_cfg) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO meta.qa_event_log
                        (question, intent, sub_intent, confidence, chunk_count,
                         top_chunk_source, had_rag_results, session_id, repo, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    """, (question, coarse, sub, confidence, chunk_count,
                          top_chunk_source, had_rag_results, session_id, repo))
                conn.commit()
        except Exception as e:
            log.warning(f"QA event log write failed: {e}")


# ---------------------------------------------------------------------------
# Reasoning Chain — Multi-step with context accumulation
# ---------------------------------------------------------------------------

class ReasoningChain:
    """
    Execute a sequence of named LLM steps, passing accumulated context forward.

    Usage:
        chain = ReasoningChain(llm)
        chain.add_step("analyze", "Analyze the following...", system="You are...")
        chain.add_step("synthesize", "Given the analysis: {analyze}\nNow synthesize...")
        result = chain.run(initial_context={"data": "..."})
    """

    def __init__(self, llm: LLMClient):
        self._llm = llm
        self._steps: List[Tuple[str, str, Optional[str], bool]] = []

    def add_step(
        self,
        name: str,
        prompt_template: str,
        *,
        system_prompt: Optional[str] = None,
        json_mode: bool = False,
    ) -> "ReasoningChain":
        """
        Add a step. Use {step_name} in prompt_template to reference previous outputs.
        """
        self._steps.append((name, prompt_template, system_prompt, json_mode))
        return self

    def run(
        self, initial_context: Optional[Dict[str, Any]] = None
    ) -> ChainResult:
        """Execute all steps in sequence."""
        context = dict(initial_context or {})
        steps: List[ChainStep] = []
        t_start = time.monotonic()

        for name, template, sys_prompt, json_mode in self._steps:
            t0 = time.monotonic()

            # Format the template with accumulated context
            try:
                prompt = template.format(**context)
            except KeyError as exc:
                prompt = template  # fallback: use raw template

            try:
                resp = self._llm.generate(
                    prompt,
                    system_prompt=sys_prompt,
                    json_mode=json_mode,
                    use_cache=False,
                )
                output = resp.as_json() if json_mode else resp.text
                context[name] = output if isinstance(output, str) else json.dumps(output)
                tokens = resp.input_tokens + resp.output_tokens
            except Exception as exc:
                log.error("Reasoning step '%s' failed: %s", name, exc)
                context[name] = f"[ERROR: {exc}]"
                tokens = 0

            steps.append(ChainStep(
                step_name=name,
                input_summary=f"prompt_length={len(prompt)}",
                output_summary=f"output_length={len(str(context[name]))}",
                latency_ms=round((time.monotonic() - t0) * 1000, 1),
                tokens_used=tokens,
            ))

        # The final step's output is the chain result
        final_key = self._steps[-1][0] if self._steps else ""
        final_output = context.get(final_key, "")
        try:
            final_output = json.loads(final_output) if isinstance(final_output, str) else final_output
        except (json.JSONDecodeError, TypeError):
            pass

        return ChainResult(
            output=final_output,
            steps=steps,
            total_latency_ms=round((time.monotonic() - t_start) * 1000, 1),
            total_tokens=sum(s.tokens_used for s in steps),
        )


# ---------------------------------------------------------------------------
# Code Analysis Chain — specialized for code understanding
# ---------------------------------------------------------------------------

class CodeAnalysisChain:
    """
    Analyze code with LLM for understanding, bug detection, or refactoring.

    Usage:
        chain = CodeAnalysisChain(llm)
        result = chain.analyze(
            code="def foo(): ...",
            question="What does this function do?",
        )
    """

    SYSTEM_PROMPT = (
        "You are a senior software engineer performing code analysis. "
        "Be precise, technical, and cite specific line numbers. "
        "Always explain your reasoning step-by-step."
    )

    def __init__(self, llm: LLMClient):
        self._llm = llm

    def analyze(
        self,
        code: str,
        question: str,
        *,
        language: str = "python",
        context: Optional[str] = None,
    ) -> ChainResult:
        """Analyze code and answer a specific question about it."""
        t0 = time.monotonic()

        prompt = (
            f"## Code ({language})\n```{language}\n{code[:12000]}\n```\n\n"
        )
        if context:
            prompt += f"## Additional Context\n{context[:4000]}\n\n"
        prompt += f"## Question\n{question}\n\nProvide a detailed analysis."

        try:
            resp = self._llm.generate(
                prompt,
                system_prompt=self.SYSTEM_PROMPT,
                temperature=0.2,
            )
            output = resp.text
            tokens = resp.input_tokens + resp.output_tokens
            success = True
        except Exception as exc:
            output = f"Analysis failed: {exc}"
            tokens = 0
            success = False

        return ChainResult(
            output=output,
            steps=[ChainStep(
                step_name="code_analysis",
                input_summary=f"code_length={len(code)} question='{question[:60]}'",
                output_summary=f"analysis_length={len(output)}",
                latency_ms=round((time.monotonic() - t0) * 1000, 1),
                tokens_used=tokens,
            )],
            total_latency_ms=round((time.monotonic() - t0) * 1000, 1),
            total_tokens=tokens,
            success=success,
        )

    def explain_impact(
        self,
        before_code: str,
        after_code: str,
        *,
        language: str = "python",
    ) -> ChainResult:
        """Compare two code versions and explain the impact of changes."""
        t0 = time.monotonic()

        prompt = (
            f"## Before\n```{language}\n{before_code[:6000]}\n```\n\n"
            f"## After\n```{language}\n{after_code[:6000]}\n```\n\n"
            "Analyze:\n"
            "1. What changed and why it matters\n"
            "2. Breaking changes (if any)\n"
            "3. Performance implications\n"
            "4. Security implications\n"
            "5. Downstream impact"
        )

        try:
            resp = self._llm.generate_json(
                prompt,
                system_prompt=self.SYSTEM_PROMPT,
                json_schema={
                    "type": "object",
                    "properties": {
                        "changes": {"type": "array", "items": {"type": "string"}},
                        "breaking_changes": {"type": "array", "items": {"type": "string"}},
                        "performance_impact": {"type": "string"},
                        "security_impact": {"type": "string"},
                        "downstream_impact": {"type": "array", "items": {"type": "string"}},
                        "risk_level": {"type": "string"},
                        "recommendation": {"type": "string"},
                    },
                    "required": ["changes", "risk_level", "recommendation"],
                },
            )
            tokens = 0  # no usage info from generate_json shorthand
            success = True
        except Exception as exc:
            resp = {"error": str(exc)}
            tokens = 0
            success = False

        return ChainResult(
            output=resp,
            steps=[ChainStep(
                step_name="impact_diff",
                input_summary=f"before={len(before_code)} after={len(after_code)}",
                output_summary=f"result_keys={list(resp.keys()) if isinstance(resp, dict) else 'N/A'}",
                latency_ms=round((time.monotonic() - t0) * 1000, 1),
                tokens_used=tokens,
            )],
            total_latency_ms=round((time.monotonic() - t0) * 1000, 1),
            total_tokens=tokens,
            success=success,
        )
