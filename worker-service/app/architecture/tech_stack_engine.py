from __future__ import annotations

from copy import deepcopy
from typing import Dict, List, Optional

from .models import (
    CandidateScore,
    ConstraintSet,
    ConstraintType,
    DecisionDimension,
    SensitivityAnalysis,
    SensitivityDelta,
    StackDecisionResult,
)


# Candidate catalog: score scale 0..1 per dimension
_CANDIDATE_CATALOG: Dict[str, Dict[str, Dict[str, float]]] = {
    "api_runtime": {
        "fastapi": {
            DecisionDimension.OPERATIONAL_COMPLEXITY.value: 0.82,
            DecisionDimension.LEARNING_CURVE.value: 0.88,
            DecisionDimension.ECOSYSTEM_MATURITY.value: 0.84,
            DecisionDimension.HORIZONTAL_SCALABILITY.value: 0.78,
            DecisionDimension.TEAM_FAMILIARITY.value: 0.80,
            DecisionDimension.LATENCY_FIT.value: 0.83,
            DecisionDimension.COMPLIANCE_FIT.value: 0.74,
            DecisionDimension.COST_EFFICIENCY.value: 0.86,
        },
        "nestjs": {
            DecisionDimension.OPERATIONAL_COMPLEXITY.value: 0.75,
            DecisionDimension.LEARNING_CURVE.value: 0.70,
            DecisionDimension.ECOSYSTEM_MATURITY.value: 0.86,
            DecisionDimension.HORIZONTAL_SCALABILITY.value: 0.79,
            DecisionDimension.TEAM_FAMILIARITY.value: 0.76,
            DecisionDimension.LATENCY_FIT.value: 0.77,
            DecisionDimension.COMPLIANCE_FIT.value: 0.72,
            DecisionDimension.COST_EFFICIENCY.value: 0.81,
        },
        "go-fiber": {
            DecisionDimension.OPERATIONAL_COMPLEXITY.value: 0.64,
            DecisionDimension.LEARNING_CURVE.value: 0.55,
            DecisionDimension.ECOSYSTEM_MATURITY.value: 0.78,
            DecisionDimension.HORIZONTAL_SCALABILITY.value: 0.92,
            DecisionDimension.TEAM_FAMILIARITY.value: 0.52,
            DecisionDimension.LATENCY_FIT.value: 0.95,
            DecisionDimension.COMPLIANCE_FIT.value: 0.80,
            DecisionDimension.COST_EFFICIENCY.value: 0.87,
        },
    },
    "database": {
        "postgres": {
            DecisionDimension.OPERATIONAL_COMPLEXITY.value: 0.80,
            DecisionDimension.LEARNING_CURVE.value: 0.86,
            DecisionDimension.ECOSYSTEM_MATURITY.value: 0.95,
            DecisionDimension.HORIZONTAL_SCALABILITY.value: 0.73,
            DecisionDimension.TEAM_FAMILIARITY.value: 0.88,
            DecisionDimension.LATENCY_FIT.value: 0.81,
            DecisionDimension.COMPLIANCE_FIT.value: 0.92,
            DecisionDimension.COST_EFFICIENCY.value: 0.84,
        },
        "mongodb": {
            DecisionDimension.OPERATIONAL_COMPLEXITY.value: 0.77,
            DecisionDimension.LEARNING_CURVE.value: 0.80,
            DecisionDimension.ECOSYSTEM_MATURITY.value: 0.86,
            DecisionDimension.HORIZONTAL_SCALABILITY.value: 0.85,
            DecisionDimension.TEAM_FAMILIARITY.value: 0.78,
            DecisionDimension.LATENCY_FIT.value: 0.76,
            DecisionDimension.COMPLIANCE_FIT.value: 0.68,
            DecisionDimension.COST_EFFICIENCY.value: 0.79,
        },
        "cockroachdb": {
            DecisionDimension.OPERATIONAL_COMPLEXITY.value: 0.59,
            DecisionDimension.LEARNING_CURVE.value: 0.54,
            DecisionDimension.ECOSYSTEM_MATURITY.value: 0.66,
            DecisionDimension.HORIZONTAL_SCALABILITY.value: 0.93,
            DecisionDimension.TEAM_FAMILIARITY.value: 0.42,
            DecisionDimension.LATENCY_FIT.value: 0.84,
            DecisionDimension.COMPLIANCE_FIT.value: 0.82,
            DecisionDimension.COST_EFFICIENCY.value: 0.69,
        },
    },
    "messaging": {
        "kafka": {
            DecisionDimension.OPERATIONAL_COMPLEXITY.value: 0.50,
            DecisionDimension.LEARNING_CURVE.value: 0.45,
            DecisionDimension.ECOSYSTEM_MATURITY.value: 0.92,
            DecisionDimension.HORIZONTAL_SCALABILITY.value: 0.96,
            DecisionDimension.TEAM_FAMILIARITY.value: 0.62,
            DecisionDimension.LATENCY_FIT.value: 0.84,
            DecisionDimension.COMPLIANCE_FIT.value: 0.79,
            DecisionDimension.COST_EFFICIENCY.value: 0.74,
        },
        "rabbitmq": {
            DecisionDimension.OPERATIONAL_COMPLEXITY.value: 0.76,
            DecisionDimension.LEARNING_CURVE.value: 0.71,
            DecisionDimension.ECOSYSTEM_MATURITY.value: 0.86,
            DecisionDimension.HORIZONTAL_SCALABILITY.value: 0.72,
            DecisionDimension.TEAM_FAMILIARITY.value: 0.72,
            DecisionDimension.LATENCY_FIT.value: 0.78,
            DecisionDimension.COMPLIANCE_FIT.value: 0.76,
            DecisionDimension.COST_EFFICIENCY.value: 0.80,
        },
        "sqs-sns": {
            DecisionDimension.OPERATIONAL_COMPLEXITY.value: 0.90,
            DecisionDimension.LEARNING_CURVE.value: 0.86,
            DecisionDimension.ECOSYSTEM_MATURITY.value: 0.87,
            DecisionDimension.HORIZONTAL_SCALABILITY.value: 0.83,
            DecisionDimension.TEAM_FAMILIARITY.value: 0.66,
            DecisionDimension.LATENCY_FIT.value: 0.70,
            DecisionDimension.COMPLIANCE_FIT.value: 0.86,
            DecisionDimension.COST_EFFICIENCY.value: 0.85,
        },
    },
}

