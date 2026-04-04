# Design Document: Frontend Six Feature Transformation

## Overview

This design specifies the technical implementation of six production-quality frontend features for the KA-CHOW engineering brain platform. The features transform the existing Next.js 14 application into a comprehensive system for Q&A chat, knowledge graph visualization, system health monitoring, CI/CD policy status, architecture blueprint viewing, and onboarding learning paths.

The design builds upon the existing global shell infrastructure (layout, sidebar, auth, Zustand store, API client, command palette, notification system) and establishes consistent patterns for data fetching, loading states, error handling, and responsive design across all features.

All API endpoints conform to the API Contract defined in Appendix A of the requirements document. All performance targets are defined in Appendix B. All SSE behavior including reconnection logic is defined in Appendix C.

### Design Goals

1. **Consistency**: Establish uniform patterns for data fetching, state management, loading states, and error handling
2. **Performance**: Meet specific performance targets (first token < 500ms, graph render < 2s, SSE events reflected < 500ms)
3. **Real-time**: Implement SSE streaming for chat responses and live updates with automatic reconnection
4. **Interactivity**: Provide rich interactions with exact pixel dimensions and animation timings
5. **Maintainability**: Use TypeScript for type safety, modular components, and clear separation of concerns
6. **No Spinners**: Use skeleton loading states that match real content dimensions - no spinner components anywhere

### Technology Stack

- **Framework**: Next.js 14 with App Router
- **Language**: TypeScript 5.x
- **Styling**: Tailwind CSS 3.x with custom design tokens
- **UI Components**: shadcn/ui (Button, Input, Select, Dialog, Tabs, Tooltip, Badge, Skeleton, AlertDialog)
- **Server State**: React Query v5 (TanStack Query)
- **Client State**: Zustand (session store only - activeRepo, sessionId, userId, userRole, commandPaletteOpen, sidebarCollapsed, activeNotifications)
- **Graph Rendering**: React Flow (knowledge graph, architecture diagrams)
- **Graph Layouts**: d3-force (Force layout), dagre (@dagrejs/dagre) (Tree layout)
- **Charts**: Recharts (health metrics, coverage, trends)
- **Code Editor**: Monaco Editor (architecture artifacts, read-only mode)
- **Command Palette**: cmdk
- **Icons**: Lucide React
- **Property-Based Testing**: fast-check (minimum 100 iterations per test)
- **File Downloads**: JSZip, file-saver (artifact downloads)
- **Confetti**: canvas-confetti (onboarding completion)
- **Markdown**: react-markdown with react-syntax-highlighter (oneDark theme)
- **Diff Viewer**: react-diff-viewer-continued (patch display)

## Architecture

### High-Level Component Hierarchy

```
App Layout (existing)
├── Sidebar (existing)
├── CommandPalette (existing)
└── Feature Routes
    ├── /qa - Q&A Chat Interface
    │   ├── ChatPage
    │   ├── HistorySidebar
    │   ├── MessageThread
    │   ├── ChatInput
    │   └── EmptyState
    ├── /graph - Knowledge Graph Visualizer
    │   ├── GraphPage
    │   ├── GraphCanvas (React Flow)
    │   ├── FilterPanel
    │   ├── NodeDetailPanel
    │   └── Custom Node Components
    ├── /health - System Health Dashboard
    │   ├── HealthPage
    │   ├── MetricCards
    │   ├── HealthScoreChart
    │   ├── CoverageChart
    │   ├── GapHeatmap
    │   ├── AlertsPanel
    │   └── ActivityFeed
    ├── /policy - CI/CD Policy Status
    │   ├── PolicyPage
    │   ├── PolicyRunList
    │   ├── PolicyDetailPanel
    │   ├── WaiverModal
    │   └── WaiverManagement
    ├── /blueprints - Architecture Blueprint Viewer
    │   ├── BlueprintPage
    │   ├── BlueprintList
    │   ├── BlueprintDetailPanel
    │   │   ├── DesignTab (React Flow)
    │   │   ├── RationaleTab
    │   │   └── ArtifactsTab (Monaco Editor)
    │   └── AlignmentBanner
    └── /onboarding - Onboarding Learning Paths
        ├── OnboardingPage
        ├── RoleSelector
        ├── StageTrack
        ├── StageDetail
        └── TeammateMap
```

### Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      User Interaction                        │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    React Component                           │
│  - Triggers action (button click, form submit, etc.)        │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                  React Query Hook                            │
│  - useQuery (GET requests, caching)                          │
│  - useMutation (POST/PUT/DELETE, optimistic updates)        │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    API Client (lib/api.ts)                   │
│  - Injects auth headers from Zustand session store          │
│  - Injects X-Repo-Scope header from activeRepo              │
│  - Handles HTTP errors, throws ApiError                     │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              Backend API (localhost:8004)                    │
│  - Validates auth headers                                    │
│  - Processes request                                         │
│  - Returns JSON response or SSE stream                       │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                  React Query Cache                           │
│  - Stores response data                                      │
│  - Provides isLoading, isError, data states                 │
│  - Triggers re-render with new data                          │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    React Component                           │
│  - Renders UI based on query state                           │
│  - Shows skeleton loading, error state, or data              │
└─────────────────────────────────────────────────────────────┘
```

### State Management Strategy

**Server State (React Query)**:
- All API data (chat messages, graph nodes, health metrics, policy runs, blueprints, onboarding paths)
- Automatic caching with configurable staleTime
- Background refetching
- Optimistic updates for mutations
- Query invalidation on related mutations

**Client State (Zustand)**:
- Session data (user, activeRepo, adminToken, authHeaders)
- Global UI preferences (theme, sidebar collapsed state)
- NOT used for feature-specific UI state (use React useState/useReducer)

**Local Component State (React useState/useReducer)**:
- UI-specific state (selected node, filter values, modal open/closed)
- Form input values
- Transient UI state (hover, focus, animation triggers)

### Authentication and Authorization

All API calls include authentication headers from the Zustand session store:

```typescript
// From store/session.ts
authHeaders(): Record<string, string> {
  const { user, adminToken, activeRepo } = get();
  const headers: Record<string, string> = {};
  
  if (adminToken) {
    headers["X-Admin-Token"] = adminToken;
  } else if (user) {
    headers["X-Auth-Subject"] = user.subject;
    headers["X-Auth-Role"] = user.role;
    headers["X-Auth-Tenant-Id"] = user.tenant_id;
    headers["X-Auth-Repo-Scope"] = user.repo_scope.join(",");
  }
  
  if (activeRepo) {
    headers["X-Repo-Scope"] = activeRepo;
  }
  
  return headers;
}
```

The API client automatically injects these headers on every request.

## Components and Interfaces

### 1. Q&A Chat Interface (/qa)

#### Component Structure

```
ChatPage (full viewport height layout)
├── Header (repo scope, new chat, history toggle)
├── HistorySidebar (320px, closed by default, 300ms translateX transition)
│   ├── "New conversation" button
│   └── Grouped sessions (Today, Yesterday, This Week, Older)
├── MessageThread (scrollable message list, auto-scroll unless user scrolled >100px up)
│   ├── UserMessage (right-aligned rounded bubble, plain text, relative timestamp)
│   └── AssistantMessage (left-aligned, 7 layers in order)
│       ├── Layer 1: IntentBadge (monospace 11px pill, colored by top-level intent)
│       ├── Layer 2: MarkdownContent (react-markdown, oneDark syntax highlighting, blinking cursor during streaming)
│       ├── Layer 3: ConfidenceBar (4px tall, Health_Color_Scale, tooltip with exact %)
│       ├── Layer 4: SourceBreakdown (horizontal pills: "{count} from {source_type}")
│       ├── Layer 5: CitationsPanel (collapsed by default, max-height 200px, internal scroll)
│       ├── Layer 6: ChainOfThoughtSteps (collapsed by default, "Reasoning" toggle)
│       └── Layer 7: FollowUpSuggestions (horizontal scroll, max-width 280px per chip)
├── ChatInput (auto-resizing textarea, 1-6 rows, hidden div mirror technique)
│   ├── Channel mode pill (Web/CLI Preview, cycles on click)
│   └── Send button (disabled when empty or streaming) / Stop button (during streaming)
└── EmptyState (when messages.length === 0)
    ├── KA-CHOW logo
    ├── Heading: "Ask anything about your codebase"
    ├── Subheading: "I have full context of your services, APIs, policies, and architecture decisions"
    └── 2x4 grid of suggestion cards (grouped by intent, colored left borders)
```

#### Exact Specifications

**History Sidebar**:
- Width: 320px
- Default state: closed
- Transition: 300ms CSS translateX
- Below 1400px: overlays chat panel instead of pushing it

**Empty State Suggestion Cards** (8 cards total):
- Architecture (blue left border): "What does the payments service do?", "What services depend on the auth service?"
- Policy (amber left border): "Which PRs are currently blocked by policy?", "Show me active waivers for this repo"
- Onboarding (green left border): "What should I understand first as a new backend engineer?", "Who owns the notification service?"
- Impact (red left border): "What breaks if I deprecate the /v1/users endpoint?", "What's affected if I change the user_id field type?"

**Intent Badge Colors**:
- architecture = blue
- policy = amber
- impact = red
- onboarding = green
- general = gray

**Streaming Cursor**:
- Width: 2px
- Height: 1em
- Animation: opacity 0 to 1 every 500ms (CSS animation)
- Appears at end of streamed text
- Disappears when metadata event received

**Confidence Bar**:
- Height: 4px
- Color: Health_Color_Scale applied to confidence score (0-100)
- Tooltip: exact percentage on hover
- Only appears after streaming completes

**Source Breakdown Pills**:
- Display names: code="Code" (purple tint), docs="Docs" (blue tint), adrs="ADRs" (amber tint), incidents="Incidents" (red tint), specs="API Specs" (green tint)
- Format: "{count} from {source_type}"
- Only appears after streaming completes

**Citations Panel**:
- Collapsed by default: "{n} citations" toggle button
- When expanded: max-height 200px with internal scroll
- Each citation: source_ref (monospace, last 40 chars, "..." prefix if longer), line number badge "L{line}", two-line excerpt in left-bordered blockquote, clipboard copy button
- Only appears after streaming completes

**Chain Steps**:
- Collapsed by default: "Reasoning" toggle button
- Each step: name in bold, input truncated to 60 chars, output truncated to 60 chars, duration in ms (muted, right-aligned)
- Only appears after streaming completes

**Follow-up Chips**:
- Horizontal scroll (overflow-x auto, scrollbar hidden)
- Max-width per chip: 280px
- Text truncated with ellipsis
- Clicking calls handleSend with chip's question text
- Only appears after streaming completes

**Auto-resizing Textarea**:
- Min rows: 1
- Max rows: 6
- Implementation: hidden div mirror technique
- Focus on Cmd+/ (or Ctrl+/ on Windows) via document keydown listener

**Auto-scroll Behavior**:
- Auto-scroll to bottom when new content arrives
- UNLESS user manually scrolled >100px above bottom
- Detection: compare scrollTop + clientHeight to scrollHeight

**Performance Targets** (from Appendix B):
- First streaming token: < 500ms
- History sidebar open/close: < 300ms
- Suggestion card click to message send: < 100ms

#### Key Interactions

1. **Sending a message**: User types in ChatInput, presses Enter (not Shift+Enter) or clicks Send button
2. **Streaming response**: Fetch API with ReadableStream parses SSE events using TextDecoder, buffering incomplete lines across chunks
3. **Token events** (type="token"): Append event.text to current assistant message using useRef to avoid stale closures
4. **Metadata event** (type="metadata"): Complete message with intent, confidence, citations, chain_steps, source_breakdown, follow_ups; mark streaming complete; hide cursor; render all post-stream layers
5. **Stream closes without metadata**: Mark message as error state, display "Response was incomplete. The service may be under load." with retry button
6. **Stop button**: Calls reader.cancel() on active stream reader to abort request
7. **Follow-up click**: Sends follow-up question as new message via handleSend
8. **Suggestion card click**: Immediately calls handleSend with card's question text
9. **History navigation**: Fetches GET /assistant/sessions/{id}/messages, loads into thread
10. **Session deletion**: Calls DELETE /assistant/sessions/{id}, removes from list with 200ms fade-out animation
11. **New conversation**: Clears thread, generates new session ID in Zustand
12. **Channel mode toggle**: Cycles between "Web" (markdown) and "CLI Preview" (monospace plain text), sent as channel field in next request
13. **Keyboard shortcut**: Cmd+/ (Ctrl+/ on Windows) focuses textarea from anywhere on page

#### Data Fetching

```typescript
// Custom hook for streaming chat
function useStreamingChat() {
  const { activeRepo, authHeaders } = useSession();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const contentRef = useRef(""); // Avoid stale closures
  
  const sendMessage = async (text: string, channel: "web" | "cli" = "web") => {
    // Add user message
    const userMsg: ChatMessage = { 
      id: generateId(), 
      role: "user", 
      content: text,
      timestamp: new Date().toISOString()
    };
    setMessages(prev => [...prev, userMsg]);
    
    // Add streaming assistant message
    const assistantMsgId = generateId();
    const assistantMsg: ChatMessage = { 
      id: assistantMsgId, 
      role: "assistant", 
      content: "", 
      streaming: true 
    };
    setMessages(prev => [...prev, assistantMsg]);
    setIsStreaming(true);
    contentRef.current = "";
    
    try {
      const response = await fetch(`${BACKEND}/adapters/web/ask`, {
        method: "POST",
        headers: { 
          "Content-Type": "application/json", 
          ...authHeaders() 
        },
        body: JSON.stringify({ 
          question: text, 
          repo: activeRepo, 
          channel,
          history: messages.slice(-6) // Last 6 messages for context
        }),
      });
      
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let buffer = ""; // Buffer for incomplete lines
      
      while (true) {
        const { done, value } = await reader!.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        
        // Keep last incomplete line in buffer
        buffer = lines.pop() || "";
        
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6));
              
              if (data.type === "token") {
                // Append token using ref to avoid stale closure
                contentRef.current += data.text;
                setMessages(prev => prev.map(m => 
                  m.id === assistantMsgId 
                    ? { ...m, content: contentRef.current } 
                    : m
                ));
              } else if (data.type === "metadata") {
                // Finalize message with all metadata
                setMessages(prev => prev.map(m => 
                  m.id === assistantMsgId 
                    ? { 
                        ...m, 
                        streaming: false,
                        intent: data.intent,
                        sub_intent: data.sub_intent,
                        confidence: data.confidence,
                        citations: data.citations,
                        source_breakdown: data.source_breakdown,
                        chain_steps: data.chain_steps,
                        follow_up_suggestions: data.follow_up_suggestions,
                      } 
                    : m
                ));
              }
            } catch (parseError) {
              console.error("Failed to parse SSE event:", parseError);
            }
          }
        }
      }
    } catch (error) {
      // Mark message as error
      setMessages(prev => prev.map(m => 
        m.id === assistantMsgId 
          ? { 
              ...m, 
              streaming: false,
              content: contentRef.current || "Response was incomplete. The service may be under load.",
              error: true
            } 
          : m
      ));
    } finally {
      setIsStreaming(false);
    }
  };
  
  return { messages, isStreaming, sendMessage };
}

