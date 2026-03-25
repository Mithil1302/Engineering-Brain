from __future__ import annotations

from typing import Dict, List

from .models import ADRDocument, ConstraintSet, RationaleDecision


def build_rationale_decisions(
    plan: Dict[str, object],
    constraint_set: ConstraintSet,
    stack_summary: Dict[str, object],
) -> List[RationaleDecision]:
    services = plan.get("services", []) if isinstance(plan, dict) else []
    decisions: List[RationaleDecision] = []

    driving = [c.type.value for c in constraint_set.constraints]
    uncertainty = max(0.0, min(1.0, 1.0 - constraint_set.ambiguity_report.overall_score))

    for idx, svc in enumerate(services, start=1):
        name = str((svc or {}).get("name") or f"service-{idx}")
        tech = str((svc or {}).get("technology") or "unknown")
        decisions.append(
            RationaleDecision(
                decision_id=f"decision-service-{idx}",
                title=f"Service boundary for {name}",
                decision=f"Define {name} as an independent service using {tech}.",
                driving_constraints=driving,
                confidence=round(0.65 + 0.3 * uncertainty, 3),
                alternatives_considered=[f"Merge {name} into existing domain service", "Modular monolith approach"],
                impact_if_constraint_changes=[
                    "Higher traffic may require splitting read/write paths",
                    "Smaller team may require consolidating service boundaries",
                ],
                tradeoffs=[
                    "Service autonomy vs operational overhead",
                    "Independent deployability vs distributed tracing complexity",
                ],
            )
        )

    if not decisions:
        decisions.append(
            RationaleDecision(
                decision_id="decision-fallback-1",
                title="Initial architecture baseline",
                decision="Start with minimal service decomposition and evolve by bounded context.",
                driving_constraints=driving,
                confidence=round(0.55 + 0.3 * uncertainty, 3),
                alternatives_considered=["Fully microservices from day 1", "Single monolith"],
                impact_if_constraint_changes=["Scaling requirements may force decomposition changes"],
                tradeoffs=["Simplicity now vs flexibility later"],
            )
        )

    return decisions


def build_adr_bundle(
    rationale_decisions: List[RationaleDecision],
    requirement: str,
) -> List[ADRDocument]:
    adrs: List[ADRDocument] = []
    for idx, d in enumerate(rationale_decisions, start=1):
        markdown = "\n".join([
            f"# ADR-{idx:04d}: {d.title}",
            "",
            "## Context",
            requirement,
            "",
            "## Decision",
            d.decision,
            "",
            "## Alternatives",
            *[f"- {a}" for a in d.alternatives_considered],
            "",
            "## Consequences",
            *[f"- {t}" for t in d.tradeoffs],
            "",
            "## Risks",
            *[f"- {x}" for x in d.impact_if_constraint_changes],
            "",
            "## Rollback / Migration Notes",
            "- Revert service decomposition and route traffic to baseline service where required.",
        ])
        adrs.append(
            ADRDocument(
                adr_id=f"ADR-{idx:04d}",
                title=d.title,
                status="proposed",
                context=requirement,
                decision=d.decision,
                alternatives=d.alternatives_considered,
                consequences="; ".join(d.tradeoffs),
                risks=d.impact_if_constraint_changes,
                rollback_notes="Use feature flags and traffic shifting for rollback.",
                markdown=markdown,
            )
        )
    return adrs


def build_traceability_map(
    rationale_decisions: List[RationaleDecision],
    constraint_set: ConstraintSet,
) -> Dict[str, List[str]]:
    by_decision: Dict[str, List[str]] = {}
    known_constraints = {c.type.value for c in constraint_set.constraints}
    for d in rationale_decisions:
        refs = [c for c in d.driving_constraints if c in known_constraints]
        if not refs:
            refs = list(known_constraints)[:2]
        by_decision[d.decision_id] = refs
    return by_decision
