Requirements Document
Introduction
This specification defines six production-quality frontend features for the KA-CHOW engineering brain platform. The features transform the existing Next.js 14 application into a comprehensive system for Q&A chat, knowledge graph visualization, system health monitoring, CI/CD policy status, architecture blueprint viewing, and onboarding learning paths. All features integrate with the existing global shell (layout, sidebar, auth, Zustand store, API client, command palette, and notification system) and follow consistent patterns for data fetching, loading states, error handling, and responsive design.
All API endpoints referenced in this document conform to the API Contract defined in Appendix A. All performance targets are defined in Appendix B. All SSE behavior including reconnection logic is defined in Appendix C.

Glossary

KA_CHOW_Platform: The autonomous engineering brain platform that provides knowledge graph, architecture assistance, and CI enforcement
Q&A_Interface: The intent-first chat interface for asking questions about the codebase
Knowledge_Graph: The visual representation of services, APIs, schemas, ADRs, engineers, and incidents with their relationships
Health_Dashboard: The system health monitoring interface showing metrics, charts, alerts, and activity
Policy_Status: The CI/CD policy enforcement interface showing policy runs, rules, and waivers
Blueprint_Viewer: The architecture blueprint interface showing design diagrams, rationale, and artifacts
Onboarding_Paths: The role-based learning path interface for new engineers
React_Query: The server state management library (v5) used for all API data fetching
Zustand: The client state management library used only for global UI state
React_Flow: The library used for rendering interactive node-edge graphs
Recharts: The charting library used for all data visualizations
Monaco_Editor: The code editor component used for viewing code artifacts
SSE: Server-Sent Events protocol used for real-time updates
Streaming_Response: Server response that sends data incrementally using SSE token and metadata events
Active_Repo: The currently selected repository from the Zustand session store
X_Repo_Scope: HTTP header containing the active repository, sent with every API call
Skeleton_Loading: Loading state that matches the shape of real content — no spinners permitted anywhere in the application
Empty_State: UI shown when no data exists, with meaningful guidance and a suggested next action
Error_State: UI shown when an error occurs, with a context-specific message derived from the API error body and a retry button
Force_Layout: Graph layout algorithm using d3-force with linkDistance=150, chargeStrength=-400, and 300 synchronous ticks before first render
Tree_Layout: Graph layout algorithm using d3-hierarchy producing a left-to-right hierarchical arrangement, roots defined as nodes with no incoming edges
Radial_Layout: Graph layout algorithm distributing all nodes at equal angles around a center point, radius computed as (nodeCount * 30) clamped to 200-600px
Health_Color_Scale: Color interpolation function: score >= 50 interpolates linearly from #f59e0b (score=50) to #22c55e (score=100); score < 50 interpolates linearly from #ef4444 (score=0) to #f59e0b (score=50)
SSE_Reconnection: Automatic reconnection behavior defined in Appendix C
Waiver: A governance approval that bypasses one or more policy rules for a specified time period
ADR: Architecture Decision Record — a document capturing a significant architectural decision
Drift: The condition where a generated architecture blueprint no longer matches the actual codebase


Requirements
Requirement 1: Q&A Chat Interface
User Story: As a developer, I want to ask questions about the codebase in natural language, so that I can quickly understand architecture, policies, onboarding steps, and impact analysis without searching through documentation.
Acceptance Criteria

THE Q&A_Interface SHALL render at route /qa with full viewport height layout divided into a main chat panel (flexible width) and a 320px history sidebar
THE Q&A_Interface SHALL display the history sidebar in a closed state by default, opening and closing with a smooth 300ms CSS translateX transition when the history icon button is clicked
WHEN the messages array is empty, THE Q&A_Interface SHALL display an Empty_State containing the KA-CHOW logo, the heading "Ask anything about your codebase", the subheading "I have full context of your services, APIs, policies, and architecture decisions", and a 2x4 grid of suggestion cards grouped by intent category (Architecture=blue left border, Policy=amber left border, Onboarding=green left border, Impact=red left border)
THE Q&A_Interface SHALL include the following eight suggestion cards: Architecture — "What does the payments service do?" and "What services depend on the auth service?"; Policy — "Which PRs are currently blocked by policy?" and "Show me active waivers for this repo"; Onboarding — "What should I understand first as a new backend engineer?" and "Who owns the notification service?"; Impact — "What breaks if I deprecate the /v1/users endpoint?" and "What's affected if I change the user_id field type?"
WHEN a suggestion card is clicked, THE Q&A_Interface SHALL immediately call handleSend with the card's question text without requiring any additional user interaction
WHEN a user sends a message, THE Q&A_Interface SHALL display the message right-aligned in a rounded bubble with plain text content and a relative timestamp below
WHEN the assistant responds, THE Q&A_Interface SHALL display the response left-aligned with seven layers rendered in this exact vertical order: (1) intent badge, (2) answer with markdown rendering, (3) confidence bar, (4) source breakdown pills, (5) collapsible citations panel, (6) collapsible chain of thought steps, (7) follow-up suggestion chips
THE intent badge SHALL be a monospace 11px pill displaying the full intent string (e.g. "architecture.trace_dependency"), colored by top-level intent: architecture=blue, policy=amber, impact=red, onboarding=green, general=gray; the badge SHALL only appear after streaming completes
THE answer layer SHALL render markdown using react-markdown with react-syntax-highlighter using the oneDark theme for code blocks; during streaming a blinking cursor (2px wide, 1em tall, opacity alternating 0 to 1 every 500ms via CSS animation) SHALL appear at the end of streamed text and disappear when the metadata event is received
THE confidence bar SHALL be a 4px tall horizontal bar showing the confidence score as a filled proportion; color SHALL follow Health_Color_Scale applied to the confidence score scaled 0-100; a tooltip on hover SHALL display the exact score as a percentage; the bar SHALL only appear after streaming completes
THE source breakdown layer SHALL display horizontal pills with text "{count} from {source_type}" using display names: code="Code" purple tint, docs="Docs" blue tint, adrs="ADRs" amber tint, incidents="Incidents" red tint, specs="API Specs" green tint; SHALL only appear after streaming completes
THE citations panel SHALL be collapsed by default with a toggle button showing "{n} citations"; when expanded it SHALL show each citation as a row containing source_ref in monospace truncated to the last 40 characters prefixed with "..." if longer, a line number badge "L{line}", a two-line excerpt in a left-bordered blockquote, and a clipboard copy button; the panel SHALL have a max-height of 200px with internal scroll; SHALL only appear after streaming completes
THE chain steps section SHALL be collapsed by default with a toggle button labeled "Reasoning"; when expanded it SHALL show each step with its name in bold, input truncated to 60 characters, output truncated to 60 characters, and duration in milliseconds as muted right-aligned text; SHALL only appear after streaming completes
THE follow-up chips layer SHALL be a horizontally scrollable row (overflow-x auto, scrollbar hidden) of pill buttons each with max-width 280px and text truncated with ellipsis; clicking a chip SHALL call handleSend with the chip's question text; SHALL only appear after streaming completes
THE Q&A_Interface SHALL implement streaming by connecting to POST /adapters/web/ask using the Fetch API with ReadableStream; the implementation SHALL use a TextDecoder to read chunks, buffer incomplete lines across chunks, and parse complete lines beginning with "data: " as SSE events
WHEN a streaming event with type "token" is received, THE Q&A_Interface SHALL append event.text to the current assistant message answer string using a useRef to avoid stale closures, triggering a re-render via setState
WHEN a streaming event with type "metadata" is received, THE Q&A_Interface SHALL populate intent, confidence, citations, chain_steps, source_breakdown, and follow_ups on the current message object, mark streaming as complete, hide the cursor, and render all post-stream layers
WHEN the stream closes without a metadata event, THE Q&A_Interface SHALL mark the message as error state and display "Response was incomplete. The service may be under load." with a retry button
THE Q&A_Interface SHALL display a first token within 500ms of sending a request; no skeleton or spinner SHALL appear before the first token
THE Q&A_Interface SHALL auto-scroll the thread to the bottom when new content arrives UNLESS the user has manually scrolled more than 100px above the bottom, detected via a scroll event listener comparing scrollTop + clientHeight to scrollHeight
THE Q&A_Interface SHALL provide an auto-resizing textarea input that grows from 1 row to a maximum of 6 rows, implemented using a hidden div mirror technique
WHEN the textarea is empty or streaming is in progress, THE Q&A_Interface SHALL display a disabled send button
WHEN streaming is in progress, THE Q&A_Interface SHALL display a "Stop" button that calls reader.cancel() on the active stream reader to abort the request
THE Q&A_Interface SHALL display a channel mode pill to the left of the input cycling between "Web" (markdown response) and "CLI Preview" (monospace plain text response) on click; the selected channel SHALL be sent as the channel field in the next request
THE Q&A_Interface SHALL focus the textarea when Cmd+/ (or Ctrl+/ on Windows) is pressed from anywhere on the page, implemented via a document keydown listener in a useEffect
THE history sidebar SHALL fetch sessions from GET /assistant/sessions?repo={activeRepo} and group them by: Today, Yesterday, This Week, Older
WHEN a session item is clicked, THE Q&A_Interface SHALL fetch GET /assistant/sessions/{id}/messages and load the returned messages into the thread
WHEN the delete button on a session item is clicked, THE Q&A_Interface SHALL call DELETE /assistant/sessions/{id} and remove the item from the list with a 200ms fade-out animation
THE history sidebar SHALL provide a "New conversation" button at the top that clears the thread and generates a new session ID in Zustand
THE Q&A_Interface SHALL display Skeleton_Loading states: a full-width gray rectangle 56px tall for each message slot while history is loading
THE Q&A_Interface SHALL display Error_State when the session list or history load fails, with message "Could not load conversation history for {activeRepo}" and a retry button
THE Q&A_Interface SHALL pass Active_Repo as X_Repo_Scope header on all API calls via the existing api.ts client
THE Q&A_Interface SHALL be fully responsive down to 1280px minimum width; below 1400px the history sidebar SHALL overlay the chat panel rather than pushing it


