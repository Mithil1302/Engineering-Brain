export function cn(...inputs: (string | undefined | null | false | 0)[]) {
  return inputs.filter(Boolean).join(" ");
}

export function formatDate(date: string | Date) {
  return new Date(date).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function formatRelativeTime(date: string | Date) {
  const now = new Date();
  const d = new Date(date);
  const diff = now.getTime() - d.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function healthColor(score: number): string {
  if (score >= 90) return "#10b981";
  if (score >= 75) return "#34d399";
  if (score >= 60) return "#f59e0b";
  if (score >= 40) return "#f97316";
  return "#ef4444";
}

export function healthGradient(score: number): string {
  if (score >= 90) return "from-emerald-500 to-emerald-400";
  if (score >= 75) return "from-green-500 to-emerald-400";
  if (score >= 60) return "from-amber-500 to-yellow-400";
  if (score >= 40) return "from-orange-500 to-amber-400";
  return "from-red-500 to-rose-400";
}

export function gradeColor(grade: string): string {
  if (grade?.startsWith("A")) return "text-emerald-400 bg-emerald-400/10 border-emerald-400/20";
  if (grade?.startsWith("B")) return "text-sky-400 bg-sky-400/10 border-sky-400/20";
  if (grade?.startsWith("C")) return "text-amber-400 bg-amber-400/10 border-amber-400/20";
  return "text-red-400 bg-red-400/10 border-red-400/20";
}

export function outcomeColor(outcome: string): string {
  if (outcome === "pass") return "text-emerald-400 bg-emerald-400/10 border-emerald-400/20";
  if (outcome === "warn") return "text-amber-400 bg-amber-400/10 border-amber-400/20";
  if (outcome === "block" || outcome === "fail") return "text-red-400 bg-red-400/10 border-red-400/20";
  return "text-slate-400 bg-slate-400/10 border-slate-400/20";
}

export function severityColor(severity: string): string {
  if (severity === "critical") return "text-red-400 bg-red-400/10 border-red-400/20";
  if (severity === "high") return "text-orange-400 bg-orange-400/10 border-orange-400/20";
  if (severity === "medium") return "text-amber-400 bg-amber-400/10 border-amber-400/20";
  if (severity === "low") return "text-blue-400 bg-blue-400/10 border-blue-400/20";
  return "text-slate-400 bg-slate-400/10 border-slate-400/20";
}

export function getNodeTypeColor(type: string): string {
  switch (type) {
    case "service": return "#6366f1";
    case "api": return "#38bdf8";
    case "schema": return "#a78bfa";
    case "database": return "#10b981";
    case "queue": return "#f59e0b";
    case "engineer": return "#f472b6";
    case "adr": return "#94a3b8";
    case "incident": return "#ef4444";
    default: return "#64748b";
  }
}

export function truncate(str: string, maxLen: number): string {
  if (!str) return "";
  return str.length > maxLen ? str.slice(0, maxLen) + "…" : str;
}

// ── Shared Utility Functions for Six Feature Transformation ──────────────────

import type { Session, GraphNode, GraphEdge } from "./types";

export function groupSessionsByTime(sessions: Session[]): {
  today: Session[];
  yesterday: Session[];
  last7Days: Session[];
  last30Days: Session[];
  older: Session[];
} {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  const last7Days = new Date(today);
  last7Days.setDate(last7Days.getDate() - 7);
  const last30Days = new Date(today);
  last30Days.setDate(last30Days.getDate() - 30);

  const result = {
    today: [] as Session[],
    yesterday: [] as Session[],
    last7Days: [] as Session[],
    last30Days: [] as Session[],
    older: [] as Session[],
  };

  for (const session of sessions) {
    const sessionDate = new Date(session.created_at);
    if (sessionDate >= today) {
      result.today.push(session);
    } else if (sessionDate >= yesterday) {
      result.yesterday.push(session);
    } else if (sessionDate >= last7Days) {
      result.last7Days.push(session);
    } else if (sessionDate >= last30Days) {
      result.last30Days.push(session);
    } else {
      result.older.push(session);
    }
  }

  return result;
}

export function filterGraphNodes(
  nodes: GraphNode[],
  edges: GraphEdge[],
  visibleTypes: Set<string>
): { filteredNodes: GraphNode[]; filteredEdges: GraphEdge[] } {
  const filteredNodes = nodes.filter((node) => visibleTypes.has(node.type));
  const visibleNodeIds = new Set(filteredNodes.map((n) => n.id));
  const filteredEdges = edges.filter(
    (edge) => visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target)
  );
  return { filteredNodes, filteredEdges };
}

export function validateWaiverRequest(waiver: {
  rule_ids: string[];
  justification: string;
  expires_at: string;
}): { valid: boolean; errors: string[] } {
  const errors: string[] = [];

  if (!waiver.rule_ids || waiver.rule_ids.length === 0) {
    errors.push("At least one rule ID is required");
  }

  if (!waiver.justification || waiver.justification.length < 50) {
    errors.push("Justification must be at least 50 characters");
  }

  if (waiver.expires_at) {
    const expiresAt = new Date(waiver.expires_at);
    const now = new Date();
    const maxExpiry = new Date(now);
    maxExpiry.setDate(maxExpiry.getDate() + 30);

    if (expiresAt > maxExpiry) {
      errors.push("Expiry date cannot be more than 30 days from now");
    }
  }

  return { valid: errors.length === 0, errors };
}

export function parseConstraintReferences(decisionText: string): string[] {
  const regex = /\[Constraint (\d+)\]/g;
  const matches: string[] = [];
  let match;
  while ((match = regex.exec(decisionText)) !== null) {
    matches.push(match[1]);
  }
  return matches;
}

export function getHealthColor(score: number): string {
  // Health_Color_Scale: score >= 50 interpolates #f59e0b (50) to #22c55e (100)
  // score < 50 interpolates #ef4444 (0) to #f59e0b (50)
  if (score >= 50) {
    const t = (score - 50) / 50; // 0 to 1
    return interpolateColor("#f59e0b", "#22c55e", t);
  } else {
    const t = score / 50; // 0 to 1
    return interpolateColor("#ef4444", "#f59e0b", t);
  }
}

export function getGapColor(gapCount: number, isDark: boolean): string {
  // 5-stop scale
  if (gapCount === 0) return isDark ? "#161b22" : "#ebedf0";
  if (gapCount <= 2) return isDark ? "#0e4429" : "#9be9a8";
  if (gapCount <= 5) return isDark ? "#006d32" : "#40c463";
  if (gapCount <= 10) return isDark ? "#26a641" : "#30a14e";
  return isDark ? "#39d353" : "#216e39";
}

export function interpolateColor(color1: string, color2: string, t: number): string {
  // Parse hex colors
  const r1 = parseInt(color1.slice(1, 3), 16);
  const g1 = parseInt(color1.slice(3, 5), 16);
  const b1 = parseInt(color1.slice(5, 7), 16);

  const r2 = parseInt(color2.slice(1, 3), 16);
  const g2 = parseInt(color2.slice(3, 5), 16);
  const b2 = parseInt(color2.slice(5, 7), 16);

  // Linear interpolation
  const r = Math.round(r1 + (r2 - r1) * t);
  const g = Math.round(g1 + (g2 - g1) * t);
  const b = Math.round(b1 + (b2 - b1) * t);

  // Convert back to hex
  return `#${r.toString(16).padStart(2, "0")}${g.toString(16).padStart(2, "0")}${b.toString(16).padStart(2, "0")}`;
}
