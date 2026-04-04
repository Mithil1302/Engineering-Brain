"""
Slack Webhook Routes

Handles incoming Slack webhook events including:
- URL verification challenge
- App mentions and direct messages
- Button action interactions
"""

import json
import logging
import os
import re
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Header, Request
from fastapi.responses import JSONResponse

from ...dependencies import PG_CFG, embedding_store
from ...qa.assistant import answer_conversation
from ..channel_formatter import ChannelFormatter

log = logging.getLogger(__name__)

slack_router = APIRouter()

# Lazy-initialized singleton
_slack_adapter: Optional["SlackDeliveryAdapter"] = None


def get_slack_adapter():
    """Get or create the Slack adapter singleton."""
    global _slack_adapter
    if _slack_adapter is None:
        from .adapter import SlackDeliveryAdapter
        
        signing_secret = os.getenv("SLACK_SIGNING_SECRET", "")
        bot_token = os.getenv("SLACK_BOT_TOKEN", "")
        
        if not signing_secret or not bot_token:
            log.error(
                "SLACK_SIGNING_SECRET and SLACK_BOT_TOKEN must be set. "
                "Slack adapter will not function."
            )
            # Return a dummy adapter that will fail signature verification
            # This prevents startup failure but logs errors on webhook attempts
        
        _slack_adapter = SlackDeliveryAdapter(
            signing_secret=signing_secret,
            bot_token=bot_token,
            pg_cfg=PG_CFG,
        )
    
    return _slack_adapter


def _get_repo_for_slack_session(session_id: str) -> str:
    """
    Get repository for a Slack session.
    
    For now, returns the default repo from environment.
    Future: could store repo preference per Slack workspace in database.
    """
    return os.getenv("DEFAULT_REPO", "")


@slack_router.post("/adapters/slack/webhook")
async def slack_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_slack_request_timestamp: str = Header(None),
    x_slack_signature: str = Header(None),
) -> JSONResponse:
    """
    Handle all Slack webhook events.
    
    Returns HTTP 200 within 3 seconds per Slack requirements.
    - url_verification: handled synchronously (Slack 3s timeout)
    - All other events: processed in BackgroundTask
    
    Security:
    - Verifies HMAC-SHA256 signature
    - Checks timestamp freshness (< 5 minutes)
    - Returns HTTP 403 on signature failure (Slack convention)
    """
    # Task 10.5.1: Read raw body BEFORE json.loads
    # Required for signature verification
    body = await request.body()
    
    adapter = get_slack_adapter()
    
    # Verify signature
    if not adapter.verify_signature(body, x_slack_request_timestamp, x_slack_signature):
        log.warning(
            f"Slack signature verification failed. "
            f"Delivery ID: {request.headers.get('x-slack-request-timestamp')}"
        )
        # Task 10.5.2: Return HTTP 403 (not 401) on Slack signature failure
        # This is Slack's convention
        return JSONResponse({"error": "invalid signature"}, status_code=403)
    
    # Parse payload after signature verification
    payload = json.loads(body)
    
    # Task 10.5.3: url_verification MUST be handled synchronously
    # Slack times out the verification handshake in 3 seconds
    if payload.get("type") == "url_verification":
        return JSONResponse({"challenge": payload["challenge"]})
    
    # Task 10.5.4: All other events processed in background
    # Return immediately to meet Slack's 3-second response requirement
    background_tasks.add_task(_process_slack_event, payload)
    return JSONResponse({"ok": True})


async def _process_slack_event(payload: dict) -> None:
    """
    Background task: route Slack event to appropriate handler.
    
    Handles:
    - event_callback: app_mention and message events
    - block_actions: button click interactions
    """
    try:
        event_type = payload.get("type")
        
        if event_type == "event_callback":
            event = payload.get("event", {})
            event_subtype = event.get("type")
            
            if event_subtype in {"app_mention", "message"}:
                # Skip bot messages to prevent loops (Task 10.6.1)
                if event.get("bot_id") or event.get("subtype") == "bot_message":
                    log.debug("Skipping bot message to prevent loop")
                    return
                
                await _handle_slack_message(event)
        
        elif event_type == "block_actions":
            await _handle_slack_button_action(payload)
        
        else:
            log.debug(f"Unhandled Slack event type: {event_type}")
    
    except Exception as e:
        log.error(f"Slack event processing failed: {e}", exc_info=True)


async def _handle_slack_message(event: dict) -> None:
    """
    Handle app_mention and direct message events.
    
    Flow:
    1. Extract channel and user
    2. Strip @mention from question text
    3. Get or create session for conversation continuity
    4. Run Q&A with chat channel formatting
    5. Deliver response via Block Kit
    """
    adapter = get_slack_adapter()
    channel = event.get("channel", "")
    user = event.get("user", "unknown")
    
    # Task 10.6.2: Strip @mention from question text
    # Pattern matches Slack's @mention format: <@USER_ID>
    question = re.sub(r'<@[A-Z0-9]+>', '', event.get("text", "")).strip()
    
    # Return early if stripped question is empty
    if not question:
        log.debug("Empty question after stripping @mention")
        return
    
    # Get or create session for conversation continuity
    session_id = adapter.get_or_create_session(channel, user)
    
    # Determine repo from session or use configured default
    repo = _get_repo_for_slack_session(session_id)
    
    if not repo:
        log.warning(f"No repo configured for Slack session {session_id}")
        # Could send an error message to Slack here
        return
    
    # Run Q&A with chat channel formatting
    formatter = ChannelFormatter()
    
    try:
        response = answer_conversation(
            question=question,
            history=[],  # History managed via session_id
            repo=repo,
            pg_cfg=PG_CFG,
            session_id=session_id,
        )
        
        # Format response for chat channel
        formatted = formatter.format_response(response, "chat")
        
        # Deliver via Block Kit
        success = await adapter.deliver(channel, formatted, session_id)
        
        if not success:
            log.warning(f"Failed to deliver Slack response to channel {channel}")
    
    except Exception as e:
        log.error(f"Error processing Slack message: {e}", exc_info=True)


async def _handle_slack_button_action(payload: dict) -> None:
    """
    Handle follow-up button clicks from Block Kit actions.
    
    Task 10.6.3: Parse button value as JSON to extract question and session_id.
    The session_id enables conversation continuity across button clicks.
    """
    adapter = get_slack_adapter()
    
    try:
        action = payload.get("actions", [{}])[0]
        value = json.loads(action.get("value", "{}"))
        
        question = value.get("question", "")
        session_id = value.get("session_id", "")
        
        if not question or not session_id:
            log.warning("Button action missing question or session_id")
            return
        
        channel = payload.get("channel", {}).get("id", "")
        if not channel:
            log.warning("Button action missing channel ID")
            return
        
        repo = _get_repo_for_slack_session(session_id)
        
        if not repo:
            log.warning(f"No repo configured for Slack session {session_id}")
            return
        
        # Run Q&A with the follow-up question
        formatter = ChannelFormatter()
        
        response = answer_conversation(
            question=question,
            history=[],  # History managed via session_id
            repo=repo,
            pg_cfg=PG_CFG,
            session_id=session_id,
        )
        
        # Format response for chat channel
        formatted = formatter.format_response(response, "chat")
        
        # Deliver via Block Kit
        success = await adapter.deliver(channel, formatted, session_id)
        
        if not success:
            log.warning(f"Failed to deliver button response to channel {channel}")
    
    except json.JSONDecodeError as e:
        log.error(f"Failed to parse button action value: {e}")
    except Exception as e:
        log.error(f"Error processing Slack button action: {e}", exc_info=True)
