from __future__ import annotations

from app.policy.doc_refresh import build_doc_refresh_plan
from app.policy.engine import evaluate_policies_with_meta, list_policy_packs, resolve_policy_pack, summary_status
from app.policy.health_score import build_knowledge_health_score
from app.policy.merge_gate import build_merge_gate_decision
from app.policy.models import (
    ChangedFile,
    CheckStatus,
    EndpointSpec,
    PolicyEvaluationRequest,
    ServiceSpec,
)


def _base_and_head_request(*, tighten: bool = False, doc_touched: bool = False) -> PolicyEvaluationRequest:
    base_ep = EndpointSpec(
        method="POST",
        path="/risk/score",
        operation_id="createRiskScore",
        request_required_fields=["customerId"],
        request_enum_fields={"channel": ["SMS", "EMAIL", "WHATSAPP"]},
        response_fields={"score": "number", "state": "string"},
        response_status_codes=["200", "400"],
    )

    if tighten:
        head_ep = EndpointSpec(
            method="POST",
            path="/risk/score",
            operation_id="createRiskScore",
            request_required_fields=["customerId", "loanId"],
            request_enum_fields={"channel": ["SMS", "EMAIL"]},
            response_fields={"score": "number", "status": "string"},
            response_status_codes=["200"],
        )
    else:
        head_ep = EndpointSpec(
            method="POST",
            path="/risk/score",
            operation_id="createRiskScore",
            request_required_fields=["customerId"],
            request_enum_fields={"channel": ["SMS", "EMAIL", "WHATSAPP"]},
            response_fields={"score": "number", "state": "string"},
            response_status_codes=["200", "400"],
        )

    changed = [ChangedFile(path="api/openapi.yaml", status="modified")]
    if doc_touched:
        changed.append(ChangedFile(path="docs/changes/pr-notes.md", status="modified"))

    return PolicyEvaluationRequest(
        repo="Mithil1302/Pre-Delinquency-Intervention-Engine",
        pr_number=2,
        correlation_id="test-corr",
        base_spec=ServiceSpec(service_id="pre-delinquency-engine", endpoints=[base_ep]),
        head_spec=ServiceSpec(service_id="pre-delinquency-engine", endpoints=[head_ep]),
        changed_files=changed,
        owners={},
        docs_touched=[] if not doc_touched else ["docs/changes/pr-notes.md"],
    )


def test_policy_pack_registry_and_resolver():
    packs = list_policy_packs()
    assert "rules-v1" in packs
    pack = resolve_policy_pack("rules-v1")
    assert pack.pack_id == "rules-v1"
    assert len(pack.checks) >= 5


def test_merge_gate_blocks_on_fail():
    request = _base_and_head_request(tighten=True)
    findings, _ = evaluate_policies_with_meta(request, rule_set="rules-v1")
    status = summary_status(findings)
    assert status in {CheckStatus.FAIL, CheckStatus.WARN}

    gate = build_merge_gate_decision(findings, rule_set="rules-v1")
    assert gate["decision"] == "block"
    assert gate["counts"]["fail"] >= 1


def test_doc_refresh_decision_recommended_without_block():
    request = _base_and_head_request(tighten=False, doc_touched=False)
    findings, _ = evaluate_policies_with_meta(request, rule_set="rules-v1")

    gate = build_merge_gate_decision(findings, rule_set="rules-v1", fail_blocks_merge=False, warn_blocks_merge=False)
    plan = build_doc_refresh_plan(
        request=request,
        findings=findings,
        suggested_patches=[],
        merge_gate=gate,
        action="update_comment",
    )

    assert plan["decision"] in {"recommended", "not_needed", "required"}
    if plan["doc_finding_count"] > 0:
        assert plan["should_emit"] is True


def test_health_score_contract_fields_present():
    request = _base_and_head_request(tighten=True)
    findings, _ = evaluate_policies_with_meta(request, rule_set="rules-v1")
    gate = build_merge_gate_decision(findings, rule_set="rules-v1")
    plan = build_doc_refresh_plan(
        request=request,
        findings=findings,
        suggested_patches=[],
        merge_gate=gate,
        action="update_comment",
    )

    health = build_knowledge_health_score(
        request=request,
        findings=findings,
        merge_gate=gate,
        doc_refresh_plan=plan,
    )

    assert 0 <= float(health["score"]) <= 100
    assert health["grade"] in {"A", "B", "C", "D", "F"}
    assert set(health["dimensions"].keys()) == {"policy", "docs", "ownership"}
    assert health["inputs"]["repo"] == request.repo
