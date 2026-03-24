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
        rerank: bool = True,
        rerank_top_k: int = 5,
    ):
        self._llm = llm
        self._store = store
        self._top_k = top_k
        self._rerank = rerank
        self._rerank_top_k = rerank_top_k

    def run(
        self,
        query: str,
        *,
        evidence: Optional[Dict[str, Any]] = None,
        source_types: Optional[List[str]] = None,
        system_prompt: Optional[str] = None,
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

        # --- Step 2: Re-rank (optional) ------------------------------------
        if self._rerank and len(results) > self._rerank_top_k:
            t0 = time.monotonic()
            results = self._rerank_chunks(query, results)
            steps.append(ChainStep(
                step_name="rerank",
                input_summary=f"ranking {len(results)} chunks",
                output_summary=f"kept top {min(len(results), self._rerank_top_k)}",
                latency_ms=round((time.monotonic() - t0) * 1000, 1),
            ))
            results = results[: self._rerank_top_k]

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

        try:
            llm_resp = self._llm.generate(
                user_prompt,
                system_prompt=system_prompt or prompt_cls.system_prompt,
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
                for idx in resp:
                    if isinstance(idx, int) and 0 <= idx < len(chunks):
                        reranked.append(chunks[idx])
                return reranked if reranked else chunks
        except Exception:
            pass
        return chunks


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
