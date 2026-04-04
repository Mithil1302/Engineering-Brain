"""
Slack Delivery Adapter

Verifies Slack request signatures, builds Block Kit payloads, and delivers
Q&A responses to Slack channels.
"""

import hashlib
import hmac
import json
import logging
import time
import uuid
from typing import Any

import httpx
import psycopg2
from psycopg2.extras import RealDictCursor

log = logging.getLogger(__name__)


class SlackDeliveryAdapter:
    """
    Adapter for delivering Q&A responses to Slack channels.
    
    Handles:
    - HMAC-SHA256 signature verification with replay attack prevention
    - Block Kit payload construction
    - Session management for conversation continuity
    - Best-effort message delivery
    """

    def __init__(self, signing_secret: str, bot_token: str, pg_cfg: dict):
        """
        Initialize Slack adapter.
        
        Args:
            signing_secret: Slack signing secret for HMAC verification
            bot_token: Slack bot token for API calls
            pg_cfg: PostgreSQL connection configuration
        """
        self.signing_secret = signing_secret
        self.bot_token = bot_token
        self.pg_cfg = pg_cfg

    def verify_signature(self, body: bytes, timestamp: str, signature: str) -> bool:
        """
        Verify Slack request signature using HMAC-SHA256.
        
        Implements Slack's signature verification protocol:
        1. Check timestamp freshness (< 5 minutes) to prevent replay attacks
        2. Compute HMAC-SHA256 of v0:{timestamp}:{body}
        3. Compare using constant-time comparison
        
        Args:
            body: Raw request body bytes (before JSON parsing)
            timestamp: X-Slack-Request-Timestamp header value
            signature: X-Slack-Signature header value
            
        Returns:
            True if signature is valid and timestamp is fresh, False otherwise
        """
        # Parse timestamp
        try:
            ts = int(timestamp)
        except (ValueError, TypeError):
            log.warning("Invalid timestamp format in Slack request")
            return False

        # Check timestamp freshness FIRST (Task 10.1.2)
        # Prevents wasted computation on replay attempts
        if abs(time.time() - ts) > 300:
            log.warning(f"Slack request timestamp too old: {timestamp}")
            return False

        # Build signature basestring (Task 10.1.3)
        # This exact format is required by Slack
        sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"

        # Compute HMAC-SHA256
        computed = "v0=" + hmac.new(
            self.signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256,
        ).hexdigest()

        # Constant-time comparison (Task 10.1.4)
        # Prevents timing attacks
        return hmac.compare_digest(computed, signature)

    def build_block_kit(self, response: Any, session_id: str) -> dict:
        """
        Construct Slack Block Kit payload from QAResponse.
        
        Blocks structure:
        1. Answer section (plain_text for safety)
        2. Citations context (max 3, then "+N more")
        3. Confidence warning (if < 0.6)
        4. Follow-up buttons (max 3, text truncated to 75 chars)
        
        Args:
            response: QAResponse object with answer, citations, confidence, follow_ups
            session_id: Session ID for embedding in button payloads
            
        Returns:
            Block Kit payload dict ready for chat.postMessage
        """
        blocks = []

        # Block 1: Answer (plain_text always safe, no injection risk)
        blocks.append({
            "type": "section",
            "text": {
                "type": "plain_text",
                "text": response.answer,
                "emoji": False,
            },
        })

        # Block 2: Citations (max 3, then "+N more")
        citations = response.citations or []
        if citations:
            display_texts = []
            for c in citations[:3]:
                # Handle both dataclass and dict citations
                if hasattr(c, 'display'):
                    display_texts.append(c.display)
                elif isinstance(c, dict) and 'display' in c:
                    display_texts.append(c['display'])
                elif hasattr(c, 'source_ref'):
                    display_texts.append(c.source_ref)
                elif isinstance(c, dict) and 'source_ref' in c:
                    display_texts.append(c['source_ref'])
                else:
                    display_texts.append(str(c))

            # Add "+N more" if there are more than 3 citations
            if len(citations) > 3:
                display_texts.append(f"+{len(citations) - 3} more")

            blocks.append({
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": " | ".join(display_texts)}],
            })

        # Block 3: Low confidence warning (conditional)
        if response.confidence < 0.6:
            blocks.append({
                "type": "context",
                "elements": [{
                    "type": "mrkdwn",
                    "text": (
                        f"⚠️ This answer may be incomplete "
                        f"(confidence: {response.confidence:.0%})"
                    ),
                }],
            })

        # Block 4: Follow-up buttons (max 3, text truncated to 75 chars)
        follow_ups = response.follow_up_questions or []
        if follow_ups:
            actions = []
            for i, question in enumerate(follow_ups[:3]):
                # Embed session_id in button payload for conversation continuity
                value = json.dumps({
                    "question": question,
                    "session_id": session_id,
                })
                # Slack rejects button text exceeding 75 characters
                actions.append({
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": question[:75],
                    },
                    "value": value,
                    "action_id": f"followup_{i}",
                })
            blocks.append({"type": "actions", "elements": actions})

        return {"blocks": blocks}

    async def deliver(self, channel: str, response: Any, session_id: str) -> bool:
        """
        Deliver Q&A response to Slack channel via chat.postMessage.
        
        Best-effort delivery:
        - Logs WARNING on failure
        - Never raises exceptions
        - No retry logic (fire-and-forget)
        
        Args:
            channel: Slack channel ID
            response: QAResponse object
            session_id: Session ID for button payloads
            
        Returns:
            True if delivery succeeded, False otherwise
        """
        try:
            payload = self.build_block_kit(response, session_id)
            payload["channel"] = channel

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={
                        "Authorization": f"Bearer {self.bot_token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=10.0,
                )
                data = resp.json()

                # HTTP 200 does not mean delivery success
                # Slack returns HTTP 200 with {"ok": false, "error": "..."} for errors
                if not data.get("ok"):
                    log.warning(
                        f"Slack delivery failed: {data.get('error')}, "
                        f"channel={channel}"
                    )
                    return False

                return True

        except Exception as e:
            log.warning(f"Slack delivery exception: {e}, channel={channel}")
            return False

    def get_or_create_session(self, slack_channel: str, slack_user: str) -> str:
        """
        Get or create session for Slack channel + user combination.
        
        Uses UPSERT pattern:
        - If session exists: updates last_active_at and returns existing session_id
        - If session doesn't exist: creates new session with new UUID
        
        Args:
            slack_channel: Slack channel ID
            slack_user: Slack user ID
            
        Returns:
            Session ID (existing or newly created)
        """
        with psycopg2.connect(**self.pg_cfg) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Generate new UUID before INSERT
                # The INSERT may use existing session_id on conflict
                new_session_id = str(uuid.uuid4())

                cur.execute(
                    """
                    INSERT INTO meta.slack_sessions
                    (slack_channel, slack_user, session_id, created_at, last_active_at)
                    VALUES (%s, %s, %s, NOW(), NOW())
                    ON CONFLICT (slack_channel, slack_user) DO UPDATE
                    SET last_active_at = NOW()
                    RETURNING session_id
                    """,
                    (slack_channel, slack_user, new_session_id),
                )
                conn.commit()
                return cur.fetchone()["session_id"]
