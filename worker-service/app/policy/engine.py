from __future__ import annotations

from collections import defaultdict, deque
from typing import Dict, List, Optional, Set, Tuple

from .models import (
    CheckStatus,
    Citation,
    EndpointSpec,
    Finding,
    ImpactEdge,
    PolicyEvaluationRequest,
    RuleConfig,
    SEVERITY_TO_STATUS,
    Severity,
)


DEFAULT_RULES: Dict[str, RuleConfig] = {
    "BREAKING_PATH_METHOD_REMOVAL": RuleConfig(enabled=True, severity=Severity.HIGH),
    "BREAKING_REQUEST_TIGHTENING": RuleConfig(enabled=True, severity=Severity.HIGH),
    "BREAKING_RESPONSE_CHANGE": RuleConfig(enabled=True, severity=Severity.HIGH),
    "BREAKING_STATUS_CODE_REMOVAL": RuleConfig(enabled=True, severity=Severity.MED),
    "DOC_DRIFT_ENDPOINT_CHANGED_NO_DOC": RuleConfig(enabled=True, severity=Severity.MED),
    "DOC_DRIFT_MISSING_OWNER": RuleConfig(enabled=True, severity=Severity.MED),
    "IMPACT_PROPAGATION": RuleConfig(enabled=True, severity=Severity.MED),
}


def _merge_rule_config(request: PolicyEvaluationRequest) -> Dict[str, RuleConfig]:
    merged = {k: RuleConfig(**v.model_dump()) for k, v in DEFAULT_RULES.items()}
    if request.config and request.config.rules:
        for key, val in request.config.rules.items():
            merged[key] = val
    return merged


def _endpoint_key(ep: EndpointSpec) -> str:
    return f"{ep.method.upper()} {ep.path}"


def _as_map(endpoints: List[EndpointSpec]) -> Dict[str, EndpointSpec]:
    return {_endpoint_key(e): e for e in endpoints}


def _evidence_for_endpoint(ep: EndpointSpec) -> Citation:
    ref = ep.operation_id or f"{ep.method.upper()} {ep.path}"
    return Citation(kind="spec", reference=ref, details=f"Endpoint {ep.method.upper()} {ep.path}")


def _finding(rule_id: str, severity: Severity, title: str, description: str, entity_refs: List[str], evidence: List[Citation], correlation_id: Optional[str]) -> Finding:
    return Finding(
        rule_id=rule_id,
        severity=severity,
        status=SEVERITY_TO_STATUS[severity],
        title=title,
        description=description,
        entity_refs=entity_refs,
        evidence=evidence,
        suggested_action="Review and remediate before merge" if severity == Severity.HIGH else "Review recommendation",
        correlation_id=correlation_id,
    )


def _check_path_method_removal(
    request: PolicyEvaluationRequest,
    rules: Dict[str, RuleConfig],
) -> List[Finding]:
    cfg = rules["BREAKING_PATH_METHOD_REMOVAL"]
    if not cfg.enabled or not request.base_spec:
        return []

    base = _as_map(request.base_spec.endpoints)
    head = _as_map(request.head_spec.endpoints)

    findings: List[Finding] = []
    removed = sorted(set(base.keys()) - set(head.keys()))
    for key in removed:
        ep = base[key]
        findings.append(
            _finding(
                "BREAKING_PATH_METHOD_REMOVAL",
                cfg.severity,
                "Endpoint removed",
                f"Endpoint {key} exists in base spec but is missing in head spec.",
                [request.head_spec.service_id, key],
                [_evidence_for_endpoint(ep)],
                request.correlation_id,
            )
        )
    return findings