// Fetch conversation history
const { data: sessions } = useQuery({
  queryKey: ["assistant-sessions", activeRepo],
  queryFn: () => fetch(`${BACKEND}/assistant/sessions?repo=${activeRepo}`, {
    headers: authHeaders()
  }).then(r => r.json()),
  enabled: !!activeRepo,
});

// Fetch session messages
const { data: sessionMessages } = useQuery({
  queryKey: ["assistant-session-messages", selectedSessionId],
  queryFn: () => fetch(`${BACKEND}/assistant/sessions/${selectedSessionId}/messages`, {
    headers: authHeaders()
  }).then(r => r.json()),
  enabled: !!selectedSessionId,
});

// Delete session mutation
const deleteSessionMutation = useMutation({
  mutationFn: (sessionId: string) => 
    fetch(`${BACKEND}/assistant/sessions/${sessionId}`, {
      method: "DELETE",
      headers: authHeaders()
    }),
  onSuccess: () => {
    queryClient.invalidateQueries(["assistant-sessions"]);
  },
});
```

#### API Endpoints (from Appendix A)

- `POST /adapters/web/ask` - Request: QARequest; Response: SSE stream of token events and final metadata event
- `GET /assistant/sessions?repo={repo}` - Response: Session[]
- `GET /assistant/sessions/{id}/messages` - Response: Message[]
- `DELETE /assistant/sessions/{id}` - Response: 204 No Content

### 2. Knowledge Graph Visualizer (/graph)

#### Component Structure

```
GraphPage (full-screen React Flow canvas)
├── Control Panel (absolutely positioned top-right: top 16px, right 16px)
│   ├── Node type toggles (6 icon+label buttons)
│   ├── Health filter range slider (0-100, default=0)
│   ├── "Unhealthy only" button (sets slider to 60)
│   ├── Search text input (debounced 200ms, clear button)
│   ├── Layout mode buttons (Force, Tree, Radial)
│   └── Minimap toggle button
├── GraphCanvas (React Flow with ReactFlowProvider)
│   ├── ServiceNode (180x72px rounded rect, health-colored, pulse animation if health<40)
│   ├── APINode (pill shape 28px height, method-colored left section)
│   ├── SchemaNode (80x80px rotated 45deg diamond)
│   ├── ADRNode (100x64px rect with folded corner)
│   ├── EngineerNode (52px diameter circle, hashed color, initials)
│   ├── IncidentNode (60x52px warning triangle, clip-path polygon)
│   ├── DependencyEdge (solid 1.5px #6b7280)
│   ├── OwnershipEdge (dashed 1.5px #3b82f6, stroke-dasharray 6 3)
│   └── CausalityEdge (dotted 1.5px #f59e0b, stroke-dasharray 2 2, arrows both ends)
└── NodeDetailPanel (absolutely positioned top-right: top 0, right 0, height 100%)
    ├── 300ms translateX transition (from translateX(100%))
    ├── ServiceNode detail (health score, mini progress bars, dependencies, ADRs, incidents)
    ├── APINode detail (method badge, path, parameters table, response codes)
    ├── ADRNode detail (number, title, status, summary, consequences, affected services)
    └── EngineerNode detail (avatar, role, owned services, expertise tags, activity)
```

#### Exact Specifications

**Control Panel Position**:
- Position: absolute
- Top: 16px
- Right: 16px

**Detail Panel**:
- Position: absolute
- Top: 0
- Right: 0
- Height: 100%
- Width: 400px (reduces to 320px below 1400px)
- Transition: 300ms translateX
- Opens: translateX(0)
- Closed: translateX(100%)
- Close triggers: X button click, Escape key press, clicking same node again

**ServiceNode**:
- Dimensions: 180x72px
- Border-radius: 8px (rx=8)
- Background: Health_Color_Scale applied to health_score
- Service name: 13px bold white
- Owner name: 11px white at 70% opacity
- Health score badge: 22px, top-right corner, white background, colored text matching node background
- Pulse animation when health_score < 40: box-shadow from none to "0 0 0 6px {nodeColor}40" over 2s infinite ease-in-out

**APINode**:
- Shape: pill (height 28px, border-radius 14px)
- Min-width: 100px
- Max-width: 160px
- Left section colors: GET=#3b82f6, POST=#22c55e, PUT=#f59e0b, DELETE=#ef4444, PATCH=#a855f7
- Method text: 9px bold white
- Path text: 11px monospace

**SchemaNode**:
- Dimensions: 80x80px
- Container: CSS transform rotate(45deg)
- Content wrapper: CSS transform rotate(-45deg) (keeps text readable)
- Label: 11px centered

**ADRNode**:
- Dimensions: 100x64px
- Folded corner: CSS ::before pseudo-element (12x12px triangle, positioned absolute top-right)
- ADR number: bold
- Title: truncated to 20 characters

**EngineerNode**:
- Diameter: 52px circle
- Background: deterministically selected from 8 predefined colors using hash of engineer name
- Initials: first letter of first and last name, 16px bold white
- Border: 2px white

**IncidentNode**:
- Dimensions: 60x52px
- Shape: warning triangle via CSS clip-path: polygon(50% 0%, 0% 100%, 100% 100%)
- Background: #ef4444 (critical severity), #f59e0b (warning severity)
- Icon: white exclamation mark centered

**Edge Styles**:
- DependencyEdge: solid 1.5px #6b7280, arrow marker at target
- OwnershipEdge: stroke-dasharray(6 3) 1.5px #3b82f6, no arrows
- CausalityEdge: stroke-dasharray(2 2) 1.5px #f59e0b, arrow markers at both ends

**Node Interactions**:
- Click: sets selectedNodeId, opens detail panel
- Double-click: calls fitView (padding=0.3, duration=600ms), fetches GET /graph/neighbors/{node_id}?depth=1, adds nodes/edges with hidden-to-visible animation
- Hover: sets opacity of non-connected nodes to 0.15, non-connected edges to 0.1; resets to 1 on hover end

**Filter Behaviors**:
- Node type toggles: sets corresponding node type to hidden in React Flow state
- Health slider: hides nodes with health_score below slider value (nodes without health_score unaffected)
- "Unhealthy only": sets slider to 60, shows only nodes with health_score < 60
- Search (debounced 200ms): sets opacity of non-matching nodes to 0.1, applies 2px blue highlight ring to matching nodes

**Layout Algorithms**:
- **Force_Layout**: d3-force with linkDistance=150, chargeStrength=-400, 300 synchronous ticks before first render
- **Tree_Layout**: d3-hierarchy left-to-right hierarchical arrangement, roots = nodes with no incoming edges
- **Radial_Layout**: equal angles around center, radius = (nodeCount * 30) clamped to 200-600px
- Layout switching: 600ms animated position transitions via requestAnimationFrame interpolation

**Performance Targets** (from Appendix B):
- Initial graph render (up to 200 nodes): < 2 seconds
- Node click to detail panel open: < 300ms
- Layout switch animation: < 600ms
- Neighbor fetch and expansion: < 1 second

#### Key Interactions

1. **Node click**: Opens detail panel with node-specific content based on node type
2. **Node double-click**: Calls React Flow fitView (padding=0.3, duration=600ms) centered on node, then fetches neighbors and adds to graph
3. **Node hover**: Highlights connected nodes/edges by setting opacity of non-connected to 0.15/0.1
4. **Filter toggle**: Shows/hides node types without removing from data array
5. **Health slider**: Filters nodes by health score (nodes without health_score unaffected)
6. **Search**: Highlights matching nodes with 2px blue ring, dims non-matching to 0.1 opacity
7. **Layout mode switch**: Animates all nodes from current to new positions over 600ms
8. **Minimap toggle**: Shows/hides React Flow MiniMap at bottom-left
9. **Detail panel close**: X button or Escape key
10. **Service detail "Ask about this"**: Navigates to /qa with pre-filled question "What does the {service_name} service do?"
11. **Service detail "View health history"**: Opens Recharts LineChart popover showing 30-day health_score trend
12. **Dependency/Used by chips**: Selects target node in graph
13. **API detail parent service chip**: Selects parent ServiceNode

#### Data Fetching

```typescript
// Fetch graph data (nodes and edges in parallel)
const { data, isLoading, error } = useQuery({
  queryKey: ["graph-data", activeRepo],
  queryFn: async () => {
    const [nodesRes, edgesRes] = await Promise.all([
      fetch(`${BACKEND}/graph/nodes?repo=${activeRepo}`, { headers: authHeaders() }),
      fetch(`${BACKEND}/graph/edges?repo=${activeRepo}`, { headers: authHeaders() })
    ]);
    const nodes = await nodesRes.json();
    const edges = await edgesRes.json();
    return { nodes, edges };
  },
  enabled: !!activeRepo,
  staleTime: 30000,
});

// Compute initial layout before first render
const layoutedNodes = useMemo(() => {
  if (!data?.nodes) return [];
  return computeForceLayout(data.nodes, data.edges);
}, [data]);

// Fetch node neighbors on double-click
const expandNodeMutation = useMutation({
  mutationFn: (nodeId: string) => 
    fetch(`${BACKEND}/graph/neighbors/${nodeId}?depth=1`, {
      headers: authHeaders()
    }).then(r => r.json()),
  onSuccess: (neighbors) => {
    // Add neighbors to graph with hidden-to-visible animation
    setNodes(prev => [...prev, ...neighbors.nodes.map(n => ({ ...n, hidden: true }))]);
    setEdges(prev => [...prev, ...neighbors.edges]);
    // Trigger animation
    setTimeout(() => {
      setNodes(prev => prev.map(n => ({ ...n, hidden: false })));
    }, 50);
  },
});
```

#### Layout Algorithms

**Force Layout** (d3-force, 300 ticks before render):
```typescript
import { forceSimulation, forceLink, forceManyBody, forceCenter } from "d3-force";

function computeForceLayout(nodes, edges) {
  const simulation = forceSimulation(nodes)
    .force("link", forceLink(edges).id(d => d.id).distance(150))
    .force("charge", forceManyBody().strength(-400))
    .force("center", forceCenter(500, 400))
    .tick(300); // 300 synchronous ticks
  
  return nodes.map(n => ({ ...n, position: { x: n.x, y: n.y } }));
}
```

**Tree Layout** (d3-hierarchy, left-to-right):
```typescript
import { hierarchy, tree } from "d3-hierarchy";

function computeTreeLayout(nodes, edges) {
  // Identify roots (nodes with no incoming edges)
  const incomingEdges = new Set(edges.map(e => e.target));
  const roots = nodes.filter(n => !incomingEdges.has(n.id));
  
  // Build hierarchy from roots
  const treeLayout = tree().size([800, 600]).separation(() => 1);
  const root = hierarchy({ id: "root", children: roots });
  treeLayout(root);
  
  return nodes.map(n => {
    const treeNode = root.descendants().find(d => d.data.id === n.id);
    return { ...n, position: { x: treeNode.y, y: treeNode.x } };
  });
}
```

**Radial Layout** (circular arrangement):
```typescript
function computeRadialLayout(nodes) {
  const radius = Math.max(200, Math.min(600, nodes.length * 30));
  return nodes.map((n, i) => ({
    ...n,
    position: {
      x: 500 + radius * Math.cos((2 * Math.PI * i) / nodes.length),
      y: 400 + radius * Math.sin((2 * Math.PI * i) / nodes.length),
    },
  }));
}
```

#### API Endpoints (from Appendix A)

- `GET /graph/nodes?repo={repo}` - Response: GraphNode[]
- `GET /graph/edges?repo={repo}` - Response: GraphEdge[]
- `GET /graph/neighbors/{node_id}?depth={depth}` - Response: { nodes: GraphNode[], edges: GraphEdge[] }

### 3. System Health Dashboard (/health)

#### Component Structure

```
HealthPage (CSS Grid layout)
├── Row 1: MetricCards (grid-template-columns: repeat(4, 1fr), gap 16px)
│   ├── Knowledge Health Score (latest score, trend vs 7 days, Health_Color_Scale accent, 60x24px sparkline)
│   ├── Services Coverage ("{documented} / {total} documented", trend %, sparkline)
│   ├── Documentation Gaps (open count, trend, red if >10/amber if 5-10/green if <5, "View gaps" link)
│   └── CI Pass Rate (pass %, 60x24px Recharts LineChart sparkline, no axes)
├── Row 2: (grid-template-columns: 3fr 2fr, gap 16px)
│   ├── HealthScoreChart (Recharts AreaChart, width 100%, height 280px, 30-day data)
│   │   ├── Area with Health_Color_Scale stroke, linearGradient fill
│   │   ├── ReferenceLine y=80 (amber, "Target"), y=50 (red, "Warning")
│   │   └── ReferenceArea for 7-day windows with score drop >15 points (red fill 15% opacity)
│   └── AlertsPanel (severity-sorted: critical/warning/info, dismissible)
│       ├── Critical alerts: pulsing red left border (3px solid #ef4444 to #ef444440 over 1.5s infinite)
│       ├── Each alert: severity badge, message with bold entity name, clickable entity link, relative time, dismiss button
│       └── Empty state: "All clear — no active alerts for {activeRepo}" with green checkmark
├── Row 3: (grid-template-columns: 1fr 1fr, gap 16px)
│   ├── CoverageChart (Recharts BarChart layout="vertical", height=(serviceCount*32) clamped 200-500px)
│   │   ├── Sorted by coverage ascending (worst at top)
│   │   ├── Bar colors: green >=80, yellow >=50, red <50
│   │   ├── Top 15 services by default, "Show all {n} services" button
│   │   └── onClick: navigate to /graph with service selected
│   └── GapHeatmap (custom SVG, 53 columns x 7 rows)
│       ├── Cell: 12x12px rect, 3px gap
│       ├── Color scale: 0 gaps=#ebedf0 (light)/#161b22 (dark), 1-2=#9be9a8/#0e4429, 3-5=#40c463/#006d32, 6-10=#30a14e/#26a641, 11+=#216e39/#39d353
│       ├── Month labels above first column of each month
│       ├── Day labels "M", "W", "F" left of rows 1, 3, 5
│       ├── Hover tooltip: "{n} gaps on {date formatted as 'January 15, 2025'}"
│       └── Click: navigate to /policy filtered to that date
└── Row 4: ActivityFeed (grid-template-columns: 1fr)
    ├── useInfiniteQuery with @tanstack/react-virtual (container height 400px, dynamic row height 56px collapsed/120px expanded)
    ├── IntersectionObserver sentinel triggers fetchNextPage
    ├── Each row: 32x32px icon circle (colored by event type), description with bold entity, repo badge, relative time, chevron
    ├── Expanded: full event payload as syntax-colored JSON in monospace block, 200ms max-height transition
    └── Event type colors: doc_refresh_completed=green checkmark, doc_rewrite_generated=blue sparkle, ci_check_run=gray CI, waiver_granted=amber shield, health_score_changed=colored trend arrow, policy_blocked=red X, doc_gap_detected=orange warning
```

#### Exact Specifications

**MetricCard** (each of 4 cards):
- 3px colored left border
- Primary value: 48px font-weight-700
- Label: 14px muted text
- Trend indicator: up/down arrow icon, percentage text "+{n}% vs last week", green if positive trend, red if negative
- Sparkline: 60x24px inline Recharts LineChart, no axes

**Health Score Chart** (Recharts AreaChart):
- Width: 100%
- Height: 280px
- XAxis: dataKey="date", format "Jan 15", tickLine=false, axisLine=false
- YAxis: domain=[0,100], ticks=[0,25,50,75,100], tickLine=false, axisLine=false
- CartesianGrid: horizontal lines only, strokeDasharray="3 3"
- Area: strokeWidth=2, dot=false, activeDot radius=4, animationDuration=1000, animationEasing="ease-out"
- Fill: linearGradient from stroke color at 30% opacity (top) to transparent (bottom)
- Stroke color: Health_Color_Scale applied to latest score
- ReferenceLine y=80: stroke amber, strokeDasharray="4 2", label "Target" right-aligned
- ReferenceLine y=50: stroke red, strokeDasharray="4 2", label "Warning" right-aligned
- ReferenceArea: for any 7-day window with score drop >15 points, red fill at 15% opacity

**Coverage Chart** (Recharts BarChart):
- Layout: "vertical"
- Width: 100%
- Height: (serviceCount * 32) clamped to min 200px, max 500px
- Data: sorted by coverage percentage ascending
- Bar color: Health_Color_Scale applied to coverage percentage
- YAxis: service names, 12px right-aligned, truncated to 20 characters
- XAxis: 0-100% with percentage labels
- Tooltip: service name and exact coverage percentage
- onClick: navigate to /graph with that service's node selected
- Default: top 15 services, "Show all {n} services" button below

**Gap Heatmap** (custom SVG):
- Grid: 53 columns (weeks) x 7 rows (days Monday-Sunday)
- Cell: 12x12px rect, 3px gap between cells
- Color scale (light mode / dark mode):
  - 0 gaps: #ebedf0 / #161b22
  - 1-2 gaps: #9be9a8 / #0e4429
  - 3-5 gaps: #40c463 / #006d32
  - 6-10 gaps: #30a14e / #26a641
  - 11+ gaps: #216e39 / #39d353
- Dark mode detection: matchMedia("(prefers-color-scheme: dark)")
- Month labels: above first column of each month
- Day labels: "M", "W", "F" left of rows 1, 3, 5
- Hover tooltip: position fixed, follows mouse, shows "{n} gaps on {date}"
- Click: navigate to /policy filtered to that date
- Horizontal scroll on overflow

**Alerts Panel**:
- Sort: severity (critical first, then warning, then info), then timestamp descending within each severity
- Critical alerts: pulsing red left border animation (3px solid #ef4444 to #ef444440 over 1.5s infinite)
- Each alert row: severity badge (CRITICAL=red, WARNING=amber, INFO=blue), message with bold entity name, clickable entity link, relative time, dismiss button
- Dismiss: POST /reporting/alerts/{id}/dismiss, remove with 200ms slide-up-and-fade animation
- Empty state: "All clear — no active alerts for {activeRepo}" with green checkmark icon centered

**Activity Feed**:
- useInfiniteQuery: GET /reporting/activity?repo={repo}&limit=20&cursor={cursor}
- Virtualization: @tanstack/react-virtual, container height 400px, dynamic row height (56px collapsed, 120px expanded)
- IntersectionObserver sentinel at bottom triggers fetchNextPage
- Each row: 32x32px icon circle (colored by event type), description with bold entity and muted action, repo badge, relative time, chevron
- Click row: expand inline showing full event payload as syntax-colored JSON, 200ms max-height CSS transition
- Event type mapping: doc_refresh_completed=green checkmark circle, doc_rewrite_generated=blue sparkle, ci_check_run=gray CI icon, waiver_granted=amber shield, health_score_changed=colored trend arrow (green if increased, red if decreased), policy_blocked=red X circle, doc_gap_detected=orange warning triangle

**SSE Live Updates** (useHealthStream hook):
- EventSource: GET /reporting/stream?repo={activeRepo}
- Events:
  - "health_update": invalidate ["health","snapshots"] query, push notification if score dropped >5 points
  - "alert": invalidate ["health","alerts"] query, push notification
  - "activity": prepend event to activity feed via queryClient.setQueryData
- Reconnection: follows Appendix C (exponential backoff, max 10 attempts, "Live updates paused" pill after 5s disconnect)
- Cleanup: close EventSource on unmount, reopen when activeRepo changes

**Responsive Behavior** (below 1400px):
- Row 2 and Row 3: stack vertically (single column)

**Performance Targets** (from Appendix B):
- All four metric cards render: < 1 second
- Health score chart animate in: < 1 second
- Activity feed first 20 items: < 1 second
- SSE events reflected in UI: < 500ms

#### Key Interactions

1. **Coverage bar click**: Navigates to /graph filtered to that service with selectedNodeId
2. **Heatmap cell hover**: Shows tooltip with date and gap count
3. **Heatmap cell click**: Navigates to /policy filtered to that date
4. **Alert dismiss**: Calls POST /reporting/alerts/{id}/dismiss, removes with 200ms slide-up-and-fade animation
5. **Activity row expand**: Shows full event payload as syntax-colored JSON with 200ms max-height transition
6. **SSE live updates**: Updates metrics, adds alerts, prepends activity events
7. **"Show all services" button**: Re-renders coverage chart with full dataset
8. **"View gaps" link**: Navigates to /graph with undocumented filter active

#### Data Fetching

```typescript
// Fetch dashboard overview
const { data: overview } = useQuery({
  queryKey: ["health-overview", activeRepo],
  queryFn: () => fetch(`${BACKEND}/health/snapshots?repo=${activeRepo}&limit=1`, {
    headers: authHeaders()
  }).then(r => r.json()),
  enabled: !!activeRepo,
  refetchInterval: 30000,
});

// Fetch health snapshots (30-day)
const { data: snapshots } = useQuery({
  queryKey: ["health-snapshots", activeRepo],
  queryFn: () => fetch(`${BACKEND}/health/snapshots?repo=${activeRepo}&days=30`, {
    headers: authHeaders()
  }).then(r => r.json()),
  enabled: !!activeRepo,
});

// Fetch coverage data
const { data: coverage } = useQuery({
  queryKey: ["health-coverage", activeRepo],
  queryFn: () => fetch(`${BACKEND}/health/coverage?repo=${activeRepo}`, {
    headers: authHeaders()
  }).then(r => r.json()),
  enabled: !!activeRepo,
});

// Fetch gaps for heatmap
const { data: gapTimeline } = useQuery({
  queryKey: ["health-gaps-timeline", activeRepo],
  queryFn: () => fetch(`${BACKEND}/health/gaps/timeline?repo=${activeRepo}&days=365`, {
    headers: authHeaders()
  }).then(r => r.json()),
  enabled: !!activeRepo,
});

// Fetch active alerts
const { data: alerts } = useQuery({
  queryKey: ["health-alerts", activeRepo],
  queryFn: () => fetch(`${BACKEND}/reporting/alerts?repo=${activeRepo}&status=active`, {
    headers: authHeaders()
  }).then(r => r.json()),
  enabled: !!activeRepo,
});

// Dismiss alert mutation
const dismissAlertMutation = useMutation({
  mutationFn: (alertId: string) => 
    fetch(`${BACKEND}/reporting/alerts/${alertId}/dismiss`, {
      method: "POST",
      headers: authHeaders()
    }),
  onSuccess: () => {
    queryClient.invalidateQueries(["health-alerts"]);
  },
});

// Fetch activity feed with infinite scroll
const { 
  data: activityData, 
  fetchNextPage, 
  hasNextPage 
} = useInfiniteQuery({
  queryKey: ["health-activity", activeRepo],
  queryFn: ({ pageParam = null }) => 
    fetch(`${BACKEND}/reporting/activity?repo=${activeRepo}&limit=20${pageParam ? `&cursor=${pageParam}` : ''}`, {
      headers: authHeaders()
    }).then(r => r.json()),
  getNextPageParam: (lastPage) => lastPage.next_cursor,
  enabled: !!activeRepo,
});

// SSE connection for live updates
useEffect(() => {
  if (!activeRepo) return;
  
  let eventSource: EventSource | null = null;
  let reconnectAttempts = 0;
  let reconnectTimeout: NodeJS.Timeout;
  
  const connect = () => {
    try {
      eventSource = new EventSource(
        `${BACKEND}/reporting/stream?repo=${activeRepo}`
      );
      
      eventSource.addEventListener("health_update", (e) => {
        const data = JSON.parse(e.data);
        queryClient.setQueryData(["health-overview", activeRepo], data);
        
        // Push notification if score dropped >5 points
        const currentScore = overview?.score || 0;
        if (data.score < currentScore - 5) {
          pushNotification({
            type: "warning",
            message: `Health score dropped to ${data.score}`,
          });
        }
      });
      
      eventSource.addEventListener("alert", (e) => {
        const alert = JSON.parse(e.data);
        queryClient.invalidateQueries(["health-alerts"]);
        pushNotification({
          type: "error",
          message: `New ${alert.severity} alert: ${alert.message}`,
        });
      });
      
      eventSource.addEventListener("activity", (e) => {
        const event = JSON.parse(e.data);
        queryClient.setQueryData(["health-activity", activeRepo], (old: any) => {
          if (!old) return old;
          return {
            ...old,
            pages: [[event, ...old.pages[0]], ...old.pages.slice(1)],
          };
        });
      });
      
      eventSource.onerror = () => {
        eventSource?.close();
        reconnectAttempts++;
        
        if (reconnectAttempts < 10) {
          const delay = Math.min(30000, 2000 * Math.pow(2, reconnectAttempts - 1));
          reconnectTimeout = setTimeout(connect, delay);
        } else {
          // Max attempts reached
          setConnectionStatus("failed");
        }
      };
      
      eventSource.onopen = () => {
        reconnectAttempts = 0;
        setConnectionStatus("connected");
      };
    } catch (err) {
      console.error("SSE connection error:", err);
    }
  };
  
  connect();
  
  return () => {
    eventSource?.close();
    if (reconnectTimeout) clearTimeout(reconnectTimeout);
  };
}, [activeRepo]);
```

#### Chart Specifications

**Health Score Chart Color Interpolation** (Health_Color_Scale):
```typescript
function getHealthColor(score: number): string {
  if (score >= 50) {
    // Interpolate from #f59e0b (50) to #22c55e (100)
    const t = (score - 50) / 50;
    return interpolateColor("#f59e0b", "#22c55e", t);
  } else {
    // Interpolate from #ef4444 (0) to #f59e0b (50)
    const t = score / 50;
    return interpolateColor("#ef4444", "#f59e0b", t);
  }
}

function interpolateColor(color1: string, color2: string, t: number): string {
  const r1 = parseInt(color1.slice(1, 3), 16);
  const g1 = parseInt(color1.slice(3, 5), 16);
  const b1 = parseInt(color1.slice(5, 7), 16);
  const r2 = parseInt(color2.slice(1, 3), 16);
  const g2 = parseInt(color2.slice(3, 5), 16);
  const b2 = parseInt(color2.slice(5, 7), 16);
  
  const r = Math.round(r1 + (r2 - r1) * t);
  const g = Math.round(g1 + (g2 - g1) * t);
  const b = Math.round(b1 + (b2 - b1) * t);
  
  return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`;
}
```

**Gap Heatmap Color Scale**:
```typescript
function getGapColor(gapCount: number, isDark: boolean): string {
  if (gapCount === 0) return isDark ? "#161b22" : "#ebedf0";
  if (gapCount <= 2) return isDark ? "#0e4429" : "#9be9a8";
  if (gapCount <= 5) return isDark ? "#006d32" : "#40c463";
  if (gapCount <= 10) return isDark ? "#26a641" : "#30a14e";
  return isDark ? "#39d353" : "#216e39";
}
```

#### API Endpoints (from Appendix A)

- `GET /health/snapshots?repo={repo}&limit={limit}&days={days}` - Response: HealthSnapshot[]
- `GET /health/coverage?repo={repo}` - Response: CoverageEntry[]
- `GET /health/gaps?repo={repo}&status={status}` - Response: GapEntry[]
- `GET /health/gaps/timeline?repo={repo}&days={days}` - Response: GapDay[]
- `GET /reporting/alerts?repo={repo}&status={status}` - Response: Alert[]
- `POST /reporting/alerts/{id}/dismiss` - Response: 204 No Content
- `GET /reporting/activity?repo={repo}&limit={limit}&cursor={cursor}` - Response: { items: ActivityEvent[], next_cursor: string | null }
- `GET /reporting/stream?repo={repo}` - SSE stream of health_update, alert, and activity events


### 4. CI/CD Policy Status (/policy)

#### Component Structure

```
PolicyPage
├── FilterBar (outcome segmented control, ruleset dropdown, date range, search)
├── PolicyRunList (380px left panel, infinite scroll)
│   └── PolicyRunCard (outcome badge, PR title, timestamp)
└── PolicyDetailPanel (flexible right panel)
    ├── MergeGateBanner (blocked/warned/open)
    ├── PRHeader (title, author, timestamp)
    ├── RulesSection (grouped by status: failed, warned, passed)
    ├── PatchesSection (diff viewer)
    ├── DocRefreshPlanSection
    └── WaiverSection (active waivers, request button)
```

#### Key Interactions

1. **Filter change**: Updates URL query params, refetches policy runs
2. **Policy run click**: Loads detail panel with run details
3. **Request waiver button**: Opens waiver modal
4. **Waiver modal submit**: Submits waiver request, optimistically updates UI
5. **Revoke waiver**: Calls API, removes waiver from list
6. **SSE live updates**: Animates new policy runs into list

#### Data Fetching

```typescript
// Fetch policy runs with filters
const { data, fetchNextPage, hasNextPage, isLoading } = useInfiniteQuery({
  queryKey: ["policy-runs", activeRepo, filters],
  queryFn: ({ pageParam = 0 }) => 
    policyApi.policyCheckRuns(activeRepo!, { 
      ...filters, 
      offset: pageParam, 
      limit: 20 
    }, authHeaders()),
  getNextPageParam: (lastPage, pages) => 
    lastPage.length === 20 ? pages.length * 20 : undefined,
  enabled: !!activeRepo,
});

// Fetch policy run detail
const { data: detail } = useQuery({
  queryKey: ["policy-run-detail", selectedRunId],
  queryFn: () => policyApi.policyRun(selectedRunId!, authHeaders()),
  enabled: !!selectedRunId,
});

// Request waiver mutation
const requestWaiverMutation = useMutation({
  mutationFn: (waiver: WaiverRequest) => 
    policyApi.requestWaiver(waiver, authHeaders()),
  onSuccess: () => {
    queryClient.invalidateQueries(["policy-runs"]);
    queryClient.invalidateQueries(["waivers"]);
  },
});

// SSE connection for new policy runs
useEffect(() => {
  if (!activeRepo) return;
  
  const eventSource = new EventSource(
    `${BACKEND}/policy/stream?repo=${activeRepo}`,
    { headers: authHeaders() }
  );
  
  eventSource.addEventListener("policy_run", (e) => {
    const run = JSON.parse(e.data);
    queryClient.setQueryData(["policy-runs", activeRepo, filters], (old) => {
      return { ...old, pages: [[run, ...old.pages[0]], ...old.pages.slice(1)] };
    });
  });
  
  return () => eventSource.close();
}, [activeRepo]);
```

#### Waiver Modal

**Fields**:
- Rule selection (multi-select dropdown)
- Justification (textarea, 50 character minimum)
- Expiry date (date picker, 30 day maximum)

**Validation**:
- At least one rule selected
- Justification >= 50 characters
- Expiry date <= 30 days from now

**Submission**:
- Optimistic update: Add waiver to list immediately
- API call: POST /policy/admin/waivers/request
- On error: Rollback optimistic update, show error message

#### API Endpoints

- `GET /policy/dashboard/policy-check-runs?repo={repo}&outcome={outcome}&offset={offset}&limit={limit}` - Fetch policy runs
- `GET /policy/run/{id}` - Fetch policy run detail
- `POST /policy/admin/waivers/request` - Request waiver
- `GET /policy/admin/waivers?repo={repo}&status={status}` - Fetch waivers
- `POST /policy/admin/waivers/{id}/decision` - Approve/reject waiver
- `GET /policy/stream?repo={repo}` - SSE stream for new policy runs

### 5. Architecture Blueprint Viewer (/blueprints)

#### Component Structure

```
BlueprintPage
├── FilterBar (pattern type dropdown, date range, alignment filter)
├── BlueprintList (340px left panel)
│   └── BlueprintCard (requirement text, pattern badge, service count, alignment indicator)
└── BlueprintDetailPanel (flexible right panel)
    ├── AlignmentBanner (aligned/drifted)
    └── Tabs
        ├── DesignTab (React Flow diagram)
        │   ├── BlueprintServiceNode (rectangle with tech stack)
        │   ├── DatabaseNode (cylinder shape)
        │   ├── ExternalNode (cloud shape)
        │   └── Edges (REST, gRPC, Async, Database)
        ├── RationaleTab (two-column layout)
        │   ├── DecisionsColumn (65%, left)
        │   └── ConstraintsSidebar (35%, right)
        └── ArtifactsTab
            ├── FileTree (200px left)
            └── MonacoEditor (right, syntax highlighting)
```

#### Key Interactions

1. **Blueprint click**: Loads detail panel with blueprint details
2. **Tab switch**: Shows Design, Rationale, or Artifacts tab
3. **Constraint hover**: Highlights decisions that reference it
4. **Decision hover**: Highlights constraints it references
5. **File tree click**: Loads file in Monaco Editor
6. **Download all button**: Downloads all artifacts as zip
7. **Re-analyze button**: Triggers alignment check

#### Data Fetching

```typescript
// Fetch blueprints
const { data: blueprints, isLoading } = useQuery({
  queryKey: ["architecture-plans", activeRepo, filters],
  queryFn: () => architectureApi.listPlans(activeRepo!, authHeaders()),
  enabled: !!activeRepo,
});

// Fetch blueprint detail
const { data: blueprint } = useQuery({
  queryKey: ["architecture-plan", selectedPlanId],
  queryFn: () => architectureApi.plan(selectedPlanId!, authHeaders()),
  enabled: !!selectedPlanId,
});

// Re-analyze alignment mutation
const reanalyzeMutation = useMutation({
  mutationFn: (planId: string) => 
    architectureApi.analyzeAlignment(planId, authHeaders()),
  onSuccess: () => {
    queryClient.invalidateQueries(["architecture-plan", selectedPlanId]);
  },
});
```

#### React Flow Diagram (Design Tab)

**Node Types**:
- **BlueprintServiceNode**: Rectangle with service name, tech stack badge (language, runtime)
- **DatabaseNode**: Cylinder shape (custom SVG path)
- **ExternalNode**: Cloud shape (custom SVG path)

**Edge Types**:
- **REST**: Solid line, blue color, arrow marker
- **gRPC**: Solid line, green color, arrow marker
- **Async**: Dashed line, purple color, arrow marker
- **Database**: Dotted line, orange color, arrow marker

**Layout**: Use dagre algorithm for hierarchical layout (top-to-bottom)

```typescript
import dagre from "dagre";

function computeBlueprintLayout(services, connections) {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "TB", nodesep: 100, ranksep: 150 });
  g.setDefaultEdgeLabel(() => ({}));
  
  services.forEach(s => g.setNode(s.name, { width: 200, height: 100 }));
  connections.forEach(c => g.setEdge(c.from, c.to));
  
  dagre.layout(g);
  
  return services.map(s => {
    const pos = g.node(s.name);
    return { ...s, position: { x: pos.x, y: pos.y } };
  });
}
```

#### Rationale Tab Cross-Highlighting

**Implementation**:
1. Parse decision text to extract constraint references (e.g., "due to [Constraint 1]")
2. Build bidirectional mapping: constraint -> decisions, decision -> constraints
3. On constraint hover: Add highlight class to referenced decisions
4. On decision hover: Add highlight class to referenced constraints

```typescript
function parseConstraintReferences(decisionText: string): string[] {
  const regex = /\[Constraint (\d+)\]/g;
  const matches = [...decisionText.matchAll(regex)];
  return matches.map(m => m[1]);
}

function buildCrossReferenceMap(decisions, constraints) {
  const constraintToDecisions = new Map<string, string[]>();
  const decisionToConstraints = new Map<string, string[]>();
  
  decisions.forEach((d, i) => {
    const refs = parseConstraintReferences(d.rationale);
    decisionToConstraints.set(String(i), refs);
    refs.forEach(ref => {
      if (!constraintToDecisions.has(ref)) {
        constraintToDecisions.set(ref, []);
      }
      constraintToDecisions.get(ref)!.push(String(i));
    });
  });
  
  return { constraintToDecisions, decisionToConstraints };
}
```

#### Artifacts Tab (Monaco Editor)

**File Tree**:
- Hierarchical tree structure (folders and files)
- Click to load file in editor
- Syntax highlighting based on file extension

**Monaco Editor**:
- Read-only mode
- Syntax highlighting for TypeScript, Python, JSON, YAML, Markdown
- Line numbers, minimap
- Download button for individual file

**Download All**:
- Generates zip file with all artifacts
- Uses JSZip library
- Downloads as `{blueprint-name}-artifacts.zip`

```typescript
import JSZip from "jszip";
import { saveAs } from "file-saver";

async function downloadAllArtifacts(artifacts: ScaffoldArtifact[], blueprintName: string) {
  const zip = new JSZip();
  
  artifacts.forEach(artifact => {
    zip.file(artifact.file_path, artifact.content);
  });
  
  const blob = await zip.generateAsync({ type: "blob" });
  saveAs(blob, `${blueprintName}-artifacts.zip`);
}
```

#### API Endpoints

- `GET /architecture/plans?repo={repo}` - Fetch blueprints
- `GET /architecture/plan/{id}` - Fetch blueprint detail
- `POST /architecture/analyze-alignment` - Trigger alignment check
- `GET /architecture/artifacts/{plan_id}` - Fetch artifacts

### 6. Onboarding Learning Paths (/onboarding)

#### Component Structure

```
OnboardingPage
├── RoleSelector (full-screen overlay, 5 role cards)
├── StageTrack (horizontal progress bar)
│   ├── StageNode (completed, current, future)
│   └── ConnectingLine (progress fill)
└── StageDetail
    ├── DocumentationResources (read status tracking)
    ├── KeyServices (links to graph and Q&A)
    ├── RelevantADRs (expandable details)
    ├── StarterTask (GitHub issue link)
    └── TeammateMap (grid of relevant contacts)
```

#### Key Interactions

1. **Role selection**: Saves role to user profile, dismisses overlay, fetches learning path
2. **Stage click**: Navigates to that stage (if unlocked)
3. **Documentation link click**: Marks as read, opens documentation
4. **Service link click**: Navigates to graph view filtered to that service
5. **Q&A link click**: Opens Q&A interface with pre-filled question
6. **ADR expand**: Shows full ADR details
7. **Mark complete button**: Shows confirmation dialog, updates progress

#### Data Fetching

```typescript
// Fetch onboarding path
const { data: path, isLoading } = useQuery({
  queryKey: ["onboarding-path", activeRepo, userRole],
  queryFn: () => onboardingApi.generatePath({ 
    repo: activeRepo!, 
    role: userRole! 
  }, authHeaders()),
  enabled: !!activeRepo && !!userRole,
});

// Update progress mutation
const updateProgressMutation = useMutation({
  mutationFn: (stageId: string) => 
    onboardingApi.updateProgress({ 
      repo: activeRepo!, 
      stage_id: stageId, 
      completed: true 
    }, authHeaders()),
  onMutate: async (stageId) => {
    // Optimistic update
    await queryClient.cancelQueries(["onboarding-path", activeRepo, userRole]);
    const previous = queryClient.getQueryData(["onboarding-path", activeRepo, userRole]);
    
    queryClient.setQueryData(["onboarding-path", activeRepo, userRole], (old: any) => ({
      ...old,
      stages: old.stages.map((s: any) => 
        s.stage_id === stageId ? { ...s, completed: true } : s
      ),
    }));
    
    return { previous };
  },
  onError: (err, stageId, context) => {
    // Rollback on error
    queryClient.setQueryData(["onboarding-path", activeRepo, userRole], context?.previous);
  },
});
```

#### Role Selector

**Roles**:
- Backend Engineer (icon: Code, color: indigo)
- SRE (icon: Server, color: emerald)
- Frontend Developer (icon: Layout, color: blue)
- Data Engineer (icon: Database, color: purple)
- Engineering Manager (icon: Users, color: amber)

**Card Design**:
- Large icon (48px)
- Role title
- Brief description (2-3 sentences)
- Hover effect: Scale up, glow border

#### Stage Track

**Stage States**:
- **Completed**: Green checkmark icon, green connecting line
- **Current**: Blue pulse animation, blue connecting line (partial fill)
- **Future**: Gray circle, gray connecting line

**Progress Calculation**:
```typescript
const progress = (completedStages / totalStages) * 100;
```

#### Confetti Animation

When final stage is completed, trigger confetti animation using `canvas-confetti` library:

```typescript
import confetti from "canvas-confetti";

function celebrateCompletion() {
  confetti({
    particleCount: 100,
    spread: 70,
    origin: { y: 0.6 },
  });
  
  setTimeout(() => {
    confetti({
      particleCount: 50,
      angle: 60,
      spread: 55,
      origin: { x: 0 },
    });
  }, 250);
  
  setTimeout(() => {
    confetti({
      particleCount: 50,
      angle: 120,
      spread: 55,
      origin: { x: 1 },
    });
  }, 400);
}
```

#### API Endpoints

- `POST /onboarding/path` - Generate learning path for role
- `POST /onboarding/progress` - Update stage completion
- `GET /onboarding/history?repo={repo}` - Fetch onboarding history

## Data Models

### Chat Message

```typescript
interface ChatMessage {
  id: string;
  role: "user" | "assistant";
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

interface Citation {
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

interface ChainStepInfo {
  name?: string;
  step_name?: string;
  latency_ms?: number;
  tokens?: number;
  tokens_used?: number;
}
```

### Graph Node

```typescript
interface GraphNodeData {
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

type GraphNodeType = "service" | "api" | "schema" | "engineer" | "adr" | "incident" | "database" | "queue";

interface GraphEdgeData {
  relationship: "depends_on" | "owns" | "causes" | "calls" | "stores";
}
```

### Health Snapshot

```typescript
interface HealthSnapshot {
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

interface DashboardOverview {
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
```

### Policy Run

```typescript
interface PolicyRun {
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

type PolicyOutcome = "pass" | "warn" | "block" | "fail" | "error";

interface MergeGate {
  decision: "allow" | "block" | "allow_with_waiver";
  blocking_rule_ids?: string[];
  reasons?: string[];
  policy_action?: string;
  waiver?: Record<string, unknown>;
  branch_protection_result?: Record<string, unknown>;
}

interface Finding {
  rule_id: string;
  severity: FindingSeverity;
  status: string;
  title: string;
  description: string;
  entity_refs?: string[];
  evidence?: string[];
  suggested_action?: string;
}

type FindingSeverity = "critical" | "high" | "medium" | "low" | "info";

interface Waiver {
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
```

### Architecture Blueprint

```typescript
interface ArchitecturePlan {
  plan_id: string;
  requirement: { requirement_text: string; domain?: string; target_cloud?: string };
  intent_tags?: string[];
  decisions?: ArchitectureDecision[];
  services?: ServiceBlueprint[];
  infrastructure?: Array<{ resource: string; purpose: string }>;
  artifacts?: ScaffoldArtifact[];
  produced_at: string;
}

interface ArchitectureDecision {
  title: string;
  rationale: string;
  tradeoffs?: string[];
  alternatives?: string[];
  confidence?: number;
  constraint?: string;
}

interface ServiceBlueprint {
  name: string;
  role: string;
  language: string;
  runtime: string;
  interfaces?: string[];
}

interface ScaffoldArtifact {
  file_path: string;
  content: string;
  content_type?: string;
}
```

### Onboarding Path

```typescript
interface OnboardingPath {
  path_id: string;
  role: OnboardingRole;
  repo: string;
  tasks?: Array<Record<string, unknown>>;
  stages?: OnboardingStage[];
  generated_at?: string;
  _meta?: Record<string, unknown>;
}

type OnboardingRole =
  | "backend_engineer"
  | "sre"
  | "frontend_developer"
  | "data_engineer"
  | "engineering_manager";

interface OnboardingStage {
  stage_id: string;
  title: string;
  description?: string;
  estimated_minutes?: number;
  resources?: OnboardingResource[];
  completed?: boolean;
}

interface OnboardingResource {
  type: "doc" | "graph_node" | "adr" | "code" | "task";
  title: string;
  description?: string;
  url?: string;
  service_name?: string;
  file_path?: string;
}
```


## Correctness Properties

A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.

### Property Reflection

After analyzing all acceptance criteria from the detailed requirements, I identified several areas of redundancy and consolidated them:

1. **Message rendering and alignment**: Combined multiple properties about user/assistant message display into single properties
2. **SSE event handling**: Consolidated token streaming, metadata completion, and reconnection behavior
3. **Node/edge rendering**: Combined similar rendering properties for different node/edge types
4. **API header injection**: Unified all properties about X-Repo-Scope and auth headers
5. **Chart rendering and interactions**: Consolidated chart configuration and click behavior properties
6. **Loading/error states**: Combined skeleton loading and error state properties across features
7. **Layout algorithms**: Unified properties about deterministic layout computation
8. **Filter and search**: Combined filtering, searching, and highlighting properties

The following properties represent the unique, non-redundant validation requirements derived from the detailed requirements document.

### Property 1: Message Role Alignment

For any chat message, if the role is "user" then the message should be right-aligned in a rounded bubble with plain text, and if the role is "assistant" then the message should be left-aligned with all seven UI layers rendered in exact vertical order: (1) intent badge, (2) markdown answer, (3) confidence bar, (4) source breakdown pills, (5) citations panel, (6) chain of thought steps, (7) follow-up suggestion chips.

**Validates: Requirements 1.4, 1.5, 1.6**

### Property 2: SSE Token Streaming with Buffer

For any sequence of SSE token events arriving in chunks, buffering incomplete lines across chunks and parsing complete lines beginning with "data: " should produce the same final content as if all tokens arrived in a single chunk.

**Validates: Requirements 1.7, 11.1, 11.2**

### Property 3: SSE Metadata Completion

For any SSE metadata event, the message should transition from streaming state (with blinking cursor) to complete state (cursor hidden) and contain all metadata fields (intent, confidence, citations, chain_steps, source_breakdown, follow_up_suggestions), with all post-stream layers (3-7) becoming visible.

**Validates: Requirements 1.8, 11.4**

### Property 4: Auto-scroll Behavior with User Override

For any chat thread, when a new message or token arrives, the scroll position should move to bottom (scrollTop + clientHeight === scrollHeight) UNLESS the user has manually scrolled more than 100px above the bottom.

**Validates: Requirements 1.9**

### Property 5: Textarea Auto-resize with Mirror

For any input text in the textarea, the height should be at least 1 row and at most 6 rows, computed using a hidden div mirror technique that matches the textarea's content and styling.

**Validates: Requirements 1.10**

### Property 6: Conditional Button States

For any chat input state, the send button should be disabled when input is empty OR streaming is in progress, enabled when input is not empty AND not streaming, and replaced with a stop button (calling reader.cancel()) when streaming is in progress.

**Validates: Requirements 1.11, 1.12**

### Property 7: History Session Grouping by Time

For any list of conversation sessions, grouping by time should produce exactly four buckets (Today, Yesterday, This Week, Older) where each session appears in exactly one bucket based on its timestamp relative to the current date.

**Validates: Requirements 1.13**

### Property 8: Session Deletion with Animation

For any conversation session in history, deleting it via DELETE /assistant/sessions/{id} should remove it from the list with a 200ms fade-out animation and not affect other sessions.

**Validates: Requirements 1.14**

### Property 9: API Header Injection for All Requests

For any API call made through the API client, the request headers should include Authorization from session token, X-Repo-Scope with activeRepo value, and all authHeaders from Zustand session store.

**Validates: Requirements 1.16, 2.27, 3.28, 4.20, 5.21, 6.18, 8.3, 8.4**

### Property 10: Node Type to Component Mapping

For any graph node, the rendered React Flow component type and visual style should match the node's type field: service → ServiceNode (180x72px rounded rect, health-colored), api → APINode (28px pill, method-colored), schema → SchemaNode (80x80px rotated diamond), adr → ADRNode (100x64px with folded corner), engineer → EngineerNode (52px circle with initials), incident → IncidentNode (60x52px triangle).

**Validates: Requirements 2.6, 2.7, 2.8, 2.9, 2.10, 2.11**

### Property 11: Edge Type to Style Mapping

For any graph edge, the rendered line style should match the relationship type: depends_on → solid 1.5px #6b7280 with arrow, owns → dashed 1.5px #3b82f6 (stroke-dasharray 6 3) no arrow, causes → dotted 1.5px #f59e0b (stroke-dasharray 2 2) with arrows both ends.

**Validates: Requirements 2.12, 2.13, 2.14**

### Property 12: Node Click Opens Detail Panel

For any graph node, clicking it should set selectedNodeId state to that node's id and open the detail panel with a 300ms translateX(0) transition from translateX(100%), displaying node-specific content based on node type.

**Validates: Requirements 2.15, 2.23, 2.24, 2.25, 2.26**

### Property 13: Node Double-Click Expansion

For any graph node, double-clicking it should call React Flow fitView (padding=0.3, duration=600ms) centered on that node, then fetch GET /graph/neighbors/{node_id}?depth=1, and add the returned nodes and edges to the graph with a hidden-to-visible animation, without removing existing nodes.

**Validates: Requirements 2.16**

### Property 14: Node Hover Opacity Adjustment

For any graph node, hovering it should set the opacity of all non-connected nodes to 0.15 and all non-connected edges to 0.1 via React Flow style props, and removing hover should reset all opacities to 1.

**Validates: Requirements 2.17**

### Property 15: Node Type Filter Visibility

For any set of visible node types (from control panel toggles), the filtered graph should contain only nodes whose type is in the visible set, and edges should only be visible if both source and target nodes are visible, without removing nodes from the underlying data array.

**Validates: Requirements 2.18**

### Property 16: Health Score Color Interpolation

For any health score value between 0 and 100, the color should be computed by Health_Color_Scale: if score >= 50, interpolate linearly from #f59e0b (score=50) to #22c55e (score=100); if score < 50, interpolate linearly from #ef4444 (score=0) to #f59e0b (score=50).

**Validates: Requirements 3.8, Glossary: Health_Color_Scale**

### Property 17: Coverage Bar Color Thresholds

For any service coverage percentage, the bar color should be green if coverage >= 80, yellow if coverage >= 50, red if coverage < 50, applied via Health_Color_Scale.

**Validates: Requirements 3.12**

### Property 18: Heatmap Cell Color Scale

For any gap count value, the heatmap cell color should follow the five-stop scale: 0 gaps = #ebedf0 (light) / #161b22 (dark), 1-2 = #9be9a8 / #0e4429, 3-5 = #40c463 / #006d32, 6-10 = #30a14e / #26a641, 11+ = #216e39 / #39d353, with dark mode detected via matchMedia("(prefers-color-scheme: dark)").

**Validates: Requirements 3.15, 3.16**

### Property 19: SSE Live Update Cache Integration

For any SSE event (health_update, alert, activity, policy_run), receiving the event should update the corresponding React Query cache via queryClient.setQueryData or invalidateQueries, triggering a re-render with the new data within 500ms.

**Validates: Requirements 3.23, 3.24, 3.25, 3.26, 4.5, 4.6, 10.1, 10.2, 10.3, Appendix B**

### Property 20: SSE Reconnection with Exponential Backoff

For any SSE connection error, the system should wait 2 seconds then attempt reconnection; if reconnection fails, apply exponential backoff (2s, 4s, 8s, 16s, capped at 30s); after 10 consecutive failed attempts, stop retrying and set status to "failed"; display "Live updates paused" pill if disconnected for more than 5 seconds.

**Validates: Requirements 10.3, Appendix C**

### Property 21: Infinite Scroll Pagination

For any scrollable list with infinite scroll (policy runs, activity feed), when the IntersectionObserver sentinel div at the bottom enters the viewport, fetchNextPage should be called if hasNextPage is true, and the new page should be appended to the existing data without replacing previous pages.

**Validates: Requirements 3.22, 4.4**

### Property 22: Filter URL Synchronization

For any filter value change (outcome, ruleset, date range, search), the URL query parameters should be updated via useSearchParams to reflect the new filter values, and navigating to a URL with query parameters should initialize filters from those parameters, making filter state shareable and persistent across page refreshes.

**Validates: Requirements 4.3**

### Property 23: Waiver Request Validation

For any waiver request, it should be rejected client-side if: (1) rule_ids array is empty, (2) justification is less than 50 characters, or (3) expiry date is more than 30 days from now; the submit button should show validation errors inline below the button.

**Validates: Requirements 4.13, 4.14, 4.15, 4.16**

### Property 24: Optimistic Update with Rollback

For any mutation with optimistic update (waiver request, stage completion), the optimistic update should be applied immediately via queryClient.setQueryData, and if the API call fails, the optimistic update should be rolled back to the previous state stored in the onMutate context.

**Validates: Requirements 4.17, 6.15**

### Property 25: Blueprint Node Shape Rendering

For any blueprint diagram node, the rendered shape should match the node type: service → 180x72px rounded rectangle with tech stack badge, database → 100x64px cylinder (rectangle with border-radius and ::before ellipse), external → cloud shape via CSS clip-path.

**Validates: Requirements 5.6, 5.7, 5.8**

### Property 26: Blueprint Edge Style and Label

For any blueprint diagram edge, the rendered line style, color, and label should match the connection type: REST → solid 1.5px blue with arrow and "REST" label, gRPC → solid 1.5px purple with arrow and "gRPC" label, Async → dashed 1.5px orange with "async" label, Database → dotted 1px gray with no arrow or label.

**Validates: Requirements 5.9**

### Property 27: Cross-Reference Highlighting

For any constraint in the Rationale tab, hovering or clicking it should apply a blue glow border (box-shadow: 0 0 0 2px #3b82f6) to all decision cards that reference that constraint (by parsing decision text for "[Constraint N]"); clicking a constraint driver chip on a decision card should scroll the constraints sidebar to the referenced constraint and apply a 600ms pulse animation.

**Validates: Requirements 5.11, 5.12, 5.13, 5.14**

### Property 28: File Tree to Monaco Editor Navigation

For any file in the artifacts file tree, clicking it should select that file, load its content via GET /blueprints/{id}/artifacts/{file_path}, and display it in the Monaco Editor with syntax highlighting auto-detected from file extension (yaml/yml=yaml, Dockerfile=dockerfile, .proto=proto, .json=json, .ts=typescript, .py=python, .go=go, default=plaintext).

**Validates: Requirements 5.15, 5.16, 12.1, 12.2**

### Property 29: Alignment Status Banner Display

For any blueprint, if alignment status is "aligned" then display green banner with checkmark icon, "Blueprint is aligned with the current codebase", and last checked timestamp; if "drifted" then display red banner with warning icon, "Blueprint has drifted from the codebase", drift_summary text, specific drift callout chips, and "Re-analyze alignment" button.

**Validates: Requirements 5.4, 5.5**

### Property 30: Role Selection and Path Generation

For any role card click in the role selector, the system should save the role to Zustand userRole, call POST /onboarding/role with { role, user_id, repo }, dismiss the overlay with a 300ms fade-out transition, and fetch GET /onboarding/path?repo={repo}&role={role} to load the learning path.

**Validates: Requirements 6.2, 6.3, 6.4**

### Property 31: Stage Visual State Computation

For any onboarding stage, the visual state should be: completed (green subtle background, checkmark icon, "Completed" text, fully clickable) if completed is true; current (white background with blue border, pulsing blue dot, resource count, estimated time) if it's the first non-completed stage; future (gray background at 50% opacity, lock icon, non-clickable with "Complete previous stages first" tooltip) otherwise.

**Validates: Requirements 6.5, 6.6, 6.7**

### Property 32: Stage Completion with Confetti

For any stage completion confirmation, the system should optimistically update the stage to completed state via queryClient.setQueryData, call POST /onboarding/progress with { stage_id, user_id, repo, completed_at }, animate the stage card to completed visual state and next stage to current visual state, grow the progress line width via CSS transition; if the completed stage is the final stage, trigger canvas-confetti animation with count=200, spread=70, origin={ y: 0.6 }.

**Validates: Requirements 6.15, 6.16**

### Property 33: React Query Cache Invalidation on Repo Change

For any change to activeRepo in Zustand, the system should call queryClient.invalidateQueries() with no arguments to invalidate all cached queries simultaneously, triggering refetches for all active queries.

**Validates: Requirements 8.2**

### Property 34: Layout Algorithm Determinism

For any graph layout mode (Force, Tree, Radial), applying the layout algorithm twice to the same input (same nodes and edges) should produce the same node positions (deterministic layout), with Force layout using 300 synchronous ticks, Tree layout using dagre with direction="LR", and Radial layout using radius = (nodeCount * 30) clamped to 200-600px.

**Validates: Requirements 13.2, 13.3, Glossary: Force_Layout, Tree_Layout, Radial_Layout**

### Property 35: Chart Tooltip Display on Hover

For any chart data point (health score, coverage bar, heatmap cell), hovering it should display a custom Recharts tooltip component or floating div tooltip with the data point's exact values and appropriate formatting, and moving the mouse away should hide the tooltip.

**Validates: Requirements 14.6**

### Property 36: Chart Click Navigation with Query Params

For any clickable chart element (coverage bar, heatmap cell), clicking it should navigate to the corresponding filtered view with the correct query parameters: coverage bar → /graph?selectedNodeId={service_id}, heatmap cell → /policy?date={date}.

**Validates: Requirements 3.13, 3.17, 14.7**

### Property 37: Skeleton Loading Shape Matching

For any data-fetching component, the skeleton loading state should match the shape of real content dimensions to within 10px: message skeletons (48px tall value rect, 16px label rect, 12px trend rect), graph node skeletons (180x72px service rect, 52px engineer circle), activity row skeletons (56px rect with varying-width inner rects).

**Validates: Requirements 8.5**

### Property 38: Error State with Retry Button

For any data-fetching component that encounters an error, the error state should display a message derived from the API response error body when available (or a context-specific fallback message), an error icon, and a retry button that calls the React Query refetch() function.

**Validates: Requirements 8.6**

### Property 39: Empty State with Guidance

For any list or graph view with no data, the empty state should display a meaningful message explaining why no data exists (e.g., "The knowledge graph for this repository hasn't been indexed yet") and a suggested next action (e.g., "Trigger an indexing run to populate the graph").

**Validates: Requirements 8.7**

### Property 40: Performance Target Compliance

For any feature interaction, the performance should meet the targets defined in Appendix B: Q&A first token < 500ms, graph render < 2s, health metrics < 1s, SSE events reflected < 500ms, policy run list < 1s, blueprint diagram < 1.5s, Monaco editor < 500ms, role selector < 100ms.

**Validates: Appendix B (all performance targets)**


## Error Handling

### Error Handling Strategy

All features implement a consistent three-tier error handling approach:

1. **API Client Level**: Catch HTTP errors, throw ApiError with status and message
2. **React Query Level**: Capture errors in query/mutation error state, provide retry mechanism
3. **Component Level**: Render error UI with context-aware messages and retry buttons

### API Error Types

```typescript
class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

// Usage in API client
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BACKEND}${path}`, options);
  
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body?.detail || body?.message || detail;
    } catch {}
    throw new ApiError(res.status, detail);
  }
  
  return res.json();
}
```

### Error UI Components

**ErrorState Component**:
```typescript
interface ErrorStateProps {
  error: Error | ApiError;
  onRetry?: () => void;
  context?: string;
}

function ErrorState({ error, onRetry, context }: ErrorStateProps) {
  const isApiError = error instanceof ApiError;
  const status = isApiError ? error.status : null;
  
  const getMessage = () => {
    if (status === 401) return "Authentication required. Please log in again.";
    if (status === 403) return "You don't have permission to access this resource.";
    if (status === 404) return `${context || "Resource"} not found.`;
    if (status === 500) return "Server error. Please try again later.";
    return error.message || "An unexpected error occurred.";
  };
  
  return (
    <div className="flex flex-col items-center justify-center p-8 text-center">
      <AlertCircle className="w-10 h-10 text-red-400 mb-4" />
      <h3 className="text-sm font-semibold text-red-400 mb-2">
        {status ? `Error ${status}` : "Error"}
      </h3>
      <p className="text-xs text-slate-400 mb-4 max-w-sm">{getMessage()}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white text-xs rounded-lg transition-colors"
        >
          Try Again
        </button>
      )}
    </div>
  );
}
```

### Feature-Specific Error Handling

**Q&A Chat Interface**:
- Streaming errors: Display error message in assistant message, allow retry
- History load errors: Show error toast, keep current conversation
- Send message errors: Display error message, keep input text for retry

**Knowledge Graph**:
- Graph fetch errors: Display error state with "Graph may not be indexed yet" message
- Neighbor fetch errors: Show error toast, don't modify graph
- Layout computation errors: Fall back to circular layout

**Health Dashboard**:
- Metrics fetch errors: Display error state in metric cards
- Chart data errors: Show "No data available" message in chart area
- SSE connection errors: Display connection status indicator, auto-reconnect after 5s

**Policy Status**:
- Policy run fetch errors: Display error state in list panel
- Waiver request errors: Show error toast, rollback optimistic update
- SSE connection errors: Display connection status indicator, auto-reconnect

**Blueprint Viewer**:
- Blueprint fetch errors: Display error state in list panel
- Artifact fetch errors: Show error message in Monaco Editor
- Layout computation errors: Fall back to simple grid layout

**Onboarding Paths**:
- Path fetch errors: Display error state with "Generate path" retry button
- Progress update errors: Show error toast, rollback optimistic update
- Role save errors: Show error toast, keep role selector open

### SSE Error Handling

```typescript
function useSSEConnection(url: string, handlers: Record<string, (data: any) => void>) {
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>();
  
  useEffect(() => {
    let eventSource: EventSource | null = null;
    
    const connect = () => {
      try {
        eventSource = new EventSource(url);
        
        eventSource.onopen = () => {
          setConnected(true);
          setError(null);
        };
        
        eventSource.onerror = (e) => {
          setConnected(false);
          setError(new Error("Connection lost"));
          eventSource?.close();
          
          // Auto-reconnect after 5s
          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, 5000);
        };
        
        Object.entries(handlers).forEach(([event, handler]) => {
          eventSource?.addEventListener(event, (e) => {
            try {
              const data = JSON.parse(e.data);
              handler(data);
            } catch (err) {
              console.error(`Failed to parse ${event} event:`, err);
            }
          });
        });
      } catch (err) {
        setError(err as Error);
      }
    };
    
    connect();
    
    return () => {
      eventSource?.close();
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [url]);
  
  return { connected, error };
}
```

### Loading State Strategy

All features use skeleton loading states that match the shape of real content:

**Skeleton Components**:
```typescript
function MessageSkeleton() {
  return (
    <div className="flex gap-3 animate-pulse">
      <div className="w-8 h-8 rounded-full bg-slate-800" />
      <div className="flex-1 space-y-2">
        <div className="h-4 bg-slate-800 rounded w-3/4" />
        <div className="h-4 bg-slate-800 rounded w-1/2" />
      </div>
    </div>
  );
}

function GraphNodeSkeleton() {
  return (
    <div className="rounded-xl border-2 border-slate-700 px-3 py-2 w-[120px] h-[60px] bg-slate-800 animate-pulse" />
  );
}

function MetricCardSkeleton() {
  return (
    <div className="glass rounded-xl p-4 space-y-3 animate-pulse">
      <div className="h-4 bg-slate-800 rounded w-1/2" />
      <div className="h-8 bg-slate-800 rounded w-3/4" />
      <div className="h-12 bg-slate-800 rounded" />
    </div>
  );
}

function PolicyRunSkeleton() {
  return (
    <div className="p-3 space-y-2 animate-pulse">
      <div className="h-4 bg-slate-800 rounded w-1/4" />
      <div className="h-4 bg-slate-800 rounded w-3/4" />
      <div className="h-3 bg-slate-800 rounded w-1/2" />
    </div>
  );
}
```

### Empty State Strategy

All features provide meaningful empty states with guidance:

**Empty State Components**:
```typescript
function EmptyGraphState() {
  return (
    <div className="flex flex-col items-center justify-center h-full p-8 text-center">
      <GitBranch className="w-12 h-12 text-slate-600 mb-4" />
      <h3 className="text-sm font-semibold text-slate-400 mb-2">No graph data found</h3>
      <p className="text-xs text-slate-500 max-w-sm">
        The knowledge graph for this repository hasn't been indexed yet. 
        Trigger an indexing run to populate the graph.
      </p>
    </div>
  );
}

function EmptyPolicyRunsState() {
  return (
    <div className="flex flex-col items-center justify-center h-full p-8 text-center">
      <Shield className="w-12 h-12 text-slate-600 mb-4" />
      <h3 className="text-sm font-semibold text-slate-400 mb-2">No policy runs found</h3>
      <p className="text-xs text-slate-500 max-w-sm">
        Policy runs will appear here when pull requests are opened or updated.
      </p>
    </div>
  );
}

function EmptyOnboardingState() {
  return (
    <div className="flex flex-col items-center justify-center h-full p-8 text-center">
      <GraduationCap className="w-12 h-12 text-slate-600 mb-4" />
      <h3 className="text-sm font-semibold text-slate-400 mb-2">Select your role to begin</h3>
      <p className="text-xs text-slate-500 max-w-sm">
        Choose your role to generate a personalized onboarding path for this repository.
      </p>
    </div>
  );
}
```

## Testing Strategy

### Testing Approach

This project uses a dual testing approach combining unit tests and property-based tests:

1. **Unit Tests**: Verify specific examples, edge cases, error conditions, and integration points
2. **Property-Based Tests**: Verify universal properties across all inputs using randomized testing

Both approaches are complementary and necessary for comprehensive coverage. Unit tests catch concrete bugs in specific scenarios, while property-based tests verify general correctness across a wide range of inputs.

### Testing Stack

- **Test Framework**: Vitest (fast, ESM-native, compatible with Vite/Next.js)
- **React Testing**: React Testing Library (@testing-library/react)
- **Property-Based Testing**: fast-check (JavaScript/TypeScript PBT library)
- **Mocking**: MSW (Mock Service Worker) for API mocking
- **Coverage**: Vitest coverage with c8

### Property-Based Testing Configuration

Each property-based test must:
- Run minimum 100 iterations (due to randomization)
- Reference the design document property in a comment tag
- Use fast-check generators for input data
- Verify the property holds for all generated inputs

**Tag Format**:
```typescript
// Feature: frontend-six-feature-transformation, Property 1: Message Role Alignment
```

### Test Organization

```
frontend/
├── __tests__/
│   ├── unit/
│   │   ├── chat/
│   │   │   ├── ChatInput.test.tsx
│   │   │   ├── MessageThread.test.tsx
│   │   │   └── streaming.test.ts
│   │   ├── graph/
│   │   │   ├── GraphCanvas.test.tsx
│   │   │   ├── FilterPanel.test.tsx
│   │   │   └── layout.test.ts
│   │   ├── health/
│   │   │   ├── MetricCards.test.tsx
│   │   │   ├── HealthScoreChart.test.tsx
│   │   │   └── GapHeatmap.test.tsx
│   │   ├── policy/
│   │   │   ├── PolicyRunList.test.tsx
│   │   │   ├── WaiverModal.test.tsx
│   │   │   └── validation.test.ts
│   │   ├── blueprints/
│   │   │   ├── BlueprintDetailPanel.test.tsx
│   │   │   ├── RationaleTab.test.tsx
│   │   │   └── cross-reference.test.ts
│   │   └── onboarding/
│   │       ├── RoleSelector.test.tsx
│   │       ├── StageTrack.test.tsx
│   │       └── progress.test.ts
│   └── properties/
│       ├── chat.properties.test.ts
│       ├── graph.properties.test.ts
│       ├── health.properties.test.ts
│       ├── policy.properties.test.ts
│       ├── blueprints.properties.test.ts
│       └── onboarding.properties.test.ts
├── __mocks__/
│   ├── api.ts
│   └── session.ts
└── vitest.config.ts
```

### Property-Based Test Examples

**Property 1: Message Role Alignment**
```typescript
import { describe, it } from "vitest";
import fc from "fast-check";
import { render } from "@testing-library/react";
import { MessageThread } from "@/components/chat/MessageThread";

// Feature: frontend-six-feature-transformation, Property 1: Message Role Alignment
describe("Property 1: Message Role Alignment", () => {
  it("should align messages based on role", () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            id: fc.string(),
            role: fc.constantFrom("user", "assistant"),
            content: fc.string(),
          })
        ),
        (messages) => {
          const { container } = render(<MessageThread messages={messages} />);
          
          messages.forEach((msg) => {
            const msgElement = container.querySelector(`[data-message-id="${msg.id}"]`);
            if (msg.role === "user") {
              expect(msgElement).toHaveClass("justify-end");
            } else {
              expect(msgElement).toHaveClass("justify-start");
            }
          });
        }
      ),
      { numRuns: 100 }
    );
  });
});
```

**Property 2: SSE Token Streaming**
```typescript
import { describe, it } from "vitest";
import fc from "fast-check";

