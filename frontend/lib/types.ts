// Shared TypeScript interfaces for the KA-CHOW frontend

// ── Health ──────────────────────────────────────────────────────────────────

export interface HealthSnapshot {
  id: number;
  repo: string;
  pr_number?: number;
  rule_set: string;
  summary_status: string;
  score: number;
  grade: string;
  weights: Record<string, number>;
  components: Record<string, number>;
  produced_at: string;
}

export interface DashboardOverview {
  repo: string;
  recent_health?: { score: number; grade: string; produced_at: string };
  score_trend?: number;
  total_check_runs?: number;
  pass_count?: number;
  warn_count?: number;
  block_count?: number;
  open_gaps?: number;
  staleness_alerts?: number;
  ci_pass_rate?: number;
}

// ── Policy ───────────────────────────────────────────────────────────────────

export type PolicyOutcome = "pass" | "warn" | "block" | "fail" | "error";
export type FindingSeverity = "critical" | "high" | "medium" | "low" | "info";

export interface Finding {
  rule_id: string;
  severity: FindingSeverity;
  status: string;
  title: string;
  description: string;
  entity_refs?: string[];
  evidence?: string[];
  suggested_action?: string;
}

export interface MergeGate {
  decision: "allow" | "block" | "allow_with_waiver";
  blocking_rule_ids?: string[];
  reasons?: string[];
  policy_action?: string;
  waiver?: Record<string, unknown>;
  branch_protection_result?: Record<string, unknown>;
}

export interface PolicyRun {
  id: number;
  repo: string;
  pr_number?: number;
  rule_set: string;
  summary_status: PolicyOutcome;
  merge_gate?: MergeGate;
  findings?: Finding[];
  suggested_patches?: Array<Record<string, unknown>>;
  doc_refresh_plan?: Record<string, unknown>;
  produced_at: string;
  idempotency_key?: string;
  action?: string;
  comment_key?: string;
}

export interface Waiver {
  id: number;
  repo: string;
  pr_number: number;
  rule_set: string;
  rule_ids: string[];
  justification: string;
  requested_by: string;
  requested_role: string;
  decided_by?: string;
  decided_role?: string;
  status: "pending" | "approved" | "rejected" | "expired";
  expires_at?: string;
  created_at: string;
}

// ── Architecture ──────────────────────────────────────────────────────────────

export interface ServiceBlueprint {
  name: string;
  role: string;
  language: string;
  runtime: string;
  interfaces?: string[];
}

export interface ArchitectureDecision {
  title: string;
  rationale: string;
  tradeoffs?: string[];
  alternatives?: string[];
  confidence?: number;
  constraint?: string;
}

export interface ScaffoldArtifact {
  file_path: string;
  content: string;
  content_type?: string;
}

export interface ArchitecturePlan {
  plan_id: string;
  requirement: { requirement_text: string; domain?: string; target_cloud?: string };
  intent_tags?: string[];
  decisions?: ArchitectureDecision[];
  services?: ServiceBlueprint[];
  infrastructure?: Array<{ resource: string; purpose: string }>;
  artifacts?: ScaffoldArtifact[];
  produced_at: string;
}

// ── Chat / Q&A ────────────────────────────────────────────────────────────────

export type MessageRole = "user" | "assistant";
export type IntentCategory = "architecture" | "policy" | "onboarding" | "impact" | "general";

export interface Citation {
  source: string;
  source_ref?: string;
  source_type?: string;
  reference?: string;
  chunk_text?: string;
  line_number?: number;
  score?: number;
  details?: string;
  relevance?: string;
}

export interface ChainStepInfo {
  name?: string;
  step_name?: string;
  latency_ms?: number;
  tokens?: number;
  tokens_used?: number;
}

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  intent?: string;
  sub_intent?: string;
  confidence?: number;
  citations?: Citation[];
  source_citations?: Citation[];
  follow_up_suggestions?: string[];
  chain_steps?: Array<string | ChainStepInfo>;
  source_breakdown?: Record<string, number>;
  streaming?: boolean;
  timestamp?: string;
}

export interface Conversation {
  id: string;
  messages: ChatMessage[];
  created_at: string;
  label?: string;
}

// ── Graph ─────────────────────────────────────────────────────────────────────

export type GraphNodeType = "service" | "api" | "schema" | "engineer" | "adr" | "incident" | "database" | "queue";

export interface GraphNodeData extends Record<string, unknown> {
  id: string;
  label: string;
  type: GraphNodeType;
  healthScore?: number;
  owner?: string;
  description?: string;
  endpoints?: Array<{ method: string; path: string; operation_id?: string }>;
  linked_adrs?: string[];
  last_updated?: string;
  documented?: boolean;
}

export interface GraphEdgeData {
  relationship: "depends_on" | "owns" | "causes" | "calls" | "stores";
}

// ── Onboarding ────────────────────────────────────────────────────────────────

export type OnboardingRole =
  | "backend_engineer"
  | "sre"
  | "frontend_developer"
  | "data_engineer"
  | "engineering_manager";

export interface OnboardingResource {
  type: "doc" | "graph_node" | "adr" | "code" | "task";
  title: string;
  description?: string;
  url?: string;
  service_name?: string;
  file_path?: string;
}

export interface OnboardingStage {
  stage_id: string;
  title: string;
  description?: string;
  estimated_minutes?: number;
  resources?: OnboardingResource[];
  completed?: boolean;
}

export interface OnboardingPath {
  path_id: string;
  role: OnboardingRole;
  repo: string;
  tasks?: Array<Record<string, unknown>>;
  stages?: OnboardingStage[];
  generated_at?: string;
  _meta?: Record<string, unknown>;
}

// ── Autofix ───────────────────────────────────────────────────────────────────

export interface AutofixResult {
  fix_id: string;
  fix_type: string;
  confidence: number;
  patch_content?: string;
  reasoning?: string;
  pr_url?: string;
  pr_number?: number;
  created_at: string;
}
