
from fastapi import APIRouter, Depends, HTTPException, status

from ..dependencies import (
    pipeline, auth_admin, auth_read_scoped, enforce_repo_scope, AuthContext
)

router = APIRouter()

from ..policy.models import PolicyEvaluationRequest
from ..policy.engine import evaluate_policies, summary_status
from ..policy.renderer import assemble_response
from ..policy.patches import build_suggested_patches
from ..policy.merge_gate import build_merge_gate_decision
from ..policy.doc_refresh import build_doc_refresh_plan
from ..policy.health_score import build_knowledge_health_score

@router.get("/policy/pipeline/health")
def policy_pipeline_health(_auth: AuthContext = Depends(auth_admin)):
    return pipeline.health()


@router.get("/policy/pipeline/readiness")
def policy_pipeline_readiness(_auth: AuthContext = Depends(auth_admin)):
    return pipeline.readiness_signals()


@router.post("/policy/evaluate")
def policy_evaluate(request: PolicyEvaluationRequest, auth: AuthContext = Depends(auth_read_scoped)):
    enforce_repo_scope(auth, request.repo)
    selected_rule_set = (request.config.rule_pack if request.config and request.config.rule_pack else "rules-v1")
    findings = evaluate_policies(request, rule_set=selected_rule_set)
    patches = build_suggested_patches(findings)
    eval_status = summary_status(findings)
    response = assemble_response(request, eval_status, findings, patches)
    payload = response.model_dump()
    merge_gate = build_merge_gate_decision(findings, rule_set=selected_rule_set)
    merge_gate["policy_action"] = "preview"
    payload["merge_gate"] = merge_gate
    payload["doc_refresh_plan"] = build_doc_refresh_plan(
        request=request,
        findings=findings,
        suggested_patches=patches,
        merge_gate=merge_gate,
        action="preview",
    )
    payload["knowledge_health"] = build_knowledge_health_score(
        request=request,
        findings=findings,
        merge_gate=merge_gate,
        doc_refresh_plan=payload["doc_refresh_plan"],
    )
    payload["rule_set"] = selected_rule_set
    return payload