// Feature: frontend-six-feature-transformation, Property 2: SSE Token Streaming
describe("Property 2: SSE Token Streaming", () => {
  it("should produce same content by appending tokens or concatenating", () => {
    fc.assert(
      fc.property(
        fc.array(fc.string(), { minLength: 1, maxLength: 50 }),
        (tokens) => {
          // Simulate appending tokens one by one
          let appendedContent = "";
          tokens.forEach((token) => {
            appendedContent += token;
          });
          
          // Concatenate all tokens at once
          const concatenatedContent = tokens.join("");
          
          expect(appendedContent).toBe(concatenatedContent);
        }
      ),
      { numRuns: 100 }
    );
  });
});
```

**Property 7: History Session Grouping**
```typescript
import { describe, it } from "vitest";
import fc from "fast-check";
import { groupSessionsByTime } from "@/lib/utils";

// Feature: frontend-six-feature-transformation, Property 7: History Session Grouping
describe("Property 7: History Session Grouping", () => {
  it("should place each session in exactly one time bucket", () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            id: fc.string(),
            timestamp: fc.date({ min: new Date("2020-01-01"), max: new Date() }).map(d => d.toISOString()),
          })
        ),
        (sessions) => {
          const grouped = groupSessionsByTime(sessions);
          const allGroupedSessions = [
            ...grouped.today,
            ...grouped.yesterday,
            ...grouped.last7Days,
            ...grouped.last30Days,
            ...grouped.older,
          ];
          
          // Each session appears exactly once
          expect(allGroupedSessions.length).toBe(sessions.length);
          
          // No duplicates
          const ids = allGroupedSessions.map(s => s.id);
          expect(new Set(ids).size).toBe(ids.length);
        }
      ),
      { numRuns: 100 }
    );
  });
});
```

**Property 9: API Header Injection**
```typescript
import { describe, it } from "vitest";
import fc from "fast-check";
import { request } from "@/lib/api";

