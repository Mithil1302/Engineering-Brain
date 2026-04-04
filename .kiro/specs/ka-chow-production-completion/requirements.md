# Requirements Document

## Introduction

This specification defines the requirements for completing the KA-CHOW 
AI-powered engineering brain platform. The platform is currently 80% 
complete with a working LLM core (Gemini 2.0 Flash), RAG pipeline, 
architecture planner, scaffolder, impact analyzer, time travel system, 
autofix engine, onboarding engine, and policy pipeline. This document 
closes 4 critical gaps that prevent end-to-end operation and applies 
5 targeted improvements to elevate existing implementations to 
production grade.

The stack is Python, FastAPI, Google Gemini 2.0 Flash, pgvector on 
PostgreSQL, Neo4j, Apache Kafka, gRPC, and GitHub API. All new modules 
integrate with existing infrastructure without rewriting working code.

All API endpoints referenced in this document conform to the API 
Contract defined in Appendix A. All performance targets are defined 
in Appendix B. All Kafka topic schemas are defined in Appendix C.

---

## Glossary

- **Ingestion_Pipeline**: The system that crawls GitHub repositories, 
  extracts code and metadata, chunks content, and populates the 
  knowledge graph and embedding store
- **GitHubRepoCrawler**: Component that authenticates with GitHub App 
  credentials, walks the repository file tree, and fetches raw file 
  content with rate limit awareness
- **CodeChunker**: Component that transforms raw file content into 
  semantically meaningful, embeddable chunks using language-specific 
  extraction strategies
- **ServiceDetector**: Component that identifies microservice boundaries 
  within a repository using heuristics (Dockerfile presence, package 
  manifests, k8s directories)
- **DependencyExtractor**: Component that identifies inter-service 
  dependencies from docker-compose, Kubernetes manifests, and import 
  statements
- **GraphPopulator**: Component that writes service, API, schema, and 
  dependency nodes and edges to Neo4j via gRPC ApplyMutations
- **EmbeddingPopulator**: Component that writes chunks to pgvector using 
  EmbeddingStore.upsert_chunks() with deduplication by chunk_id
- **Knowledge_Graph**: Neo4j graph database storing service manifests, 
  API endpoints, schemas, engineers, and dependency relationships as 
  typed nodes and edges
- **Embedding_Store**: pgvector extension on PostgreSQL storing 768-
  dimension Gemini text-embedding-004 vectors for semantic search
- **Impact_Analyzer**: Component that traverses the Knowledge_Graph via 
  gRPC to determine downstream effects of API, schema, or service changes
- **Time_Travel_System**: Temporal graph store capturing architecture 
  snapshots with valid_from/valid_to semantics for historical queries, 
  drift detection, and future state projection
- **Policy_Engine**: Kafka-driven system that evaluates deterministic 
  policy rules against PR events and produces check results
- **GitHub_Bridge**: agent-service component that authenticates as a 
  GitHub App, delivers Check Runs, posts PR comments, and processes 
  incoming webhook events
- **RAG_Chain**: Retrieve-Augment-Generate pipeline that embeds queries, 
  retrieves top-K chunks from pgvector, reranks with Gemini, applies 
  freshness scoring, and generates grounded answers
- **Intent_Classifier**: Two-stage LLM classifier that maps user questions 
  to coarse intents then sub-intents using constrained JSON output
- **INTENT_TREE**: Module-level constant mapping coarse intents to their 
  sub-intent candidates
- **INTENT_EVIDENCE_MAP**: Module-level constant mapping intents and 
  sub-intents to their PostgreSQL and Neo4j evidence sources
- **Coreference_Resolver**: Pre-classification component that resolves 
  pronouns and elliptical references in multi-turn conversations to 
  previously mentioned named entities
- **ConversationState**: Dataclass maintaining entity_registry and 
  subject_stack across conversation turns, stored in session store
- **Gap_Detector**: System that mines meta.qa_event_log for unanswered 
  or low-confidence questions and surfaces them as documentation gaps
- **KnowledgeGap**: Dataclass representing a detected documentation gap 
  with frequency, severity, and suggested remediation
- **GapReport**: Dataclass aggregating KnowledgeGap instances by service 
  with a documentation debt score
- **Channel_Formatter**: Component that shapes QAResponse content and 
  injects tone instructions based on the delivery channel profile
- **ChannelProfile**: Dataclass defining formatting constraints for a 
  specific delivery channel (max sentences, citation style, markdown 
  permission, tone instruction, field suppression flags)
- **Slack_Adapter**: Integration that receives Slack webhook events, 
  verifies signatures, calls the Q&A assistant, and delivers responses 
  via Block Kit
- **CLI_Adapter**: FastAPI SSE endpoint and standalone Python client 
  that streams Q&A responses to the terminal with ANSI color formatting
- **GitHub_Webhook_Handler**: FastAPI endpoint that processes pull_request 
  and push webhook events, triggers policy checks, and triggers 
  incremental ingestion
- **Graph_Service**: gRPC service in graph-service/ providing 
  ApplyMutations and QueryGraph operations against Neo4j
- **Chunk**: Semantically meaningful segment of code or documentation 
  with a SHA-256 chunk_id, source_type, metadata, and character-bounded 
  content (max 2000 characters)
- **IngestionResult**: Dataclass returned by IngestionPipeline containing 
  repo, run_id, files_processed, chunks_created, embeddings_created, 
  services_detected, duration_seconds, status
- **ServiceManifest**: Dataclass representing a detected microservice 
  with name, root_path, language, dependency list, and capability flags
- **Temporal_Snapshot**: A point-in-time record of all Knowledge_Graph 
  nodes and edges for a given repo, stored in architecture_snapshots 
  with valid_from timestamp
- **QAEventLog**: PostgreSQL table (meta.qa_event_log) storing every 
  Q&A request with intent, confidence, RAG result presence, and session 
  metadata for gap detection analysis
- **Freshness_Score**: Per-chunk recency multiplier: 1.2 for chunks 
  modified within 7 days, 1.1 within 30 days, 1.0 within 90 days, 
  0.9 older than 90 days
- **Final_Rerank_Score**: Weighted combination: 
  (rerank_score * 0.7) + (freshness_score * 0.3)
- **Documentation_Debt_Score**: Per-service aggregate: 
  sum(gap.frequency * severity_weight) where weights are 
  critical=4, high=3, medium=2, low=1
- **Incremental_Ingestion**: Re-ingestion of only the changed files 
  in a push or PR event, as opposed to full repo re-crawl
- **Chunk_Deduplication**: SHA-256 keyed upsert that skips unchanged 
  chunks and replaces changed ones without deleting existing embeddings

---

## Requirements

### Requirement 1: GitHub Repository Ingestion Pipeline

**User Story:** As a platform operator, I want to ingest GitHub 
repositories into the knowledge graph and embedding store, so that 
the RAG pipeline has real code data to retrieve and reason over, 
making Q&A answers grounded in actual codebase artifacts.

#### Acceptance Criteria

**GitHubRepoCrawler (ingestion/crawler.py)**

1. THE GitHubRepoCrawler SHALL authenticate using a GitHub App 
   installation token derived from GITHUB_APP_ID and 
   GITHUB_APP_PRIVATE_KEY via JWT, following the same pattern 
   as the existing agent-service authentication
