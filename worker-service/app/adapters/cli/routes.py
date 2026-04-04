"""CLI adapter SSE endpoint for streaming Q&A responses."""

import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ...dependencies import (
    PG_CFG,
    auth_read_scoped,
    enforce_repo_scope,
    AuthContext,
    embedding_store,
)
from ...qa.assistant import answer_conversation
from ..channel_formatter import ChannelFormatter

log = logging.getLogger("worker-service.cli")

cli_router = APIRouter(prefix="/adapters/cli", tags=["cli"])


class CLIRequest(BaseModel):
    """CLI streaming request."""
    question: str = Field(min_length=3)
    repo: str
    session_id: Optional[str] = None


@cli_router.post("/ask")
async def cli_ask(
    request: CLIRequest,
    auth: AuthContext = Depends(auth_read_scoped),
):
    """
    Stream Q&A response as SSE.
    Events: token → token → ... → metadata → [DONE]
    Headers: text/event-stream, no-cache, X-Accel-Buffering: no
    """
    if not request.repo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="repo is required"
        )
    enforce_repo_scope(auth, request.repo)
    
    # Task 11.1.2: Generate new UUID when absent; non-fatal, just loses conversation context
    session_id = request.session_id or str(uuid.uuid4())
    
    async def event_generator():
        try:
            formatter = ChannelFormatter()
            # Get tone instruction for CLI channel
            tone = formatter.get_tone_instruction("cli")
            
            # For now, use the non-streaming answer_conversation
            # Task 11.2 will implement stream_answer() on QAAssistant
            response = answer_conversation(
                question=request.question,
                history=[],
                repo=request.repo,
                pg_cfg=PG_CFG,
                session_id=session_id,
                channel="cli",
            )
            
            # Apply channel formatting
            formatted = formatter.format_response(response, "cli")
            
            # Stream the answer as tokens (simulate streaming for now)
            # This will be replaced with actual streaming in Task 11.2
            answer_text = formatted.answer
            for char in answer_text:
                # Task 11.1.4: Token event format with double newline
                yield f"data: {json.dumps({'type': 'token', 'text': char})}\n\n"
            
            # Task 11.1.5: Metadata event with citations, follow_ups, confidence, intent
            metadata = {
                "type": "metadata",
                "citations": [
                    {
                        "display": getattr(c, 'display', '') if hasattr(c, 'display') else c.get('display', ''),
                        "source_ref": getattr(c, 'source_ref', '') if hasattr(c, 'source_ref') else c.get('source_ref', ''),
                    }
                    for c in (formatted.citations or [])
                ],
                "follow_ups": formatted.follow_up_questions or [],
                "confidence": formatted.confidence,
                "intent": formatted.intent,
            }
            yield f"data: {json.dumps(metadata)}\n\n"
            
            # Task 11.1.7: [DONE] marker in exact format
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            log.error(f"CLI stream error: {e}", exc_info=True)
            # Task 11.1.6: Error event format followed by [DONE]
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            yield "data: [DONE]\n\n"
    
    # Task 11.1.3: SSE response headers - all four required
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
            "Connection": "keep-alive",
        },
    )