// Feature: frontend-six-feature-transformation, Property 9: API Header Injection
describe("Property 9: API Header Injection", () => {
  it("should inject auth headers and X-Repo-Scope on all API calls", () => {
    fc.assert(
      fc.property(
        fc.string(),
        fc.record({
          subject: fc.string(),
          role: fc.string(),
          tenant_id: fc.string(),
          repo_scope: fc.array(fc.string()),
        }),
        fc.string(),
        async (path, user, activeRepo) => {
          const mockFetch = vi.fn().mockResolvedValue({
            ok: true,
            json: async () => ({}),
          });
          global.fetch = mockFetch;
          
          const authHeaders = {
            "X-Auth-Subject": user.subject,
            "X-Auth-Role": user.role,
            "X-Auth-Tenant-Id": user.tenant_id,
            "X-Auth-Repo-Scope": user.repo_scope.join(","),
          };
          
          await request(path, {}, { ...authHeaders, "X-Repo-Scope": activeRepo });
          
          expect(mockFetch).toHaveBeenCalledWith(
            expect.any(String),
            expect.objectContaining({
              headers: expect.objectContaining({
                ...authHeaders,
                "X-Repo-Scope": activeRepo,
              }),
            })
          );
        }
      ),
      { numRuns: 100 }
    );
  });
});
```

**Property 15: Node Type Filtering**
```typescript
import { describe, it } from "vitest";
import fc from "fast-check";
import { filterGraphNodes } from "@/lib/utils";

