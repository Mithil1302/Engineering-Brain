/**
 * API client — all calls go through the backend at port 8004.
 * Auth headers are injected from the session store.
 */

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8004";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  authHeaders?: Record<string, string>
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(authHeaders || {}),
    ...(options.headers as Record<string, string> || {}),
  };

  const res = await fetch(`${BACKEND}${path}`, { ...options, headers });

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body?.detail || body?.message || detail;
    } catch {}
    throw new ApiError(res.status, detail);
  }

  const text = await res.text();
  if (!text) return {} as T;
  return JSON.parse(text) as T;
}

// ── Policy ──────────────────────────────────────────────────────────────────

export const policyApi = {
  evaluate: (body: unknown, auth: Record<string, string>) =>
    request("/policy/evaluate", { method: "POST", body: JSON.stringify(body) }, auth),

  pipelineHealth: (auth: Record<string, string>) =>
    request("/policy/pipeline/health", {}, auth),

  pipelineReadiness: (auth: Record<string, string>) =>
    request("/policy/pipeline/readiness", {}, auth),

  dashboardOverview: (repo: string, params: Record<string, string>, auth: Record<string, string>) =>
    request(`/policy/dashboard/overview?repo=${encodeURIComponent(repo)}&${new URLSearchParams(params)}`, {}, auth),

  healthSnapshots: (repo: string, params: Record<string, string>, auth: Record<string, string>) =>
    request(`/policy/dashboard/health-snapshots?repo=${encodeURIComponent(repo)}&${new URLSearchParams(params)}`, {}, auth),

  docRefreshJobs: (repo: string, params: Record<string, string>, auth: Record<string, string>) =>
    request(`/policy/dashboard/doc-refresh-jobs?repo=${encodeURIComponent(repo)}&${new URLSearchParams(params)}`, {}, auth),

  docRewriteRuns: (repo: string, params: Record<string, string>, auth: Record<string, string>) =>
    request(`/policy/dashboard/doc-rewrite-runs?repo=${encodeURIComponent(repo)}&${new URLSearchParams(params)}`, {}, auth),

  policyCheckRuns: (repo: string, params: Record<string, string>, auth: Record<string, string>) =>
    request(`/policy/dashboard/policy-check-runs?repo=${encodeURIComponent(repo)}&${new URLSearchParams(params)}`, {}, auth),

  listTemplates: (auth: Record<string, string>) =>
    request("/policy/admin/templates", {}, auth),

  upsertTemplate: (body: unknown, auth: Record<string, string>) =>
    request("/policy/admin/templates/upsert", { method: "POST", body: JSON.stringify(body) }, auth),

  effectiveTemplate: (repo: string, auth: Record<string, string>) =>
    request(`/policy/admin/templates/effective?repo=${encodeURIComponent(repo)}`, {}, auth),

  listWaivers: (params: Record<string, string>, auth: Record<string, string>) =>
    request(`/policy/admin/waivers?${new URLSearchParams(params)}`, {}, auth),

  requestWaiver: (body: unknown, auth: Record<string, string>) =>
    request("/policy/admin/waivers/request", { method: "POST", body: JSON.stringify(body) }, auth),

  decideWaiver: (waiverId: number, body: unknown, auth: Record<string, string>) =>
    request(`/policy/admin/waivers/${waiverId}/decision`, { method: "POST", body: JSON.stringify(body) }, auth),

  waiverHistory: (waiverId: number, auth: Record<string, string>) =>
    request(`/policy/admin/waivers/${waiverId}/history`, {}, auth),

  emitRetryJobs: (auth: Record<string, string>) =>
    request("/policy/admin/emit-retry/jobs", {}, auth),

  emitRetryDeadLetters: (auth: Record<string, string>) =>
    request("/policy/admin/emit-retry/dead-letters", {}, auth),

  emitRetryAlerts: (repo: string, auth: Record<string, string>) =>
    request(`/policy/admin/emit-retry/alerts?repo=${encodeURIComponent(repo)}`, {}, auth),

  emitRetryMetrics: (repo: string, auth: Record<string, string>) =>
    request(`/policy/admin/emit-retry/metrics?repo=${encodeURIComponent(repo)}`, {}, auth),

  requeueDeadLetter: (poisonId: number, body: unknown, auth: Record<string, string>) =>
    request(`/policy/admin/emit-retry/dead-letters/${poisonId}/requeue`, { method: "POST", body: JSON.stringify(body) }, auth),
  
  // New endpoints for six feature transformation
  runs: (repo: string, params: Record<string, string>, auth: Record<string, string>) => {
    const queryParams = new URLSearchParams(params);
    return request(`/policy/runs?repo=${encodeURIComponent(repo)}&${queryParams}`, {}, auth);
  },
  
  rulesets: (repo: string, auth: Record<string, string>) =>
    request(`/policy/rulesets?repo=${encodeURIComponent(repo)}`, {}, auth),
  
  runsStats: (repo: string, days: number, auth: Record<string, string>) =>
    request(`/policy/runs/stats?repo=${encodeURIComponent(repo)}&days=${days}`, {}, auth),
};

