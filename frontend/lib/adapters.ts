import { ArchitecturePlan, ChainStepInfo, Citation, OnboardingPath, OnboardingStage } from "@/lib/types";

function toArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

export function normalizeCitations(raw: unknown): Citation[] {
  return toArray<Record<string, unknown>>(raw).map((c) => ({
    source: String(c.source || c.source_type || c.source_ref || c.reference || "unknown"),
    source_ref: c.source_ref ? String(c.source_ref) : undefined,
    source_type: c.source_type ? String(c.source_type) : undefined,
    reference: c.reference ? String(c.reference) : undefined,
    details: c.details ? String(c.details) : undefined,
    relevance: c.relevance ? String(c.relevance) : undefined,
    chunk_text: c.chunk_text ? String(c.chunk_text) : undefined,
    line_number: typeof c.line_number === "number" ? c.line_number : undefined,
    score: typeof c.score === "number" ? c.score : undefined,
  }));
}

export function normalizeChainSteps(raw: unknown): Array<string | ChainStepInfo> {
  const arr = toArray<unknown>(raw);
  return arr.map((s) => {
    if (typeof s === "string") return s;
    if (typeof s === "object" && s) {
      const obj = s as Record<string, unknown>;
      return {
        name: typeof obj.name === "string" ? obj.name : undefined,
        step_name: typeof obj.step_name === "string" ? obj.step_name : undefined,
        latency_ms: typeof obj.latency_ms === "number" ? obj.latency_ms : undefined,
        tokens: typeof obj.tokens === "number" ? obj.tokens : undefined,
        tokens_used: typeof obj.tokens_used === "number" ? obj.tokens_used : undefined,
      } as ChainStepInfo;
    }
    return String(s);
  });
}

export function normalizeArchitecturePlans(payload: unknown): ArchitecturePlan[] {
  const root = (payload || {}) as Record<string, unknown>;
  const items = toArray<Record<string, unknown>>(root.items || root.plans || []);
  return items
    .map((row) => {
      const plan = (row.plan && typeof row.plan === "object" ? row.plan : row) as Record<string, unknown>;
      const contractArtifacts = (plan.contract_artifacts && typeof plan.contract_artifacts === "object")
        ? (plan.contract_artifacts as Record<string, unknown>)
        : {};

      const artifactsFromContracts = Object.entries(contractArtifacts).map(([file_path, content]) => ({
        file_path,
        content: typeof content === "string" ? content : JSON.stringify(content, null, 2),
        content_type: file_path.endsWith(".proto") ? "application/protobuf" : "text/plain",
      }));

      const artifacts = toArray<Record<string, unknown>>(plan.artifacts || []).map((a) => ({
        file_path: String(a.file_path || "artifact.txt"),
        content: String(a.content || ""),
        content_type: a.content_type ? String(a.content_type) : undefined,
      }));

      return {
        plan_id: String(plan.plan_id || row.id || (plan._meta as Record<string, unknown> | undefined)?.plan_id || "plan"),
        requirement: (plan.requirement as ArchitecturePlan["requirement"]) || { requirement_text: String(row.requirement || "") },
        intent_tags: toArray<string>(plan.intent_tags),
        decisions: toArray(plan.decisions),
        services: toArray(plan.services),
        infrastructure: toArray(plan.infrastructure),
        artifacts: artifacts.length > 0 ? artifacts : artifactsFromContracts,
        produced_at: String(plan.produced_at || row.created_at || new Date().toISOString()),
      } as ArchitecturePlan;
    })
    .filter((p) => !!p.requirement?.requirement_text || !!p.plan_id);
}

export function normalizeOnboardingPath(payload: unknown): OnboardingPath {
  const root = (payload || {}) as Record<string, unknown>;
  const tasks = toArray<Record<string, unknown>>(root.tasks || []);
  const stages: OnboardingStage[] = tasks.map((t, idx) => {
    const refs = toArray<string>(t.references || []);
    const exercises = toArray<string>(t.exercises || []);
    const resources = [
      ...refs.map((r) => ({ type: "doc" as const, title: r, description: "Reference material" })),
      ...exercises.map((e) => ({ type: "task" as const, title: e, description: "Hands-on exercise" })),
    ];

    return {
      stage_id: String(t.sequence || idx + 1),
      title: String(t.title || `Stage ${idx + 1}`),
      description: typeof t.description === "string" ? t.description : undefined,
      estimated_minutes: typeof t.estimated_hours === "number" ? Math.round(t.estimated_hours * 60) : undefined,
      resources,
      completed: false,
    };
  });

  return {
    path_id: String((root._meta as Record<string, unknown> | undefined)?.path_id || "path"),
    role: (String(root.role || "developer") as OnboardingPath["role"]),
    repo: String(root.repo || ""),
    tasks,
    stages,
    generated_at: typeof (root._meta as Record<string, unknown> | undefined)?.generated_at === "string"
      ? String((root._meta as Record<string, unknown>).generated_at)
      : new Date().toISOString(),
    _meta: (root._meta as Record<string, unknown>) || {},
  };
}