// Feature: frontend-six-feature-transformation, Property 15: Node Type Filtering
describe("Property 15: Node Type Filtering", () => {
  it("should filter nodes and edges based on visible types", () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            id: fc.string(),
            type: fc.constantFrom("service", "api", "schema", "database", "queue"),
          })
        ),
        fc.array(
          fc.record({
            id: fc.string(),
            source: fc.string(),
            target: fc.string(),
          })
        ),
        fc.set(fc.constantFrom("service", "api", "schema", "database", "queue")),
        (nodes, edges, visibleTypes) => {
          const { filteredNodes, filteredEdges } = filterGraphNodes(nodes, edges, visibleTypes);
          
          // All filtered nodes have visible types
          filteredNodes.forEach((node) => {
            expect(visibleTypes.has(node.type)).toBe(true);
          });
          
          // All filtered edges connect visible nodes
          const visibleNodeIds = new Set(filteredNodes.map(n => n.id));
          filteredEdges.forEach((edge) => {
            expect(visibleNodeIds.has(edge.source)).toBe(true);
            expect(visibleNodeIds.has(edge.target)).toBe(true);
          });
        }
      ),
      { numRuns: 100 }
    );
  });
});
```

### Unit Test Examples

**Chat Input Component**
```typescript
import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ChatInput } from "@/components/chat/ChatInput";

