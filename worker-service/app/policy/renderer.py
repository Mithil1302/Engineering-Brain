from __future__ import annotations

from collections import defaultdict
from typing import List

from .models import CheckStatus, Citation, Finding, PolicyEvaluationRequest, PolicyEvaluationResponse, SuggestedPatch


def _status_emoji(status: CheckStatus) -> str:
    return {
        CheckStatus.FAIL: "❌",
        CheckStatus.WARN: "⚠️",
        CheckStatus.INFO: "ℹ️",
        CheckStatus.PASS: "✅",
    }[status]


def _render_findings(findings: List[Finding]) -> str:
    if not findings:
        return "- No findings detected."

    lines: List[str] = []
    for f in findings:
        lines.append(f"- {_status_emoji(f.status)} **{f.title}** (`{f.rule_id}` / {f.severity})")
        lines.append(f"  - {f.description}")
        if f.entity_refs:
            lines.append(f"  - Entities: {', '.join(f.entity_refs)}")
        if f.evidence:
            refs = "; ".join([c.reference for c in f.evidence])
            lines.append(f"  - Citations: {refs}")
    return "\n".join(lines)


def _render_patches(patches: List[SuggestedPatch]) -> str:
    if not patches:
        return "- No patch suggestions generated."

    lines = []
    for p in patches:
        lines.append(f"- **{p.summary}** (`{p.patch_type}` → `{p.file_path}`)")
    return "\n".join(lines)


def _render_affected(findings: List[Finding]) -> str:
    affected = sorted({e for f in findings for e in f.entity_refs})
    return ", ".join(affected) if affected else "None"


def render_markdown_comment(request: PolicyEvaluationRequest, response: PolicyEvaluationResponse) -> str:
    findings = response.findings
    grouped = defaultdict(int)
    for f in findings:
        grouped[f.status] += 1

    status_summary = " ".join([f"{_status_emoji(s)} {s}:{grouped.get(s, 0)}" for s in [CheckStatus.FAIL, CheckStatus.WARN, CheckStatus.INFO]])

    body = [
        f"## KA-CHOW PR Policy Check – Repo `{request.repo}` PR `{request.pr_number or 'n/a'}`",
        "",
        f"**Overall status:** {_status_emoji(response.summary_status)} `{response.summary_status}`",
        f"**Finding counters:** {status_summary}",
        f"**Affected entities:** {_render_affected(findings)}",
        "",
        "### Key findings",
        _render_findings(findings),
        "",
        "### Suggested patches",
        _render_patches(response.suggested_patches),
    ]
    return "\n".join(body)


def build_annotations(findings: List[Finding]) -> List[dict]:
    annotations = []
    for f in findings:
        for ev in f.evidence:
            if ev.kind in {"file", "line"}:
                annotations.append(
                    {
                        "path": ev.reference,
                        "start_line": ev.line_start or 1,
                        "end_line": ev.line_end or ev.line_start or 1,
                        "annotation_level": "failure" if f.status == CheckStatus.FAIL else "warning",
                        "message": f"{f.rule_id}: {f.description}",
                        "title": f.title,
                    }
                )
    return annotations


def assemble_response(
    request: PolicyEvaluationRequest,
    summary_status: CheckStatus,
    findings: List[Finding],
    suggested_patches: List[SuggestedPatch],
) -> PolicyEvaluationResponse:
    citations: List[Citation] = [c for f in findings for c in f.evidence]
    response = PolicyEvaluationResponse(
        repo=request.repo,
        pr_number=request.pr_number,
        summary_status=summary_status,
        findings=findings,
        suggested_patches=suggested_patches,
        citations=citations,
        markdown_comment="",
        check_annotations=build_annotations(findings),
    )
    response.markdown_comment = render_markdown_comment(request, response)
    return response