_DEFAULT_WEIGHTS: Dict[str, float] = {
    DecisionDimension.OPERATIONAL_COMPLEXITY.value: 0.15,
    DecisionDimension.LEARNING_CURVE.value: 0.12,
    DecisionDimension.ECOSYSTEM_MATURITY.value: 0.10,
    DecisionDimension.HORIZONTAL_SCALABILITY.value: 0.16,
    DecisionDimension.TEAM_FAMILIARITY.value: 0.14,
    DecisionDimension.LATENCY_FIT.value: 0.11,
    DecisionDimension.COMPLIANCE_FIT.value: 0.12,
    DecisionDimension.COST_EFFICIENCY.value: 0.10,
}


def _normalize(weights: Dict[str, float]) -> Dict[str, float]:
    safe = {k: max(0.0, float(v)) for k, v in weights.items()}
    s = sum(safe.values()) or 1.0
    return {k: v / s for k, v in safe.items()}


def derive_dimension_weights(constraint_set: ConstraintSet) -> Dict[str, float]:
    weights = deepcopy(_DEFAULT_WEIGHTS)

    for c in constraint_set.constraints:
        if c.type == ConstraintType.TEAM_SIZE and (c.normalized_value or 0) <= 4:
            weights[DecisionDimension.OPERATIONAL_COMPLEXITY.value] += 0.10
            weights[DecisionDimension.LEARNING_CURVE.value] += 0.08
            weights[DecisionDimension.TEAM_FAMILIARITY.value] += 0.08
        if c.type == ConstraintType.TRAFFIC_RPM and (c.normalized_value or 0) >= 300_000:
            weights[DecisionDimension.HORIZONTAL_SCALABILITY.value] += 0.12
            weights[DecisionDimension.LATENCY_FIT.value] += 0.05
        if c.type == ConstraintType.LATENCY_SLA_MS and (c.normalized_value or 9999) <= 20:
            weights[DecisionDimension.LATENCY_FIT.value] += 0.14
            weights[DecisionDimension.HORIZONTAL_SCALABILITY.value] += 0.05
        if c.type == ConstraintType.COMPLIANCE:
            weights[DecisionDimension.COMPLIANCE_FIT.value] += 0.14
            weights[DecisionDimension.ECOSYSTEM_MATURITY.value] += 0.06
        if c.type == ConstraintType.BUDGET_MONTHLY and (c.normalized_value or 0) <= 5000:
            weights[DecisionDimension.COST_EFFICIENCY.value] += 0.12
            weights[DecisionDimension.OPERATIONAL_COMPLEXITY.value] += 0.05

    if constraint_set.conflicts:
        weights[DecisionDimension.ECOSYSTEM_MATURITY.value] += 0.04
        weights[DecisionDimension.OPERATIONAL_COMPLEXITY.value] += 0.04

    return _normalize(weights)