2. THE GitHubRepoCrawler SHALL fetch the repository file tree via 
   GET /repos/{owner}/{repo}/git/trees/{sha}?recursive=1
3. THE GitHubRepoCrawler SHALL filter files to these extensions only: 
   .py, .ts, .js, .go, .java, .yaml, .yml, .json, .md, .proto, 
   .tf, .sql
4. THE GitHubRepoCrawler SHALL skip files in these path patterns: 
   node_modules/, .git/, dist/, build/, __pycache__/, vendor/, 
   coverage/, .next/, .nuxt/
5. THE GitHubRepoCrawler SHALL skip files whose size_bytes exceeds 
   the INGESTION_MAX_FILE_SIZE_KB environment variable (default 500) 
   converted to bytes
6. THE GitHubRepoCrawler SHALL fetch raw file content via 
   GET /repos/{owner}/{repo}/contents/{path} and decode base64
7. THE GitHubRepoCrawler SHALL read the X-RateLimit-Remaining header 
   on every GitHub API response; WHEN remaining falls below 100, 
   THE crawler SHALL sleep until the X-RateLimit-Reset timestamp
8. THE GitHubRepoCrawler SHALL return 429 responses with exponential 
   backoff starting at 2 seconds, doubling on each retry, capped 
   at 60 seconds, with a maximum of 5 retry attempts per file
9. THE GitHubRepoCrawler SHALL use an asyncio Semaphore with limit 
   equal to INGESTION_MAX_CONCURRENT_FETCHES (default 10) to bound 
   concurrent GitHub API calls
10. THE GitHubRepoCrawler SHALL return a RepoCrawlResult dataclass 
    with fields: repo (str), default_branch (str), total_files (int), 
    files (list[FileContent]), crawled_at (datetime)
11. THE FileContent dataclass SHALL have fields: path (str), 
    content (str), extension (str), size_bytes (int), sha (str), 
    last_modified (datetime | None)

**CodeChunker (ingestion/chunker.py)**

12. THE CodeChunker SHALL produce Chunk dataclasses with fields: 
    chunk_id (SHA-256 of repo+path+content), repo (str), 
    file_path (str), extension (str), content (str), 
    source_type ("code"|"docs"|"spec"|"config"|"migration"|"infra"), 
    metadata (dict), start_line (int), end_line (int), char_count (int)
13. FOR Python files (.py), THE CodeChunker SHALL use the ast module 
    to extract each top-level function and class as a separate chunk; 
    chunk metadata SHALL include function_name or class_name, 
    start_line, end_line, docstring; WHEN ast.parse() raises 
    SyntaxError, THE CodeChunker SHALL fall back to sliding window
14. FOR TypeScript and JavaScript files (.ts, .js), THE CodeChunker 
    SHALL use the pattern r'(?:export\s+)?(?:async\s+)?
    (?:function|class|interface|type|const)\s+(\w+)' to identify 
    declaration boundaries and extract 30 lines of context per match
15. FOR Go files (.go), THE CodeChunker SHALL use the pattern 
    r'func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(' for function extraction 
    and r'type\s+(\w+)\s+(?:struct|interface)' for type extraction; 
    chunk metadata SHALL include receiver_type when present
16. FOR Markdown files (.md), THE CodeChunker SHALL split on ## and 
    ### headings; each heading section SHALL be one chunk; chunk 
    metadata SHALL include section_title
17. FOR YAML/JSON files that contain "openapi:" or "swagger:" at the 
    document root, THE CodeChunker SHALL extract each path+method 
    combination as a separate chunk; chunk metadata SHALL include 
    http_method, path, operation_id, tags, deprecated (bool); 
    source_type SHALL be "spec"
18. FOR YAML files containing "kind:" and "apiVersion:", THE CodeChunker 
    SHALL treat the entire file as one chunk; source_type SHALL be 
    "config"
19. FOR Proto files (.proto), THE CodeChunker SHALL extract each service 
    definition and each message definition as separate chunks; chunk 
    metadata SHALL include proto_type ("service"|"message") and name
20. FOR SQL files (.sql), THE CodeChunker SHALL extract each CREATE TABLE, 
    CREATE INDEX, CREATE FUNCTION statement as a separate chunk; chunk 
    metadata SHALL include statement_type and object_name
21. FOR Terraform files (.tf), THE CodeChunker SHALL extract each resource 
    block as a separate chunk; chunk metadata SHALL include 
    resource_type and resource_name
22. FOR all other file types, THE CodeChunker SHALL apply sliding window 
    chunking with 50-line windows and 10-line overlap
23. WHEN any chunk exceeds 2000 characters, THE CodeChunker SHALL 
    subdivide it into sub-chunks using a sliding window with 200-
    character overlap; THE CodeChunker SHALL never truncate content — 
    all content must appear in at least one sub-chunk

**ServiceDetector (ingestion/service_detector.py)**

24. THE ServiceDetector SHALL identify a directory as a service when 
    it contains a Dockerfile at its root
25. THE ServiceDetector SHALL identify a directory as a service when 
    it contains pyproject.toml, package.json, or go.mod at its root
26. THE ServiceDetector SHALL identify a directory as a service when 
    it contains a k8s/ or kubernetes/ subdirectory
27. THE ServiceDetector SHALL parse docker-compose.yaml files and 
    extract all service names from the services: block
28. THE ServiceDetector SHALL return a ServiceManifest dataclass for 
    each detected service with fields: service_name (str), 
    root_path (str), language (str — dominant extension by file count), 
    has_dockerfile (bool), has_openapi (bool), has_proto (bool), 
    has_migrations (bool), has_tests (bool), has_ci (bool), 
    owner_hint (str | None from CODEOWNERS), 
    dependencies (list[str]), endpoints (list[str]), 
    file_paths (list[str])
29. THE DependencyExtractor SHALL parse docker-compose depends_on 
    blocks and return (source, target, "runtime") tuples
