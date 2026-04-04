"""Channel-aware response formatting for Q&A system."""

import re
from dataclasses import dataclass
from typing import Literal


@dataclass
class ChannelProfile:
    """Formatting constraints for a specific delivery channel."""
    max_answer_sentences: int | None  # None = unlimited
    citation_style: Literal["footnote", "inline", "path_only", "none"]
    allow_markdown: bool
    tone_instruction: str
    include_chain_steps: bool
    include_evidence_detail: bool



CHANNEL_PROFILES: dict[str, ChannelProfile] = {
    "web": ChannelProfile(
        max_answer_sentences=None,
        citation_style="footnote",
        allow_markdown=True,
        tone_instruction=(
            "Respond with full technical depth. Use markdown headers, "
            "code blocks, and numbered lists where helpful."
        ),
        include_chain_steps=True,
        include_evidence_detail=True,
    ),
    "chat": ChannelProfile(
        max_answer_sentences=4,
        citation_style="inline",
        allow_markdown=False,
        tone_instruction=(
            "Respond concisely in plain text. Maximum 3-4 sentences. "
            "No markdown formatting."
        ),
        include_chain_steps=False,
        include_evidence_detail=False,
    ),
    "cli": ChannelProfile(
        max_answer_sentences=6,
        citation_style="path_only",
        allow_markdown=False,
        tone_instruction=(
            "Respond in plain text. Reference file paths and line numbers "
            "directly. Be direct and actionable."
        ),
        include_chain_steps=False,
        include_evidence_detail=False,
    ),
    "api": ChannelProfile(
        max_answer_sentences=None,
        citation_style="none",  # consumer handles display
        allow_markdown=True,
        tone_instruction="Respond with full technical depth.",
        include_chain_steps=True,
        include_evidence_detail=True,
    ),
}


class ChannelFormatter:
    """Format Q&A responses for specific delivery channels."""

    def get_tone_instruction(self, channel: str) -> str:
        """
        Return tone instruction for injection into LLM system prompt.
        Called BEFORE generation. Falls back to "api" profile for unknown channels.
        """
        profile = CHANNEL_PROFILES.get(channel, CHANNEL_PROFILES["api"])
        return profile.tone_instruction

    def format_response(self, response, channel: str):
        """
        Reshape QAResponse for the target channel.
        Applied AFTER generation in this order:
        1. Strip markdown (if not allowed)
        2. Truncate to max_answer_sentences
        3. Reshape citations
        4. Remove chain_steps (if not included)
        5. Remove evidence (if not included)
        """
        profile = CHANNEL_PROFILES.get(channel, CHANNEL_PROFILES["api"])

        if not profile.allow_markdown:
            response.answer = self._strip_markdown(response.answer)

        if profile.max_answer_sentences is not None:
            response.answer = self._truncate_sentences(
                response.answer, profile.max_answer_sentences
            )

        response.citations = self._format_citations(
            response.citations, profile.citation_style
        )

        if not profile.include_chain_steps:
            response.chain_steps = []

        if not profile.include_evidence_detail:
            response.evidence = {}

        return response

    def _strip_markdown(self, text: str) -> str:
        """
        Remove markdown syntax while preserving content.
        
        Regex order matters: fenced code blocks BEFORE inline code to prevent confusion.
        """
        # Headers: ## Heading → Heading
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        # Bold: **text** → text
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
        # Italic: *text* → text
        text = re.sub(r'\*([^*]+)\*', r'\1', text)
        # Fenced code blocks: ```...``` → (removed entirely) — MUST be before inline code
        text = re.sub(r'```[^`]*```', '', text, flags=re.DOTALL)
        # Inline code: `code` → code
        text = re.sub(r'`([^`]+)`', r'\1', text)
        # Links: [text](url) → text
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        # Bullet points: - item → item (handles indented bullets)
        text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
        # Remove leading/trailing whitespace left by removed elements
        return text.strip()

    def _truncate_sentences(self, text: str, max_sentences: int) -> str:
        """Split on '. ' boundary and rejoin up to max_sentences."""
        sentences = text.split('. ')
        if len(sentences) <= max_sentences:
            return text
        return '. '.join(sentences[:max_sentences]) + '.'

    def _format_citations(self, citations: list, citation_style: str) -> list:
        """Add display field to each citation based on citation_style."""
        for i, citation in enumerate(citations):
            # Task 9.5.2: For citation_style="none", skip the iteration entirely
            if citation_style == "none":
                continue
            
            # Task 9.5.3: Extract line with proper fallback handling
            line = getattr(citation, 'line', None) or citation.get('line', 0) if isinstance(citation, dict) else 0
            
            # Task 9.5.1: Handle both dataclass and dict citations
            if hasattr(citation, 'source_ref'):
                source_ref = citation.source_ref
            else:
                source_ref = citation.get('source_ref', '')
            
            if citation_style == "footnote":
                display = f"[{i+1}] {source_ref}#L{line}"
            elif citation_style == "inline":
                display = f"(src: {source_ref})"
            elif citation_style == "path_only":
                display = f"{source_ref}:{line}"
            
            # Set display field based on citation type
            if hasattr(citation, 'display'):
                citation.display = display
            elif isinstance(citation, dict):
                citation['display'] = display
        return citations