def _penalty_for_prohibition(candidate: str, constraint_set: ConstraintSet) -> float:
    penalty = 0.0
    for c in constraint_set.constraints:
        if c.type == ConstraintType.TECH_PROHIBITION and str(c.normalized_value).lower() in candidate.lower():
            penalty += 0.45
    return penalty


def _bonus_for_preference(candidate: str, constraint_set: ConstraintSet) -> float:
    bonus = 0.0
    for c in constraint_set.constraints:
        if c.type == ConstraintType.TECH_PREFERENCE and str(c.normalized_value).lower() in candidate.lower():
            bonus += 0.08
    return bonus


def score_candidates(category: str, dimension_weights: Dict[str, float], constraint_set: ConstraintSet) -> List[CandidateScore]:
    catalog = _CANDIDATE_CATALOG.get(category, {})
    scored: List[CandidateScore] = []

    for candidate, dims in catalog.items():
        weighted = 0.0
        for d, w in dimension_weights.items():
            weighted += (dims.get(d, 0.0) * w)

        penalties = {
            "prohibition": _penalty_for_prohibition(candidate, constraint_set),
        }
        bonuses = _bonus_for_preference(candidate, constraint_set)
        final = max(0.0, min(1.0, weighted - penalties["prohibition"] + bonuses))

        notes: List[str] = []
        if penalties["prohibition"] > 0:
            notes.append("penalized_by_tech_prohibition")
        if bonuses > 0:
            notes.append("boosted_by_tech_preference")

        scored.append(
            CandidateScore(
                candidate=candidate,
                category=category,
                raw_scores=dims,
                weighted_score=round(final, 4),
                penalties={k: round(v, 4) for k, v in penalties.items()},
                notes=notes,
            )
        )

    scored.sort(key=lambda x: x.weighted_score, reverse=True)
    return scored


def _build_why(category: str, scores: List[CandidateScore], dimension_weights: Dict[str, float]) -> Dict[str, object]:
    winner = scores[0] if scores else None
    second = scores[1] if len(scores) > 1 else None
    if winner is None:
        return {"category": category, "reason": "no candidates"}

    top_dims = sorted(dimension_weights.items(), key=lambda x: x[1], reverse=True)[:3]
    return {
        "category": category,
        "winner": winner.candidate,
        "winner_score": winner.weighted_score,
        "runner_up": second.candidate if second else None,
        "score_gap": round(winner.weighted_score - (second.weighted_score if second else 0.0), 4),
        "dominant_dimensions": [{"dimension": d, "weight": round(w, 4)} for d, w in top_dims],
        "winner_notes": winner.notes,
    }


def run_stack_decision_engine(constraint_set: ConstraintSet, categories: Optional[List[str]] = None) -> Dict[str, StackDecisionResult]:
    selected = categories or list(_CANDIDATE_CATALOG.keys())
    weights = derive_dimension_weights(constraint_set)
    out: Dict[str, StackDecisionResult] = {}

    for category in selected:
        scores = score_candidates(category, weights, constraint_set)
        winner = scores[0] if scores else None
        out[category] = StackDecisionResult(
            dimension_weights=weights,
            candidate_scores=scores,
            winner=winner,
            alternatives_ranked=[s.candidate for s in scores],
            why=_build_why(category, scores, weights),
            sensitivity_analysis=None,
        )

    return out


def run_sensitivity_analysis(
    base_result: StackDecisionResult,
    adjusted_weights: Dict[str, float],
) -> SensitivityAnalysis:
    before_scores = {c.candidate: c.weighted_score for c in base_result.candidate_scores}
    # recompute from raw scores using adjusted weights
    norm = _normalize(adjusted_weights)
    deltas: List[SensitivityDelta] = []

    recomputed: Dict[str, float] = {}
    for c in base_result.candidate_scores:
        after = 0.0
        for d, w in norm.items():
            after += c.raw_scores.get(d, 0.0) * w
        recomputed[c.candidate] = round(after, 4)
        deltas.append(
            SensitivityDelta(
                candidate=c.candidate,
                before=before_scores.get(c.candidate, 0.0),
                after=recomputed[c.candidate],
                delta=round(recomputed[c.candidate] - before_scores.get(c.candidate, 0.0), 4),
            )
        )

    before_winner = base_result.candidate_scores[0].candidate if base_result.candidate_scores else None
    after_winner = sorted(recomputed.items(), key=lambda x: x[1], reverse=True)[0][0] if recomputed else None

    return SensitivityAnalysis(
        changed_weights=norm,
        deltas=sorted(deltas, key=lambda x: x.after, reverse=True),
        winner_changed=(before_winner != after_winner),
    )
