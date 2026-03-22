from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

ROLE_PATHS = {
    "developer": [
        "Understand policy check lifecycle",
        "Review merge-gate and waiver process",
        "Run doc automation and validate artifacts",
    ],
    "architect": [
        "Review architecture plan outputs",
        "Assess governance template precedence",
        "Evaluate trend and simulation reports",
    ],
    "platform-lead": [
        "Configure org/team policy templates",
        "Set approval chains and expiry controls",
        "Define SLOs for automation pipelines",
    ],
}


def build_onboarding_path(role: str, repo: str, pr_number: int | None, evidence: Dict[str, Any]) -> Dict[str, Any]:
    r = (role or "developer").strip().lower()
    steps = ROLE_PATHS.get(r, ROLE_PATHS["developer"])

    tasks: List[Dict[str, Any]] = []
    for idx, step in enumerate(steps, start=1):
        tasks.append(
            {
                "sequence": idx,
                "title": step,
                "objective": f"{step} for {repo}",
                "done": False,
                "signals": {
                    "policy_runs": len(evidence.get("policy_runs", [])),
                    "doc_rewrite_runs": len(evidence.get("doc_rewrite_runs", [])),
                    "waivers": len(evidence.get("waivers", [])),
                },
            }
        )

    return {
        "role": r,
        "repo": repo,
        "pr_number": pr_number,
        "tasks": tasks,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