def _check_request_tightening(request: PolicyEvaluationRequest, rules: Dict[str, RuleConfig]) -> List[Finding]:
    cfg = rules["BREAKING_REQUEST_TIGHTENING"]
    if not cfg.enabled or not request.base_spec:
        return []

    base = _as_map(request.base_spec.endpoints)
    head = _as_map(request.head_spec.endpoints)
    findings: List[Finding] = []

    for key in sorted(set(base.keys()) & set(head.keys())):
        b, h = base[key], head[key]

        b_required = set(b.request_required_fields)
        h_required = set(h.request_required_fields)
        newly_required = sorted(h_required - b_required)

        enum_breaks: List[str] = []
        for field, b_values in b.request_enum_fields.items():
            if field in h.request_enum_fields:
                removed = set(b_values) - set(h.request_enum_fields[field])
                if removed:
                    enum_breaks.append(f"{field} removed values: {sorted(removed)}")

        if newly_required or enum_breaks:
            desc_parts = []
            if newly_required:
                desc_parts.append(f"New required fields: {newly_required}")
            if enum_breaks:
                desc_parts.append("Enum narrowing: " + "; ".join(enum_breaks))

            findings.append(
                _finding(
                    "BREAKING_REQUEST_TIGHTENING",
                    cfg.severity,
                    "Request contract tightened",
                    " | ".join(desc_parts),
                    [request.head_spec.service_id, key],
                    [_evidence_for_endpoint(h)],
                    request.correlation_id,
                )
            )

    return findings


def _check_response_change(request: PolicyEvaluationRequest, rules: Dict[str, RuleConfig]) -> List[Finding]:
    cfg = rules["BREAKING_RESPONSE_CHANGE"]
    if not cfg.enabled or not request.base_spec:
        return []

    base = _as_map(request.base_spec.endpoints)
    head = _as_map(request.head_spec.endpoints)
    findings: List[Finding] = []

    for key in sorted(set(base.keys()) & set(head.keys())):
        b, h = base[key], head[key]
        removed_fields = sorted(set(b.response_fields.keys()) - set(h.response_fields.keys()))
        changed_types = []
        for field, b_type in b.response_fields.items():
            h_type = h.response_fields.get(field)
            if h_type is not None and h_type != b_type:
                changed_types.append(f"{field}: {b_type} -> {h_type}")

        if removed_fields or changed_types:
            detail = []
            if removed_fields:
                detail.append(f"Removed response fields: {removed_fields}")
            if changed_types:
                detail.append(f"Changed response field types: {changed_types}")

            findings.append(
                _finding(
                    "BREAKING_RESPONSE_CHANGE",
                    cfg.severity,
                    "Response contract breaking change",
                    " | ".join(detail),
                    [request.head_spec.service_id, key],
                    [_evidence_for_endpoint(h)],
                    request.correlation_id,
                )
            )

    return findings


def _check_status_code_removal(request: PolicyEvaluationRequest, rules: Dict[str, RuleConfig]) -> List[Finding]:
    cfg = rules["BREAKING_STATUS_CODE_REMOVAL"]
    if not cfg.enabled or not request.base_spec:
        return []

    base = _as_map(request.base_spec.endpoints)
    head = _as_map(request.head_spec.endpoints)
    findings: List[Finding] = []

    for key in sorted(set(base.keys()) & set(head.keys())):
        b, h = base[key], head[key]
        removed_codes = sorted(set(b.response_status_codes) - set(h.response_status_codes))
        if removed_codes:
            findings.append(
                _finding(
                    "BREAKING_STATUS_CODE_REMOVAL",
                    cfg.severity,
                    "Response status code removed",
                    f"Removed status codes: {removed_codes}",
                    [request.head_spec.service_id, key],
                    [_evidence_for_endpoint(h)],
                    request.correlation_id,
                )
            )

    return findings


