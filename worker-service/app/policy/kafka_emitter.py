"""
kafka_emitter.py — Kafka produce helpers for the policy pipeline.

KafkaEmitter wraps a KafkaProducer and provides one method per event type
so the pipeline orchestrator never handles serialisation or topic routing.
"""
from __future__ import annotations

import json
from typing import Any, Dict

from kafka import KafkaProducer


class KafkaEmitter:
    """Thin wrapper around KafkaProducer for the three policy event types."""

    def __init__(
        self,
        producer: KafkaProducer,
        *,
        output_topic: str,
        docs_refresh_topic: str,
        docs_rewrite_topic: str,
    ) -> None:
        self._producer = producer
        self._output_topic = output_topic
        self._docs_refresh_topic = docs_refresh_topic
        self._docs_rewrite_topic = docs_rewrite_topic

    # ------------------------------------------------------------------
    # Public emit methods
    # ------------------------------------------------------------------

    def emit_check_event(self, event: Dict[str, Any]) -> None:
        """Produce a policy check result to the pr.checks topic."""
        self._producer.send(
            self._output_topic,
            key=(event.get("comment_key") or "policy-check").encode("utf-8"),
            value=json.dumps(event, default=str).encode("utf-8"),
            headers=[
                ("x-correlation-id", str(event.get("correlation_id") or "").encode("utf-8")),
                ("x-repo",           str(event.get("repo")           or "").encode("utf-8")),
                ("x-pr-number",      str(event.get("pr_number")      or "").encode("utf-8")),
            ],
        )
        self._producer.flush(timeout=5)

    def emit_doc_refresh_event(self, event: Dict[str, Any]) -> None:
        """Produce a doc refresh plan to the docs.refresh topic."""
        self._producer.send(
            self._docs_refresh_topic,
            key=(event.get("doc_refresh_key") or "doc-refresh").encode("utf-8"),
            value=json.dumps(event, default=str).encode("utf-8"),
            headers=[
                ("x-correlation-id", str(event.get("correlation_id") or "").encode("utf-8")),
                ("x-repo",           str(event.get("repo")           or "").encode("utf-8")),
                ("x-pr-number",      str(event.get("pr_number")      or "").encode("utf-8")),
            ],
        )
        self._producer.flush(timeout=5)

    def emit_doc_rewrite_event(self, event: Dict[str, Any]) -> None:
        """Produce a doc rewrite bundle to the docs.rewrite topic."""
        self._producer.send(
            self._docs_rewrite_topic,
            key=(event.get("rewrite_key") or "doc-rewrite").encode("utf-8"),
            value=json.dumps(event, default=str).encode("utf-8"),
            headers=[
                ("x-correlation-id", str(event.get("correlation_id") or "").encode("utf-8")),
                ("x-repo",           str(event.get("repo")           or "").encode("utf-8")),
                ("x-pr-number",      str(event.get("pr_number")      or "").encode("utf-8")),
            ],
        )
        self._producer.flush(timeout=5)

    def emit_by_type(self, emit_type: str, event_payload: Dict[str, Any]) -> None:
        """Dispatch to the correct emit method based on emit_type string."""
        if emit_type == "policy_check":
            self.emit_check_event(event_payload)
        elif emit_type == "doc_refresh":
            self.emit_doc_refresh_event(event_payload)
        elif emit_type == "doc_rewrite":
            self.emit_doc_rewrite_event(event_payload)
        else:
            raise ValueError(f"unsupported emit_type for retry: {emit_type}")
