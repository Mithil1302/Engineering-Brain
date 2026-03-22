from __future__ import annotations

import logging

from app.policy.pipeline import PolicyPipeline


def test_emit_retry_idempotency_key_stable():
    pipeline = PolicyPipeline(logging.getLogger("test-emit-retry"))
    k1 = pipeline._emit_retry_idempotency_key(
        emit_type="policy_check",
        base_idempotency_key="idem-123",
        repo="owner/repo",
        pr_number=55,
    )
    k2 = pipeline._emit_retry_idempotency_key(
        emit_type="policy_check",
        base_idempotency_key="idem-123",
        repo="owner/repo",
        pr_number=55,
    )
    assert k1 == k2
    assert k1.startswith("emit-retry:policy_check:owner/repo:55:")


def test_emit_retry_idempotency_key_differs_by_emit_type():
    pipeline = PolicyPipeline(logging.getLogger("test-emit-retry"))
    a = pipeline._emit_retry_idempotency_key(
        emit_type="policy_check",
        base_idempotency_key="idem-123",
        repo="owner/repo",
        pr_number=55,
    )
    b = pipeline._emit_retry_idempotency_key(
        emit_type="doc_refresh",
        base_idempotency_key="idem-123",
        repo="owner/repo",
        pr_number=55,
    )
    assert a != b
