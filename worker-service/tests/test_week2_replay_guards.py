from __future__ import annotations

import logging

from app.policy.models import PolicyEvaluationRequest, ServiceSpec
from app.policy.pipeline import PolicyPipeline


def _request() -> PolicyEvaluationRequest:
    return PolicyEvaluationRequest(
        repo="Mithil1302/Pre-Delinquency-Intervention-Engine",
        pr_number=42,
        correlation_id="corr-week2-test",
        head_spec=ServiceSpec(service_id="svc", endpoints=[]),
        changed_files=[],
    )


def test_event_dedup_key_stable_for_same_payload_without_idempotency():
    pipeline = PolicyPipeline(logging.getLogger("test-week2"))
    request = _request()
    payload = {
        "event_type": "pull_request",
        "correlation_id": "corr-week2-test",
        "repo": {"full_name": request.repo},
        "pull_request": {"number": request.pr_number},
    }

    k1 = pipeline._event_dedup_key(payload, request, "rules-v1")
    k2 = pipeline._event_dedup_key(payload, request, "rules-v1")
    assert k1 == k2


def test_event_dedup_key_uses_explicit_idempotency_when_present():
    pipeline = PolicyPipeline(logging.getLogger("test-week2"))
    request = _request()
    payload = {
        "event_type": "pull_request",
        "idempotency_key": "idem-week2-123",
        "repo": {"full_name": request.repo},
        "pull_request": {"number": request.pr_number},
    }

    key = pipeline._event_dedup_key(payload, request, "rules-v1")
    assert key.endswith(":idem-week2-123")