Requirement 2: Knowledge Graph Visualizer
User Story: As a developer, I want to visualize the knowledge graph of services, APIs, schemas, ADRs, engineers, and incidents, so that I can understand system architecture and relationships at a glance.
Acceptance Criteria

THE Knowledge_Graph SHALL render at route /graph with a full-screen React Flow canvas using ReactFlowProvider, with the control panel absolutely positioned top-right (top: 16px, right: 16px) and the detail panel absolutely positioned top-right (top: 0, right: 0, height: 100%)
THE Knowledge_Graph SHALL fetch nodes from GET /graph/nodes?repo={activeRepo} and edges from GET /graph/edges?repo={activeRepo} in parallel using Promise.all inside a single useQuery
WHEN graph data is loaded, THE Knowledge_Graph SHALL compute initial node positions using Force_Layout before first render, so nodes appear in their final positions immediately without visible simulation
THE Knowledge_Graph SHALL render ServiceNode as a 180x72px rounded rectangle (rx=8) with background color computed by Health_Color_Scale applied to health_score; service name in 13px bold white; owner name in 11px white at 70% opacity; a 22px health score badge in the top-right corner with white background and colored text matching the node background; WHEN health_score < 40 the node SHALL display a CSS box-shadow pulse animation cycling from no shadow to "0 0 0 6px {nodeColor}40" over 2 seconds infinite ease-in-out
THE Knowledge_Graph SHALL render APINode as a pill shape (height 28px, border-radius 14px, min-width 100px, max-width 160px) with a colored left section (GET=#3b82f6, POST=#22c55e, PUT=#f59e0b, DELETE=#ef4444, PATCH=#a855f7) displaying the HTTP method in 9px bold white, and the path in 11px monospace in the right section
THE Knowledge_Graph SHALL render SchemaNode as an 80x80px div with CSS transform rotate(45deg) applied to the container and transform rotate(-45deg) applied to the content wrapper so text remains readable; label in 11px centered
THE Knowledge_Graph SHALL render ADRNode as a 100x64px rectangle with a folded top-right corner implemented as a CSS ::before pseudo-element (12x12px triangle, background matching the parent, positioned absolute top-right); ADR number in bold and title truncated to 20 characters below
THE Knowledge_Graph SHALL render EngineerNode as a 52px diameter circle with background color deterministically selected from 8 predefined colors using a hash of the engineer name; initials (first letter of first and last name) in 16px bold white; 2px white border
THE Knowledge_Graph SHALL render IncidentNode as a 60x52px warning triangle implemented using CSS clip-path: polygon(50% 0%, 0% 100%, 100% 100%); background #ef4444 for critical severity, #f59e0b for warning severity; a white exclamation mark in the center
THE Knowledge_Graph SHALL render DependencyEdge as a solid 1.5px #6b7280 line with an arrow marker at the target end
THE Knowledge_Graph SHALL render OwnershipEdge as a stroke-dasharray(6 3) 1.5px #3b82f6 line with no arrow markers
THE Knowledge_Graph SHALL render CausalityEdge as a stroke-dasharray(2 2) 1.5px #f59e0b line with arrow markers at both ends
WHEN a node is clicked, THE Knowledge_Graph SHALL set selectedNodeId in local state and open the detail panel with a 300ms translateX(0) transition from translateX(100%)
WHEN the same node is clicked again while the detail panel is open, THE Knowledge_Graph SHALL close the detail panel
WHEN a node is double-clicked, THE Knowledge_Graph SHALL call React Flow's fitView centered on that node with padding=0.3 and duration=600ms, then fetch GET /graph/neighbors/{node_id}?depth=1 and add the returned nodes and edges to the graph state; new nodes SHALL animate from hidden to visible using React Flow's isHidden property
WHEN a node is hovered, THE Knowledge_Graph SHALL set the opacity of all non-connected nodes to 0.15 and all non-connected edges to 0.1 via React Flow's node and edge style props; WHEN hover ends all opacities SHALL reset to 1
THE control panel SHALL provide node type toggles as icon+label buttons for each of the six node types; toggling SHALL set the corresponding node type to hidden in React Flow state without removing nodes from the data array
THE control panel SHALL provide a health filter range slider (0-100, default=0) that hides nodes with health_score below the slider value; nodes without a health_score (APINode, ADRNode, EngineerNode, IncidentNode) SHALL be unaffected by the slider; an "Unhealthy only" button SHALL set the slider to 60 and show only nodes with health_score below 60
THE control panel SHALL provide a search text input (debounced 200ms) that sets opacity of non-matching nodes to 0.1 and applies a 2px blue highlight ring to matching nodes via React Flow node styles; a clear button SHALL appear when the input has content
THE control panel SHALL provide three layout mode buttons: Force (Force_Layout), Tree (Tree_Layout), Radial (Radial_Layout); switching layout SHALL animate all nodes from current positions to new positions over 600ms using requestAnimationFrame interpolation
THE control panel SHALL provide a minimap toggle button that shows and hides the React Flow MiniMap component positioned at bottom-left
THE detail panel for ServiceNode SHALL display: service name as h2, owner with a 32px avatar circle showing initials, health score as a large number colored by Health_Color_Scale, four mini horizontal progress bars labeled "API Docs / Architecture Decisions / Incident Postmortems / Code Comments" each 0-100% colored by their own percentage, last updated as relative time, a "Depends on ({n})" section of clickable chips that select the target node in the graph, a "Used by ({n})" section of clickable chips, a linked ADRs list with ADR number and status badge, a linked incidents list with severity badge and title, an "Ask about this" button that navigates to /qa with question pre-filled as "What does the {service_name} service do?", and a "View health history" button that opens a Recharts LineChart popover showing this service's health_score over the last 30 days
THE detail panel for APINode SHALL display: HTTP method badge, full path, description if available, a parameters table with columns name/type/required/description, a response codes list, and a parent service chip that selects the parent ServiceNode when clicked
THE detail panel for ADRNode SHALL display: ADR number and title, status badge (proposed/accepted/superseded/deprecated), decision summary paragraph, consequences as a bulleted list, affected services as clickable chips, date created and last modified
THE detail panel for EngineerNode SHALL display: 64px avatar circle with initials, name as heading, role as subheading, owned services as clickable chips, expertise tags as pills, and a list of the last five activity events for this engineer
THE detail panel SHALL close when the X button is clicked or when the Escape key is pressed
THE Knowledge_Graph SHALL display Skeleton_Loading as circular placeholder nodes (matching EngineerNode diameter) and rectangular placeholders (matching ServiceNode dimensions) connected by line placeholders while graph data is loading
THE Knowledge_Graph SHALL display Error_State when graph data fails to load, with the message "The knowledge graph for {activeRepo} hasn't been indexed yet" if the API returns 404, or "Failed to load the knowledge graph. Check your connection." for other errors, with a retry button in both cases
THE Knowledge_Graph SHALL pass Active_Repo as X_Repo_Scope header on all API calls
THE Knowledge_Graph SHALL be fully responsive down to 1280px minimum width; the detail panel SHALL reduce to 320px width below 1400px


Requirement 3: System Health Dashboard
User Story: As an engineering manager, I want to monitor system health metrics, coverage, documentation gaps, and activity, so that I can identify issues and track improvements over time.
Acceptance Criteria

THE Health_Dashboard SHALL render at route /health using CSS Grid with the following row structure: Row 1 — four equal-width metric cards (grid-template-columns: repeat(4, 1fr)); Row 2 — health score chart and alerts panel (grid-template-columns: 3fr 2fr); Row 3 — coverage chart and gap heatmap (grid-template-columns: 1fr 1fr); Row 4 — activity feed (grid-template-columns: 1fr); all rows separated by 16px gap
THE Health_Dashboard SHALL display four MetricCard components in Row 1 with the following content: (1) Knowledge Health Score — latest score from GET /health/snapshots?repo={activeRepo}&limit=1, trend vs 7 days ago, accent colored by Health_Color_Scale; (2) Services Coverage — "{documented} / {total} documented" from GET /health/coverage?repo={activeRepo}, trend as coverage percentage change vs last week; (3) Documentation Gaps — open gap count from GET /health/gaps?repo={activeRepo}&status=open, trend as change in open gaps vs last week, accent red if >10, amber if 5-10, green if <5, with an action link "View gaps" that navigates to /graph with the undocumented filter active; (4) CI Pass Rate — pass percentage from GET /policy/runs/stats?repo={activeRepo}&days=7, with a 60x24px inline Recharts LineChart sparkline showing daily pass rates with no axes
EACH MetricCard SHALL display: a 3px colored left border, the primary value in 48px font-weight-700, the label in 14px muted text, a trend indicator with an up or down arrow icon and percentage text formatted as "+{n}% vs last week", colored green if the trend is positive for the metric and red if negative
THE health score chart SHALL be a Recharts AreaChart with width=100% and height=280px; XAxis dataKey="date" formatted as "Jan 15" with tickLine=false and axisLine=false; YAxis domain=[0,100] with ticks at [0,25,50,75,100] and tickLine=false and axisLine=false; CartesianGrid with horizontal lines only and strokeDasharray="3 3"; Area strokeWidth=2 with dot=false and activeDot radius=4; fill computed as a linearGradient from the stroke color at 30% opacity at the top stop to transparent at the bottom stop; animationDuration=1000 and animationEasing="ease-out"
THE health score chart area stroke color SHALL be computed by Health_Color_Scale applied to the latest score value
THE health score chart SHALL display two ReferenceLine components: y=80 with stroke amber and strokeDasharray="4 2" labeled "Target" right-aligned, and y=50 with stroke red and strokeDasharray="4 2" labeled "Warning" right-aligned
WHEN any 7-day window in the health score chart data shows a score drop greater than 15 points, THE Health_Dashboard SHALL render a Recharts ReferenceArea component spanning that window with a red fill at 15% opacity
THE coverage chart SHALL be a Recharts BarChart with layout="vertical" and width=100% and height computed as (serviceCount * 32) clamped to a minimum of 200px and maximum of 500px; data sorted by coverage percentage ascending so the worst-covered service appears at the top; each bar colored by Health_Color_Scale applied to the coverage percentage; YAxis showing service names in 12px right-aligned text truncated to 20 characters; XAxis showing 0-100% with percentage labels; tooltip showing service name and exact coverage percentage; onClick navigating to /graph with that service's node selected
THE coverage chart SHALL show the top 15 services by default with a "Show all {n} services" button below that re-renders with the full dataset when clicked
THE gap heatmap SHALL be a custom SVG component with 53 columns (weeks) and 7 rows (days Monday through Sunday); each cell SHALL be a 12x12px rect with 3px gap between cells; month labels SHALL appear above the first column of each month; day labels "M", "W", "F" SHALL appear to the left of rows 1, 3, 5; the SVG SHALL be horizontally scrollable on overflow
THE gap heatmap cell color scale SHALL be: 0 gaps = #ebedf0 in light mode / #161b22 in dark mode; 1-2 gaps = #9be9a8 / #0e4429; 3-5 gaps = #40c463 / #006d32; 6-10 gaps = #30a14e / #26a641; 11+ gaps = #216e39 / #39d353; dark mode SHALL be detected via matchMedia("(prefers-color-scheme: dark)")
WHEN a gap heatmap cell is hovered, THE Health_Dashboard SHALL display a floating tooltip (position fixed, following the mouse cursor) showing "{n} gaps on {date formatted as 'January 15, 2025'}"
WHEN a gap heatmap cell is clicked, THE Health_Dashboard SHALL navigate to /policy filtered to that date
THE alerts panel SHALL fetch from GET /reporting/alerts?repo={activeRepo}&status=active and sort alerts by severity (critical first, then warning, then info) then by timestamp descending within each severity group
EACH alert row SHALL display: a severity badge (CRITICAL=red, WARNING=amber, INFO=blue), the alert message with the entity name in bold inline, a clickable entity link navigating to the relevant page, the time since the alert was triggered as relative time, and a dismiss button
WHEN the dismiss button is clicked, THE Health_Dashboard SHALL call POST /reporting/alerts/{id}/dismiss and remove the alert from the list with a 200ms slide-up-and-fade animation
CRITICAL alerts SHALL display a pulsing red left border animation cycling from 3px solid #ef4444 to 3px solid #ef444440 over 1.5 seconds infinite
WHEN no active alerts exist, THE alerts panel SHALL display "All clear — no active alerts for {activeRepo}" with a green checkmark icon centered in the panel
THE activity feed SHALL use useInfiniteQuery fetching GET /reporting/activity?repo={activeRepo}&limit=20&cursor={cursor} and SHALL be virtualized using @tanstack/react-virtual with container height=400px and dynamic row height measurement via measureElement (56px collapsed, 120px expanded)
EACH activity row SHALL display: a 32x32px icon circle colored by event type on the left, event description with bold entity name and muted action text in the center, a repo badge and relative timestamp, and a chevron icon indicating expandability; clicking the row SHALL expand it inline showing the full event payload as syntax-colored JSON in a monospace block, with 200ms max-height CSS transition
THE event type to icon to color mapping SHALL be: doc_refresh_completed=green checkmark circle; doc_rewrite_generated=blue sparkle; ci_check_run=gray CI icon; waiver_granted=amber shield; health_score_changed=colored trend arrow (green if score increased, red if decreased); policy_blocked=red X circle; doc_gap_detected=orange warning triangle
WHEN the IntersectionObserver sentinel div at the bottom of the activity feed enters the viewport, THE Health_Dashboard SHALL call fetchNextPage from useInfiniteQuery
THE Health_Dashboard SHALL mount a useHealthStream hook in a useEffect that opens an EventSource to GET /reporting/stream?repo={activeRepo}; WHEN a "health_update" event is received it SHALL invalidate the ["health","snapshots"] React Query cache and push a notification via UISlice if the score dropped more than 5 points; WHEN an "alert" event is received it SHALL invalidate ["health","alerts"] and push a notification; WHEN an "activity" event is received it SHALL prepend the event to the activity feed via queryClient.setQueryData; the EventSource SHALL be closed and reopened when activeRepo changes; SSE reconnection SHALL follow Appendix C
THE Health_Dashboard SHALL display Skeleton_Loading: four MetricCard skeletons (a 48px tall rectangle for the value, a 16px rectangle for the label, a 12px rectangle for the trend), an AreaChart skeleton (a gray rectangle matching the chart dimensions), and five activity row skeletons (five 56px rectangles with varying-width inner rectangles)
THE Health_Dashboard SHALL display Error_State per panel: if the health snapshot fetch fails, show "Health data unavailable for {activeRepo}" with a retry button inside the chart panel; if the alerts fetch fails, show "Could not load alerts" with a retry button inside the alerts panel
THE Health_Dashboard SHALL pass Active_Repo as X_Repo_Scope header on all API calls
THE Health_Dashboard SHALL be fully responsive down to 1280px minimum width; below 1400px Row 2 and Row 3 SHALL stack vertically (single column)


Requirement 4: CI/CD Policy Status
User Story: As a developer, I want to view CI/CD policy check results, understand rule failures, and request waivers, so that I can ensure my pull requests meet quality standards or get exceptions when needed.
Acceptance Criteria

THE Policy_Status SHALL render at route /policy using CSS Grid with grid-template-columns: 380px 1fr; below 1400px the layout SHALL stack vertically with the list on top
THE Policy_Status SHALL display a filter bar above the run list with four controls: (1) an outcome segmented control with options All / Pass / Warn / Block each with a matching colored dot; (2) a ruleset dropdown populated from GET /policy/rulesets?repo={activeRepo} with an "All rulesets" default; (3) a date range selector with buttons Today / Last 7 days / Last 30 days and a Custom option opening a popover with two calendar inputs; (4) a search text input filtering by PR number or branch name
ALL filter values SHALL be reflected in URL query parameters using useSearchParams from next/navigation so filter state persists on page refresh and URLs are shareable
THE policy run list SHALL use useInfiniteQuery fetching GET /policy/runs?repo={activeRepo}&outcome=&ruleset=&from=&to=&search=&limit=25&cursor= with an IntersectionObserver sentinel div triggering fetchNextPage
EACH policy run row (56px tall) SHALL display: repo name in 12px muted text, PR number as "#123" formatted text that opens the GitHub PR URL in a new tab with an external link icon, branch name in a monospace pill truncated to 20 characters, ruleset as a small gray badge, outcome badge (PASS=green, WARN=amber, BLOCK=red, all caps 10px bold rounded), merge gate as a lock icon (red=locked, green=unlocked), and timestamp as relative time
THE selected policy run row SHALL display a 3px blue left border and a slightly elevated background color
THE Policy_Status SHALL open an EventSource to GET /policy/stream?repo={activeRepo}; WHEN a "policy_run" event is received the new run SHALL be prepended to the top of the list via queryClient.setQueryData and SHALL animate in with a 300ms slide-down-from-above animation (transform translateY(-10px) to translateY(0), opacity 0 to 1)
THE detail panel SHALL display "Select a policy run to view details" centered vertically and horizontally when no run is selected
THE merge gate banner SHALL span the full width at the top of the detail panel with three states: BLOCKED — red background, white bold text "This PR is blocked from merging", a bulleted list of blocking items each with a fix link, and a "Request waiver" button on the right; WARNED — amber background, "This PR has warnings that should be resolved", same bullet list treatment; OPEN — green background, "This PR is clear to merge", last check timestamp
THE PR header SHALL display below the banner: PR title, branch name with a right-arrow separator and repo name, ruleset badge, and timestamp
THE rules section SHALL display three collapsible accordion groups labeled "Failed ({n})", "Warned ({n})", "Passed ({n})"; the Failed group SHALL be expanded by default and the others collapsed; each failed rule accordion item SHALL display on the header: rule name and a red X badge with a chevron; when expanded it SHALL display: "What's missing" as plain text, "How to fix" as a numbered step list where each step may include a link, a "View documentation gap" button navigating to /graph if fix_url exists, and a "Create waiver for this rule" button opening WaiverModal pre-filled with that rule
THE patches section SHALL be a collapsible section labeled "Suggested Patches ({n})" shown only when suggested_patches.length > 0; each patch SHALL display the file path in monospace and a unified diff using react-diff-viewer-continued with splitView=false and showDiffOnly=true; an "Apply patch" button SHALL call POST /policy/patches/{id}/apply
THE doc refresh plan section SHALL display "Documentation updates triggered" as heading and list each triggered refresh job with service name, refresh type badge, and a status badge (queued/running/completed/failed)
THE waiver section SHALL display when a waiver exists: an "Applied" amber badge, requested by with avatar and name, approved by with avatar and name, rules bypassed as a comma-separated list, expiry date colored red if within 7 days, and an expandable justification paragraph; WHEN no waiver exists and outcome is block or warn, a "Request a waiver" button SHALL open WaiverModal
THE WaiverModal SHALL be a shadcn Dialog with the following fields: rule being waived as a read-only pre-filled select; justification textarea with a character counter showing "{n}/50 minimum" in red text when below 50 characters; expiry date picker defaulting to 7 days from today with a maximum of 30 days from today
WHEN the WaiverModal submit button is clicked, THE Policy_Status SHALL validate all fields client-side before submitting; the submit button SHALL show a loading state during the POST /governance/waivers request; on success it SHALL close the modal, push a success notification, and invalidate the policy run query; on error it SHALL display the API error message inline below the submit button
THE waiver management tab SHALL be accessible from a tab control at the top of the /policy page alongside the main runs view; it SHALL contain two sub-tabs: Active and Expired; each sub-tab SHALL display a table with columns: Requested by (avatar + name), Approved by (avatar + name or "Pending approval" badge), Rules bypassed (comma list truncated to 40 characters with a tooltip showing full text on hover), Repo, Expiry (red text if active waiver expires within 7 days), Status badge; active waivers SHALL have a Revoke button calling DELETE /governance/waivers/{id}
THE Policy_Status SHALL display Skeleton_Loading: five 56px row skeletons in the list each containing five rectangles of varying widths; a full-width rectangle matching the banner height in the detail panel; three accordion header skeletons in the rules section
THE Policy_Status SHALL display Error_State when the run list fails to load, with message "No policy runs found for {activeRepo} in the selected date range" for empty results and "Failed to load policy runs. Check your connection." for network errors, each with a retry button
THE Policy_Status SHALL pass Active_Repo as X_Repo_Scope header on all API calls
THE Policy_Status SHALL be fully responsive down to 1280px minimum width


Requirement 5: Architecture Blueprint Viewer
User Story: As an architect, I want to view architecture blueprints with design diagrams, rationale, and artifacts, so that I can understand approved patterns and check alignment with actual implementation.
Acceptance Criteria

THE Blueprint_Viewer SHALL render at route /blueprints using CSS Grid with grid-template-columns: 340px 1fr; a header above both panels SHALL display "Architecture Blueprints" and a "New Blueprint" button navigating to /blueprints/new
THE blueprint list filter bar SHALL contain: a pattern type multi-select dropdown populated from distinct pattern values in the list data; a date range selector matching the Policy_Status date range control; an alignment toggle with options All / Aligned / Drifted
EACH blueprint card SHALL display: requirement text truncated to 2 lines with ellipsis; a pattern badge colored by pattern type (Microservices=blue, Monolith=gray, CQRS=purple, BFF=green, Saga=amber, Event-driven=orange); service count as "{n} services" with a grid icon; date as relative time; an alignment indicator (green dot + "Aligned" or red dot + "Drifted"); the selected card SHALL display a 3px blue left border
THE alignment banner SHALL appear at the top of the detail panel in two states: Aligned — green background, checkmark icon, "Blueprint is aligned with the current codebase", last checked timestamp; Drifted — red background, warning icon, "Blueprint has drifted from the codebase", drift_summary text, specific callout chips for each drift item formatted as "{service_name} was added to codebase but not in blueprint" or "{service_name} was removed from codebase", and a "Re-analyze alignment" button calling POST /blueprints/{id}/analyze that shows a loading state and invalidates the blueprint query on completion
THE detail panel SHALL display three tabs: Design, Rationale, Artifacts
THE Design tab SHALL render a React Flow diagram using a separate ReactFlowProvider instance; initial layout SHALL be computed using the dagre library (@dagrejs/dagre) with direction="LR" (left to right); React Flow controls (zoom in/out, fit view) SHALL be enabled; no minimap is required for blueprints
THE Design tab SHALL render BlueprintServiceNode as a 180x72px rounded rectangle with a tech stack badge (e.g., "Node.js", "Python", "Go") in the bottom-left corner; clicking a BlueprintServiceNode SHALL open a popover (not a side panel) showing: tech stack with icon, one-sentence role description, API surface as endpoint count, key data schema fields as a list, and Kubernetes resource requests as CPU request/limit and Memory request/limit
THE Design tab SHALL render DatabaseNode as a cylinder shape implemented with a rectangle with border-radius applied to top and bottom and a CSS ::before ellipse pseudo-element on top, 100px wide and 64px tall, gray background, database icon, and a database type badge (Postgres/Redis/MongoDB/etc.)
THE Design tab SHALL render ExternalNode as a cloud shape using CSS clip-path, with muted border and lighter background, displaying the external service name
THE Design tab SHALL render edges with distinct visual styles: REST — solid 1.5px blue line with arrow at target and "REST" label in 10px text; gRPC — solid 1.5px purple line with arrow at target and "gRPC" label; Async — 1.5px dashed orange line with "async" label; Database — 1px gray dotted line with no arrow and no label
THE Rationale tab SHALL display a two-column layout with decisions occupying 65% of the width on the left and a constraints sidebar occupying 35% on the right
THE constraints sidebar SHALL display each constraint as a pill with: a type icon (scale=chart icon, team_size=people icon, compliance=shield icon, latency=clock icon, existing_tech=code icon) and the constraint text
WHEN a constraint pill in the sidebar is hovered or clicked, THE Blueprint_Viewer SHALL apply a blue glow border (box-shadow: 0 0 0 2px #3b82f6) to all decision cards that reference that constraint
EACH decision card SHALL display: decision title as a heading, "What was decided" section, "Why" section as a paragraph, a "Constraint driver" section showing chips for each linked constraint (clicking a chip scrolls to and briefly pulses that constraint in the sidebar), a collapsible "Alternatives considered" section listing each alternative with name and rejection reason in muted text, and a confidence badge in the top-right corner colored green if >= 80%, amber if 50-79%, red if < 50%
WHEN a constraint driver chip on a decision card is clicked, THE Blueprint_Viewer SHALL scroll the constraints sidebar to the referenced constraint and apply a 600ms pulse animation (background color flash from highlighted to normal)
THE Artifacts tab SHALL display a two-column layout: a 200px file tree on the left and a Monaco_Editor filling the remaining width on the right
THE file tree SHALL display the artifact hierarchy in this structure: /services/{service_name}/Dockerfile, /services/{service_name}/k8s/deployment.yaml, /services/{service_name}/k8s/service.yaml, /api/{service_name}/openapi.yaml, /proto/{service_name}.proto; folder nodes SHALL be expandable with a chevron toggle; all folders SHALL be expanded by default; clicking a file node SHALL select that file and load its content
THE Monaco_Editor SHALL be configured with: theme="vs-dark" always regardless of app color mode; readOnly=true; language auto-detected from extension (yaml/yml=yaml, Dockerfile=dockerfile, .proto=proto, .json=json, .ts=typescript, .py=python, .go=go); minimap enabled; lineNumbers="on"; wordWrap="on"; scrollBeyondLastLine=false; fontSize=13; content fetched from GET /blueprints/{id}/artifacts/{file_path} with a Skeleton_Loading gray rectangle matching the editor dimensions while loading
THE Artifacts tab SHALL display a "Download all artifacts" button in the top-right above the editor that calls GET /blueprints/{id}/artifacts/download; the response SHALL be handled by creating a Blob URL, creating a temporary anchor element with a download attribute, programmatically clicking it, and revoking the Blob URL after download starts; the button SHALL display a loading state during the request
THE Blueprint_Viewer SHALL display Skeleton_Loading: three blueprint card skeletons in the list (two rectangles of varying width per card), a full-width banner skeleton, and three tab content skeletons matching the structure of each tab
THE Blueprint_Viewer SHALL display Error_State when blueprint data fails, with message "No blueprints found for {activeRepo}" for empty results and "Failed to load blueprint details." for fetch errors, each with a retry button
THE Blueprint_Viewer SHALL pass Active_Repo as X_Repo_Scope header on all API calls
THE Blueprint_Viewer SHALL be fully responsive down to 1280px minimum width; below 1400px the list panel SHALL reduce to 280px


Requirement 6: Onboarding Learning Paths
User Story: As a new engineer, I want to follow a role-based learning path with documentation, key services, ADRs, and starter tasks, so that I can onboard efficiently and understand the codebase.
Acceptance Criteria

THE Onboarding_Paths SHALL render at route /onboarding
WHEN userRole in Zustand is null, THE Onboarding_Paths SHALL display a full-screen overlay (not a modal) replacing the page content, containing: the KA-CHOW logo, the heading "Welcome to {activeRepo}", the subheading "What's your role on this team? I'll build a personalized learning path for you.", and five role cards in a responsive grid (3 columns above 1400px, 2 columns above 1280px)
THE five role cards SHALL be: Backend Engineer ("Services, APIs, data schemas, and system dependencies"), SRE ("Infrastructure, incident patterns, runbooks, and reliability decisions"), Frontend Developer ("API contracts, BFF patterns, and frontend-relevant services"), Data Engineer ("Data schemas, pipeline services, and data flow dependencies"), Engineering Manager ("Team ownership, service health, and architectural decisions"); each card SHALL display a role icon, role name, and description; hovering SHALL apply a subtle box-shadow and border color change
WHEN a role card is clicked, THE Onboarding_Paths SHALL save the role to Zustand userRole, call POST /onboarding/role with { role, user_id: sessionId, repo: activeRepo }, and dismiss the overlay with a 300ms fade-out transition
WHEN userRole is already set, THE Onboarding_Paths SHALL display a "Change role" button in the top-right of the page that opens a dropdown to switch roles; switching SHALL call the same endpoint and invalidate the onboarding path query
THE learning path progress SHALL fetch from GET /onboarding/path?repo={activeRepo}&role={userRole} and display a horizontally scrollable stage track; stages SHALL be connected by a two-layer line: a full-width 2px muted gray background line and a 2px green progress line that fills from left to right based on the proportion of completed stages, animated with a CSS width transition when a stage completes
EACH stage card (200px wide, 100px tall) SHALL display one of three visual states: Completed — green subtle background, checkmark icon top-right, stage title, "Completed" in green muted text, fully clickable; Current — white background with blue border, pulsing blue dot top-right (CSS animation: scale 1 to 1.4 to 1 over 1.5s infinite), stage title, resource count, estimated time in minutes; Future (locked) — gray background at 50% opacity, lock icon top-right, stage title visible, non-clickable with tooltip "Complete previous stages first" on hover
THE active stage SHALL display a downward arrow indicator connecting the stage card to the StageDetail section below
THE StageDetail SHALL display four sections: Documentation Resources, Key Services, Relevant ADRs, Starter Task
THE Documentation Resources section SHALL list each resource with: a colored source-type icon on the left, document title in bold and source service as a muted breadcrumb "{repo} / {service}" in the center, estimated read time as "~{n} min read", a read checkbox on the right that when checked calls POST /onboarding/progress/resource with the resource_id and updates a completion progress bar at the bottom of the section showing "{read_count} of {total} read", and an "Ask about this" button that navigates to /qa with input pre-filled as "Explain {doc_title} and why it matters for a {userRole} on the {activeRepo} team"
THE Key Services section SHALL display a 2-column grid of service cards each showing: service name in bold, one-line role description truncated with ellipsis, health score badge colored by Health_Color_Scale, a "View in graph" button navigating to /graph with selectedNodeId set to that service via URL parameter, and an "Ask about this" button navigating to /qa with input pre-filled as "What does the {service_name} service do and how does it relate to my work as a {userRole}?"
THE Relevant ADRs section SHALL list each ADR with: ADR number badge, title, status badge (accepted/superseded/deprecated), affected services as chips, a role-specific "Why this matters for you" explanation from the API response, and an expandable section showing full decision summary and consequences; an "Ask about this ADR" button SHALL navigate to /qa with input pre-filled as "Explain ADR-{number} and what I need to know about it as a {userRole}"
THE Starter Task section SHALL display a single featured card with: GitHub issue number and title as heading, issue labels as colored chips, a complexity indicator (Good first issue=green, Medium=amber, Complex=red), the first 200 characters of the issue description, skills involved as tags, an "Open issue" button opening the GitHub issue URL in a new tab, and a "Get context" button navigating to /qa with input pre-filled as "Give me full context on issue #{number} in {activeRepo}. What do I need to understand to work on this as a {userRole}? What services are involved?"
WHEN no starter task is available, THE Onboarding_Paths SHALL display "No starter tasks assigned yet. Ask your manager to link issues to your learning path." in the Starter Task section
THE TeammateMap SHALL display below the StageDetail and SHALL always be visible (not behind a tab); it SHALL fetch engineers relevant to the current stage and display a 3-column grid of engineer cards each showing: a 56px avatar circle with initials and hashed background color, name in bold, role in muted text, owned services as chips filtered to only those relevant to the current stage, expertise tags as pills, and a "View in graph" link navigating to /graph with that engineer's EngineerNode selected
THE "Mark this stage complete" button SHALL appear at the bottom of the StageDetail only for the current active stage; clicking it SHALL display a shadcn AlertDialog with "Are you sure? This will unlock the next stage." and Confirm / Cancel buttons
WHEN completion is confirmed, THE Onboarding_Paths SHALL optimistically update the stage to completed state in the React Query cache before the POST /onboarding/progress request resolves, using queryClient.setQueryData; the request payload SHALL be { stage_id, user_id, repo, completed_at: new Date().toISOString() }; if the request fails the optimistic update SHALL be rolled back using the onError callback
WHEN a stage completes, THE Onboarding_Paths SHALL animate the completed stage card to the completed visual state and the next stage card to the current visual state, and grow the progress line width via CSS transition
WHEN the final stage is completed, THE Onboarding_Paths SHALL fire a canvas-confetti animation with count=200, spread=70, origin={ y: 0.6 } and then display a completion card showing: "You've completed the onboarding path for {activeRepo}!", a summary of stages completed and resources read, a "Start contributing" button navigating to /qa, and a "View your team's graph" button navigating to /graph
THE Onboarding_Paths SHALL display Skeleton_Loading: five role card skeletons (matching card dimensions) in the role selector; five stage card skeletons (200x100px rectangles) in the progress track; and section skeletons in the StageDetail matching the structure of each section (three resource row skeletons, four service card skeletons, three ADR row skeletons, one large task card skeleton)
THE Onboarding_Paths SHALL display Error_State when the learning path fails to load, with message "Could not load your learning path for {activeRepo}. Try selecting your role again." with a retry button and a "Change role" secondary button
THE Onboarding_Paths SHALL pass Active_Repo as X_Repo_Scope header on all API calls
THE Onboarding_Paths SHALL be fully responsive down to 1280px minimum width


Requirement 7: TypeScript Type Safety
User Story: As a developer, I want full TypeScript type safety across all features, so that I can catch errors at compile time and have better IDE support.
Acceptance Criteria

THE KA_CHOW_Platform SHALL define TypeScript interfaces for all API request and response types in lib/types.ts
THE KA_CHOW_Platform SHALL define TypeScript interfaces for all component props using the naming convention {ComponentName}Props
THE KA_CHOW_Platform SHALL define TypeScript types for all Zustand store slices in store/slices/
THE KA_CHOW_Platform SHALL define typed return values for all React Query hooks using the useQuery generic parameter
THE KA_CHOW_Platform SHALL not use the any type except where required by React Flow's NodeProps and EdgeProps generics, which SHALL be immediately narrowed using a type assertion inside the component
THE KA_CHOW_Platform SHALL pass tsc --noEmit with zero errors and zero warnings


Requirement 8: Data Fetching Patterns
User Story: As a developer, I want consistent data fetching patterns using React Query, so that I have predictable caching, loading states, and error handling across all features.
Acceptance Criteria

THE KA_CHOW_Platform SHALL use React_Query useQuery and useInfiniteQuery for all server state; no fetch calls SHALL be made outside of React Query query functions except for the streaming chat endpoint and SSE connections
THE KA_CHOW_Platform SHALL use Zustand only for: activeRepo, sessionId, userId, userRole, commandPaletteOpen, sidebarCollapsed, and activeNotifications; all other state SHALL be component-local or React Query cache
ALL API calls SHALL include the Authorization header from the session token and the X-Repo-Scope header from activeRepo, injected via the existing api.ts client's request interceptor
WHEN activeRepo changes, THE KA_CHOW_Platform SHALL call queryClient.invalidateQueries() with no arguments to invalidate all cached queries simultaneously
ALL data-fetching components SHALL implement Skeleton_Loading states whose shapes match the real content dimensions to within 10px
ALL data-fetching components SHALL implement Error_State with a message derived from the API response error body when available, or a context-specific fallback message when not, plus a retry button calling refetch()
ALL list and graph views SHALL implement Empty_State with a meaningful message explaining why no data exists and a suggested next action
No spinner components SHALL appear anywhere in the application


Requirement 9: Responsive Design
User Story: As a developer, I want all features to be fully responsive, so that I can use the platform on different screen sizes.
Acceptance Criteria

THE KA_CHOW_Platform SHALL support a minimum viewport width of 1280px; content SHALL not overflow or clip at this width
AT viewport widths below 1400px: the Knowledge_Graph detail panel SHALL reduce from 400px to 320px; the Health_Dashboard Rows 2 and 3 SHALL stack to single column; the Policy_Status SHALL stack list above detail; the Blueprint_Viewer list panel SHALL reduce from 340px to 280px; the Q&A_Interface history sidebar SHALL overlay the chat panel rather than pushing it
ALL text SHALL remain readable at all supported widths — minimum font size 11px, no text overflow clipping except where truncation with ellipsis is explicitly specified


Requirement 10: Real-Time Updates
User Story: As a developer, I want real-time updates for health metrics, policy runs, and activity, so that I see the latest information without manual refresh.
Acceptance Criteria

THE Health_Dashboard SHALL implement an SSE connection to GET /reporting/stream?repo={activeRepo} handling events: health_update, alert, and activity as specified in Requirement 3
THE Policy_Status SHALL implement an SSE connection to GET /policy/stream?repo={activeRepo} handling the policy_run event as specified in Requirement 4
ALL SSE connections SHALL implement the reconnection behavior defined in Appendix C
WHEN an SSE connection is disconnected for more than 5 seconds, THE KA_CHOW_Platform SHALL display a "Live updates paused" pill indicator in the bottom-left of the affected page; the pill SHALL disappear automatically when the connection is restored


Requirement 11: Streaming Chat Responses
User Story: As a developer, I want to see chat responses stream in real-time, so that I get immediate feedback and can read answers as they are generated.
Acceptance Criteria

THE Q&A_Interface SHALL connect to POST /adapters/web/ask using the Fetch API with ReadableStream as specified in Requirement 1
THE Q&A_Interface SHALL parse SSE events using a TextDecoder, buffering incomplete lines across chunks, and processing lines beginning with "data: " as JSON
WHEN a token event is received, THE Q&A_Interface SHALL append event.text to the current message using a useRef
WHEN a metadata event is received, THE Q&A_Interface SHALL finalize the message with all metadata fields and hide the streaming cursor
WHEN the stop button is clicked, THE Q&A_Interface SHALL call reader.cancel() and mark the current message as complete with whatever content has streamed so far
WHEN the stream closes without a metadata event, THE Q&A_Interface SHALL display "Response was incomplete. The service may be under load." with a retry button that resends the same question


Requirement 12: Code Viewing and Syntax Highlighting
User Story: As a developer, I want to view code artifacts with syntax highlighting, so that I can read and understand code easily.
Acceptance Criteria

THE Blueprint_Viewer SHALL use Monaco_Editor for displaying artifact file content with the configuration specified in Requirement 5 criterion 18
THE Blueprint_Viewer SHALL detect file language from extension: yaml/yml=yaml, Dockerfile=dockerfile, .proto=proto, .json=json, .ts=typescript, .py=python, .go=go; unrecognized extensions SHALL default to plaintext
THE Blueprint_Viewer SHALL display Monaco_Editor in readOnly=true mode at all times
THE Blueprint_Viewer SHALL support downloading individual files from GET /blueprints/{id}/artifacts/{file_path} and all files as a zip from GET /blueprints/{id}/artifacts/download, both using the Blob URL download technique specified in Requirement 5 criterion 19


Requirement 13: Graph Interactions and Layouts
User Story: As a developer, I want to interact with the knowledge graph using click, double-click, and hover, so that I can explore relationships and view details.
Acceptance Criteria

THE Knowledge_Graph SHALL use React_Flow with ReactFlowProvider, custom node types registered via the nodeTypes prop, and custom edge types registered via the edgeTypes prop
THE Knowledge_Graph SHALL compute initial layout using Force_Layout (d3-force, linkDistance=150, chargeStrength=-400, 300 synchronous ticks) before the first render
THE Knowledge_Graph SHALL support layout switching to Tree_Layout and Radial_Layout with 600ms animated position transitions via requestAnimationFrame interpolation
WHEN a node is clicked, THE Knowledge_Graph SHALL open the detail panel as specified in Requirement 2
WHEN a node is double-clicked, THE Knowledge_Graph SHALL fetch neighbors from GET /graph/neighbors/{node_id}?depth=1 and add them to the graph with a hidden-to-visible animation
WHEN a node is hovered, THE Knowledge_Graph SHALL reduce non-connected node and edge opacity to 0.15 and 0.1 respectively via React Flow style props
THE Knowledge_Graph SHALL expose zoom in, zoom out, and fit-to-view controls via React Flow's built-in Controls component positioned at bottom-right


Requirement 14: Chart Visualizations
User Story: As an engineering manager, I want to view health metrics, coverage, and trends in charts, so that I can understand system health at a glance.
Acceptance Criteria

THE Health_Dashboard SHALL use Recharts for: the MetricCard sparklines (60x24px LineChart, no axes), the health score AreaChart, and the coverage HorizontalBarChart
THE health score AreaChart SHALL use color interpolation via Health_Color_Scale, a gradient fill, reference lines at y=80 and y=50, and ReferenceArea for score drops greater than 15 points in a 7-day window
THE coverage HorizontalBarChart SHALL sort services by coverage ascending, color bars by Health_Color_Scale, and navigate to /graph on bar click
THE gap heatmap SHALL be a custom SVG component (not a Recharts component) with 53x7 cells, a five-stop color scale, hover tooltips, and click navigation, as specified in Requirement 3
ALL Recharts components SHALL display a custom tooltip component on hover showing the exact data values with appropriate formatting
ALL chart click interactions SHALL navigate to the relevant filtered view as specified per chart in Requirement 3


Requirement 15: Build Order and Implementation Strategy
User Story: As a developer implementing this specification, I want a clear build order, so that I can implement features incrementally and test as I go.
Acceptance Criteria

THE KA_CHOW_Platform SHALL implement features in this order: Q&A Interface, Knowledge Graph, Health Dashboard, Policy Status, Blueprint Viewer, Onboarding Paths
WITHIN each feature, THE KA_CHOW_Platform SHALL implement components in this order: page layout and routing, TypeScript types for that feature, React Query hooks, main list or primary component, detail or secondary component, all sub-components, Skeleton_Loading states, Error_State components, Empty_State components
EACH feature SHALL be fully functional including loading states and error states before implementation of the next feature begins
NO placeholder components, TODO comments, or console.log statements SHALL exist in the delivered code


Appendix A — API Contract
All endpoints accept and return JSON unless otherwise noted. All requests must include the Authorization header with a Bearer token and the X-Repo-Scope header with the active repository name.
Q&A Endpoints

POST /adapters/web/ask — request: QARequest; response: SSE stream of token events and a final metadata event
GET /assistant/sessions?repo= — response: Session[]
GET /assistant/sessions/{id}/messages — response: Message[]
DELETE /assistant/sessions/{id} — response: 204 No Content

Graph Endpoints

GET /graph/nodes?repo= — response: GraphNode[]
GET /graph/edges?repo= — response: GraphEdge[]
GET /graph/neighbors/{node_id}?depth= — response: { nodes: GraphNode[], edges: GraphEdge[] }

Health Endpoints

GET /health/snapshots?repo=&limit=&days= — response: HealthSnapshot[]
GET /health/coverage?repo= — response: CoverageEntry[]
GET /health/gaps?repo=&status= — response: GapEntry[]
GET /health/gaps/timeline?repo=&days= — response: GapDay[]
GET /reporting/alerts?repo=&status= — response: Alert[]
POST /reporting/alerts/{id}/dismiss — response: 204 No Content
GET /reporting/activity?repo=&limit=&cursor= — response: { items: ActivityEvent[], next_cursor: string | null }
GET /reporting/stream?repo= — SSE stream of health_update, alert, and activity events

Policy Endpoints

GET /policy/runs?repo=&outcome=&ruleset=&from=&to=&search=&limit=&cursor= — response: { items: PolicyRun[], next_cursor: string | null }
GET /policy/rulesets?repo= — response: string[]
GET /policy/runs/stats?repo=&days= — response: PolicyStats
POST /policy/patches/{id}/apply — response: 204 No Content
GET /policy/stream?repo= — SSE stream of policy_run events
POST /governance/waivers — request: WaiverRequest; response: Waiver
DELETE /governance/waivers/{id} — response: 204 No Content

Blueprint Endpoints

GET /blueprints?repo=&pattern=&from=&to=&aligned= — response: Blueprint[]
GET /blueprints/{id} — response: Blueprint
POST /blueprints/{id}/analyze — response: { aligned: boolean, drift_summary: string | null }
GET /blueprints/{id}/artifacts/{file_path} — response: text/plain file content
GET /blueprints/{id}/artifacts/download — response: application/zip

Onboarding Endpoints

POST /onboarding/role — request: { role, user_id, repo }; response: 204 No Content
GET /onboarding/path?repo=&role= — response: OnboardingPath
POST /onboarding/progress/resource — request: { resource_id, user_id, repo }; response: 204 No Content
POST /onboarding/progress — request: { stage_id, user_id, repo, completed_at }; response: 204 No Content


Appendix B — Performance Targets
The following performance targets apply per feature. These are acceptance criteria for the delivered implementation.
Q&A Interface

First streaming token must appear within 500ms of sending a request
History sidebar must open and close within 300ms
Suggestion card click must trigger message send within 100ms

Knowledge Graph

Initial graph render with up to 200 nodes must complete within 2 seconds of data load
Node click must open the detail panel within 300ms
Layout switch animation must complete within 600ms
Neighbor fetch and graph expansion must complete within 1 second of double-click

Health Dashboard

All four metric cards must render within 1 second of page load
The health score chart must animate in within 1 second of data load
Activity feed must render the first 20 items within 1 second of page load
SSE events must be reflected in the UI within 500ms of receipt

Policy Status

The policy run list must render the first 25 items within 1 second of page load
New SSE policy run entries must animate into the list within 300ms of receipt
The waiver modal must open within 200ms of button click

Blueprint Viewer

The Design tab React Flow diagram must render within 1.5 seconds of tab selection
Monaco Editor must display file content within 500ms of file selection
The artifact zip download must begin within 2 seconds of button click

Onboarding Paths

The role selector overlay must appear immediately (within 100ms) on page load when no role is set
Stage completion optimistic update must appear within 100ms of confirmation
Confetti animation must fire within 200ms of final stage completion


Appendix C — SSE Reconnection Behavior
All SSE connections in the application SHALL follow this reconnection protocol.
Initial connection: Open an EventSource using the native browser EventSource API. Set a connection status variable to "connected" in component local state.
On error event: Set connection status to "disconnected". Wait 2 seconds, then attempt to reconnect by closing the existing EventSource and opening a new one. If the reconnection fails, apply exponential backoff: wait 2s, then 4s, then 8s, then 16s, capping at 30 seconds between attempts. Reset backoff to 2s on successful reconnection.
Maximum reconnection attempts: After 10 consecutive failed reconnection attempts, stop retrying and set connection status to "failed". Display an Error_State in the affected component with message "Live updates are unavailable. Reload the page to try again." with a reload button.
Connection status indicator: WHEN connection status is "disconnected" or "failed" for more than 5 seconds, display a "Live updates paused" pill in the bottom-left of the affected page. The pill SHALL disappear automatically when status returns to "connected".
Cleanup: ALL EventSource instances SHALL be closed in the cleanup function of the useEffect that created them, and SHALL be reopened when the activeRepo value changes.