from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List


def simulate_health(history: List[Dict[str, Any]], horizon: int = 5) -> Dict[str, Any]:
    points = list(reversed(history))
    scores = [float(p.get("score") or 0.0) for p in points]
    if len(scores) < 2:
        slope = 0.0
    else:
        slope = (scores[-1] - scores[0]) / max(1, len(scores) - 1)

    future = []
    base = scores[-1] if scores else 0.0
    for i in range(1, max(1, horizon) + 1):
        val = max(0.0, min(100.0, round(base + slope * i, 2)))
        future.append({"step": i, "projected_score": val})

    return {
        "history_points": len(scores),
        "current_score": round(base, 2),
        "trend_slope": round(slope, 4),
        "projection": future,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