describe("ChatInput", () => {
  it("should render with placeholder text", () => {
    render(<ChatInput onSend={vi.fn()} />);
    expect(screen.getByPlaceholderText(/Ask anything/i)).toBeInTheDocument();
  });
  
  it("should call onSend when Enter is pressed", () => {
    const onSend = vi.fn();
    render(<ChatInput onSend={onSend} />);
    
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "test message" } });
    fireEvent.keyDown(input, { key: "Enter" });
    
    expect(onSend).toHaveBeenCalledWith("test message");
  });
  
  it("should not call onSend when Shift+Enter is pressed", () => {
    const onSend = vi.fn();
    render(<ChatInput onSend={onSend} />);
    
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "test message" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: true });
    
    expect(onSend).not.toHaveBeenCalled();
  });
  
  it("should disable send button when input is empty", () => {
    render(<ChatInput onSend={vi.fn()} />);
    const button = screen.getByRole("button", { name: /send/i });
    expect(button).toBeDisabled();
  });
});
```

**Waiver Validation**
```typescript
import { describe, it, expect } from "vitest";
import { validateWaiverRequest } from "@/lib/validation";

describe("Waiver Validation", () => {
  it("should reject waiver with no rules selected", () => {
    const waiver = {
      rule_ids: [],
      justification: "This is a valid justification with more than 50 characters.",
      expires_at: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
    };
    
    const result = validateWaiverRequest(waiver);
    expect(result.valid).toBe(false);
    expect(result.errors).toContain("At least one rule must be selected");
  });
  
  it("should reject waiver with short justification", () => {
    const waiver = {
      rule_ids: ["rule-1"],
      justification: "Too short",
      expires_at: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
    };
    
    const result = validateWaiverRequest(waiver);
    expect(result.valid).toBe(false);
    expect(result.errors).toContain("Justification must be at least 50 characters");
  });
  
  it("should reject waiver with expiry > 30 days", () => {
    const waiver = {
      rule_ids: ["rule-1"],
      justification: "This is a valid justification with more than 50 characters.",
      expires_at: new Date(Date.now() + 31 * 24 * 60 * 60 * 1000).toISOString(),
    };
    
    const result = validateWaiverRequest(waiver);
    expect(result.valid).toBe(false);
    expect(result.errors).toContain("Expiry date must be within 30 days");
  });
  
  it("should accept valid waiver", () => {
    const waiver = {
      rule_ids: ["rule-1", "rule-2"],
      justification: "This is a valid justification with more than 50 characters explaining why we need this waiver.",
      expires_at: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
    };
    
    const result = validateWaiverRequest(waiver);
    expect(result.valid).toBe(true);
    expect(result.errors).toHaveLength(0);
  });
});
```

### Integration Tests

Integration tests verify that components work together correctly with React Query, Zustand, and API mocking:

```typescript
import { describe, it, expect } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { GraphPage } from "@/app/(app)/graph/page";

