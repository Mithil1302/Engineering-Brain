from __future__ import annotations

from typing import Any, Dict, List


def evaluate_scaffold_guardrails(
    *,
    plan: Dict[str, Any],
    extracted_constraints: Dict[str, Any],
) -> List[Dict[str, Any]]:
    warnings: List[Dict[str, Any]] = []

    services = plan.get("services") or []
    service_count = len(services)

    team_size = None
    for c in extracted_constraints.get("constraints", []):
        if c.get("type") == "team_size":
            team_size = c.get("normalized_value") or c.get("value")
            break

    if team_size is not None:
        try:
            ts = int(team_size)
            if ts <= 3 and service_count >= 10:
                warnings.append(
                    {
                        "severity": "high",
                        "code": "OVER_ENGINEERING_TEAM_SIZE",
                        "message": f"{service_count} services for a {ts}-person team is likely over-engineered.",
                        "suggestion": "Consider modular monolith or reduce service boundaries to critical domains only.",
                    }
                )
            elif ts <= 6 and service_count >= 15:
                warnings.append(
                    {
                        "severity": "medium",
                        "code": "SERVICE_COUNT_PRESSURE",
                        "message": f"Service count ({service_count}) may strain a {ts}-person team.",
                        "suggestion": "Introduce platform templates and shared runtime contracts.",
                    }
                )
        except Exception:
            pass

    has_observability = bool(plan.get("observability") or plan.get("infrastructure", {}).get("observability"))
    if not has_observability:
        warnings.append(
            {
                "severity": "medium",
                "code": "MISSING_OBSERVABILITY_BASELINE",
                "message": "No explicit observability baseline found.",
                "suggestion": "Inject structured logging, health checks, metrics, and trace propagation by default.",
            }
        )

    if service_count == 0:
        warnings.append(
            {
                "severity": "high",
                "code": "EMPTY_BLUEPRINT",
                "message": "Blueprint has no services.",
                "suggestion": "Re-run intent parsing and add minimum bounded contexts.",
            }
        )

    return warnings
