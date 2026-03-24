"""
KA-CHOW Doc Rewrite Engine — LLM-Enhanced Documentation Generation.

Produces actual documentation content using LLM when available,
with graceful fallback to template-based generation.

Documents generated:
  - PR changelog (knowledge update)
  - ADR (Architecture Decision Record)
  - Propagated doc updates for target files
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .models import Finding, PolicyEvaluationRequest

log = logging.getLogger("ka-chow.doc-rewrite")


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# LLM-powered doc generation
# ---------------------------------------------------------------------------

def _generate_changelog_with_llm(
    request: PolicyEvaluationRequest,
    findings: List[Finding],
    health: Dict[str, Any],
) -> str:
    """Generate a rich PR changelog using LLM."""
    try:
        from ..llm import get_llm_client
        from ..llm.prompts import DocRewritePrompt

        llm = get_llm_client()
        findings_data = [
            {
                "rule_id": f.rule_id,
                "title": f.title,
                "description": f.description,
                "severity": f.status.value if hasattr(f.status, "value") else str(f.status),
            }
            for f in findings[:15]
        ]

        prompt = json.dumps({
            "type": "changelog",
            "repo": request.repo,
            "pr_number": request.pr_number,
            "findings": findings_data,
            "health_score": health.get("score"),
            "health_grade": health.get("grade"),
            "health_dimensions": health.get("dimensions", {}),
            "task": (
                "Generate a detailed, well-structured PR knowledge update document in Markdown. "
                "Include: executive summary, findings breakdown by severity, health snapshot analysis, "
                "and recommended actions. Make it suitable for engineering review."
            ),
        })

        resp = llm.generate(
            prompt,
            system_prompt=DocRewritePrompt.system_prompt,
            temperature=0.3,
        )
        return resp.text
    except Exception as exc:
        log.warning("LLM changelog generation failed, using template: %s", exc)
        return _render_change_log_template(request, findings, health)


def _generate_adr_with_llm(
    request: PolicyEvaluationRequest,
    findings: List[Finding],
    merge_gate: Dict[str, Any],
) -> str:
    """Generate a detailed ADR using LLM."""
    try:
        from ..llm import get_llm_client

        llm = get_llm_client()
        findings_data = [
            {"rule_id": f.rule_id, "title": f.title, "description": f.description}
            for f in findings[:10]
        ]

        prompt = json.dumps({
            "type": "adr",
            "repo": request.repo,
            "pr_number": request.pr_number,
            "findings": findings_data,
            "merge_gate_decision": merge_gate.get("decision"),
            "merge_gate_counts": merge_gate.get("counts", {}),
            "task": (
                "Generate a proper Architecture Decision Record (ADR) in Markdown following "
                "the Michael Nygard template: Title, Status, Context, Decision, Consequences, "
                "and Alternatives Considered. Base the ADR on the policy findings and merge gate decision."
            ),
        })

        resp = llm.generate(
            prompt,
            system_prompt=(
                "You are a principal architect writing Architecture Decision Records. "
                "Be specific, reference actual findings, and provide actionable consequences. "
                "Use proper Markdown formatting."
            ),
            temperature=0.3,
        )
        return resp.text
    except Exception as exc:
        log.warning("LLM ADR generation failed, using template: %s", exc)
        return _render_adr_template(request, findings, merge_gate)


def _generate_doc_update_with_llm(
    target_file: str,
    request: PolicyEvaluationRequest,
    findings: List[Finding],
) -> str:
    """Generate targeted doc update content using LLM."""
    try:
        from ..llm import get_llm_client

        llm = get_llm_client()
        findings_data = [
            {"rule_id": f.rule_id, "title": f.title, "description": f.description}
            for f in findings[:8]
        ]

        prompt = json.dumps({
            "target_file": target_file,
            "repo": request.repo,
            "pr_number": request.pr_number,
            "findings": findings_data,
            "task": (
                f"Generate documentation content for '{target_file}' that addresses the "
                "policy findings. Include: what changed, why it changed, migration instructions "
                "if applicable, and updated API reference sections."
            ),
        })

        resp = llm.generate(
            prompt,
            system_prompt=(
                "You are a technical writer generating targeted documentation updates. "
                "Be concise but thorough. Include code examples where relevant."
            ),
            temperature=0.3,
        )
        return resp.text
    except Exception as exc:
        log.warning("LLM doc update generation failed for %s: %s", target_file, exc)
        return _render_scaffold_template(target_file, request, findings)


# ---------------------------------------------------------------------------
# Fallback template renderers (kept for resilience)
# ---------------------------------------------------------------------------

def _render_change_log_template(
    request: PolicyEvaluationRequest, findings: List[Finding], health: Dict[str, Any]
) -> str:
    lines = [
        f"# PR {request.pr_number} Knowledge Update",
        "",
        f"Repository: {request.repo}",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Health Snapshot",
        f"- Score: {health.get('score')}",
        f"- Grade: {health.get('grade')}",
        "",
        "## Findings",
    ]
    if not findings:
        lines.append("- No findings")
    for f in findings:
        lines.append(f"- [{f.rule_id}] {f.title}: {f.description}")
    return "\n".join(lines)


def _render_adr_template(
    request: PolicyEvaluationRequest, findings: List[Finding], merge_gate: Dict[str, Any]
) -> str:
    lines = [
        "# ADR: PR Policy Governance Decision",
        "",
        f"- Repo: {request.repo}",
        f"- PR: {request.pr_number}",
        f"- Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Context",
        f"Policy findings count: {len(findings)}",
        "",
        "## Decision",
        f"Merge gate decision: {merge_gate.get('decision')}",
        "",
        "## Evidence",
    ]
    for f in findings[:10]:
        lines.append(f"- {f.rule_id}: {f.title}")
    lines.extend(["", "## Consequences", "- This ADR was auto-generated and should be reviewed by maintainers."])
    return "\n".join(lines)


def _render_scaffold_template(
    target_file: str, request: PolicyEvaluationRequest, findings: List[Finding]
) -> str:
    lines = [
        f"# Documentation Update: {target_file}",
        "",
        f"Target: {target_file}",
        f"Repo: {request.repo}",
        f"PR: {request.pr_number}",
        "",
        "## Required updates",
        "- Align documentation with detected API/schema changes.",
        "- Add owner metadata and migration notes.",
        "",
        "## Relevant Findings",
    ]
    for f in findings[:5]:
        lines.append(f"- [{f.rule_id}] {f.title}: {f.description}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_doc_rewrite_bundle(
    *,
    request: PolicyEvaluationRequest,
    findings: List[Finding],
    doc_refresh_plan: Dict[str, Any],
    merge_gate: Dict[str, Any],
    knowledge_health: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build a complete doc rewrite bundle with LLM-generated content.
    Falls back to templates if LLM is unavailable.
    """
    # Generate changelog with LLM
    change_doc = _generate_changelog_with_llm(request, findings, knowledge_health)

    # Generate ADR with LLM
    adr_doc = _generate_adr_with_llm(request, findings, merge_gate)

    prn = request.pr_number or 0
    targets = [
        {
            "file_path": f"docs/changes/pr-{prn}-knowledge-update.md",
            "template": "change-log",
            "content": change_doc,
            "content_hash": _hash_text(change_doc),
            "generated_by": "llm",
        },
        {
            "file_path": f"docs/adr/ADR-pr-{prn}-policy-governance.md",
            "template": "adr",
            "content": adr_doc,
            "content_hash": _hash_text(adr_doc),
            "generated_by": "llm",
        },
    ]

    # Generate targeted doc updates
    source_targets = doc_refresh_plan.get("target_files") or []
    for tf in source_targets:
        content = _generate_doc_update_with_llm(tf, request, findings)
        targets.append(
            {
                "file_path": tf,
                "template": "propagated-update",
                "content": content,
                "content_hash": _hash_text(content),
                "generated_by": "llm",
            }
        )

    return {
        "repo": request.repo,
        "pr_number": request.pr_number,
        "decision": doc_refresh_plan.get("decision"),
        "priority": doc_refresh_plan.get("priority"),
        "targets": targets,
        "target_count": len(targets),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