const server = setupServer(
  http.get("/simulation/graph", () => {
    return HttpResponse.json({
      nodes: [
        { id: "1", label: "Service A", type: "service", health_score: 85 },
        { id: "2", label: "Service B", type: "service", health_score: 92 },
      ],
      edges: [
        { id: "e1", source: "1", target: "2", relationship: "depends_on" },
      ],
    });
  })
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("GraphPage Integration", () => {
  it("should fetch and render graph data", async () => {
    const queryClient = new QueryClient();
    
    render(
      <QueryClientProvider client={queryClient}>
        <GraphPage />
      </QueryClientProvider>
    );
    
    await waitFor(() => {
      expect(screen.getByText("Service A")).toBeInTheDocument();
      expect(screen.getByText("Service B")).toBeInTheDocument();
    });
  });
});
```

### Coverage Goals

- **Unit Test Coverage**: Minimum 80% line coverage for all components
- **Property Test Coverage**: All 35 correctness properties must have corresponding property-based tests
- **Integration Test Coverage**: All major user flows (chat conversation, graph exploration, policy run review, blueprint viewing, onboarding completion)

### Running Tests

```bash
# Run all tests
npm test

# Run unit tests only
npm test -- unit

# Run property tests only
npm test -- properties

# Run with coverage
npm test -- --coverage

# Run in watch mode
npm test -- --watch

# Run specific test file
npm test -- chat.properties.test.ts
```

## Appendices Reference

This design document references three appendices defined in the requirements document:

### Appendix A: API Contract

All API endpoints, request/response formats, and authentication requirements are defined in Appendix A of the requirements document. Key points:
- All requests must include Authorization header with Bearer token
- All requests must include X-Repo-Scope header with active repository name
- All endpoints accept and return JSON unless otherwise noted (SSE streams, file downloads)
- SSE endpoints use Server-Sent Events protocol with event types: token, metadata, health_update, alert, activity, policy_run

### Appendix B: Performance Targets

All performance targets are defined in Appendix B of the requirements document. These are acceptance criteria for the delivered implementation:
- Q&A Interface: First streaming token < 500ms, history sidebar < 300ms, suggestion card click < 100ms
- Knowledge Graph: Initial render (200 nodes) < 2s, node click < 300ms, layout switch < 600ms, neighbor fetch < 1s
- Health Dashboard: Metric cards < 1s, chart animation < 1s, activity feed < 1s, SSE events < 500ms
- Policy Status: Run list < 1s, SSE animation < 300ms, waiver modal < 200ms
- Blueprint Viewer: Diagram render < 1.5s, Monaco editor < 500ms, artifact download < 2s
- Onboarding Paths: Role selector < 100ms, stage completion < 100ms, confetti < 200ms

### Appendix C: SSE Reconnection Behavior

All SSE connections follow the reconnection protocol defined in Appendix C:
- Initial connection: Open EventSource, set status to "connected"
- On error: Set status to "disconnected", wait 2s, attempt reconnection
- Exponential backoff: 2s, 4s, 8s, 16s, capped at 30s between attempts
- Maximum attempts: After 10 consecutive failures, stop retrying, set status to "failed"
- Connection indicator: Display "Live updates paused" pill after 5s disconnect
- Cleanup: Close EventSource on unmount, reopen when activeRepo changes

## Implementation Notes

### Build Order (from Requirements 15)

Features must be implemented in this order:
1. Q&A Interface
2. Knowledge Graph
3. Health Dashboard
4. Policy Status
5. Blueprint Viewer
6. Onboarding Paths

Within each feature, implement in this order:
1. Page layout and routing
2. TypeScript types for that feature
3. React Query hooks
4. Main list or primary component
5. Detail or secondary component
6. All sub-components
7. Skeleton loading states
8. Error state components
9. Empty state components

### Critical Requirements

- **No Spinners**: Use skeleton loading states that match real content dimensions - no spinner components anywhere
- **TypeScript Strict Mode**: Pass tsc --noEmit with zero errors and zero warnings
- **No Placeholders**: No placeholder components, TODO comments, or console.log statements in delivered code
- **Minimum Viewport**: Support minimum 1280px viewport width
- **Responsive Breakpoint**: Below 1400px, layouts adjust (sidebars overlay, grids stack)
- **Property-Based Tests**: Minimum 100 iterations per test, tagged with feature name and property number
- **SSE Reconnection**: All SSE connections must implement Appendix C reconnection protocol
- **Performance Compliance**: All interactions must meet Appendix B performance targets