// ── Architecture ─────────────────────────────────────────────────────────────

export const architectureApi = {
  generatePlan: (body: unknown, auth: Record<string, string>) =>
    request("/architecture/plan", { method: "POST", body: JSON.stringify(body) }, auth),

  listPlans: (repo: string, auth: Record<string, string>) =>
    request(`/architecture/plans?repo=${encodeURIComponent(repo)}`, {}, auth),

  scaffold: (body: unknown, auth: Record<string, string>) =>
    request("/architecture/scaffold", { method: "POST", body: JSON.stringify(body) }, auth),

  refine: (body: unknown, auth: Record<string, string>) =>
    request("/architecture/refine", { method: "POST", body: JSON.stringify(body) }, auth),

  diff: (body: unknown, auth: Record<string, string>) =>
    request("/architecture/diff", { method: "POST", body: JSON.stringify(body) }, auth),

  generateAdr: (body: unknown, auth: Record<string, string>) =>
    request("/architecture/adr", { method: "POST", body: JSON.stringify(body) }, auth),

  explorer: (repo: string, auth: Record<string, string>) =>
    request(`/architecture/explorer?repo=${encodeURIComponent(repo)}`, {}, auth),
};

// ── Assistant ─────────────────────────────────────────────────────────────────

export const assistantApi = {
  ask: (body: unknown, auth: Record<string, string>) =>
    request("/assistant/ask", { method: "POST", body: JSON.stringify(body) }, auth),

  conversation: (body: unknown, auth: Record<string, string>) =>
    request("/assistant/conversation", { method: "POST", body: JSON.stringify(body) }, auth),

  search: (body: unknown, auth: Record<string, string>) =>
    request("/assistant/search", { method: "POST", body: JSON.stringify(body) }, auth),

  health: (auth: Record<string, string>) =>
    request("/assistant/health", {}, auth),
  
  // New endpoints for six feature transformation
  sessions: (repo: string, auth: Record<string, string>) =>
    request(`/assistant/sessions?repo=${encodeURIComponent(repo)}`, {}, auth),
  
  sessionMessages: (sessionId: string, auth: Record<string, string>) =>
    request(`/assistant/sessions/${encodeURIComponent(sessionId)}/messages`, {}, auth),
  
  deleteSession: (sessionId: string, auth: Record<string, string>) =>
    request(`/assistant/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" }, auth),
};

// ── Simulation ────────────────────────────────────────────────────────────────

export const simulationApi = {
  timeTravel: (repo: string, horizon: number, auth: Record<string, string>) =>
    request(`/simulation/time-travel?repo=${encodeURIComponent(repo)}&horizon=${horizon}`, { method: "POST" }, auth),

  impact: (body: unknown, auth: Record<string, string>) =>
    request("/simulation/impact", { method: "POST", body: JSON.stringify(body) }, auth),

  failureCascade: (body: unknown, auth: Record<string, string>) =>
    request("/simulation/failure-cascade", { method: "POST", body: JSON.stringify(body) }, auth),

  graph: (repo: string, auth: Record<string, string>) =>
    request(`/simulation/graph?repo=${encodeURIComponent(repo)}`, {}, auth),

  history: (repo: string, auth: Record<string, string>) =>
    request(`/simulation/history?repo=${encodeURIComponent(repo)}`, {}, auth),
};

// ── Autofix ───────────────────────────────────────────────────────────────────

export const autofixApi = {
  generate: (body: unknown, auth: Record<string, string>) =>
    request("/autofix/generate", { method: "POST", body: JSON.stringify(body) }, auth),

  apply: (body: unknown, auth: Record<string, string>) =>
    request("/autofix/apply", { method: "POST", body: JSON.stringify(body) }, auth),

  history: (repo: string, auth: Record<string, string>) =>
    request(`/autofix/history?repo=${encodeURIComponent(repo)}`, {}, auth),
};

// ── Onboarding ────────────────────────────────────────────────────────────────

export const onboardingApi = {
  generatePath: (body: unknown, auth: Record<string, string>) =>
    request("/onboarding/path", { method: "POST", body: JSON.stringify(body) }, auth),

  updateProgress: (body: unknown, auth: Record<string, string>) =>
    request("/onboarding/progress", { method: "POST", body: JSON.stringify(body) }, auth),

  ask: (body: unknown, auth: Record<string, string>) =>
    request("/onboarding/ask", { method: "POST", body: JSON.stringify(body) }, auth),

  history: (repo: string, auth: Record<string, string>) =>
    request(`/onboarding/history?repo=${encodeURIComponent(repo)}`, {}, auth),
  
  // New endpoints for six feature transformation
  selectRole: (body: unknown, auth: Record<string, string>) =>
    request("/onboarding/role", { method: "POST", body: JSON.stringify(body) }, auth),
  
  getPath: (repo: string, role: string, auth: Record<string, string>) =>
    request(`/onboarding/path?repo=${encodeURIComponent(repo)}&role=${encodeURIComponent(role)}`, {}, auth),
  
  updateResourceProgress: (body: unknown, auth: Record<string, string>) =>
    request("/onboarding/progress/resource", { method: "POST", body: JSON.stringify(body) }, auth),
};

// ── Health ────────────────────────────────────────────────────────────────────

export const healthApi = {
  mesh: () => request("/mesh"),
  
  snapshots: (repo: string, params: Record<string, string>, auth: Record<string, string>) =>
    request(`/health/snapshots?repo=${encodeURIComponent(repo)}&${new URLSearchParams(params)}`, {}, auth),
  
  coverage: (repo: string, auth: Record<string, string>) =>
    request(`/health/coverage?repo=${encodeURIComponent(repo)}`, {}, auth),
  
  gapsTimeline: (repo: string, days: number, auth: Record<string, string>) =>
    request(`/health/gaps/timeline?repo=${encodeURIComponent(repo)}&days=${days}`, {}, auth),
};

// ── Graph ─────────────────────────────────────────────────────────────────────

export const graphApi = {
  nodes: (repo: string, auth: Record<string, string>) =>
    request(`/graph/nodes?repo=${encodeURIComponent(repo)}`, {}, auth),
  
  edges: (repo: string, auth: Record<string, string>) =>
    request(`/graph/edges?repo=${encodeURIComponent(repo)}`, {}, auth),
  
  neighbors: (nodeId: string, depth: number, auth: Record<string, string>) =>
    request(`/graph/neighbors/${encodeURIComponent(nodeId)}?depth=${depth}`, {}, auth),
};

// ── Reporting ─────────────────────────────────────────────────────────────────

export const reportingApi = {
  alerts: (repo: string, status: string, auth: Record<string, string>) =>
    request(`/reporting/alerts?repo=${encodeURIComponent(repo)}&status=${status}`, {}, auth),
  
  dismissAlert: (alertId: string, auth: Record<string, string>) =>
    request(`/reporting/alerts/${encodeURIComponent(alertId)}/dismiss`, { method: "POST" }, auth),
  
  activity: (repo: string, limit: number, cursor: string | null, auth: Record<string, string>) => {
    const params = new URLSearchParams({ limit: limit.toString() });
    if (cursor) params.set("cursor", cursor);
    return request(`/reporting/activity?repo=${encodeURIComponent(repo)}&${params}`, {}, auth);
  },
};

// ── Adapters (Web Chat) ───────────────────────────────────────────────────────

export const adaptersApi = {
  // Note: This endpoint returns SSE stream, not JSON
  // Use fetch directly with ReadableStream for streaming
  askEndpoint: (auth: Record<string, string>) => ({
    url: `${BACKEND}/adapters/web/ask`,
    headers: {
      "Content-Type": "application/json",
      ...auth,
    },
  }),
};

// ── Blueprints ────────────────────────────────────────────────────────────────

export const blueprintsApi = {
  list: (repo: string, params: Record<string, string>, auth: Record<string, string>) =>
    request(`/blueprints?repo=${encodeURIComponent(repo)}&${new URLSearchParams(params)}`, {}, auth),
  
  get: (id: string, auth: Record<string, string>) =>
    request(`/blueprints/${encodeURIComponent(id)}`, {}, auth),
  
  analyze: (id: string, auth: Record<string, string>) =>
    request(`/blueprints/${encodeURIComponent(id)}/analyze`, { method: "POST" }, auth),
  
  artifact: (id: string, filePath: string, auth: Record<string, string>) =>
    request(`/blueprints/${encodeURIComponent(id)}/artifacts/${encodeURIComponent(filePath)}`, {}, auth),
  
  downloadArtifacts: (id: string, auth: Record<string, string>) => ({
    url: `${BACKEND}/blueprints/${encodeURIComponent(id)}/artifacts/download`,
    headers: auth,
  }),
};

// ── Governance (Waivers) ──────────────────────────────────────────────────────

export const governanceApi = {
  createWaiver: (body: unknown, auth: Record<string, string>) =>
    request("/governance/waivers", { method: "POST", body: JSON.stringify(body) }, auth),
  
  deleteWaiver: (id: number, auth: Record<string, string>) =>
    request(`/governance/waivers/${id}`, { method: "DELETE" }, auth),
};