30. THE DependencyExtractor SHALL parse Kubernetes Service names from 
    k8s/*.yaml files and cross-reference them against detected 
    service names to produce (source, target, "network") tuples
31. THE DependencyExtractor SHALL parse Python import statements using 
    pattern r'^(?:from|import)\s+([\w.]+)' and TypeScript import 
    statements using pattern r"from\s+['\"](@[\w-]+/[\w-]+|
    \.\.?/[\w-]+)['\"]" to produce (source, target, "import") tuples; 
    only imports referencing other detected service names SHALL be 
    included

**GraphPopulator (ingestion/graph_populator.py)**

32. THE GraphPopulator SHALL call Graph_Service ApplyMutations gRPC 
    endpoint for each ServiceManifest, creating a Neo4j node with 
    node_type="service" and properties: service_name, language, 
    root_path, has_dockerfile, has_openapi, has_proto, owner_hint, 
    health_score (default 50), last_ingested (timestamp), repo
33. THE GraphPopulator SHALL call Graph_Service ApplyMutations for 
    each OpenAPI path+method extracted by CodeChunker, creating a 
    Neo4j node with node_type="api" and properties: http_method, 
    path, operation_id, service_name, tags, deprecated, repo
34. THE GraphPopulator SHALL call Graph_Service ApplyMutations for 
    each CREATE TABLE statement extracted by CodeChunker, creating a 
    Neo4j node with node_type="schema" and properties: table_name, 
    columns (JSON), service_name, repo
35. THE GraphPopulator SHALL call Graph_Service ApplyMutations for 
    each proto service definition, creating a Neo4j node with 
    node_type="schema" and properties: proto_service_name, 
    message_names (list), repo
36. THE GraphPopulator SHALL call Graph_Service ApplyMutations for 
    each dependency tuple from DependencyExtractor, creating a Neo4j 
    edge with edge_type="dependency", source and target matching 
    service node IDs, and properties: dependency_type, repo
37. THE GraphPopulator SHALL mirror all service and API Neo4j nodes 
    as records in PostgreSQL meta.graph_nodes table (columns: node_id, 
    repo, node_type, label, properties JSON, created_at) so the 
    Impact_Analyzer and Policy_Engine can query without gRPC

**EmbeddingPopulator (ingestion/embedding_populator.py)**

38. THE EmbeddingPopulator SHALL call the existing 
    EmbeddingStore.upsert_chunks() for each batch of chunks
39. THE EmbeddingPopulator SHALL process chunks in batches of 
    INGESTION_BATCH_SIZE (default 50) matching the Gemini embedding 
    API batch limit
40. THE EmbeddingPopulator SHALL use chunk_id (SHA-256) for upsert 
    deduplication: chunks with unchanged content produce the same 
    chunk_id and are skipped; chunks with changed content produce 
    a new chunk_id and replace the old embedding
41. THE EmbeddingPopulator SHALL write progress to meta.ingestion_runs: 
    update files_processed, chunks_created, and embeddings_created 
    after each batch completes
42. WHEN EmbeddingStore.upsert_chunks() raises an exception, THE 
    EmbeddingPopulator SHALL mark the ingestion run as status="failed" 
    with error_message set to the exception string; existing embeddings 
    written before the failure SHALL NOT be deleted

**IngestionPipeline (ingestion/ingestion_pipeline.py)**

43. THE IngestionPipeline.ingest_repo() SHALL execute steps in this 
    exact sequence: crawl → chunk → detect services → populate graph 
    → populate embeddings; all steps are synchronous and sequential
44. THE IngestionPipeline.ingest_repo() SHALL complete within 5 minutes 
    for repositories with up to 500 files under normal GitHub API 
    conditions
45. THE IngestionPipeline.ingest_on_push() SHALL accept a list of 
    changed_files and only re-crawl, re-chunk, and re-embed those 
    specific files; the Neo4j graph SHALL be updated only for nodes 
    whose source files are in the changed_files list
46. THE IngestionPipeline.get_ingestion_status() SHALL return the 
    latest meta.ingestion_runs record for the given repo as an 
    IngestionStatus dataclass
47. THE IngestionPipeline SHALL return an IngestionResult dataclass 
    with fields: repo, run_id, files_processed, chunks_created, 
    embeddings_created, services_detected, duration_seconds, status
48. WHEN the "repo.ingestion" Kafka topic receives an event with 
    changed_files=null, THE Ingestion_Pipeline SHALL call ingest_repo()
49. WHEN the "repo.ingestion" Kafka topic receives an event with 
    changed_files as a non-empty list, THE Ingestion_Pipeline SHALL 
    call ingest_on_push()
50. AFTER successful ingestion, THE Ingestion_Pipeline SHALL produce 
    a "repo.ingestion.complete" Kafka event with schema defined in 
    Appendix C
51. THE Ingestion_Pipeline SHALL expose POST /ingestion/trigger with 
    request body { repo: str } and response { run_id: str, status: str }
52. THE Ingestion_Pipeline SHALL expose GET /ingestion/status/{repo} 
    returning the latest IngestionStatus
53. THE Ingestion_Pipeline SHALL expose GET /ingestion/runs/{repo} 
    returning a list of the last 20 IngestionResult records ordered 
    by started_at descending

---

### Requirement 2: Neo4j Graph Service Integration for Impact Analyzer

**User Story:** As a developer querying impact analysis, I want the 
analyzer to use real dependency data from Neo4j, so that blast radius 
calculations reflect actual architecture relationships rather than 
mock or fallback data.

#### Acceptance Criteria

1. THE Impact_Analyzer._get_dependency_edges() SHALL call 
   Graph_Service QueryGraph gRPC endpoint with this Cypher query: 
   MATCH (s:Service {repo: $repo})-[r:DEPENDENCY]->(t:Service) 
   RETURN s.service_name AS source, t.service_name AS target, 
   r.dependency_type AS type
2. THE Impact_Analyzer._get_dependency_edges() SHALL transform the 
   gRPC QueryGraph response into the list[tuple[str, str, str]] 
   format (source, target, type) that the existing BFS traversal 
   already expects; no changes to the BFS logic are permitted
3. WHEN the Graph_Service gRPC call fails with any connection error 
   or deadline exceeded, THE Impact_Analyzer SHALL fall back to 
   querying PostgreSQL meta.graph_nodes within the same request; 
   the fallback SHALL be transparent to callers
4. THE Impact_Analyzer._get_dependency_edges() SHALL cache results 
   in a module-level dict keyed by repo with a 60-second TTL; cache 
   entries SHALL be invalidated when a "repo.ingestion.complete" 
   Kafka event is received for that repo
5. THE Impact_Analyzer._get_service_node() SHALL execute this Cypher 
   via Graph_Service QueryGraph: 
   MATCH (s:Service {service_name: $name, repo: $repo}) RETURN s; 
   SHALL apply the same fallback and caching strategy as 
   _get_dependency_edges()
6. THE Impact_Analyzer._get_api_nodes() SHALL execute this Cypher: 
   MATCH (a:API {repo: $repo}) WHERE a.path CONTAINS $path_fragment 
   RETURN a; SHALL apply the same fallback and caching strategy
7. THE Impact_Analyzer.simulate_failure_cascade() SHALL use Neo4j 
   dependency edges from _get_dependency_edges() instead of the 
   existing mock edge list; the BFS cascade traversal code SHALL 
   remain unchanged
8. THE Impact_Analyzer.get_dependency_graph() SHALL execute this 
   Cypher: MATCH (n)-[r]->(m) WHERE n.repo = $repo RETURN n, r, m; 
   SHALL transform the result into the existing dict format with 
   nodes and edges keys
9. THE Impact_Analyzer SHALL log a WARNING level message whenever 
   the PostgreSQL fallback is used, including the repo and the 
   gRPC error message, so operators can detect when Neo4j is 
   unhealthy

---

### Requirement 3: Temporal Graph Data Population

**User Story:** As a platform operator, I want architecture snapshots 
captured automatically after every ingestion, so that the time travel 
system has the historical data needed for drift detection, failure 
replay, and future state projection.

#### Acceptance Criteria

1. THE Time_Travel_System SHALL add a record_ingestion_snapshot(repo, 
   ingestion_result) method that reads all current Neo4j nodes and 
   edges for the repo via Graph_Service QueryGraph and writes a 
   Temporal_Snapshot to architecture_snapshots with valid_from set 
   to the current timestamp
2. WHEN record_ingestion_snapshot() is called, THE Time_Travel_System 
   SHALL set valid_to on all nodes and edges from the previous snapshot 
   that do not appear in the current snapshot (nodes removed from the 
   architecture since last ingestion)
3. WHEN record_ingestion_snapshot() is called, THE Time_Travel_System 
   SHALL write new TemporalNode records for nodes that appear in the 
   current snapshot but not the previous one (nodes added since last 
   ingestion)
4. THE Time_Travel_System SHALL add a record_policy_event(repo, 
   policy_run_id, findings) method that writes to 
   architecture_snapshots for findings of type DOC_DRIFT_* or 
   BREAKING_*; each finding SHALL produce one snapshot record with 
   event_type="policy_finding" and the finding payload in properties
5. WHEN a "repo.ingestion.complete" Kafka event is received in 
   pipeline.py, THE pipeline SHALL call 
   time_travel.record_ingestion_snapshot() automatically
6. WHEN a policy run completes in pipeline.py, THE pipeline SHALL 
   call time_travel.record_policy_event() for runs with any 
   DOC_DRIFT or BREAKING finding
7. THE architecture_nodes table SHALL have a composite index on 
   (repo, valid_from, valid_to) if not already present; THE 
   Time_Travel_System SHALL verify this index exists at startup 
   via an EXPLAIN query and log a WARNING if it is missing
8. THE existing get_snapshot_at(timestamp) method SHALL correctly 
   handle nodes where valid_to IS NULL by treating them as currently 
   active; this SHALL be verified by a unit test with at least three 
   test cases: past timestamp before any ingestion, timestamp between 
   two ingestions, and current timestamp

---

### Requirement 4: GitHub Webhook for Automatic CI Triggering

**User Story:** As a developer, I want policy checks to run 
automatically when I open or update a PR, so that I receive 
immediate GitHub Check Run feedback without any manual triggering.

#### Acceptance Criteria

1. THE GitHub_Bridge SHALL expose POST /webhooks/github as a FastAPI 
   endpoint; if this endpoint already exists, the pull_request event 
   handling SHALL be added to the existing router
2. THE GitHub_Bridge SHALL verify every incoming webhook request using 
   HMAC-SHA256 with GITHUB_WEBHOOK_SECRET against the X-Hub-Signature-
   256 header; the raw request body SHALL be read before JSON parsing 
   to ensure the signature is computed against the original bytes
3. WHEN signature verification fails, THE GitHub_Bridge SHALL return 
   HTTP 401 with body { "error": "invalid signature" } and SHALL log 
   a WARNING with the repo and delivery ID from the X-GitHub-Delivery 
   header
4. WHEN a pull_request event is received with action "opened" or 
   "synchronize", THE GitHub_Bridge SHALL extract: repo full_name, 
   PR number, head SHA, base branch, and the changed files list from 
   GET /repos/{owner}/{repo}/pulls/{number}/files
5. THE GitHub_Bridge SHALL produce a "repo.events" Kafka message with 
   schema: { event_type: "pull_request", repo: str, pr_number: int, 
   head_sha: str, base_branch: str, changed_files: list[str], 
   additions: int, deletions: int, triggered_at: ISO8601 timestamp }
6. THE GitHub_Bridge SHALL produce a "repo.ingestion" Kafka message 
   with schema: { repo: str, triggered_by: "webhook", 
   changed_files: list[str], commit_sha: str } for incremental 
   re-ingestion of only the PR's changed files
7. THE GitHub_Bridge SHALL create a GitHub Check Run immediately after 
   receiving the pull_request event via POST /repos/{owner}/{repo}/
   check-runs with status="in_progress", name="KA-CHOW Policy Check", 
   head_sha=head_sha; this ensures the PR shows a pending check while 
   processing occurs asynchronously
8. THE GitHub_Bridge SHALL store the check_run_id in PostgreSQL in a 
   new table meta.check_run_tracking with columns: repo (text), 
   pr_number (int), head_sha (text), check_run_id (bigint), 
   created_at (timestamptz); this allows pipeline.py to update the 
   Check Run when processing completes
9. WHEN pipeline.py finishes processing a "pull_request" repo.events 
   message, THE pipeline SHALL update the GitHub Check Run status to 
   "completed" with conclusion "success" or "failure" based on the 
   policy outcome, using the check_run_id from meta.check_run_tracking
10. WHEN a push event is received targeting the repository default 
    branch, THE GitHub_Bridge SHALL produce ONLY a "repo.ingestion" 
    Kafka message for incremental re-ingestion; push events SHALL 
    NOT produce "repo.events" messages and SHALL NOT trigger policy 
    checks
11. WHEN a push event is received targeting a non-default branch, 
    THE GitHub_Bridge SHALL take no action and SHALL return HTTP 200
12. THE webhook endpoint SHALL return HTTP 200 within 500ms for all 
    event types by performing Kafka production in a FastAPI 
    BackgroundTask; the GitHub API requires webhook responses within 
    10 seconds and a 500ms target provides safety margin

---

### Requirement 5: Hierarchical Intent Classification

**User Story:** As a user, I want the Q&A assistant to distinguish 
between nuanced variants of architecture, impact, and onboarding 
questions, so that evidence retrieval is precisely targeted and 
answers are more accurate.

#### Acceptance Criteria

1. THE Intent_Classifier SHALL define INTENT_TREE as a module-level 
   constant in assistant.py with this exact structure:
   { "architecture": ["architecture.explain_service", 
     "architecture.trace_dependency", "architecture.why_decision", 
     "architecture.add_service", "architecture.compare_services"],
   "impact": ["impact.deprecate_endpoint", "impact.change_schema", 
     "impact.change_dependency"],
   "policy_status": ["policy_status.pr_check", 
     "policy_status.merge_gate", "policy_status.waiver_status"],
   "doc_health": ["doc_health.missing_docs", "doc_health.stale_docs", 
     "doc_health.coverage_score"],
   "onboarding": ["onboarding.getting_started", 
     "onboarding.find_owner", "onboarding.understand_flow"],
   "health": ["health"], "waiver": ["waiver"], "general": ["general"] }
2. THE _classify_intent() method SHALL run the existing coarse LLM 
   classification first without modification; coarse classification 
   behavior SHALL be unchanged
3. WHEN the coarse intent maps to more than one sub-intent in 
   INTENT_TREE, THE _classify_intent() method SHALL run a second LLM 
   call using SubIntentClassifierPrompt with the original question, 
   the coarse intent, and the candidate sub-intent list
4. THE SubIntentClassifierPrompt SHALL use llm.generate_json() with 
   a response_schema of { "sub_intent": { "type": "string", 
   "enum": candidates } } to produce constrained output
5. WHEN the sub-intent LLM call fails for any reason, THE 
   _classify_intent() method SHALL return the coarse intent string 
   unchanged; the fallback SHALL be silent (no exception propagation)
6. THE _classify_intent() method SHALL return dot-notation sub-intents 
   when available (e.g., "architecture.trace_dependency") and bare 
   coarse intents when sub-classification is unavailable or 
   unnecessary (e.g., "health")
7. THE INTENT_EVIDENCE_MAP SHALL be expanded with these sub-intent 
   entries alongside the existing coarse intent entries:
   "architecture.explain_service": ["graph_nodes", 
     "knowledge_chunks", "api_specs"],
   "architecture.trace_dependency": ["dependency_graph", 
     "graph_nodes"],
   "architecture.why_decision": ["adrs", "knowledge_chunks"],
   "architecture.add_service": ["adrs", "scaffold_templates", 
     "knowledge_chunks"],
   "architecture.compare_services": ["graph_nodes", "api_specs", 
     "knowledge_chunks"],
   "impact.deprecate_endpoint": ["api_specs", "dependency_graph", 
     "policy_runs"],
   "impact.change_schema": ["schema_registry", "dependency_graph"],
   "impact.change_dependency": ["dependency_graph", 
     "knowledge_chunks"],
   "onboarding.getting_started": ["onboarding_paths", 
     "knowledge_chunks"],
   "onboarding.find_owner": ["graph_nodes", "team_metadata"],
   "onboarding.understand_flow": ["knowledge_chunks", "api_specs", 
     "dependency_graph"]
8. THE SubIntentClassifierPrompt SHALL be added to prompts.py 
   following the same pattern as QAIntentClassifierPrompt with 
   system_prompt, user_prompt(question, coarse_intent, candidates), 
   and response_schema() methods

---

### Requirement 6: Coreference Resolution for Multi-Turn Q&A

**User Story:** As a user having a multi-turn conversation, I want 
to use pronouns and elliptical references naturally, so that I can 
ask follow-up questions without repeating full entity names.

#### Acceptance Criteria

1. THE Coreference_Resolver SHALL implement a ConversationState class 
   with fields: entity_registry (dict[str, list[str]] mapping entity 
   type to entity names, most recent last), subject_stack (list[str] 
   of primary subjects per turn, most recent last), turn_count (int)
2. THE ConversationState.extract_entities() SHALL extract service names 
   by matching against known service names from meta.graph_nodes for 
   the active repo; service matches SHALL be case-insensitive
3. THE ConversationState.extract_entities() SHALL extract endpoint paths 
   using pattern r'/[a-z][a-z0-9/_\-\{\}]+' with minimum 2 path 
   segments
4. THE ConversationState.extract_entities() SHALL extract schema and 
   table names using pattern r'\b[A-Z][a-zA-Z]+(?:Table|Schema|Model|
   Record|Entity)\b'
5. THE ConversationState.extract_entities() SHALL extract engineer names 
   using pattern r'\b[A-Z][a-z]+ [A-Z][a-z]+\b' and matching against 
   known engineer names from meta.graph_nodes
6. THE ConversationState.update() SHALL call extract_entities() on both 
   the question and the answer, append found entities to entity_registry 
   with most recent last, set the primary subject from the question as 
   the last entry in subject_stack, and increment turn_count
7. THE ConversationState.resolve_references() SHALL scan the incoming 
   question for these pronoun patterns: "it", "this", "that", "they", 
   "its", "their", "the service", "the endpoint", "the schema", 
   "the table" using case-insensitive word boundary matching
8. WHEN a pronoun is found, THE ConversationState.resolve_references() 
   SHALL substitute it with the most recent entity of the contextually 
   appropriate type: service pronouns resolve to the last service, 
   endpoint pronouns resolve to the last endpoint, schema pronouns 
   resolve to the last schema
9. WHEN entity_registry is empty (first turn), THE 
   ConversationState.resolve_references() SHALL return the question 
   unchanged
10. WHEN the same entity type has two candidates of equal recency that 
    differ, THE ConversationState.resolve_references() SHALL return 
    the question unchanged rather than making an ambiguous substitution
11. THE Q&A assistant SHALL serialize ConversationState to JSON and 
    store it in the existing session store keyed by session_id 
    alongside conversation history
12. THE Q&A assistant SHALL load ConversationState from the session 
    store at the start of answer_conversation(); WHEN no state exists 
    for the session_id, a new ConversationState SHALL be initialized
13. THE Q&A assistant SHALL call resolve_references() on the incoming 
    question BEFORE passing it to _classify_intent(); the rewritten 
    question SHALL be used for classification and RAG retrieval but 
    the original question SHALL be stored in the conversation history 
    and returned in QAResponse for transparency
14. THE Q&A assistant SHALL call state.update(original_question, answer) 
    AFTER answer generation and SHALL persist the updated state back 
    to the session store

---

### Requirement 7: Always-On Reranking with Freshness Scoring

**User Story:** As a user, I want RAG retrieval to prioritize recent 
and highly relevant content, so that answers reflect the current state 
of the codebase rather than stale documentation.

#### Acceptance Criteria

1. THE RAG_Chain SHALL make reranking unconditionally active; the 
   enable_reranking configuration flag SHALL be removed and the 
   reranking code path SHALL always execute
2. THE RAG_Chain SHALL compute Freshness_Score for each chunk using 
   the last_modified timestamp from chunk metadata: 1.2 for chunks 
   modified within 7 days, 1.1 for chunks modified within 30 days, 
   1.0 for chunks modified within 90 days, 0.9 for chunks older 
   than 90 days; WHEN last_modified is absent from metadata, 
   Freshness_Score SHALL default to 1.0
3. THE RAG_Chain SHALL compute Final_Rerank_Score for each chunk as 
   (rerank_score * 0.7) + (freshness_score * 0.3)
4. THE RAG_Chain SHALL sort chunks by Final_Rerank_Score descending 
   after applying the freshness boost
5. THE RAG_Chain SHALL discard chunks with Final_Rerank_Score below 
   0.3 after sorting
6. WHEN fewer than 2 chunks remain after the score threshold filter, 
   THE RAG_Chain SHALL bypass the threshold and retain the top 3 
   chunks by Final_Rerank_Score regardless of their scores
7. AFTER each generation, THE RAG_Chain SHALL write one record to 
   meta.qa_event_log with fields: question (str), intent (str), 
   sub_intent (str | None), confidence (float), chunk_count (int — 
   number of chunks that passed the threshold filter), 
   top_chunk_source (str — file_path of the highest-scoring chunk 
   or None), had_rag_results (bool — True if chunk_count > 0), 
   session_id (str), repo (str), created_at (now())
8. THE QAEventLog write SHALL be non-blocking; WHEN the INSERT 
   fails for any reason, THE failure SHALL be logged at WARNING 
   level and generation SHALL proceed normally without raising

---

### Requirement 8: Documentation Gap Detection

**User Story:** As a platform operator, I want to identify topics 
that users ask about but the platform cannot answer well, so that I 
can prioritize documentation improvements where they have the most 
impact.

#### Acceptance Criteria

1. THE Gap_Detector.detect_gaps(repo, lookback_days) SHALL query 
   meta.qa_event_log WHERE repo = $repo AND created_at >= 
   NOW() - INTERVAL '$lookback_days days'
2. THE Gap_Detector.detect_gaps() SHALL group rows by 
   LEFT(question, 50) to cluster similar questions; this is a 
   deliberate approximation that balances grouping accuracy against 
   query complexity
3. THE Gap_Detector.detect_gaps() SHALL flag a group as a gap WHEN 
   had_rag_results = false OR avg(confidence) < 0.5
4. THE Gap_Detector SHALL produce a KnowledgeGap dataclass for each 
   flagged group with fields: question_sample (str — the most recent 
   question in the group), intent (str), frequency (int — row count 
   in the group), avg_confidence (float), suggested_doc_title (str — 
   generated by Gemini from the question_sample using a single LLM 
   call: "What documentation title would best answer: {question}?"), 
   suggested_doc_location (str — the service name inferred from 
   entities in question_sample using extract_entities()), 
   gap_severity ("critical"|"high"|"medium"|"low")
5. THE gap_severity SHALL be computed as: critical when frequency > 10 
   AND avg_confidence < 0.3; high when frequency > 5 OR 
   avg_confidence < 0.4; medium when frequency > 2; low otherwise
6. THE Gap_Detector.generate_gap_report(repo) SHALL call detect_gaps() 
   with default lookback_days=7 and return a GapReport dataclass with 
   fields: repo (str), generated_at (datetime), total_gaps (int), 
   gaps_by_service (dict[str, list[KnowledgeGap]]), 
   top_gaps (list[KnowledgeGap] — top 10 by frequency), 
   documentation_debt_score (float — Documentation_Debt_Score 
   summed across all gaps)
7. THE Gap_Detector SHALL expose GET /qa/gaps?repo=&days= endpoint 
   returning GapReport as JSON; the days parameter SHALL default to 7
8. THE reporting_store SHALL also expose gap count as a metric so 
   the existing health dashboard meta.ingestion_runs query can 
   include open gap count in its response without a separate API call

---

### Requirement 9: Channel-Aware Response Formatting

**User Story:** As a user accessing KA-CHOW from Slack, CLI, web, 
or API, I want responses formatted appropriately for my context, 
so that answers are immediately usable without reformatting.

#### Acceptance Criteria

1. THE Channel_Formatter SHALL define a ChannelProfile dataclass 
   with fields: max_answer_sentences (int | None), citation_style 
   ("footnote"|"inline"|"path_only"|"none"), allow_markdown (bool), 
   tone_instruction (str), include_chain_steps (bool), 
   include_evidence_detail (bool)
2. THE Channel_Formatter SHALL define CHANNEL_PROFILES as a module-
   level dict with entries for "web", "chat", "cli", and "api" using 
   the exact values specified in the implementation guide; "api" 
   SHALL be the fallback for any unrecognized channel string
3. THE Channel_Formatter.get_tone_instruction(channel) SHALL return 
   the tone_instruction from the matching ChannelProfile; this SHALL 
   be called BEFORE LLM generation and injected into QAAnswerPrompt 
   as a tone_instruction parameter in the system message
4. THE Channel_Formatter.format_response(response, channel) SHALL 
   apply these transformations in order: (1) strip markdown using 
   regex patterns for headers, bold, code blocks, and links WHEN 
   allow_markdown is False; (2) truncate answer to 
   max_answer_sentences by splitting on '. ' and rejoining WHEN 
   max_answer_sentences is not None; (3) reshape each citation by 
   adding a display field formatted per citation_style; (4) set 
   chain_steps to empty list WHEN include_chain_steps is False; 
   (5) set evidence to empty list WHEN include_evidence_detail is 
   False
5. THE citation display formats SHALL be: footnote — 
   "[{i+1}] {source_ref}#L{line}"; inline — "(src: {source_ref})"; 
   path_only — "{source_ref}:{line}"; none — citations passed 
   through with no display field added
6. THE Q&A assistant SHALL call 
   formatter.get_tone_instruction(channel) before every LLM 
   generation call and SHALL call formatter.format_response() 
   immediately before returning QAResponse from any endpoint; 
   the channel value SHALL come from QARequest.channel defaulting 
   to "api" when absent

---

### Requirement 10: Slack Delivery Adapter

**User Story:** As an engineer using Slack, I want to mention 
KA-CHOW in a channel or DM and receive a formatted Block Kit 
answer with citations and follow-up buttons, so that I can access 
platform intelligence without leaving Slack.

#### Acceptance Criteria

1. THE SlackDeliveryAdapter.verify_signature() SHALL compute 
   HMAC-SHA256 over f"v0:{timestamp}:{body}" using 
   SLACK_SIGNING_SECRET and compare against the signature from 
   X-Slack-Signature header (after removing the "v0=" prefix); 
   WHEN the timestamp in X-Slack-Request-Timestamp is more than 
   5 minutes old, verification SHALL fail regardless of signature 
   correctness (replay attack prevention)
2. WHEN verification fails, THE Slack_Adapter SHALL return HTTP 403 
   with body { "error": "invalid signature" } and SHALL NOT process 
   the event
3. THE SlackDeliveryAdapter.build_block_kit() SHALL construct a 
   Slack Block Kit payload with these blocks in order: (1) a section 
   block with plain_text answer (not mrkdwn — plain_text is 
   always safe); (2) a context block with up to 3 citation display 
   strings and a "+N more" suffix when citations exceed 3; (3) a 
   context block with "⚠️ This answer may be incomplete 
   (confidence: {confidence:.0%})" ONLY when confidence < 0.6; 
   (4) an actions block with up to 3 button elements for follow_ups, 
   each button value being JSON-encoded { "question": text, 
   "session_id": session_id } and each button text truncated to 
   75 characters
4. THE SlackDeliveryAdapter.deliver() SHALL POST the Block Kit 
   payload to Slack using SLACK_BOT_TOKEN via 
   https://slack.com/api/chat.postMessage for message events; 
   deliver() SHALL log errors at WARNING level and return False on 
   failure without raising; deliver() SHALL NOT retry (Slack 
   message delivery is best-effort in this implementation)
5. THE webhook endpoint at POST /adapters/slack/webhook SHALL respond 
   HTTP 200 within 3 seconds for all event types; Q&A processing 
   SHALL be performed in a FastAPI BackgroundTask
6. WHEN type == "url_verification" is received, THE endpoint SHALL 
   return { "challenge": body["challenge"] } synchronously without 
   processing as a background task
7. THE Slack_Adapter SHALL look up or create a session_id in 
   meta.slack_sessions keyed by (slack_channel, slack_user) to 
   maintain conversation continuity across Slack messages; meta.
   slack_sessions SHALL have a UNIQUE constraint on 
   (slack_channel, slack_user) and an upsert on conflict SHALL 
   update last_active_at
8. WHEN a Slack button action is received (payload.type == 
   "block_actions"), THE endpoint SHALL extract the question and 
   session_id from the button value JSON and call answer_conversation() 
   using the existing session_id to continue the conversation thread

---

### Requirement 11: CLI Streaming Adapter

**User Story:** As a developer working in the terminal, I want to 
query KA-CHOW from the command line and see the answer stream in 
real time with colored output, so that I can integrate platform 
intelligence into my shell workflow.

#### Acceptance Criteria

1. THE CLI_Adapter endpoint POST /adapters/cli/ask SHALL accept 
   request body { question: str, repo: str, session_id: str | None } 
   with Authorization: Bearer token authentication using the existing 
   auth dependency
2. THE CLI_Adapter endpoint SHALL return a StreamingResponse with 
   Content-Type: text/event-stream, Cache-Control: no-cache, and 
   X-Accel-Buffering: no headers
3. THE SSE stream SHALL emit events in this exact format: token events 
   as "data: {\"type\": \"token\", \"text\": \"{escaped_text}\"}\n\n"; 
   after all tokens, one metadata event as "data: {\"type\": 
   \"metadata\", \"citations\": [...], \"follow_ups\": [...], 
   \"confidence\": 0.87, \"intent\": \"architecture.explain_service\"}
   \n\n"; then "data: [DONE]\n\n"
4. THE CLI_Adapter SHALL generate a session_id via uuid4 WHEN none 
   is provided in the request
5. THE CLI client script at adapters/cli/client.py SHALL be a 
   standalone Python script with no FastAPI dependency
6. THE CLI client SHALL read configuration from 
   ~/.kachow/config.json with fields: api_url (str), token (str), 
   default_repo (str)
7. THE CLI client SHALL persist session_id to ~/.kachow/session 
   (a plain text file containing just the UUID) and read it at 
   startup; a new session_id SHALL be generated and written WHEN 
   the file does not exist
8. THE CLI client SHALL make a streaming POST request using httpx 
   with stream=True and parse SSE events by splitting on "\n\n" 
   boundaries
9. WHEN a token event is received, THE CLI client SHALL call 
   print(text, end="", flush=True) with no newline to produce 
   progressive output
10. WHEN the metadata event is received, THE CLI client SHALL print 
    a blank line, then citations using ANSI dim escape 
    (\033[2m{display}\033[0m), then follow-ups using ANSI cyan 
    (\033[36m) with a numbered list
11. AFTER printing follow-ups, THE CLI client SHALL print 
    "Select (1-{n}) or press Enter to skip: " and read stdin; 
    WHEN the user enters a valid number, THE CLI client SHALL 
    call the same streaming request with the selected follow-up 
    as the question and the same session_id; WHEN the user presses 
    Enter, THE CLI client SHALL exit
12. THE CLI client SHALL handle KeyboardInterrupt (Ctrl+C) gracefully 
    by printing a newline and exiting with code 0

---

### Requirement 12: Database Schema

**User Story:** As a platform operator, I want all new database 
tables and indexes created via a single migration file, so that 
schema changes are versioned, repeatable, and applied consistently 
across environments.

#### Acceptance Criteria

1. THE Database_Migration SHALL be a single SQL file at 
   worker-service/migrations/003_ingestion_and_gaps.sql
2. THE migration SHALL be idempotent — all CREATE TABLE and 
   CREATE INDEX statements SHALL use IF NOT EXISTS
3. THE migration SHALL create meta.ingestion_runs with columns: 
   id (UUID PRIMARY KEY DEFAULT gen_random_uuid()), repo (TEXT NOT 
   NULL), triggered_by (TEXT NOT NULL), started_at (TIMESTAMPTZ NOT 
   NULL DEFAULT NOW()), completed_at (TIMESTAMPTZ), 
   files_processed (INTEGER DEFAULT 0), chunks_created (INTEGER 
   DEFAULT 0), embeddings_created (INTEGER DEFAULT 0), 
   status (TEXT NOT NULL DEFAULT 'running'), error_message (TEXT), 
   commit_sha (TEXT)
4. THE migration SHALL create an index on meta.ingestion_runs 
   (repo, started_at DESC) named idx_ingestion_runs_repo
5. THE migration SHALL create meta.qa_event_log with columns: 
   id (UUID PRIMARY KEY DEFAULT gen_random_uuid()), 
   question (TEXT NOT NULL), intent (TEXT), sub_intent (TEXT), 
   confidence (FLOAT), chunk_count (INTEGER), 
   top_chunk_source (TEXT), had_rag_results (BOOLEAN NOT NULL 
   DEFAULT FALSE), session_id (TEXT), repo (TEXT NOT NULL), 
   created_at (TIMESTAMPTZ NOT NULL DEFAULT NOW())
6. THE migration SHALL create an index on meta.qa_event_log 
   (repo, created_at DESC) named idx_qa_event_log_repo_created
7. THE migration SHALL create a partial index on meta.qa_event_log 
   (repo, confidence, created_at DESC) WHERE had_rag_results = false 
   named idx_qa_event_log_gap_detection — this index is used 
   exclusively by Gap_Detector queries and must be partial to remain 
   small
8. THE migration SHALL create meta.slack_sessions with columns: 
   id (UUID PRIMARY KEY DEFAULT gen_random_uuid()), 
   slack_channel (TEXT NOT NULL), slack_user (TEXT NOT NULL), 
   session_id (TEXT NOT NULL), created_at (TIMESTAMPTZ NOT NULL 
   DEFAULT NOW()), last_active_at (TIMESTAMPTZ NOT NULL DEFAULT 
   NOW()), with UNIQUE(slack_channel, slack_user)
9. THE migration SHALL create meta.check_run_tracking with columns: 
   repo (TEXT NOT NULL), pr_number (INTEGER NOT NULL), 
   head_sha (TEXT NOT NULL), check_run_id (BIGINT NOT NULL), 
   created_at (TIMESTAMPTZ NOT NULL DEFAULT NOW()), 
   PRIMARY KEY (repo, pr_number, head_sha)
10. THE migration SHALL create meta.graph_nodes mirror table with 
    columns: node_id (TEXT NOT NULL), repo (TEXT NOT NULL), 
    node_type (TEXT NOT NULL), label (TEXT NOT NULL), 
    properties (JSONB), created_at (TIMESTAMPTZ NOT NULL DEFAULT 
    NOW()), PRIMARY KEY (node_id, repo)
11. THE migration SHALL be run by the existing ensure_schema() 
    function in pipeline.py at startup; THE ensure_schema() function 
    SHALL detect the migration version and skip execution if 
    migration 003 has already been applied

---

### Requirement 13: Environment Configuration

**User Story:** As a platform operator, I want all new configuration 
in environment variables with documented defaults, so that I can 
deploy to different environments without code changes.

#### Acceptance Criteria

1. THE worker-service SHALL read GITHUB_APP_ID from environment 
   (no default — required for ingestion)
2. THE worker-service SHALL read GITHUB_APP_PRIVATE_KEY from 
   environment as a PEM string (no default — required for ingestion)
3. THE worker-service SHALL read GITHUB_INSTALLATION_ID from 
   environment (no default — required for ingestion)
4. THE worker-service SHALL read GITHUB_WEBHOOK_SECRET from 
   environment (no default — required for webhook verification)
5. THE worker-service SHALL read SLACK_SIGNING_SECRET from 
   environment (no default — required for Slack adapter)
6. THE worker-service SHALL read SLACK_BOT_TOKEN from environment 
   (no default — required for Slack adapter)
7. THE worker-service SHALL read INGESTION_MAX_FILE_SIZE_KB from 
   environment with default 500
8. THE worker-service SHALL read INGESTION_MAX_CONCURRENT_FETCHES 
   from environment with default 10
9. THE worker-service SHALL read INGESTION_BATCH_SIZE from 
   environment with default 50
10. THE worker-service SHALL read NEO4J_URI from environment 
    (already may exist — ensure present)
11. THE worker-service SHALL read NEO4J_USERNAME from environment 
    (already may exist — ensure present)
12. THE worker-service SHALL read NEO4J_PASSWORD from environment 
    (already may exist — ensure present)
13. ALL environment variables SHALL be documented in a .env.example 
    file at the worker-service root with inline comments explaining 
    each variable, its default if any, and where to find the value 
    (e.g., GitHub App settings page, Slack App management page)
14. WHEN a required environment variable (no default) is missing at 
    startup, THE worker-service SHALL log a CRITICAL level message 
    listing all missing required variables and SHALL exit with 
    code 1 rather than starting in a broken state

---

### Requirement 14: End-to-End Integration Verification

**User Story:** As a platform operator, I want to verify that all 
components work together end-to-end, so that I can confirm the 
system is operational before releasing to engineering teams.

#### Acceptance Criteria

1. WHEN POST /ingestion/trigger is called with a valid repo, 
   THE Knowledge_Graph SHALL contain at least one service node 
   for that repo within 5 minutes
2. WHEN POST /ingestion/trigger is called with a valid repo, 
   THE Embedding_Store SHALL contain at least one chunk for that 
   repo within 5 minutes
3. WHEN a user asks a question about an ingested repo via 
   POST /assistant/ask, THE QAResponse SHALL have had_rag_results=
   true and citations referencing actual file paths from that repo
4. WHEN GET /simulation/impact?repo=&change=deprecate_endpoint&
   path=/v1/users is called after ingestion, THE response SHALL 
   reference at least one affected service from the Knowledge_Graph 
   rather than returning an empty blast radius
5. WHEN ingestion completes, GET /simulation/time-travel/snapshots?
   repo= SHALL return at least one snapshot with a valid_from 
   timestamp matching the ingestion time
6. WHEN a PR is opened on a GitHub repository with the KA-CHOW 
   GitHub App installed, a GitHub Check Run SHALL appear on the 
   PR within 30 seconds with status "in_progress"
7. WHEN the Policy_Engine completes processing a pull_request event, 
   the GitHub Check Run SHALL update to status "completed" with 
   the appropriate conclusion
8. WHEN a multi-turn conversation has mentioned "payments service" 
   in turn 1 and asks "what calls it?" in turn 2, THE QAResponse 
   for turn 2 SHALL have been classified with intent 
   "architecture.trace_dependency" using "payments service" as 
   the resolved entity
9. WHEN GET /qa/gaps?repo= is called 24 hours after system operation, 
   THE GapReport SHALL contain at least one KnowledgeGap for the 
   repo if any questions returned had_rag_results=false
10. WHEN @KA-CHOW is mentioned in a Slack channel where the app is 
    installed, THE Slack channel SHALL receive a Block Kit response 
    within 10 seconds
11. WHEN the CLI client is run with a question about an ingested repo, 
    THE terminal SHALL begin displaying streamed tokens within 2 
    seconds of invocation

---

## Appendix A — API Contract

All new endpoints accept and return JSON unless otherwise noted. 
All requests must include Authorization: Bearer {token} and 
X-Repo-Scope: {repo} headers.

**Ingestion Endpoints**
POST /ingestion/trigger
  Request: { repo: str }
  Response: { run_id: str, status: "running" }
  Auth: required

GET /ingestion/status/{repo}
  Response: IngestionStatus { run_id, repo, status, 
    files_processed, chunks_created, embeddings_created, 
    services_detected, started_at, completed_at, error_message }
  Auth: required

GET /ingestion/runs/{repo}
  Response: list[IngestionResult] — last 20 runs ordered by 
    started_at descending
  Auth: required

**Gap Detection Endpoint**
GET /qa/gaps
  Query params: repo (required), days (optional, default 7)
  Response: GapReport { repo, generated_at, total_gaps, 
    gaps_by_service, top_gaps, documentation_debt_score }
  Auth: required

**Slack Adapter Endpoint**
POST /adapters/slack/webhook
  Request: Slack event payload (raw body required for signature)
  Response: HTTP 200 { ok: true } or HTTP 403 { error: str }
  Auth: Slack signature verification (not Bearer token)

**CLI Adapter Endpoint**
POST /adapters/cli/ask
  Request: { question: str, repo: str, session_id: str | None }
  Response: StreamingResponse (text/event-stream)
  Auth: Bearer token

**GitHub Webhook Endpoint**
POST /webhooks/github
  Request: GitHub webhook payload (raw body required for signature)
  Response: HTTP 200 { ok: true } or HTTP 401 { error: str }
  Auth: HMAC-SHA256 webhook signature verification

---

## Appendix B — Performance Targets

**Ingestion Pipeline**
Full repo ingestion (up to 500 files): complete within 5 minutes
Incremental ingestion (changed files only): complete within 60 seconds
POST /ingestion/trigger response time: under 200ms (Kafka produce 
  is async, response is immediate)

**Impact Analyzer**
Neo4j dependency query with cache hit: under 50ms
Neo4j dependency query with cache miss: under 500ms
Full impact analysis including LLM explanation: under 10 seconds

**Webhook Handler**
POST /webhooks/github response time: under 500ms for all event types
GitHub Check Run creation: within 2 seconds of webhook receipt
Policy check completion and Check Run update: within 60 seconds 
  of webhook receipt

**Q&A with Hierarchical Intent**
Coarse intent classification: unchanged from current performance
Sub-intent classification (second LLM call): adds at most 1 second 
  to total response time

**Gap Detection**
GET /qa/gaps for 7-day window with up to 10,000 log rows: 
  under 2 seconds (idx_qa_event_log_gap_detection index enforces this)

**Slack Adapter**
First Slack response after mention: within 10 seconds
Webhook acknowledgment (HTTP 200): within 500ms

**CLI Adapter**
First streamed token to terminal: within 2 seconds of invocation

---

## Appendix C — Kafka Topic Schemas

All Kafka messages are JSON-encoded. All timestamps are ISO 8601.

**Topic: repo.ingestion**
{ 
  "repo": str,              // full repo name e.g. "org/repo"
  "triggered_by": str,      // "webhook" | "manual" | "scheduled"
  "changed_files": list[str] | null,  // null = full ingestion
  "commit_sha": str         // head commit SHA
}

**Topic: repo.ingestion.complete**
{
  "repo": str,
  "run_id": str,            // UUID from meta.ingestion_runs
  "files_processed": int,
  "chunks_created": int,
  "embeddings_created": int,
  "services_detected": int,
  "duration_seconds": float,
  "status": str,            // "success" | "failed"
  "triggered_at": str       // ISO 8601 timestamp
}

**Topic: repo.events (pull_request event type)**
{
  "event_type": "pull_request",
  "repo": str,
  "pr_number": int,
  "head_sha": str,
  "base_branch": str,
  "changed_files": list[str],
  "additions": int,
  "deletions": int,
  "triggered_at": str       // ISO 8601 timestamp
}

**Consumer group assignments**
repo.events → worker-service policy pipeline consumer
repo.ingestion → worker-service ingestion pipeline consumer
repo.ingestion.complete → worker-service pipeline.py consumer 
  (triggers time travel snapshot)
pr.checks → agent-service github bridge consumer
pr.checks.dlq → dead letter queue, monitored but not consumed