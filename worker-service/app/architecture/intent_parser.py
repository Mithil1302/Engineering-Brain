from __future__ import annotations

import re
from typing import Dict, List

from .models import (
    AmbiguityItem,
    AmbiguityReport,
    ClarificationQuestion,
    Conflict,
    ConflictSeverity,
    Constraint,
    ConstraintSet,
    ConstraintType,
)

_TRAFFIC_RE = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>[kKmM]?)\s*(?:rpm|rps|req/s|requests?\s*/\s*(?:min|sec))")
_TEAM_RE = re.compile(r"(?:(?:team|engineers?|devs?|people|members?)\s*(?:of|size)?\s*)(?P<size>\d{1,3})")
_LATENCY_RE = re.compile(r"(?:sub[-\s]?)?(?P<ms>\d+(?:\.\d+)?)\s*ms")
_BUDGET_RE = re.compile(r"\$\s*(?P<budget>\d+(?:\.\d+)?)\s*(?P<period>\/month|per\s*month|monthly)?")
_TIMELINE_RE = re.compile(r"(?:in|within)\s+(?P<weeks>\d{1,2})\s+weeks?")

_COMPLIANCE_KEYWORDS = {
    "hipaa": "HIPAA",
    "gdpr": "GDPR",
    "pci": "PCI-DSS",
    "soc2": "SOC2",
    "iso27001": "ISO27001",
}

_TECH_PREFS = ["postgres", "mongodb", "kafka", "redis", "python", "node", "grpc", "graphql", "kubernetes"]


def _to_float(value: str) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _normalize_traffic(value: float, unit: str) -> float:
    mul = 1.0
    u = (unit or "").lower()
    if u == "k":
        mul = 1_000.0
    elif u == "m":
        mul = 1_000_000.0
    return value * mul


def extract_constraints(requirement_text: str) -> ConstraintSet:
    text = requirement_text or ""
    lower = text.lower()
    constraints: List[Constraint] = []

    for m in _TRAFFIC_RE.finditer(lower):
        raw = _to_float(m.group("value"))
        normalized = _normalize_traffic(raw, m.group("unit"))
        constraints.append(
            Constraint(
                type=ConstraintType.TRAFFIC_RPM,
                value=raw,
                normalized_value=normalized,
                units="rpm",
                confidence=0.9,
                source_span=text[m.start():m.end()],
                priority=0.9,
            )
        )

    for m in _TEAM_RE.finditer(lower):
        team_size = int(m.group("size"))
        constraints.append(
            Constraint(
                type=ConstraintType.TEAM_SIZE,
                value=team_size,
                normalized_value=team_size,
                units="people",
                confidence=0.85,
                source_span=text[m.start():m.end()],
                priority=0.8,
            )
        )

    for m in _LATENCY_RE.finditer(lower):
        latency = _to_float(m.group("ms"))
        constraints.append(
            Constraint(
                type=ConstraintType.LATENCY_SLA_MS,
                value=latency,
                normalized_value=latency,
                units="ms",
                confidence=0.88,
                source_span=text[m.start():m.end()],
                priority=0.92,
            )
        )

    for m in _BUDGET_RE.finditer(lower):
        budget = _to_float(m.group("budget"))
        constraints.append(
            Constraint(
                type=ConstraintType.BUDGET_MONTHLY,
                value=budget,
                normalized_value=budget,
                units="USD/month",
                confidence=0.8,
                source_span=text[m.start():m.end()],
                priority=0.7,
            )
        )

    for m in _TIMELINE_RE.finditer(lower):
        weeks = int(m.group("weeks"))
        constraints.append(
            Constraint(
                type=ConstraintType.TIMELINE,
                value=weeks,
                normalized_value=weeks,
                units="weeks",
                confidence=0.76,
                source_span=text[m.start():m.end()],
                priority=0.65,
            )
        )

    for key, label in _COMPLIANCE_KEYWORDS.items():
        if key in lower:
            idx = lower.index(key)
            constraints.append(
                Constraint(
                    type=ConstraintType.COMPLIANCE,
                    value=label,
                    normalized_value=label,
                    confidence=0.95,
                    source_span=text[idx:idx + len(key)],
                    priority=0.95,
                )
            )

    for tech in _TECH_PREFS:
        if f"no {tech}" in lower or f"without {tech}" in lower or f"avoid {tech}" in lower:
            idx = lower.index(tech)
            constraints.append(
                Constraint(
                    type=ConstraintType.TECH_PROHIBITION,
                    value=tech,
                    normalized_value=tech,
                    confidence=0.75,
                    source_span=text[max(0, idx - 8):idx + len(tech)],
                    priority=0.6,
                )
            )
        elif tech in lower:
            idx = lower.index(tech)
            constraints.append(
                Constraint(
                    type=ConstraintType.TECH_PREFERENCE,
                    value=tech,
                    normalized_value=tech,
                    confidence=0.62,
                    source_span=text[idx:idx + len(tech)],
                    priority=0.5,
                )
            )

    constraint_set = ConstraintSet(constraints=constraints)
    constraint_set.conflicts = detect_conflicts(constraint_set)
    constraint_set.ambiguity_report = score_ambiguity(constraint_set)
    constraint_set.clarification_questions = generate_targeted_questions(constraint_set.ambiguity_report)
    return constraint_set