def _check_doc_drift_no_doc(request: PolicyEvaluationRequest, rules: Dict[str, RuleConfig]) -> List[Finding]:
    cfg = rules["DOC_DRIFT_ENDPOINT_CHANGED_NO_DOC"]
    if not cfg.enabled:
        return []

    doc_touched = any(
        f.path.startswith("docs/") or f.path.endswith(".md")
        for f in request.changed_files
    ) or bool(request.docs_touched)

    if doc_touched:
        return []

    return [
        _finding(
            "DOC_DRIFT_ENDPOINT_CHANGED_NO_DOC",
            cfg.severity,
            "Doc drift risk",
            "Endpoint or schema changes detected without documentation updates.",
            [request.head_spec.service_id],
            [Citation(kind="file", reference=f.path) for f in request.changed_files[:5]],
            request.correlation_id,
        )
    ]


def _check_missing_owner(request: PolicyEvaluationRequest, rules: Dict[str, RuleConfig]) -> List[Finding]:
    cfg = rules["DOC_DRIFT_MISSING_OWNER"]
    if not cfg.enabled:
        return []

    findings: List[Finding] = []
    for ep in request.head_spec.endpoints:
        key = f"{request.head_spec.service_id}:{ep.method.upper()}:{ep.path}"
        owner = ep.owner or request.owners.get(key)
        if not owner:
            findings.append(
                _finding(
                    "DOC_DRIFT_MISSING_OWNER",
                    cfg.severity,
                    "Missing owner metadata",
                    f"No owner metadata found for endpoint {ep.method.upper()} {ep.path}",
                    [request.head_spec.service_id, key],
                    [_evidence_for_endpoint(ep)],
                    request.correlation_id,
                )
            )
    return findings


def _build_graph(edges: List[ImpactEdge]) -> Dict[str, List[Tuple[str, str]]]:
    g: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    for edge in edges:
        g[edge.src].append((edge.dst, edge.edge_type))
    return g


def _check_impact_propagation(request: PolicyEvaluationRequest, rules: Dict[str, RuleConfig]) -> List[Finding]:
    cfg = rules["IMPACT_PROPAGATION"]
    if not cfg.enabled or not request.impact_edges:
        return []

    graph = _build_graph(request.impact_edges)
    changed_entities: Set[str] = set()
    for ep in request.head_spec.endpoints:
        changed_entities.add(f"{request.head_spec.service_id}:{ep.method.upper()}:{ep.path}")

    findings: List[Finding] = []
    for root in sorted(changed_entities):
        visited = {root}
        q = deque([(root, [])])
        impacted = []
        while q:
            current, path = q.popleft()
            for nxt, edge_type in graph.get(current, []):
                if nxt in visited:
                    continue
                visited.add(nxt)
                npath = path + [f"{current} -[{edge_type}]-> {nxt}"]
                impacted.append((nxt, npath))
                q.append((nxt, npath))

        if impacted:
            top = impacted[:5]
            citations = [
                Citation(kind="graph-path", reference=p[0], details=" | ".join(p[1]))
                for p in top
            ]
            findings.append(
                _finding(
                    "IMPACT_PROPAGATION",
                    cfg.severity,
                    "Impact propagation detected",
                    f"{len(impacted)} potentially impacted entities reachable from {root}",
                    [root] + [p[0] for p in top],
                    citations,
                    request.correlation_id,
                )
            )

    return findings


def summary_status(findings: List[Finding]) -> CheckStatus:
    if any(f.status == CheckStatus.FAIL for f in findings):
        return CheckStatus.FAIL
    if any(f.status == CheckStatus.WARN for f in findings):
        return CheckStatus.WARN
    if any(f.status == CheckStatus.INFO for f in findings):
        return CheckStatus.INFO
    return CheckStatus.PASS


def evaluate_policies(request: PolicyEvaluationRequest) -> List[Finding]:
    rules = _merge_rule_config(request)
    findings: List[Finding] = []

    findings.extend(_check_path_method_removal(request, rules))
    findings.extend(_check_request_tightening(request, rules))
    findings.extend(_check_response_change(request, rules))
    findings.extend(_check_status_code_removal(request, rules))
    findings.extend(_check_doc_drift_no_doc(request, rules))
    findings.extend(_check_missing_owner(request, rules))
    findings.extend(_check_impact_propagation(request, rules))

    return findings
