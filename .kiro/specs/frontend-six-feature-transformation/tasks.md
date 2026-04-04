# Implementation Plan: Frontend Six Feature Transformation

## Overview

This implementation plan breaks down the six production-quality frontend features into actionable coding tasks with implementation-ready precision. The features will be implemented in the order specified in the requirements: Q&A Chat Interface, Knowledge Graph Visualizer, System Health Dashboard, CI/CD Policy Status, Architecture Blueprint Viewer, and Onboarding Learning Paths.

Each feature follows a consistent implementation pattern: page layout and routing, data fetching hooks (React Query), main component, detail/sub-components, loading states (skeleton components), error states, and real-time updates (SSE where applicable).

The implementation uses TypeScript for type safety, React Query v5 for server state management, Zustand for global client state, React Flow for graph rendering, Recharts for charts, and Monaco Editor for code viewing.

**Critical Implementation Details:**
- All specifications include exact pixel dimensions (e.g., 180x72px, 320px width, 3px border)
- All colors specified with exact hex codes (e.g., #3b82f6, #22c55e, #ef4444)
- All animations include duration and easing (e.g., 300ms translateX, 600ms ease-out)
- All API calls include full endpoint paths with query parameters
- All performance targets explicitly stated (e.g., < 500ms, < 2s, < 1s)
- All 40 correctness properties referenced in tasks
- All loading states specify exact skeleton dimensions matching real content
- All error states include specific messages for different error types
- All responsive breakpoints clearly defined (1280px min, 1400px breakpoint)
- SSE reconnection protocol: exponential backoff (2s, 4s, 8s, 16s, max 30s), max 10 attempts, "Live updates paused" pill after 5s disconnect
- Health_Color_Scale interpolation: score >= 50 interpolates #f59e0b (50) to #22c55e (100), score < 50 interpolates #ef4444 (0) to #f59e0b (50)

## Tasks

- [x] 1. Set up shared infrastructure and type definitions
  - Create TypeScript interfaces for all API request/response types in `frontend/lib/types.ts`:
    - ChatMessage: { id: string, role: "user" | "assistant", content: string, intent?: string, sub_intent?: string, confidence?: number (0-100), citations?: Citation[], source_breakdown?: Record<string, number>, follow_up_suggestions?: string[], chain_steps?: ChainStepInfo[], streaming?: boolean, timestamp?: string, error?: boolean }
    - Citation: { source: string, source_ref?: string, source_type?: "code" | "docs" | "adrs" | "incidents" | "specs", chunk_text?: string, line_number?: number, score?: number }
    - ChainStepInfo: { name?: string, step_name?: string, latency_ms?: number, tokens?: number }
    - GraphNode: { id: string, label: string, type: "service" | "api" | "schema" | "adr" | "engineer" | "incident", health_score?: number (0-100), owner?: string, description?: string, endpoints?: Array<{ method: "GET" | "POST" | "PUT" | "DELETE" | "PATCH", path: string }>, linked_adrs?: string[], last_updated?: string, documented?: boolean }
    - GraphEdge: { id: string, source: string, target: string, relationship: "depends_on" | "owns" | "causes" }
    - HealthSnapshot: { id: number, repo: string, score: number (0-100), grade: string, produced_at: string }
    - CoverageEntry: { service_id: string, service_name: string, coverage_percentage: number (0-100) }
    - GapDay: { date: string (ISO 8601), gap_count: number }
    - Alert: { id: string, severity: "CRITICAL" | "WARNING" | "INFO", message: string, entity_name: string, entity_link: string, triggered_at: string }
    - ActivityEvent: { id: string, type: "doc_refresh_completed" | "doc_rewrite_generated" | "ci_check_run" | "waiver_granted" | "health_score_changed" | "policy_blocked" | "doc_gap_detected", description: string, entity_name: string, repo: string, timestamp: string, payload: Record<string, unknown> }
    - PolicyRun: { id: number, repo: string, pr_number?: number, rule_set: string, summary_status: "pass" | "warn" | "block", merge_gate?: { decision: "allow" | "block" | "allow_with_waiver", blocking_rule_ids?: string[] }, findings?: Finding[], produced_at: string }
    - Finding: { rule_id: string, severity: "critical" | "high" | "medium" | "low", status: string, title: string, description: string, suggested_action?: string }
    - Waiver: { id: number, repo: string, pr_number: number, rule_ids: string[], justification: string (min 50 chars), requested_by: string, approved_by?: string, status: "pending" | "approved" | "rejected" | "expired", expires_at?: string (max 30 days from now), created_at: string }
    - Blueprint: { plan_id: string, requirement: { requirement_text: string }, pattern?: "Microservices" | "Monolith" | "CQRS" | "BFF" | "Saga" | "Event-driven", services?: ServiceBlueprint[], aligned: boolean, drift_summary?: string, produced_at: string }
    - ServiceBlueprint: { name: string, role: string, language: string, runtime: string }
    - OnboardingPath: { path_id: string, role: "backend_engineer" | "sre" | "frontend_developer" | "data_engineer" | "engineering_manager", repo: string, stages?: OnboardingStage[] }
    - OnboardingStage: { stage_id: string, title: string, description?: string, estimated_minutes?: number, resources?: OnboardingResource[], completed?: boolean }
    - OnboardingResource: { type: "doc" | "graph_node" | "adr" | "code" | "task", title: string, description?: string, url?: string, service_name?: string }
  - Extend API client in `frontend/lib/api.ts` with endpoint functions (all include authHeaders() and X-Repo-Scope header injection):
    - POST /adapters/web/ask (body: { question: string, repo: string, channel: "web" | "cli", history: ChatMessage[] }) → SSE stream
    - GET /assistant/sessions?repo={repo} → Session[]
    - GET /assistant/sessions/{id}/messages → Message[]
    - DELETE /assistant/sessions/{id} → 204
    - GET /graph/nodes?repo={repo} → GraphNode[]
    - GET /graph/edges?repo={repo} → GraphEdge[]
    - GET /graph/neighbors/{node_id}?depth=1 → { nodes: GraphNode[], edges: GraphEdge[] }
    - GET /health/snapshots?repo={repo}&limit={limit}&days={days} → HealthSnapshot[]
    - GET /health/coverage?repo={repo} → CoverageEntry[]
    - GET /health/gaps/timeline?repo={repo}&days=365 → GapDay[]
    - GET /reporting/alerts?repo={repo}&status=active → Alert[]
    - POST /reporting/alerts/{id}/dismiss → 204
    - GET /reporting/activity?repo={repo}&limit=20&cursor={cursor} → { items: ActivityEvent[], next_cursor: string | null }
    - GET /reporting/stream?repo={repo} → SSE stream (health_update, alert, activity events)
    - GET /policy/runs?repo={repo}&outcome={outcome}&ruleset={ruleset}&from={from}&to={to}&search={search}&limit=25&cursor={cursor} → { items: PolicyRun[], next_cursor: string | null }
    - GET /policy/rulesets?repo={repo} → string[]
    - GET /policy/runs/stats?repo={repo}&days=7 → PolicyStats
    - GET /policy/stream?repo={repo} → SSE stream (policy_run events)
    - POST /governance/waivers (body: { rule_ids: string[], justification: string, expires_at: string, repo: string, pr_number: number }) → Waiver
    - DELETE /governance/waivers/{id} → 204
    - GET /blueprints?repo={repo}&pattern={pattern}&from={from}&to={to}&aligned={aligned} → Blueprint[]
    - GET /blueprints/{id} → Blueprint
    - POST /blueprints/{id}/analyze → { aligned: boolean, drift_summary: string | null }
    - GET /blueprints/{id}/artifacts/{file_path} → text/plain
    - GET /blueprints/{id}/artifacts/download → application/zip
    - POST /onboarding/role (body: { role: string, user_id: string, repo: string }) → 204
    - GET /onboarding/path?repo={repo}&role={role} → OnboardingPath
    - POST /onboarding/progress (body: { stage_id: string, user_id: string, repo: string, completed_at: string }) → 204
    - POST /onboarding/progress/resource (body: { resource_id: string, user_id: string, repo: string }) → 204
  - Create shared utility functions in `frontend/lib/utils.ts`:
    - groupSessionsByTime(sessions: Session[]): { today: Session[], yesterday: Session[], last7Days: Session[], last30Days: Session[], older: Session[] } - Groups by: Today (same day), Yesterday (1 day ago), This Week (2-7 days ago), Older (>7 days ago)
    - filterGraphNodes(nodes: GraphNode[], edges: GraphEdge[], visibleTypes: Set<string>): { filteredNodes: GraphNode[], filteredEdges: GraphEdge[] } - Filters nodes by type, edges by visible source/target
    - validateWaiverRequest(waiver: { rule_ids: string[], justification: string, expires_at: string }): { valid: boolean, errors: string[] } - Validates: rule_ids not empty, justification >= 50 chars, expires_at <= 30 days from now
    - parseConstraintReferences(decisionText: string): string[] - Extracts constraint numbers from "[Constraint N]" using regex /\[Constraint (\d+)\]/g
    - getHealthColor(score: number): string - Health_Color_Scale: if score >= 50 interpolate #f59e0b (50) to #22c55e (100), else interpolate #ef4444 (0) to #f59e0b (50)
    - getGapColor(gapCount: number, isDark: boolean): string - 5-stop scale: 0=#ebedf0/#161b22, 1-2=#9be9a8/#0e4429, 3-5=#40c463/#006d32, 6-10=#30a14e/#26a641, 11+=#216e39/#39d353
    - interpolateColor(color1: string, color2: string, t: number): string - RGB linear interpolation between two hex colors
  - Create shared error handling components:
    - ErrorState component: displays error icon (AlertCircle from lucide-react), error message derived from ApiError status (401="Authentication required", 403="Permission denied", 404="Resource not found", 500="Server error", default=error.message), retry button calling onRetry prop
    - ApiError class: extends Error, adds status: number field, used by API client to throw HTTP errors
  - Create shared skeleton loading components (all use animate-pulse, bg-slate-800, rounded):
    - MessageSkeleton: 56px tall (h-14) full-width rectangle
    - GraphNodeSkeleton: 180x72px (w-[180px] h-[72px]) rounded rectangle for services, 52px (w-[52px] h-[52px]) circle for engineers
    - MetricCardSkeleton: 48px tall (h-12) rectangle for value, 16px (h-4) for label, 12px (h-3) for trend
    - PolicyRunSkeleton: 56px (h-14) row with 5 varying-width inner rectangles
    - BlueprintCardSkeleton: two rectangles per card (h-4 full-width, h-3 w-3/4)
    - StageSkeleton: 200x100px (w-[200px] h-[100px]) rectangle
  - Create shared empty state components (all centered with icon, heading, description):
    - EmptyGraphState: GitBranch icon (w-12 h-12 text-slate-600), "No graph data found", "The knowledge graph for this repository hasn't been indexed yet. Trigger an indexing run to populate the graph."
    - EmptyPolicyRunsState: Shield icon, "No policy runs found", "Policy runs will appear here when pull requests are opened or updated."
    - EmptyOnboardingState: GraduationCap icon, "Select your role to begin", "Choose your role to generate a personalized onboarding path for this repository."
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 8.3, 8.5, 8.6, 8.7_
  - _Properties: 9 (API header injection), 37 (skeleton shape matching), 38 (error state with retry), 39 (empty state with guidance)_

- [ ] 2. Implement Q&A Chat Interface (/qa)
  - [x] 2.1 Create page layout and routing
    - Create `frontend/app/(app)/qa/page.tsx` with full viewport height layout (h-screen flex flex-col)
    - Implement header with repo scope display, new chat button, and history toggle button
    - Set up three-panel layout: history sidebar (320px w-80, slide-in with 300ms translateX transition), message thread (flex-1), chat input (bottom fixed)
    - History sidebar closed by default, opens/closes with 300ms CSS transition
    - Below 1400px: history sidebar overlays chat panel (absolute positioning) instead of pushing it
    - _Requirements: 1.1, 1.2, 1.19, 9.2_
    - _Properties: None_

  - [x] 2.2 Implement streaming chat hook
    - Create `frontend/hooks/useStreamingChat.ts` custom hook with sendMessage(text: string, channel: "web" | "cli" = "web") function
    - Implement Fetch API with ReadableStream for SSE parsing:
      - POST /adapters/web/ask with body: { question: text, repo: activeRepo, channel, history: messages.slice(-6) }
      - Headers: { "Content-Type": "application/json", ...authHeaders() }
      - Response: ReadableStream<Uint8Array>
    - Use TextDecoder to read chunks: const decoder = new TextDecoder(); const { value, done } = await reader.read(); buffer += decoder.decode(value, { stream: true })
    - Buffer incomplete lines across chunks in string variable: buffer = ""; lines = buffer.split("\n"); buffer = lines.pop() || ""
    - Parse complete lines beginning with "data: " as JSON SSE events: if (line.startsWith("data: ")) { const data = JSON.parse(line.slice(6)); }
    - Handle token events (type="token"): append event.text to message content using useRef to avoid stale closures: contentRef.current += data.text; setMessages(prev => prev.map(m => m.id === assistantMsgId ? { ...m, content: contentRef.current } : m))
    - Handle metadata events (type="metadata"): complete message with { intent: data.intent, sub_intent: data.sub_intent, confidence: data.confidence (0-100), citations: data.citations, source_breakdown: data.source_breakdown, chain_steps: data.chain_steps, follow_up_suggestions: data.follow_up_suggestions }; mark streaming=false; hide cursor
    - Implement stop streaming functionality: expose stopStreaming() function that calls reader.cancel() on active stream reader
    - Handle streaming errors: if stream closes without metadata event, mark message as error with content="Response was incomplete. The service may be under load." and error=true, display retry button
    - First token must appear within 500ms (performance target from Appendix B: Q&A Interface first streaming token < 500ms)
    - _Requirements: 1.6, 1.7, 1.8, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, Appendix B_
    - _Properties: 2 (SSE token streaming with buffer), 3 (SSE metadata completion), 40 (performance target compliance)_

  - [x] 2.3 Create MessageThread component
    - Create `frontend/components/chat/MessageThread.tsx` with auto-scroll behavior
    - Implement UserMessage component: right-aligned (justify-end), rounded bubble (rounded-2xl bg-blue-600), plain text content, relative timestamp below in muted text
    - Implement AssistantMessage component: left-aligned (justify-start) with seven layers in exact vertical order
    - Layer 1 IntentBadge: monospace 11px pill (font-mono text-xs px-2 py-0.5 rounded-full), colored by top-level intent (architecture=blue, policy=amber, impact=red, onboarding=green, general=gray), displays full intent string (e.g., "architecture.trace_dependency"), only visible after streaming completes
    - Layer 2 MarkdownContent: react-markdown with react-syntax-highlighter using oneDark theme for code blocks; during streaming show blinking cursor (2px wide, 1em tall, opacity 0 to 1 every 500ms via CSS animation @keyframes blink) at end of text; hide cursor when metadata event received
    - Layer 3 ConfidenceBar: 4px tall horizontal bar (h-1 rounded-full), filled proportion = confidence/100, color via Health_Color_Scale applied to confidence score, tooltip on hover showing exact percentage, only visible after streaming completes
    - Layer 4 SourceBreakdown: horizontal pills (flex gap-2) with text "{count} from {source_type}", display names: code="Code" (purple tint bg-purple-100), docs="Docs" (blue tint bg-blue-100), adrs="ADRs" (amber tint bg-amber-100), incidents="Incidents" (red tint bg-red-100), specs="API Specs" (green tint bg-green-100), only visible after streaming completes
    - Layer 5 CitationsPanel: collapsed by default with toggle button "{n} citations", when expanded max-height 200px with internal scroll (overflow-y-auto), each citation row: source_ref in monospace truncated to last 40 chars with "..." prefix if longer, line number badge "L{line}", two-line excerpt in left-bordered blockquote (border-l-2 pl-3), clipboard copy button, only visible after streaming completes
    - Layer 6 ChainOfThoughtSteps: collapsed by default with toggle button "Reasoning", when expanded show each step with name in bold, input truncated to 60 chars, output truncated to 60 chars, duration in ms as muted right-aligned text, only visible after streaming completes
    - Layer 7 FollowUpSuggestions: horizontally scrollable row (flex overflow-x-auto scrollbar-hidden), pill buttons with max-width 280px and text truncated with ellipsis, clicking chip calls handleSend with chip's question text, only visible after streaming completes
    - Implement auto-scroll: scroll to bottom when new content arrives UNLESS user manually scrolled >100px above bottom (detect via scrollTop + clientHeight vs scrollHeight comparison)
    - _Requirements: 1.4, 1.5, 1.9_
    - _Properties: 1 (message role alignment), 4 (auto-scroll with user override)_

  - [x] 2.4 Create ChatInput component
    - Create `frontend/components/chat/ChatInput.tsx` with auto-resizing textarea
    - Implement auto-resizing textarea: 1-6 rows, use hidden div mirror technique (create hidden div with same content and styling, measure height, apply to textarea)
    - Implement conditional button rendering: send button (disabled when empty or streaming), stop button (when streaming, calls reader.cancel())
    - Handle Enter key (send message) and Shift+Enter (new line) via onKeyDown
    - Implement channel mode pill to left of input: cycles between "Web" (markdown response) and "CLI Preview" (monospace plain text) on click, sends as channel field in request
    - Implement keyboard shortcut: Cmd+/ (Ctrl+/ on Windows) focuses textarea via document keydown listener in useEffect
    - _Requirements: 1.10, 1.11, 1.12_
    - _Properties: 5 (textarea auto-resize with mirror), 6 (conditional button states)_

  - [x] 2.5 Create HistorySidebar component
    - Create `frontend/components/chat/HistorySidebar.tsx` with 320px width (w-80)
    - Implement slide-in/out animation: 300ms translateX transition (transition-transform duration-300), closed=translateX(-100%), open=translateX(0)
    - Fetch sessions from GET /assistant/sessions?repo={activeRepo} using React Query
    - Group sessions by time using groupSessionsByTime utility: Today (same day), Yesterday (1 day ago), This Week (2-7 days ago), Older (>7 days ago)
    - Each session item: PR title or first message preview, relative timestamp, delete button (trash icon)
    - Implement session deletion: DELETE /assistant/sessions/{id}, remove from list with 200ms fade-out animation (transition-opacity duration-200)
    - Implement new conversation button at top: clears thread, generates new session ID in Zustand
    - Clicking session item: fetches GET /assistant/sessions/{id}/messages, loads into thread
    - _Requirements: 1.2, 1.13, 1.14, 1.15_
    - _Properties: 7 (history session grouping by time), 8 (session deletion with animation)_

  - [x] 2.6 Create EmptyState component
    - Create `frontend/components/chat/EmptyState.tsx` displayed when messages.length === 0
    - Display KA-CHOW logo (centered)
    - Display heading "Ask anything about your codebase" (text-2xl font-bold)
    - Display subheading "I have full context of your services, APIs, policies, and architecture decisions" (text-sm text-muted)
    - Display 2x4 grid of suggestion cards (grid grid-cols-2 gap-4) grouped by intent category
    - Architecture cards (blue left border border-l-4 border-blue-500): "What does the payments service do?", "What services depend on the auth service?"
    - Policy cards (amber left border border-l-4 border-amber-500): "Which PRs are currently blocked by policy?", "Show me active waivers for this repo"
    - Onboarding cards (green left border border-l-4 border-green-500): "What should I understand first as a new backend engineer?", "Who owns the notification service?"
    - Impact cards (red left border border-l-4 border-red-500): "What breaks if I deprecate the /v1/users endpoint?", "What's affected if I change the user_id field type?"
    - Clicking suggestion card immediately calls handleSend with card's question text (no additional user interaction required)
    - _Requirements: 1.3_
    - _Properties: None_

  - [x] 2.7 Implement loading and error states
    - Create MessageSkeleton component: full-width gray rectangle 56px tall (h-14 bg-slate-800 rounded animate-pulse) for each message slot while history is loading
    - Create ErrorState component for history load failures: "Could not load conversation history for {activeRepo}" with retry button
    - Handle streaming errors: display error message in assistant message with retry button that resends same question
    - _Requirements: 1.17, 1.18, 8.5, 8.6_
    - _Properties: 37 (skeleton shape matching), 38 (error state with retry)_

  - [x] 2.8 Implement responsive design
    - Ensure layout works at 1280px minimum width (min-w-[1280px])
    - Below 1400px: history sidebar overlays chat panel (absolute z-50) instead of pushing it (use media query @media (max-width: 1400px))
    - Adjust spacing and font sizes for different screen sizes (responsive text classes text-sm md:text-base)
    - _Requirements: 1.19, 9.1, 9.2, 9.3_
    - _Properties: None_

- [ ] 3. Implement Knowledge Graph Visualizer (/graph)
  - [x] 3.1 Create page layout and routing
    - Create `frontend/app/(app)/graph/page.tsx` with full-screen layout (h-screen w-screen)
    - Set up React Flow canvas with ReactFlowProvider wrapper
    - Add control panel absolutely positioned top-right (absolute top-4 right-4 z-10)
    - Add detail panel absolutely positioned top-right (absolute top-0 right-0 h-full z-20), 400px width (w-[400px]), reduces to 320px below 1400px
    - Detail panel slide-in animation: 300ms translateX transition, closed=translateX(100%), open=translateX(0)
    - _Requirements: 2.1, 2.2, 2.3, 2.30, 9.2_
    - _Properties: None_

  - [x] 3.2 Create data fetching hooks
    - Create `frontend/hooks/useGraphData.ts` using React Query
    - Fetch nodes and edges in parallel using Promise.all: GET /graph/nodes?repo={activeRepo} and GET /graph/edges?repo={activeRepo}
    - Implement neighbor expansion mutation: POST to GET /graph/neighbors/{node_id}?depth=1, returns { nodes: GraphNode[], edges: GraphEdge[] }
    - Cache with staleTime 30000ms (30 seconds)
    - Initial graph render with up to 200 nodes must complete within 2 seconds (performance target from Appendix B)
    - _Requirements: 2.4, 2.16, Appendix B_
    - _Properties: 13 (node double-click expansion), 40 (performance target compliance)_

  - [x] 3.3 Implement layout algorithms
    - Create `frontend/lib/graph-layout.ts` with three layout functions
    - Implement Force layout using d3-force: forceSimulation with forceLink (linkDistance=150), forceManyBody (chargeStrength=-400), forceCenter, run 300 synchronous ticks before first render (simulation.tick(300))
    - Implement Tree layout using dagre (@dagrejs/dagre): direction="LR" (left-to-right), identify roots as nodes with no incoming edges, build hierarchy, apply dagre.layout
    - Implement Radial layout: distribute nodes at equal angles around center point, radius = (nodeCount * 30) clamped to 200-600px (Math.max(200, Math.min(600, nodeCount * 30)))
    - Layout switching animates positions over 600ms using requestAnimationFrame interpolation
    - _Requirements: 2.5, 2.21, 13.2, 13.3, Glossary: Force_Layout, Tree_Layout, Radial_Layout_
    - _Properties: 34 (layout algorithm determinism)_

  - [x] 3.4 Create custom node components
    - Create `frontend/components/graph/nodes/ServiceNode.tsx`: 180x72px rounded rectangle (w-[180px] h-[72px] rounded-lg), background color via Health_Color_Scale applied to health_score, service name 13px bold white (text-sm font-bold text-white), owner name 11px white 70% opacity (text-xs text-white/70), 22px health score badge top-right corner (absolute top-1 right-1 w-[22px] h-[22px] rounded-full bg-white text-xs font-bold) with colored text matching node background, pulse animation when health_score < 40 (animate-pulse box-shadow: 0 0 0 6px {nodeColor}40 over 2s infinite ease-in-out)
    - Create `frontend/components/graph/nodes/APINode.tsx`: pill shape height 28px (h-7 rounded-full), min-width 100px max-width 160px (min-w-[100px] max-w-[160px]), colored left section for HTTP method (GET=#3b82f6 bg-blue-500, POST=#22c55e bg-green-500, PUT=#f59e0b bg-amber-500, DELETE=#ef4444 bg-red-500, PATCH=#a855f7 bg-purple-500) displaying method in 9px bold white (text-[9px] font-bold text-white), path in 11px monospace in right section (text-xs font-mono)
    - Create `frontend/components/graph/nodes/SchemaNode.tsx`: 80x80px div (w-20 h-20) with CSS transform rotate(45deg) on container and rotate(-45deg) on content wrapper (transform rotate-45 on outer div, transform -rotate-45 on inner div) so text remains readable, label 11px centered (text-xs text-center)
    - Create `frontend/components/graph/nodes/ADRNode.tsx`: 100x64px rectangle (w-[100px] h-16), folded top-right corner via CSS ::before pseudo-element (before:absolute before:top-0 before:right-0 before:w-3 before:h-3 before:bg-inherit before:transform before:rotate-45), ADR number in bold, title truncated to 20 characters (truncate max-w-[20ch])
    - Create `frontend/components/graph/nodes/EngineerNode.tsx`: 52px diameter circle (w-[52px] h-[52px] rounded-full), background color deterministically selected from 8 predefined colors using hash of engineer name (use name.charCodeAt sum % 8 to select from palette), initials (first letter of first and last name) 16px bold white (text-base font-bold text-white), 2px white border (border-2 border-white)
    - Create `frontend/components/graph/nodes/IncidentNode.tsx`: 60x52px warning triangle (w-[60px] h-[52px]) via CSS clip-path: polygon(50% 0%, 0% 100%, 100% 100%), background #ef4444 for critical severity (bg-red-500), #f59e0b for warning severity (bg-amber-500), white exclamation mark centered (text-white text-2xl font-bold)
    - _Requirements: 2.6, 2.7, 2.8, 2.9, 2.10, 2.11_
    - _Properties: 10 (node type to component mapping)_

  - [x] 3.5 Create custom edge components
    - Create `frontend/components/graph/edges/DependencyEdge.tsx`: solid 1.5px #6b7280 line (stroke-[1.5px] stroke-gray-500), arrow marker at target end (markerEnd="url(#arrow)")
    - Create `frontend/components/graph/edges/OwnershipEdge.tsx`: dashed 1.5px #3b82f6 line (stroke-[1.5px] stroke-blue-500 stroke-dasharray-[6,3]), no arrow markers
    - Create `frontend/components/graph/edges/CausalityEdge.tsx`: dotted 1.5px #f59e0b line (stroke-[1.5px] stroke-amber-500 stroke-dasharray-[2,2]), arrow markers at both ends (markerStart and markerEnd)
    - _Requirements: 2.12, 2.13, 2.14_
    - _Properties: 11 (edge type to style mapping)_

  - [x] 3.6 Create GraphCanvas component
    - Create `frontend/components/graph/GraphCanvas.tsx` integrating React Flow
    - Register custom node types via nodeTypes prop: { service: ServiceNode, api: APINode, schema: SchemaNode, adr: ADRNode, engineer: EngineerNode, incident: IncidentNode }
    - Register custom edge types via edgeTypes prop: { dependency: DependencyEdge, ownership: OwnershipEdge, causality: CausalityEdge }
    - Implement node click: sets selectedNodeId state, opens detail panel with 300ms translateX(0) transition, clicking same node again closes panel
    - Implement node double-click: calls React Flow fitView (padding=0.3, duration=600ms) centered on node, fetches GET /graph/neighbors/{node_id}?depth=1, adds returned nodes/edges with hidden-to-visible animation (set hidden=true initially, setTimeout 50ms then set hidden=false)
    - Implement node hover: sets opacity of non-connected nodes to 0.15 and non-connected edges to 0.1 via React Flow style props, resets to 1 on hover end
    - Implement zoom, pan, and fit-to-view controls via React Flow Controls component positioned bottom-right (position="bottom-right")
    - Node click to detail panel open must complete within 300ms (performance target from Appendix B)
    - _Requirements: 2.15, 2.16, 2.17, 13.4, 13.5, 13.6, 13.7, Appendix B_
    - _Properties: 12 (node click opens detail panel), 13 (node double-click expansion), 14 (node hover opacity adjustment), 40 (performance target compliance)_

  - [x] 3.7 Create FilterPanel component
    - Create `frontend/components/graph/FilterPanel.tsx` in control panel
    - Add node type toggles: 6 icon+label buttons (service, api, schema, adr, engineer, incident), toggling sets corresponding node type to hidden in React Flow state without removing from data array
    - Add health filter slider: 0-100 range (input type="range" min="0" max="100"), default=0, hides nodes with health_score below slider value (nodes without health_score unaffected)
    - Add "Unhealthy only" button: sets slider to 60, shows only nodes with health_score < 60
    - Add search input: debounced 200ms (use useDebouncedValue hook), sets opacity of non-matching nodes to 0.1, applies 2px blue highlight ring to matching nodes (ring-2 ring-blue-500), clear button appears when input has content
    - Add layout mode buttons: Force, Tree, Radial, switching triggers 600ms animated position transitions via requestAnimationFrame interpolation
    - Add minimap toggle button: shows/hides React Flow MiniMap component positioned bottom-left (position="bottom-left")
    - _Requirements: 2.18, 2.19, 2.20, 2.21, 2.22_
    - _Properties: 15 (node type filter visibility)_

  - [x] 3.8 Create NodeDetailPanel component
    - Create `frontend/components/graph/NodeDetailPanel.tsx` with 400px width (w-[400px]), reduces to 320px below 1400px
    - Implement slide-in animation from right: 300ms translateX transition, closed=translateX(100%), open=translateX(0)
    - Display node-specific content based on node type (use switch statement on node.type)
    - For ServiceNode: service name as h2, owner with 32px avatar circle showing initials, health score as large number colored by Health_Color_Scale, four mini horizontal progress bars (h-2 rounded-full) labeled "API Docs / Architecture Decisions / Incident Postmortems / Code Comments" each 0-100% colored by their own percentage, last updated as relative time, "Depends on ({n})" section of clickable chips that select target node, "Used by ({n})" section of clickable chips, linked ADRs list with ADR number and status badge, linked incidents list with severity badge and title, "Ask about this" button navigating to /qa with pre-filled question "What does the {service_name} service do?", "View health history" button opening Recharts LineChart popover showing 30-day health_score trend
    - For APINode: HTTP method badge, full path, description if available, parameters table with columns name/type/required/description, response codes list, parent service chip that selects parent ServiceNode when clicked
    - For ADRNode: ADR number and title, status badge (proposed/accepted/superseded/deprecated), decision summary paragraph, consequences as bulleted list, affected services as clickable chips, date created and last modified
    - For EngineerNode: 64px avatar circle with initials, name as heading, role as subheading, owned services as clickable chips, expertise tags as pills, last five activity events for this engineer
    - Close triggers: X button click, Escape key press (via useEffect document keydown listener), clicking same node again
    - _Requirements: 2.23, 2.24, 2.25, 2.26, 2.27_
    - _Properties: 12 (node click opens detail panel)_

  - [x] 3.9 Implement loading and error states
    - Create GraphNodeSkeleton component: circular placeholder nodes 52px diameter (w-[52px] h-[52px] rounded-full bg-slate-800 animate-pulse) and rectangular placeholders 180x72px (w-[180px] h-[72px] rounded-lg bg-slate-800 animate-pulse) connected by line placeholders while graph data is loading
    - Create EmptyGraphState component: "The knowledge graph for {activeRepo} hasn't been indexed yet" with graph icon, "Trigger an indexing run to populate the graph" guidance
    - Create ErrorState component: "Failed to load the knowledge graph. Check your connection." for network errors, "The knowledge graph for {activeRepo} hasn't been indexed yet" for 404 errors, both with retry button
    - _Requirements: 2.28, 2.29, 8.5, 8.6, 8.7_
    - _Properties: 37 (skeleton shape matching), 38 (error state with retry), 39 (empty state with guidance)_

  - [x] 3.10 Implement responsive design
    - Ensure layout works at 1280px minimum width (min-w-[1280px])
    - Below 1400px: detail panel reduces from 400px to 320px (w-[400px] lg:w-[320px])
    - Adjust panel sizes and spacing for different screen sizes
    - _Requirements: 2.30, 9.1, 9.2, 9.3_
    - _Properties: None_

- [x] 4. Implement System Health Dashboard (/health)
  - [x] 4.1 Create page layout and routing
    - Create `frontend/app/(app)/health/page.tsx` with CSS Grid layout
    - Set up four-row grid structure: Row 1 (grid-template-columns: repeat(4, 1fr)), Row 2 (grid-template-columns: 3fr 2fr), Row 3 (grid-template-columns: 1fr 1fr), Row 4 (grid-template-columns: 1fr), all rows separated by 16px gap (gap-4)
    - Below 1400px: Row 2 and Row 3 stack vertically (single column via media query)
    - _Requirements: 3.1, 3.30, 9.2_
    - _Properties: None_

  - [x] 4.2 Create data fetching hooks
    - Create `frontend/hooks/useHealthData.ts` using React Query
    - Fetch dashboard overview: GET /health/snapshots?repo={activeRepo}&limit=1 for latest score
    - Fetch health snapshots (30-day history): GET /health/snapshots?repo={activeRepo}&days=30
    - Fetch coverage data: GET /health/coverage?repo={activeRepo}
    - Fetch gaps timeline: GET /health/gaps/timeline?repo={activeRepo}&days=365 for heatmap
    - Fetch active alerts: GET /reporting/alerts?repo={activeRepo}&status=active
    - Fetch activity feed with infinite scroll: GET /reporting/activity?repo={activeRepo}&limit=20&cursor={cursor} using useInfiniteQuery
    - Implement SSE connection for live updates: GET /reporting/stream?repo={activeRepo} handling health_update, alert, and activity events
    - All four metric cards must render within 1 second (performance target from Appendix B)
    - _Requirements: 3.23, 3.24, 3.25, 3.26, 10.1, 10.2, 10.3, 10.4, Appendix B_
    - _Properties: 19 (SSE live update cache integration), 20 (SSE reconnection with exponential backoff), 40 (performance target compliance)_

  - [x] 4.3 Create MetricCards component
    - Create `frontend/components/health/MetricCards.tsx` displaying four cards in Row 1
    - Card 1 Knowledge Health Score: latest score from snapshots, 3px colored left border (border-l-[3px]) via Health_Color_Scale, primary value 48px font-weight-700 (text-5xl font-bold), label "Knowledge Health Score" 14px muted (text-sm text-muted), trend indicator with up/down arrow icon and "+{n}% vs last week" text (green if positive, red if negative), 60x24px inline Recharts LineChart sparkline (width={60} height={24}) showing 7-day trend with no axes (hide={true} for XAxis and YAxis)
    - Card 2 Services Coverage: "{documented} / {total} documented" from coverage data, trend as coverage percentage change vs last week, sparkline showing coverage trend
    - Card 3 Documentation Gaps: open gap count from gaps data, trend as change in open gaps vs last week, accent red if >10 (border-red-500), amber if 5-10 (border-amber-500), green if <5 (border-green-500), action link "View gaps" navigating to /graph with undocumented filter active
    - Card 4 CI Pass Rate: pass percentage from GET /policy/runs/stats?repo={activeRepo}&days=7, 60x24px inline Recharts LineChart sparkline showing daily pass rates with no axes
    - Each card: 3px colored left border, 48px primary value, 14px label, trend indicator with arrow and percentage
    - _Requirements: 3.2, 3.3, 14.2, Appendix B_
    - _Properties: 40 (performance target compliance)_

  - [x] 4.4 Create HealthScoreChart component
    - Create `frontend/components/health/HealthScoreChart.tsx` in Row 2 left panel
    - Render Recharts AreaChart: width=100% height=280px (width="100%" height={280})
    - XAxis: dataKey="date" formatted as "Jan 15" (format via date-fns), tickLine=false, axisLine=false
    - YAxis: domain=[0,100], ticks=[0,25,50,75,100], tickLine=false, axisLine=false
    - CartesianGrid: horizontal lines only (horizontal={true} vertical={false}), strokeDasharray="3 3"
    - Area: strokeWidth=2, dot=false, activeDot radius=4, animationDuration=1000, animationEasing="ease-out"
    - Fill: linearGradient from stroke color at 30% opacity (top stop offset="0%") to transparent (bottom stop offset="100%")
    - Stroke color: Health_Color_Scale applied to latest score value
    - ReferenceLine y=80: stroke amber (#f59e0b), strokeDasharray="4 2", label "Target" right-aligned
    - ReferenceLine y=50: stroke red (#ef4444), strokeDasharray="4 2", label "Warning" right-aligned
    - ReferenceArea: for any 7-day window with score drop >15 points, red fill at 15% opacity (#ef444426)
    - Chart must animate in within 1 second of data load (performance target from Appendix B)
    - _Requirements: 3.7, 3.8, 3.9, 3.10, 14.3, Appendix B_
    - _Properties: 16 (health score color interpolation), 40 (performance target compliance)_

  - [x] 4.5 Create CoverageChart component
    - Create `frontend/components/health/CoverageChart.tsx` in Row 3 left panel
    - Render Recharts BarChart: layout="vertical", width=100%, height=(serviceCount * 32) clamped to min 200px max 500px (height={Math.max(200, Math.min(500, serviceCount * 32))})
    - Data sorted by coverage percentage ascending (worst-covered service at top)
    - Bar color: Health_Color_Scale applied to coverage percentage (green >=80, yellow >=50, red <50)
    - YAxis: service names 12px right-aligned (fontSize={12} textAnchor="end") truncated to 20 characters
    - XAxis: 0-100% with percentage labels (domain=[0,100] tickFormatter={(v) => `${v}%`})
    - Tooltip: service name and exact coverage percentage
    - onClick: navigate to /graph with that service's node selected (onClick={(data) => router.push(`/graph?selectedNodeId=${data.service_id}`)})
    - Default: top 15 services, "Show all {n} services" button below that re-renders with full dataset
    - _Requirements: 3.11, 3.12, 3.13, 14.4_
    - _Properties: 17 (coverage bar color thresholds), 36 (chart click navigation with query params)_

  - [x] 4.6 Create GapHeatmap component
    - Create `frontend/components/health/GapHeatmap.tsx` in Row 3 right panel
    - Render custom SVG component: 53 columns (weeks) x 7 rows (days Monday-Sunday)
    - Each cell: 12x12px rect (width={12} height={12}) with 3px gap between cells (x={col * 15} y={row * 15})
    - Color scale (light mode / dark mode detected via matchMedia("(prefers-color-scheme: dark)")): 0 gaps=#ebedf0/#161b22, 1-2=#9be9a8/#0e4429, 3-5=#40c463/#006d32, 6-10=#30a14e/#26a641, 11+=#216e39/#39d353
    - Month labels: above first column of each month (text element with y={-5})
    - Day labels: "M", "W", "F" left of rows 1, 3, 5 (text element with x={-20})
    - Hover tooltip: position fixed (position: fixed), follows mouse cursor (style={{ left: e.clientX, top: e.clientY }}), shows "{n} gaps on {date formatted as 'January 15, 2025'}"
    - Click: navigate to /policy filtered to that date (onClick={() => router.push(`/policy?date=${date}`)})
    - SVG horizontally scrollable on overflow (overflow-x-auto)
    - _Requirements: 3.14, 3.15, 3.16, 3.17, 14.5_
    - _Properties: 18 (heatmap cell color scale), 36 (chart click navigation with query params)_

  - [x] 4.7 Create AlertsPanel component
    - Create `frontend/components/health/AlertsPanel.tsx` in Row 2 right panel
    - Fetch alerts from GET /reporting/alerts?repo={activeRepo}&status=active
    - Sort alerts by severity (critical first, then warning, then info), then by timestamp descending within each severity group
    - Each alert row: severity badge (CRITICAL=red bg-red-500, WARNING=amber bg-amber-500, INFO=blue bg-blue-500), message with bold entity name (font-bold), clickable entity link navigating to relevant page, relative time (via date-fns formatDistanceToNow), dismiss button (trash icon)
    - Critical alerts: pulsing red left border animation (animate-pulse border-l-[3px] border-red-500, CSS @keyframes pulse from border-red-500 to border-red-500/25 over 1.5s infinite)
    - Dismiss button: calls POST /reporting/alerts/{id}/dismiss, removes alert with 200ms slide-up-and-fade animation (transition-all duration-200 opacity-0 -translate-y-2)
    - Empty state: "All clear — no active alerts for {activeRepo}" with green checkmark icon (CheckCircle from lucide-react) centered in panel
    - _Requirements: 3.18, 3.19, 3.20_
    - _Properties: None_

  - [x] 4.8 Create ActivityFeed component
    - Create `frontend/components/health/ActivityFeed.tsx` in Row 4
    - Use useInfiniteQuery: GET /reporting/activity?repo={activeRepo}&limit=20&cursor={cursor}
    - Implement virtualization using @tanstack/react-virtual: container height 400px (h-[400px]), dynamic row height (56px collapsed, 120px expanded) via measureElement
    - IntersectionObserver sentinel div at bottom triggers fetchNextPage when entering viewport
    - Each row: 32x32px icon circle (w-8 h-8 rounded-full) colored by event type, description with bold entity name and muted action text, repo badge, relative timestamp, chevron icon indicating expandability
    - Event type to icon to color mapping: doc_refresh_completed=green checkmark circle (CheckCircle bg-green-500), doc_rewrite_generated=blue sparkle (Sparkles bg-blue-500), ci_check_run=gray CI icon (GitBranch bg-gray-500), waiver_granted=amber shield (Shield bg-amber-500), health_score_changed=colored trend arrow (TrendingUp/TrendingDown, green if increased red if decreased), policy_blocked=red X circle (XCircle bg-red-500), doc_gap_detected=orange warning triangle (AlertTriangle bg-orange-500)
    - Click row: expand inline showing full event payload as syntax-colored JSON in monospace block (font-mono text-xs), 200ms max-height CSS transition (transition-all duration-200 max-h-0 to max-h-[120px])
    - Activity feed first 20 items must render within 1 second (performance target from Appendix B)
    - _Requirements: 3.21, 3.22, Appendix B_
    - _Properties: 21 (infinite scroll pagination), 40 (performance target compliance)_

  - [x] 4.9 Implement SSE live updates
    - Create useHealthStream hook mounting EventSource to GET /reporting/stream?repo={activeRepo}
    - Handle health_update events: invalidate ["health","snapshots"] React Query cache via queryClient.invalidateQueries, push notification via UISlice if score dropped >5 points
    - Handle alert events: invalidate ["health","alerts"] query, push notification
    - Handle activity events: prepend event to activity feed via queryClient.setQueryData (update pages[0] array)
    - Implement connection status indicator: display "Live updates paused" pill (fixed bottom-4 left-4 bg-amber-500 text-white px-3 py-1 rounded-full text-xs) if disconnected for >5 seconds
    - Implement auto-reconnect on error: exponential backoff (2s, 4s, 8s, 16s, capped at 30s), max 10 attempts, set status to "failed" after max attempts
    - Close EventSource on unmount, reopen when activeRepo changes
    - SSE events must be reflected in UI within 500ms of receipt (performance target from Appendix B)
    - _Requirements: 3.23, 3.24, 3.25, 3.26, 10.3, 10.4, Appendix B, Appendix C_
    - _Properties: 19 (SSE live update cache integration), 20 (SSE reconnection with exponential backoff), 40 (performance target compliance)_

  - [x] 4.10 Implement loading and error states
    - Create MetricCardSkeleton component: 48px tall rectangle for value (h-12 bg-slate-800 rounded animate-pulse), 16px rectangle for label (h-4 bg-slate-800 rounded animate-pulse), 12px rectangle for trend (h-3 bg-slate-800 rounded animate-pulse)
    - Create AreaChart skeleton: gray rectangle matching chart dimensions 280px height (h-[280px] bg-slate-800 rounded animate-pulse)
    - Create activity row skeletons: five 56px rectangles (h-14 bg-slate-800 rounded animate-pulse) with varying-width inner rectangles
    - Create ErrorState component: "Health data unavailable for {activeRepo}" with retry button for snapshot fetch failures, "Could not load alerts" with retry button for alerts fetch failures
    - _Requirements: 3.28, 3.29, 8.5, 8.6_
    - _Properties: 37 (skeleton shape matching), 38 (error state with retry)_

  - [x] 4.11 Implement responsive design
    - Ensure layout works at 1280px minimum width (min-w-[1280px])
    - Below 1400px: Row 2 and Row 3 stack vertically (grid-cols-1 via media query @media (max-width: 1400px))
    - Adjust grid layout and spacing for different screen sizes
    - _Requirements: 3.30, 9.1, 9.2, 9.3_
    - _Properties: None_

- [x] 5. Implement CI/CD Policy Status (/policy)
  - [x] 5.1 Create page layout and routing
    - Create `frontend/app/(app)/policy/page.tsx` with two-panel layout
    - Set up CSS Grid: grid-template-columns: 380px 1fr (w-[380px] for list panel, flex-1 for detail panel)
    - Below 1400px: stack vertically (grid-cols-1 via media query) with list on top
    - _Requirements: 4.1, 4.24, 9.2_
    - _Properties: None_

  - [x] 5.2 Create FilterBar component
    - Create `frontend/components/policy/FilterBar.tsx` above run list
    - Add outcome segmented control: All / Pass / Warn / Block options, each with matching colored dot (green/amber/red), active option highlighted
    - Add ruleset dropdown: populated from GET /policy/rulesets?repo={activeRepo}, "All rulesets" default option
    - Add date range selector: buttons Today / Last 7 days / Last 30 days, Custom option opening popover with two calendar inputs (react-day-picker)
    - Add search text input: filters by PR number or branch name, debounced 200ms
    - Sync filter values with URL query parameters using useSearchParams from next/navigation (outcome, ruleset, from, to, search params)
    - _Requirements: 4.2, 4.3_
    - _Properties: 22 (filter URL synchronization)_

  - [x] 5.3 Create data fetching hooks
    - Create `frontend/hooks/usePolicyData.ts` using React Query
    - Implement infinite query for policy runs: GET /policy/runs?repo={activeRepo}&outcome={outcome}&ruleset={ruleset}&from={from}&to={to}&search={search}&limit=25&cursor={cursor} using useInfiniteQuery
    - Fetch policy run detail: GET /policy/runs/{id} when run is selected
    - Implement SSE connection for new policy runs: GET /policy/stream?repo={activeRepo} handling policy_run events
    - Implement waiver request mutation: POST /governance/waivers with { rule_ids, justification, expiry_date, repo, pr_number }
    - Implement waiver revoke mutation: DELETE /governance/waivers/{id}
    - Policy run list first 25 items must render within 1 second (performance target from Appendix B)
    - _Requirements: 4.4, 4.5, 4.6, 10.2, Appendix B_
    - _Properties: 19 (SSE live update cache integration), 20 (SSE reconnection with exponential backoff), 21 (infinite scroll pagination), 40 (performance target compliance)_

  - [x] 5.4 Create PolicyRunList component
    - Create `frontend/components/policy/PolicyRunList.tsx` in left panel (380px width w-[380px])
    - Display policy run cards (56px tall h-14): repo name 12px muted (text-xs text-muted), PR number "#123" with external link icon opening GitHub PR URL in new tab, branch name in monospace pill (font-mono px-2 py-0.5 rounded-full bg-slate-800) truncated to 20 characters, ruleset as small gray badge (text-xs px-1.5 py-0.5 rounded bg-gray-700), outcome badge (PASS=green bg-green-500, WARN=amber bg-amber-500, BLOCK=red bg-red-500, all caps 10px bold rounded text-[10px] font-bold uppercase), merge gate as lock icon (red=locked LockClosed text-red-500, green=unlocked LockOpen text-green-500), timestamp as relative time
    - Selected run: 3px blue left border (border-l-[3px] border-blue-500), slightly elevated background (bg-slate-800/50)
    - Implement infinite scroll: IntersectionObserver sentinel div at bottom triggers fetchNextPage
    - Animate new policy runs from SSE: prepend to list with 300ms slide-down-from-above animation (transition-all duration-300 -translate-y-4 opacity-0 to translate-y-0 opacity-100)
    - New SSE policy run entries must animate into list within 300ms (performance target from Appendix B)
    - _Requirements: 4.4, 4.6, Appendix B_
    - _Properties: 21 (infinite scroll pagination), 40 (performance target compliance)_

  - [x] 5.5 Create PolicyDetailPanel component
    - Create `frontend/components/policy/PolicyDetailPanel.tsx` in right panel (flex-1)
    - Display "Select a policy run to view details" centered (flex items-center justify-center h-full) when no run selected
    - Merge gate banner: full width at top, three states
      - BLOCKED: red background (bg-red-500), white bold text "This PR is blocked from merging" (text-white font-bold), bulleted list of blocking items each with fix link, "Request waiver" button on right
      - WARNED: amber background (bg-amber-500), "This PR has warnings that should be resolved", same bullet list treatment
      - OPEN: green background (bg-green-500), "This PR is clear to merge", last check timestamp
    - PR header below banner: PR title (text-lg font-semibold), branch name with right-arrow separator and repo name (text-sm text-muted), ruleset badge, timestamp
    - Rules section: three collapsible accordion groups (shadcn Accordion component) labeled "Failed ({n})", "Warned ({n})", "Passed ({n})", Failed group expanded by default
      - Each failed rule accordion item header: rule name, red X badge (XCircle text-red-500), chevron
      - When expanded: "What's missing" as plain text, "How to fix" as numbered step list (ol list-decimal pl-5) where each step may include a link, "View documentation gap" button navigating to /graph if fix_url exists, "Create waiver for this rule" button opening WaiverModal pre-filled with that rule
    - Patches section: collapsible section labeled "Suggested Patches ({n})" shown only when suggested_patches.length > 0, each patch displays file path in monospace (font-mono text-xs) and unified diff using react-diff-viewer-continued with splitView=false showDiffOnly=true, "Apply patch" button calls POST /policy/patches/{id}/apply
    - Doc refresh plan section: "Documentation updates triggered" heading, list each triggered refresh job with service name, refresh type badge, status badge (queued/running/completed/failed)
    - Waiver section: when waiver exists display "Applied" amber badge (bg-amber-500), requested by with avatar and name, approved by with avatar and name, rules bypassed as comma-separated list, expiry date colored red if within 7 days (text-red-500), expandable justification paragraph; when no waiver exists and outcome is block or warn, "Request a waiver" button opens WaiverModal
    - _Requirements: 4.7, 4.8, 4.9, 4.10, 4.11, 4.12_
    - _Properties: None_

  - [x] 5.6 Create WaiverModal component
    - Create `frontend/components/policy/WaiverModal.tsx` as shadcn Dialog
    - Fields: rule being waived as read-only pre-filled select (disabled), justification textarea with character counter showing "{n}/50 minimum" in red text (text-red-500) when below 50 characters, expiry date picker (react-day-picker) defaulting to 7 days from today with maximum 30 days from today
    - Client-side validation before submit: rule_ids array not empty, justification >= 50 characters, expiry date <= 30 days from now
    - Submit button: shows loading state (disabled with spinner) during POST /governance/waivers request
    - On success: close modal, push success notification via UISlice, invalidate policy run query
    - On error: display API error message inline below submit button (text-red-500 text-sm)
    - Waiver modal must open within 200ms of button click (performance target from Appendix B)
    - _Requirements: 4.13, 4.14, 4.15, 4.16, 4.17, Appendix B_
    - _Properties: 23 (waiver request validation), 40 (performance target compliance)_

  - [x] 5.7 Create WaiverManagement component
    - Create `frontend/components/policy/WaiverManagement.tsx` accessible from tab control at top of /policy page
    - Display two sub-tabs: Active and Expired (shadcn Tabs component)
    - Each sub-tab displays table with columns: Requested by (avatar + name), Approved by (avatar + name or "Pending approval" badge), Rules bypassed (comma list truncated to 40 characters with tooltip showing full text on hover), Repo, Expiry (red text if active waiver expires within 7 days text-red-500), Status badge
    - Active waivers: Revoke button calls DELETE /governance/waivers/{id}, removes from list with optimistic update
    - _Requirements: 4.18, 4.19, 4.20_
    - _Properties: 24 (optimistic update with rollback)_

  - [x] 5.8 Implement loading and error states
    - Create PolicyRunSkeleton component: five 56px row skeletons (h-14 bg-slate-800 rounded animate-pulse) in list, each containing five rectangles of varying widths
    - Create full-width banner skeleton matching banner height in detail panel (h-16 bg-slate-800 rounded animate-pulse)
    - Create three accordion header skeletons in rules section (h-10 bg-slate-800 rounded animate-pulse)
    - Create ErrorState: "No policy runs found for {activeRepo} in the selected date range" for empty results, "Failed to load policy runs. Check your connection." for network errors, both with retry button
    - _Requirements: 4.22, 4.23, 8.5, 8.6_
    - _Properties: 37 (skeleton shape matching), 38 (error state with retry)_

  - [x] 5.9 Implement responsive design
    - Ensure layout works at 1280px minimum width (min-w-[1280px])
    - Below 1400px: stack list above detail (grid-cols-1 via media query)
    - _Requirements: 4.24, 9.1, 9.2, 9.3_
    - _Properties: None_

- [x] 6. Implement Architecture Blueprint Viewer (/blueprints)
  - [x] 6.1 Create page layout and routing
    - Create `frontend/app/(app)/architecture/page.tsx` with split panel layout
    - Set up CSS Grid: grid-template-columns: 340px 1fr (w-[340px] for list panel, flex-1 for detail panel)
    - Header above both panels: "Architecture Blueprints" heading, "New Blueprint" button navigating to /blueprints/new
    - Below 1400px: list panel reduces from 340px to 280px (w-[340px] lg:w-[280px])
    - _Requirements: 5.1, 5.23, 9.2_
    - _Properties: None_

  - [x] 6.2 Create FilterBar component
    - Create `frontend/components/blueprints/FilterBar.tsx` above blueprint list
    - Add pattern type multi-select dropdown: populated from distinct pattern values in list data (Microservices, Monolith, CQRS, BFF, Saga, Event-driven)
    - Add date range selector: matching Policy_Status date range control (Today / Last 7 days / Last 30 days / Custom)
    - Add alignment toggle: All / Aligned / Drifted options
    - _Requirements: 5.2_
    - _Properties: None_

  - [x] 6.3 Create data fetching hooks
    - Create `frontend/hooks/useBlueprintData.ts` using React Query
    - Fetch blueprints with filters: GET /blueprints?repo={activeRepo}&pattern={pattern}&from={from}&to={to}&aligned={aligned}
    - Fetch blueprint detail: GET /blueprints/{id}
    - Fetch artifact file content: GET /blueprints/{id}/artifacts/{file_path}
    - Implement re-analyze alignment mutation: POST /blueprints/{id}/analyze returns { aligned: boolean, drift_summary: string | null }
    - _Requirements: 5.19_
    - _Properties: None_

  - [x] 6.4 Create BlueprintList component
    - Create `frontend/components/blueprints/BlueprintList.tsx` in left panel (340px width w-[340px])
    - Display blueprint cards: requirement text truncated to 2 lines with ellipsis (line-clamp-2), pattern badge colored by pattern type (Microservices=blue bg-blue-500, Monolith=gray bg-gray-500, CQRS=purple bg-purple-500, BFF=green bg-green-500, Saga=amber bg-amber-500, Event-driven=orange bg-orange-500), service count "{n} services" with grid icon (Grid2X2), date as relative time, alignment indicator (green dot + "Aligned" text-green-500 or red dot + "Drifted" text-red-500)
    - Selected card: 3px blue left border (border-l-[3px] border-blue-500)
    - _Requirements: 5.3_
    - _Properties: None_

  - [x] 6.5 Create BlueprintDetailPanel component
    - Create `frontend/components/blueprints/BlueprintDetailPanel.tsx` in right panel (flex-1)
    - Display alignment banner at top in two states:
      - Aligned: green background (bg-green-500), checkmark icon (CheckCircle), "Blueprint is aligned with the current codebase", last checked timestamp
      - Drifted: red background (bg-red-500), warning icon (AlertTriangle), "Blueprint has drifted from the codebase", drift_summary text, specific callout chips for each drift item formatted as "{service_name} was added to codebase but not in blueprint" or "{service_name} was removed from codebase", "Re-analyze alignment" button calling POST /blueprints/{id}/analyze with loading state, invalidates blueprint query on completion
    - Display three tabs: Design, Rationale, Artifacts (shadcn Tabs component)
    - _Requirements: 5.4, 5.18, 5.19_
    - _Properties: 29 (alignment status banner display)_

  - [x] 6.6 Create DesignTab component
    - Create `frontend/components/blueprints/DesignTab.tsx` rendering React Flow diagram
    - Use separate ReactFlowProvider instance for blueprint diagrams
    - Compute initial layout using dagre library (@dagrejs/dagre): direction="LR" (left to right), nodesep=100, ranksep=150
    - Create BlueprintServiceNode: 180x72px rounded rectangle (w-[180px] h-[72px] rounded-lg), tech stack badge (e.g., "Node.js", "Python", "Go") in bottom-left corner (absolute bottom-1 left-1 px-2 py-0.5 rounded bg-slate-700 text-xs)
    - Clicking BlueprintServiceNode opens popover (not side panel) showing: tech stack with icon, one-sentence role description, API surface as endpoint count, key data schema fields as list, Kubernetes resource requests as CPU request/limit and Memory request/limit
    - Create DatabaseNode: cylinder shape 100px wide 64px tall (w-[100px] h-16), implemented with rectangle with border-radius applied to top and bottom and CSS ::before ellipse pseudo-element on top, gray background (bg-gray-700), database icon (Database from lucide-react), database type badge (Postgres/Redis/MongoDB/etc.)
    - Create ExternalNode: cloud shape using CSS clip-path, muted border (border-slate-600), lighter background (bg-slate-800/50), external service name
    - Create edges with distinct styles: REST (solid 1.5px blue stroke-[1.5px] stroke-blue-500 with arrow and "REST" label text-[10px]), gRPC (solid 1.5px purple stroke-purple-500 with arrow and "gRPC" label), Async (dashed 1.5px orange stroke-orange-500 stroke-dasharray-[6,3] with "async" label), Database (dotted 1px gray stroke-gray-500 stroke-dasharray-[2,2] no arrow no label)
    - Enable React Flow controls (zoom in/out, fit view) positioned bottom-right (position="bottom-right"), no minimap required
    - Design tab diagram must render within 1.5 seconds of tab selection (performance target from Appendix B)
    - _Requirements: 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, Appendix B_
    - _Properties: 25 (blueprint node shape rendering), 26 (blueprint edge style and label), 40 (performance target compliance)_

  - [x] 6.7 Create RationaleTab component
    - Create `frontend/components/blueprints/RationaleTab.tsx` with two-column layout
    - Decisions column: 65% width (w-[65%]), left side
    - Constraints sidebar: 35% width (w-[35%]), right side
    - Constraints sidebar: each constraint as pill with type icon (scale=chart icon BarChart, team_size=people icon Users, compliance=shield icon Shield, latency=clock icon Clock, existing_tech=code icon Code) and constraint text
    - When constraint pill hovered or clicked: apply blue glow border (ring-2 ring-blue-500 shadow-lg shadow-blue-500/50) to all decision cards that reference that constraint
    - Each decision card: decision title as heading (text-lg font-semibold), "What was decided" section, "Why" section as paragraph, "Constraint driver" section showing chips for each linked constraint (clicking chip scrolls to and briefly pulses that constraint in sidebar), collapsible "Alternatives considered" section (shadcn Collapsible) listing each alternative with name and rejection reason in muted text (text-muted), confidence badge in top-right corner (absolute top-2 right-2) colored green if >=80% (bg-green-500), amber if 50-79% (bg-amber-500), red if <50% (bg-red-500)
    - When constraint driver chip clicked: scroll constraints sidebar to referenced constraint (scrollIntoView({ behavior: 'smooth' })), apply 600ms pulse animation (animate-pulse duration-600)
    - Parse constraint references from decision text using regex /\[Constraint (\d+)\]/g
    - _Requirements: 5.11, 5.12, 5.13, 5.14_
    - _Properties: 27 (cross-reference highlighting)_

  - [x] 6.8 Create ArtifactsTab component
    - Create `frontend/components/blueprints/ArtifactsTab.tsx` with two-column layout
    - File tree: 200px width (w-[200px]), left side, displays artifact hierarchy: /services/{service_name}/Dockerfile, /services/{service_name}/k8s/deployment.yaml, /services/{service_name}/k8s/service.yaml, /api/{service_name}/openapi.yaml, /proto/{service_name}.proto
    - Folder nodes: expandable with chevron toggle (ChevronRight/ChevronDown icons), all folders expanded by default
    - Clicking file node: selects file, loads content via GET /blueprints/{id}/artifacts/{file_path}
    - Monaco Editor: fills remaining width (flex-1), right side
    - Monaco Editor configuration: theme="vs-dark" (always regardless of app color mode), readOnly=true, language auto-detected from extension (yaml/yml=yaml, Dockerfile=dockerfile, .proto=proto, .json=json, .ts=typescript, .py=python, .go=go, unrecognized=plaintext), minimap enabled (minimap: { enabled: true }), lineNumbers="on", wordWrap="on", scrollBeyondLastLine=false, fontSize=13
    - Display Skeleton_Loading gray rectangle matching editor dimensions (h-[600px] bg-slate-800 rounded animate-pulse) while content loading
    - "Download all artifacts" button: top-right above editor (absolute top-2 right-2), calls GET /blueprints/{id}/artifacts/download, handles response by creating Blob URL (URL.createObjectURL(blob)), creating temporary anchor element with download attribute (document.createElement('a')), programmatically clicking it (anchor.click()), revoking Blob URL after download starts (URL.revokeObjectURL(url)), button shows loading state during request
    - Monaco Editor must display file content within 500ms of file selection (performance target from Appendix B)
    - Artifact zip download must begin within 2 seconds of button click (performance target from Appendix B)
    - _Requirements: 5.15, 5.16, 5.17, 12.1, 12.2, 12.3, 12.4, Appendix B_
    - _Properties: 28 (file tree to Monaco editor navigation), 40 (performance target compliance)_

  - [x] 6.9 Implement loading and error states
    - Create BlueprintCardSkeleton component: two rectangles of varying width per card (h-4 bg-slate-800 rounded animate-pulse, h-3 bg-slate-800 rounded animate-pulse w-3/4)
    - Create full-width banner skeleton (h-16 bg-slate-800 rounded animate-pulse)
    - Create three tab content skeletons matching structure of each tab (Design: graph skeleton, Rationale: two-column skeleton, Artifacts: file tree + editor skeleton)
    - Create ErrorState: "No blueprints found for {activeRepo}" for empty results, "Failed to load blueprint details." for fetch errors, both with retry button
    - _Requirements: 5.21, 5.22, 8.5, 8.6_
    - _Properties: 37 (skeleton shape matching), 38 (error state with retry)_

  - [x] 6.10 Implement responsive design
    - Ensure layout works at 1280px minimum width (min-w-[1280px])
    - Below 1400px: list panel reduces from 340px to 280px (w-[340px] lg:w-[280px])
    - _Requirements: 5.23, 9.1, 9.2, 9.3_
    - _Properties: None_

- [x] 7. Implement Onboarding Learning Paths (/onboarding)
  - [x] 7.1 Create page layout and routing
    - Create `frontend/app/(app)/onboarding/page.tsx`
    - Set up conditional rendering based on userRole from Zustand: if null show RoleSelector overlay, else show learning path
    - _Requirements: 6.1, 6.2_
    - _Properties: None_

  - [x] 7.2 Create RoleSelector component
    - Create `frontend/components/onboarding/RoleSelector.tsx` as full-screen overlay (fixed inset-0 z-50 bg-slate-900/95 flex items-center justify-center)
    - Display KA-CHOW logo centered at top
    - Display heading "Welcome to {activeRepo}" (text-3xl font-bold)
    - Display subheading "What's your role on this team? I'll build a personalized learning path for you." (text-lg text-muted)
    - Display five role cards in responsive grid: 3 columns above 1400px (grid-cols-3), 2 columns above 1280px (grid-cols-2)
    - Role cards: Backend Engineer ("Services, APIs, data schemas, and system dependencies"), SRE ("Infrastructure, incident patterns, runbooks, and reliability decisions"), Frontend Developer ("API contracts, BFF patterns, and frontend-relevant services"), Data Engineer ("Data schemas, pipeline services, and data flow dependencies"), Engineering Manager ("Team ownership, service health, and architectural decisions")
    - Each card: role icon (Code/Server/Layout/Database/Users from lucide-react), role name (text-xl font-semibold), description (text-sm text-muted)
    - Hover effect: subtle box-shadow (hover:shadow-lg) and border color change (hover:border-blue-500)
    - Clicking role card: saves role to Zustand userRole, calls POST /onboarding/role with { role, user_id: sessionId, repo: activeRepo }, dismisses overlay with 300ms fade-out transition (transition-opacity duration-300 opacity-100 to opacity-0)
    - Role selector overlay must appear within 100ms on page load when no role set (performance target from Appendix B)
    - _Requirements: 6.2, 6.3, 6.4, Appendix B_
    - _Properties: 30 (role selection and path generation), 40 (performance target compliance)_

  - [x] 7.3 Create data fetching hooks
    - Create `frontend/hooks/useOnboardingData.ts` using React Query
    - Fetch onboarding path for role: GET /onboarding/path?repo={activeRepo}&role={userRole}
    - Implement update progress mutation: POST /onboarding/progress with { stage_id, user_id, repo, completed_at: new Date().toISOString() }, use optimistic update via queryClient.setQueryData
    - Implement mark resource read mutation: POST /onboarding/progress/resource with { resource_id, user_id, repo }
    - _Requirements: 6.15_
    - _Properties: 24 (optimistic update with rollback)_

  - [x] 7.4 Create StageTrack component
    - Create `frontend/components/onboarding/StageTrack.tsx` displaying horizontal progress bar
    - Stages connected by two-layer line: full-width 2px muted gray background line (h-0.5 bg-gray-600 w-full), 2px green progress line (h-0.5 bg-green-500 absolute top-0 left-0) that fills from left to right based on proportion of completed stages (width: `${(completedStages / totalStages) * 100}%`), animated with CSS width transition (transition-all duration-500)
    - Each stage card: 200px wide 100px tall (w-[200px] h-[100px])
    - Three visual states:
      - Completed: green subtle background (bg-green-500/10), checkmark icon top-right (absolute top-2 right-2 CheckCircle text-green-500), stage title (text-sm font-semibold), "Completed" in green muted text (text-xs text-green-500), fully clickable
      - Current: white background with blue border (bg-white border-2 border-blue-500), pulsing blue dot top-right (absolute top-2 right-2 w-2 h-2 rounded-full bg-blue-500 animate-pulse, CSS @keyframes pulse scale 1 to 1.4 to 1 over 1.5s infinite), stage title, resource count (text-xs text-muted), estimated time in minutes (text-xs text-muted)
      - Future (locked): gray background at 50% opacity (bg-gray-700/50), lock icon top-right (absolute top-2 right-2 Lock text-gray-500), stage title visible, non-clickable (pointer-events-none), tooltip "Complete previous stages first" on hover (via shadcn Tooltip)
    - Active stage: downward arrow indicator connecting stage card to StageDetail section below (absolute -bottom-4 left-1/2 -translate-x-1/2 ChevronDown text-blue-500)
    - _Requirements: 6.5, 6.6, 6.7_
    - _Properties: 31 (stage visual state computation)_

  - [x] 7.5 Create StageDetail component
    - Create `frontend/components/onboarding/StageDetail.tsx` displaying four sections
    - Documentation Resources section: list each resource with colored source-type icon on left (File/Book/FileText from lucide-react colored by type), document title in bold (font-semibold) and source service as muted breadcrumb "{repo} / {service}" (text-xs text-muted), estimated read time "~{n} min read" (text-xs text-muted), read checkbox on right (shadcn Checkbox) that when checked calls POST /onboarding/progress/resource with resource_id and updates completion progress bar at bottom showing "{read_count} of {total} read" (text-sm text-muted), "Ask about this" button navigating to /qa with input pre-filled as "Explain {doc_title} and why it matters for a {userRole} on the {activeRepo} team"
    - Key Services section: 2-column grid (grid-cols-2 gap-4) of service cards, each showing service name in bold (font-semibold), one-line role description truncated with ellipsis (truncate), health score badge colored by Health_Color_Scale (px-2 py-0.5 rounded text-xs font-bold), "View in graph" button navigating to /graph with selectedNodeId set to that service via URL parameter (?selectedNodeId={service_id}), "Ask about this" button navigating to /qa with input pre-filled as "What does the {service_name} service do and how does it relate to my work as a {userRole}?"
    - Relevant ADRs section: list each ADR with ADR number badge (px-2 py-0.5 rounded bg-slate-700 text-xs font-mono), title (font-semibold), status badge (accepted/superseded/deprecated, colored green/amber/gray), affected services as chips (px-2 py-0.5 rounded-full bg-slate-700 text-xs), role-specific "Why this matters for you" explanation from API response (text-sm text-muted), expandable section (shadcn Collapsible) showing full decision summary and consequences, "Ask about this ADR" button navigating to /qa with input pre-filled as "Explain ADR-{number} and what I need to know about it as a {userRole}"
    - Starter Task section: single featured card with GitHub issue number and title as heading (text-lg font-semibold), issue labels as colored chips (px-2 py-0.5 rounded text-xs), complexity indicator (Good first issue=green bg-green-500, Medium=amber bg-amber-500, Complex=red bg-red-500), first 200 characters of issue description (line-clamp-3), skills involved as tags (px-2 py-0.5 rounded-full bg-slate-700 text-xs), "Open issue" button opening GitHub issue URL in new tab (target="_blank" rel="noopener noreferrer"), "Get context" button navigating to /qa with input pre-filled as "Give me full context on issue #{number} in {activeRepo}. What do I need to understand to work on this as a {userRole}? What services are involved?"
    - When no starter task available: display "No starter tasks assigned yet. Ask your manager to link issues to your learning path." (text-sm text-muted italic)
    - _Requirements: 6.8, 6.9, 6.10, 6.11_
    - _Properties: None_

  - [x] 7.6 Create TeammateMap component
    - Create `frontend/components/onboarding/TeammateMap.tsx` below StageDetail, always visible (not behind tab)
    - Fetch engineers relevant to current stage
    - Display 3-column grid (grid-cols-3 gap-4) of engineer cards
    - Each card: 56px avatar circle (w-14 h-14 rounded-full) with initials and hashed background color (use name.charCodeAt sum % 8 to select from palette), name in bold (font-semibold), role in muted text (text-sm text-muted), owned services as chips filtered to only those relevant to current stage (px-2 py-0.5 rounded-full bg-slate-700 text-xs), expertise tags as pills (px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-500 text-xs), "View in graph" link navigating to /graph with that engineer's EngineerNode selected (?selectedNodeId={engineer_id})
    - _Requirements: 6.12_
    - _Properties: None_

  - [x] 7.7 Implement stage completion
    - Add "Mark this stage complete" button at bottom of StageDetail, only visible for current active stage (not completed, not future)
    - Clicking button: displays shadcn AlertDialog with "Are you sure? This will unlock the next stage." and Confirm / Cancel buttons
    - When confirmed: optimistically update stage to completed state in React Query cache via queryClient.setQueryData before POST /onboarding/progress resolves, request payload { stage_id, user_id, repo, completed_at: new Date().toISOString() }, if request fails rollback optimistic update using onError callback
    - Animate completed stage card to completed visual state (bg-green-500/10 with checkmark) and next stage card to current visual state (bg-white border-blue-500 with pulsing dot), grow progress line width via CSS transition (transition-all duration-500)
    - If completed stage is final stage: fire canvas-confetti animation with count=200, spread=70, origin={ y: 0.6 }, then display completion card showing "You've completed the onboarding path for {activeRepo}!" (text-2xl font-bold), summary of stages completed and resources read (text-sm text-muted), "Start contributing" button navigating to /qa, "View your team's graph" button navigating to /graph
    - Stage completion optimistic update must appear within 100ms of confirmation (performance target from Appendix B)
    - Confetti animation must fire within 200ms of final stage completion (performance target from Appendix B)
    - _Requirements: 6.13, 6.14, 6.15, 6.16, Appendix B_
    - _Properties: 24 (optimistic update with rollback), 32 (stage completion with confetti), 40 (performance target compliance)_

  - [x] 7.8 Implement loading and error states
    - Create StageSkeleton component: five 200x100px rectangles (w-[200px] h-[100px] bg-slate-800 rounded animate-pulse) in progress track
    - Create role card skeletons: five cards matching card dimensions (h-32 bg-slate-800 rounded animate-pulse) in role selector
    - Create section skeletons in StageDetail: three resource row skeletons (h-12 bg-slate-800 rounded animate-pulse), four service card skeletons (h-24 bg-slate-800 rounded animate-pulse), three ADR row skeletons (h-16 bg-slate-800 rounded animate-pulse), one large task card skeleton (h-40 bg-slate-800 rounded animate-pulse)
    - Create EmptyOnboardingState component: "Select your role to begin" with graduation cap icon (GraduationCap from lucide-react), "Choose your role to generate a personalized onboarding path for this repository." guidance
    - Create ErrorState: "Could not load your learning path for {activeRepo}. Try selecting your role again." with retry button and "Change role" secondary button
    - _Requirements: 6.18, 6.19, 8.5, 8.6, 8.7_
    - _Properties: 37 (skeleton shape matching), 38 (error state with retry), 39 (empty state with guidance)_

  - [x] 7.9 Implement responsive design
    - Ensure layout works at 1280px minimum width (min-w-[1280px])
    - Role selector grid: 3 columns above 1400px (grid-cols-3), 2 columns above 1280px (grid-cols-2)
    - Adjust spacing and font sizes for different screen sizes
    - _Requirements: 6.20, 9.1, 9.2, 9.3_
    - _Properties: None_

- [x] 8. Final integration and testing
  - [x] 8.1 Verify TypeScript compilation
    - Run TypeScript compiler with no errors: `npx tsc --noEmit`
    - Ensure all types are properly defined in lib/types.ts
    - Verify no use of `any` type except where required by React Flow NodeProps and EdgeProps generics (immediately narrowed with type assertion)
    - _Requirements: 7.5, 7.6_
    - _Properties: None_

  - [x] 8.2 Verify API client integration
    - Ensure all API endpoints are properly integrated in lib/api.ts
    - Verify auth headers (Authorization from session token) and X-Repo-Scope header (from activeRepo) injection on all requests
    - Test API client error handling: ApiError class with status field, proper error messages
    - _Requirements: 8.3, 8.4_
    - _Properties: 9 (API header injection for all requests)_

  - [x] 8.3 Verify React Query cache management
    - Ensure mutations invalidate or update relevant cache keys: waiver request invalidates ["policy-runs"], stage completion updates ["onboarding-path"], alert dismiss invalidates ["health-alerts"]
    - Verify optimistic updates and rollback on error: waiver request, stage completion, resource read
    - Test activeRepo change triggers queryClient.invalidateQueries() with no arguments
    - _Requirements: 8.1, 8.2_
    - _Properties: 24 (optimistic update with rollback), 33 (React Query cache invalidation on repo change)_

  - [x] 8.4 Verify responsive design
    - Test all features at 1280px minimum width: ensure no overflow or clipping
    - Test below 1400px breakpoint: history sidebar overlays chat panel, graph detail panel reduces to 320px, health dashboard rows stack, policy status stacks, blueprint list reduces to 280px
    - Verify all text remains readable: minimum font size 11px, no text overflow clipping except where truncation with ellipsis is specified
    - _Requirements: 9.1, 9.2, 9.3_
    - _Properties: None_

  - [x] 8.5 Verify loading and error states
    - Ensure all features display skeleton loading states matching real content dimensions to within 10px
    - Ensure all features display error states with message derived from API response error body when available, or context-specific fallback message, plus retry button calling refetch()
    - Ensure all features display empty states with meaningful message explaining why no data exists and suggested next action
    - Verify no spinner components appear anywhere in application
    - _Requirements: 8.5, 8.6, 8.7_
    - _Properties: 37 (skeleton shape matching), 38 (error state with retry), 39 (empty state with guidance)_

  - [x] 8.6 Verify real-time updates
    - Test SSE connections for health dashboard (GET /reporting/stream) and policy status (GET /policy/stream)
    - Verify connection status indicators: "Live updates paused" pill appears if disconnected for >5 seconds
    - Test auto-reconnect: exponential backoff (2s, 4s, 8s, 16s, capped at 30s), max 10 attempts, status "failed" after max attempts
    - Verify SSE events reflected in UI within 500ms: health_update, alert, activity, policy_run
    - _Requirements: 10.1, 10.2, 10.3, 10.4, Appendix C_
    - _Properties: 19 (SSE live update cache integration), 20 (SSE reconnection with exponential backoff)_

  - [x] 8.7 Verify chart visualizations
    - Test all Recharts components: MetricCard sparklines (60x24px LineChart no axes), health score AreaChart (280px height, Health_Color_Scale stroke, gradient fill, reference lines y=80 and y=50, ReferenceArea for score drops >15 points), coverage HorizontalBarChart (sorted ascending, Health_Color_Scale bars, onClick navigation)
    - Test custom SVG heatmap: 53x7 grid, 12x12px cells with 3px gap, five-stop color scale, hover tooltip, click navigation
    - Verify tooltips display exact data values with appropriate formatting
    - Verify click interactions navigate to relevant filtered views: coverage bar → /graph?selectedNodeId={service_id}, heatmap cell → /policy?date={date}
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7_
    - _Properties: 16 (health score color interpolation), 17 (coverage bar color thresholds), 18 (heatmap cell color scale), 35 (chart tooltip display on hover), 36 (chart click navigation with query params)_

  - [x] 8.8 Verify graph interactions
    - Test React Flow interactions: node click opens detail panel within 300ms, node double-click calls fitView (padding=0.3, duration=600ms) and fetches neighbors, node hover sets non-connected opacity to 0.15/0.1
    - Test layout algorithms: Force (d3-force, 300 ticks, linkDistance=150, chargeStrength=-400), Tree (dagre, direction="LR"), Radial (equal angles, radius=(nodeCount*30) clamped 200-600px)
    - Test layout switching: 600ms animated position transitions via requestAnimationFrame interpolation
    - Test filtering and search: node type toggles hide nodes, health slider filters by score, search debounced 200ms highlights matching nodes with 2px blue ring
    - Verify initial graph render with up to 200 nodes completes within 2 seconds
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, Appendix B_
    - _Properties: 10 (node type to component mapping), 11 (edge type to style mapping), 12 (node click opens detail panel), 13 (node double-click expansion), 14 (node hover opacity adjustment), 15 (node type filter visibility), 34 (layout algorithm determinism)_

  - [x] 8.9 Verify code viewing
    - Test Monaco Editor integration: theme="vs-dark", readOnly=true, language auto-detected from extension (yaml/yml=yaml, Dockerfile=dockerfile, .proto=proto, .json=json, .ts=typescript, .py=python, .go=go, default=plaintext)
    - Verify syntax highlighting for different file types
    - Test file tree navigation: clicking file loads content within 500ms
    - Test download functionality: "Download all artifacts" button generates zip with JSZip, downloads as {blueprint-name}-artifacts.zip, download begins within 2 seconds
    - _Requirements: 12.1, 12.2, 12.3, 12.4, Appendix B_
    - _Properties: 28 (file tree to Monaco editor navigation), 40 (performance target compliance)_

  - [x] 8.10 Verify streaming chat responses
    - Test SSE token streaming: POST /adapters/web/ask with ReadableStream, TextDecoder reads chunks, buffer incomplete lines across chunks, parse complete lines beginning with "data: " as JSON
    - Verify token events append to message content using useRef to avoid stale closures
    - Verify metadata event finalizes message with all fields (intent, confidence, citations, chain_steps, source_breakdown, follow_ups), hides cursor, renders all post-stream layers
    - Test stop button: calls reader.cancel(), marks message as complete with streamed content so far
    - Verify first token appears within 500ms of sending request
    - Test stream closes without metadata: displays "Response was incomplete. The service may be under load." with retry button
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, Appendix B_
    - _Properties: 2 (SSE token streaming with buffer), 3 (SSE metadata completion), 6 (conditional button states), 40 (performance target compliance)_

  - [x] 8.11 Verify all performance targets from Appendix B
    - Q&A Interface: first streaming token < 500ms, history sidebar open/close < 300ms, suggestion card click to message send < 100ms
    - Knowledge Graph: initial graph render (up to 200 nodes) < 2 seconds, node click to detail panel open < 300ms, layout switch animation < 600ms, neighbor fetch and expansion < 1 second
    - Health Dashboard: all four metric cards render < 1 second, health score chart animate in < 1 second, activity feed first 20 items < 1 second, SSE events reflected < 500ms
    - Policy Status: policy run list first 25 items < 1 second, new SSE policy run entries animate < 300ms, waiver modal open < 200ms
    - Blueprint Viewer: Design tab diagram render < 1.5 seconds, Monaco Editor display file content < 500ms, artifact zip download begin < 2 seconds
    - Onboarding Paths: role selector overlay appear < 100ms, stage completion optimistic update < 100ms, confetti animation fire < 200ms
    - _Requirements: Appendix B (all performance targets)_
    - _Properties: 40 (performance target compliance)_

  - [x] 8.12 Checkpoint - Ensure all features are functional
    - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Each task references correctness properties from the design document for validation
- Checkpoints ensure incremental validation
- All features follow consistent patterns for data fetching, loading states, and error handling
- TypeScript type safety is enforced throughout
- React Query is used for all server state management
- Zustand is used only for global client state (session, UI preferences)
- All features are fully responsive down to 1280px minimum width
- All specifications include exact pixel dimensions, animation timings, and performance targets
- No spinner components are permitted - only skeleton loading states that match real content dimensions