def detect_conflicts(constraint_set: ConstraintSet) -> List[Conflict]:
    constraints = constraint_set.constraints
    conflicts: List[Conflict] = []

    latencies = [c for c in constraints if c.type == ConstraintType.LATENCY_SLA_MS]
    teams = [c for c in constraints if c.type == ConstraintType.TEAM_SIZE]
    traffics = [c for c in constraints if c.type == ConstraintType.TRAFFIC_RPM]
    budgets = [c for c in constraints if c.type == ConstraintType.BUDGET_MONTHLY]

    for lat in latencies:
        for team in teams:
            if (lat.normalized_value or 0) <= 10 and (team.normalized_value or 999) <= 3:
                conflicts.append(
                    Conflict(
                        conflict_id=f"conflict-latency-team-{len(conflicts)+1}",
                        constraint_a=lat,
                        constraint_b=team,
                        severity=ConflictSeverity.HIGH,
                        reason="Sub-10ms SLO often requires specialized infra and high ops maturity, which conflicts with very small teams.",
                        resolution_options=[
                            "Relax latency to p95<=50ms",
                            "Increase platform team capacity",
                            "Adopt managed edge/cache strategy",
                        ],
                    )
                )

    for traffic in traffics:
        for budget in budgets:
            if (traffic.normalized_value or 0) >= 1_000_000 and (budget.normalized_value or 9999999) < 5000:
                conflicts.append(
                    Conflict(
                        conflict_id=f"conflict-traffic-budget-{len(conflicts)+1}",
                        constraint_a=traffic,
                        constraint_b=budget,
                        severity=ConflictSeverity.CRITICAL,
                        reason="Very high expected throughput with a low monthly budget is usually not feasible without major scope reduction.",
                        resolution_options=[
                            "Increase budget",
                            "Reduce throughput target",
                            "Introduce staged rollout and autoscaling caps",
                        ],
                    )
                )

    prohibitions = [c for c in constraints if c.type == ConstraintType.TECH_PROHIBITION]
    preferences = [c for c in constraints if c.type == ConstraintType.TECH_PREFERENCE]
    for p in preferences:
        for n in prohibitions:
            if str(p.normalized_value).lower() == str(n.normalized_value).lower():
                conflicts.append(
                    Conflict(
                        conflict_id=f"conflict-tech-pref-ban-{len(conflicts)+1}",
                        constraint_a=p,
                        constraint_b=n,
                        severity=ConflictSeverity.MEDIUM,
                        reason="Same technology appears as both preferred and prohibited.",
                        resolution_options=[
                            "Keep technology as optional",
                            "Prioritize prohibition",
                            "Prioritize preference",
                        ],
                    )
                )

    return conflicts


def score_ambiguity(constraint_set: ConstraintSet) -> AmbiguityReport:
    items: List[AmbiguityItem] = []
    constraints = constraint_set.constraints

    def _has(t: ConstraintType) -> bool:
        return any(c.type == t for c in constraints)

    if not _has(ConstraintType.TRAFFIC_RPM):
        items.append(AmbiguityItem(field="traffic_rpm", score=0.95, reason="Traffic expectations are missing."))
    if not _has(ConstraintType.LATENCY_SLA_MS):
        items.append(AmbiguityItem(field="latency_sla_ms", score=0.8, reason="Latency objective is not clearly specified."))
    if not _has(ConstraintType.TEAM_SIZE):
        items.append(AmbiguityItem(field="team_size", score=0.72, reason="Team capacity is unclear."))
    if not _has(ConstraintType.COMPLIANCE):
        items.append(AmbiguityItem(field="compliance", score=0.6, reason="Regulatory requirements are not explicit."))
    if not _has(ConstraintType.BUDGET_MONTHLY):
        items.append(AmbiguityItem(field="budget_monthly", score=0.68, reason="Budget envelope is missing."))

    for c in constraints:
        if c.confidence < 0.65:
            items.append(
                AmbiguityItem(
                    field=c.type.value,
                    score=min(1.0, 1.0 - c.confidence),
                    reason=f"Low extraction confidence ({c.confidence:.2f}) for {c.type.value}.",
                )
            )

    if constraint_set.conflicts:
        items.append(
            AmbiguityItem(
                field="conflicts",
                score=0.9,
                reason="Conflicting constraints detected; clarification required.",
            )
        )

    if not items:
        return AmbiguityReport(overall_score=0.1, items=[])

    overall = sum(i.score for i in items) / len(items)
    return AmbiguityReport(overall_score=min(1.0, overall), items=items)


def generate_targeted_questions(ambiguity_report: AmbiguityReport) -> List[ClarificationQuestion]:
    questions: List[ClarificationQuestion] = []
    for i, item in enumerate(sorted(ambiguity_report.items, key=lambda x: x.score, reverse=True), start=1):
        if item.score < 0.55:
            continue
        if item.field == "traffic_rpm":
            q = "What are expected peak and sustained request rates (RPM/RPS), and what burst factor should we design for?"
        elif item.field == "latency_sla_ms":
            q = "What is the target latency SLO (e.g., p95/p99 in ms) for critical endpoints?"
        elif item.field == "team_size":
            q = "How many engineers will actively own this platform over the next 6 months?"
        elif item.field == "compliance":
            q = "Do you need HIPAA, GDPR, PCI-DSS, SOC2, or data-residency controls?"
        elif item.field == "budget_monthly":
            q = "What is your monthly cloud/platform budget range for this workload?"
        elif item.field == "conflicts":
            q = "Constraint conflict detected. Which priority should dominate: performance, team simplicity, or budget?"
        else:
            q = f"Please clarify requirement for '{item.field}' to reduce design ambiguity."

        questions.append(
            ClarificationQuestion(
                question_id=f"cq-{i}",
                question=q,
                priority=item.score,
                target_field=item.field,
                reason=item.reason,
            )
        )
    return questions
