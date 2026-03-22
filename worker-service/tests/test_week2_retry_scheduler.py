from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.policy.pipeline import PolicyPipeline


def test_due_for_retry_true_when_missing_next_attempt():
    pipeline = PolicyPipeline(logging.getLogger("test-retry-scheduler"))
    assert pipeline._due_for_retry({}) is True


def test_due_for_retry_respects_future_timestamp():
    pipeline = PolicyPipeline(logging.getLogger("test-retry-scheduler"))
    future = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    assert pipeline._due_for_retry({"next_attempt_at": future}) is False


def test_due_for_retry_true_for_past_timestamp():
    pipeline = PolicyPipeline(logging.getLogger("test-retry-scheduler"))
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    assert pipeline._due_for_retry({"next_attempt_at": past}) is True
