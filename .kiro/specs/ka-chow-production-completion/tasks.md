# Implementation Tasks: KA-CHOW Production Completion

## Overview

This task file maps directly to the Design Document and Requirements Document. Every task is traceable to a requirement and a design decision. Tasks are ordered by dependency — complete them in sequence within each task group. Do not mark a task complete until all sub-tasks pass their corresponding verification in Task 14.

**Dependency order across tasks:**
Task 12 (schema) → Task 1 (ingestion) → Task 2 (Neo4j) → Task 3 (temporal) → Task 4 (webhook) → Tasks 5-9 (Q&A improvements) → Tasks 10-11 (adapters) → Task 13 (env config) → Task 14 (verification)

---

## Task 1: GitHub Repository Ingestion Pipeline

> **Design ref:** Components 1.1–1.6 | **Requirements ref:** Requirement 1 (all criteria)
> **Blocks:** Task 2, Task 3, Task 14.1

- [x] **1.1 Implement GitHubRepoCrawler**
  > File: `worker-service/app/ingestion/crawler.py`
  > Design ref: GitHubRepoCrawler class structure
  - [x] 1.1.1 Create `worker-service/app/ingestion/` directory with `__init__.py`
  - [x] 1.1.2 Create `crawler.py` with `FileContent` and `RepoCrawlResult` dataclasses matching the design exactly — `last_modified: datetime | None` must be present on `FileContent` for freshness scoring downstream
  - [x] 1.1.3 Implement `_create_jwt()` using RS256 algorithm with payload `{"iat": now-60, "exp": now+540, "iss": app_id}` — the 60-second backdate is required by GitHub
  - [x] 1.1.4 Implement `_get_installation_token()` with token caching; refresh when `datetime.now(timezone.utc) < expiry - timedelta(minutes=1)` — cache key is `"default"`, value is `(token, expiry)` tuple
  - [x] 1.1.5 Implement `_get_default_branch()` via `GET /repos/{owner}/{repo}` returning `default_branch` field
  - [x] 1.1.6 Implement `_get_branch_sha()` via `GET /repos/{owner}/{repo}/git/ref/heads/{branch}` returning `object.sha`
  - [x] 1.1.7 Implement `_fetch_tree()` via `GET /repos/{owner}/{repo}/git/trees/{sha}?recursive=1` — filter result to `item["type"] == "blob"` only
  - [x] 1.1.8 Implement `_fetch_file_content()` within `asyncio.Semaphore` context — return `None` on 404, return `None` if `size_bytes > max_file_size_bytes`, decode base64 content with `errors="replace"` to handle binary files gracefully
  - [x] 1.1.9 Implement `_should_include_file()` checking all three conditions in order: extension in `EXTENSION_WHITELIST`, no path segment in `PATH_BLACKLIST`, `size_bytes <= max_file_size_bytes` — size check uses value from response header `size` field, not file content length
  - [x] 1.1.10 Implement `_handle_rate_limit()` reading `X-RateLimit-Remaining` and `X-RateLimit-Reset` headers — sleep for `max(0, reset_ts - int(time.time())) + 5` seconds when remaining < 100; the +5 is a safety buffer
  - [x] 1.1.11 Implement exponential backoff for 429 responses: `wait = 2 ** attempt`, `await asyncio.sleep(min(wait, 60))`, max 5 attempts before returning `None` — this is separate from rate limit handling
  - [x] 1.1.12 Implement `crawl_repo()` supporting both full (`changed_files=None`) and incremental (`changed_files=list[str]`) modes — incremental skips tree fetch entirely and constructs `file_items` directly from the list
  - [x] 1.1.13 Initialize `EXTENSION_WHITELIST` and `PATH_BLACKLIST` as class-level constants, not instance variables — `.next/` and `.nuxt/` must be included in the blacklist alongside the standard entries

- [x] **1.2 Implement CodeChunker**
  > File: `worker-service/app/ingestion/chunker.py`
  > Design ref: CodeChunker class structure
  - [x] 1.2.1 Create `chunker.py` with `Chunk` dataclass — `chunk_id` and `repo` start as empty strings `""` and are filled by `chunk_files()` after extraction, not inside individual extractors
  - [x] 1.2.2 Implement `_extract_python()` using `ast.parse()` — filter with `node.col_offset != 0` to exclude nested functions and methods; on `SyntaxError` fall back to `_sliding_window()` with a DEBUG log
  - [x] 1.2.3 Implement `_extract_typescript()` and `_extract_javascript()` — `_extract_javascript` must delegate to `_extract_typescript` identically; context window is 30 lines after match start with 2 lines before
  - [x] 1.2.4 Implement `_extract_go()` — must handle both func pattern `r'func\s+(?:\(([^)]+)\)\s+)?(\w+)\s*\('` (receiver in group 1, name in group 2) and type pattern `r'type\s+(\w+)\s+(?:struct|interface)'` (name in group 1); receiver_type in metadata must be None for non-method functions
  - [x] 1.2.5 Implement `_extract_markdown()` — split on `r'\n(?=#{2,3}\s)'`; skip empty sections; `section_title` in metadata is the heading text with `#` symbols stripped; `line_offset` must accumulate correctly across sections
  - [x] 1.2.6 Implement `_extract_yaml()` with three branches in this exact priority order: (1) OpenAPI check — `"openapi" in parsed or "swagger" in parsed`; (2) Kubernetes check — `"kind" in parsed and "apiVersion" in parsed`; (3) generic fallback — entire file as one chunk with `source_type="config"`
  - [x] 1.2.7 Implement `_extract_json()` — try `json.loads()`, check for `"openapi"` or `"swagger"` key, convert to YAML string via `yaml.dump()` and create a fake `FileContent` with `extension=".yaml"` to reuse `_extract_yaml()`; on `JSONDecodeError` return entire file as one chunk
  - [x] 1.2.8 Implement `_extract_proto()` — regex patterns must use `re.DOTALL`; `is_service` determined by `match.group(0).startswith("service")`; `proto_type` in metadata is `"service"` or `"message"`
  - [x] 1.2.9 Implement `_extract_sql()` — regex must capture `CREATE OR REPLACE FUNCTION` in addition to `CREATE TABLE`, `CREATE INDEX`, `CREATE UNIQUE INDEX`, `CREATE FUNCTION`; object name extracted with `re.IGNORECASE`
  - [x] 1.2.10 Implement `_extract_terraform()` — regex captures resource type (group 1) and resource name (group 2); `source_type="infra"`
  - [x] 1.2.11 Implement `_sliding_window()` — step = `window_lines - overlap_lines` = 40; `source_type` determined by extension: `"code"` for `.py`, `.ts`, `.js`, `.go`, `.java`; `"config"` for everything else
  - [x] 1.2.12 Implement `_subdivide_large_chunk()` — step = `max_chunk_chars - overlap` = 1800; iterate `range(0, len(content), step)`; each sub-chunk gets `sub_chunk_index` and `original_start_line` in metadata merged with parent metadata; must never truncate — all content appears in at least one sub-chunk
  - [x] 1.2.13 Implement `_compute_chunk_id()` — `hashlib.sha256(f"{repo}:{path}:{content}".encode()).hexdigest()`; this exact string format is required for deduplication consistency with `EmbeddingPopulator`
  - [x] 1.2.14 Implement `chunk_files()` — for each file: get extractor from dict with `_sliding_window` as default, call in try-except wrapping the extractor call, subdivide oversized chunks, then assign `chunk.repo = repo` and `chunk.chunk_id = _compute_chunk_id(...)` in a final pass

- [x] **1.3 Implement ServiceDetector and DependencyExtractor**
  > File: `worker-service/app/ingestion/service_detector.py`
  > Design ref: ServiceDetector and DependencyExtractor class structures
  - [x] 1.3.1 Create `service_detector.py` with `ServiceManifest` dataclass — all boolean fields (`has_dockerfile`, `has_openapi`, etc.) must default to `False`, not `None`
  - [x] 1.3.2 Define `SERVICE_MARKERS = {"Dockerfile", "pyproject.toml", "package.json", "go.mod"}` as a class constant on `ServiceDetector`
  - [x] 1.3.3 Implement `detect_services()` — group files by top-level directory (`file.path.split("/")[0]`); detect marker presence by comparing `{Path(f.path).name for f in dir_files}` against `SERVICE_MARKERS`; also detect `k8s/` or `kubernetes/` subdirectory presence
  - [x] 1.3.4 Implement docker-compose service union — call `_parse_docker_compose_services()` and add any service names not already in `{s.service_name for s in services}` as skeleton `ServiceManifest` entries with `language="unknown"`
  - [x] 1.3.5 Implement `_determine_language()` using `Counter` — count only extensions in `{".py", ".ts", ".js", ".go", ".java"}`; return `counter.most_common(1)[0][0]` or `"unknown"` if counter is empty
  - [x] 1.3.6 Implement `_extract_owner_from_codeowners()` — check both `"CODEOWNERS"` and `".github/CODEOWNERS"` paths; split each line, check if `dir_path` is in `parts[0]`, return `parts[1].lstrip("@")`
  - [x] 1.3.7 Implement `_extract_endpoints()` — only process files with `"openapi"` in `f.content[:500].lower()`; use `yaml.safe_load()` with a try-except and return `parsed.get("paths", {}).keys()`
  - [x] 1.3.8 Implement `_parse_docker_compose_services()` — only process files named `"docker-compose.yaml"` or `"docker-compose.yml"`; return `list(parsed.get("services", {}).keys())`
  - [x] 1.3.9 Implement `DependencyExtractor.extract_dependencies()` — union results from all three sources, call `list(set(deps))` to deduplicate before returning
  - [x] 1.3.10 Implement `_parse_docker_compose()` — handle both list and dict `depends_on` formats; `isinstance(depends_on, dict)` → `list(depends_on.keys())`; only include deps where target is in `service_names`
  - [x] 1.3.11 Implement `_parse_k8s_services()` — extract Kubernetes `kind: Service` names into `k8s_service_names` set; create `"network"` tuples for pairs where both are in `service_names` and source ≠ target
  - [x] 1.3.12 Implement `_parse_import_statements()` — Python pattern: `r'^(?:from|import)\s+([\w.]+)'` with `re.MULTILINE`; take first segment of dotted module name; TypeScript pattern: `r"from\s+['\"](@[\w-]+/[\w-]+|\.\.?/[\w/-]+)['\"]"`; take last segment and strip `@`; only include if imported name is in `service_names` and not equal to `source_service`

- [x] **1.4 Implement GraphPopulator**
  > File: `worker-service/app/ingestion/graph_populator.py`
  > Design ref: GraphPopulator class structure
  - [x] 1.4.1 Create `graph_populator.py` with `GraphPopulator` class — initialize `grpc.aio.insecure_channel(graph_service_url)` and `GraphServiceStub` in `__init__`
  - [x] 1.4.2 Implement `populate_graph()` — call the four creation methods in this exact order: service nodes → API nodes → schema nodes → dependency edges; this order ensures service nodes exist before edges reference them
  - [x] 1.4.3 Implement `_create_service_nodes()` — node_id format is `f"service:{repo}:{svc.service_name}"`; `health_score` defaults to `50.0`; `owner_hint` defaults to `""` not `None` (gRPC proto fields cannot be None); raise on `grpc.RpcError` so the pipeline marks the run as failed
  - [x] 1.4.4 Implement `_create_api_nodes()` — filter `spec_chunks` by `source_type == "spec" and c.metadata.get("http_method")`; node_id format is `f"api:{repo}:{method}:{path}"`; service_name inferred from `Path(chunk.file_path).parts[0]`; `tags` serialized as `json.dumps(list)` — not passed as a list directly to gRPC
  - [x] 1.4.5 Implement `_create_schema_nodes()` — two conditions: migration chunks (`source_type == "migration"` and `metadata.get("object_name")`) and proto service chunks (`source_type == "spec"` and `metadata.get("proto_type") == "service"`); log WARNING on `grpc.RpcError` here (non-fatal unlike service nodes)
  - [x] 1.4.6 Implement `_create_dependency_edges()` — source_id and target_id use `f"service:{repo}:{name}"` format; edge_type is `"DEPENDENCY"`; log WARNING on `grpc.RpcError` (non-fatal, partial dependency graph is acceptable)
  - [x] 1.4.7 Implement `_mirror_to_postgres()` — use `ON CONFLICT (node_id, repo) DO UPDATE SET properties = EXCLUDED.properties, label = EXCLUDED.label`; wrap in try-except, log WARNING, never raise — this is explicitly non-fatal
  - [x] 1.4.8 Implement `_build_mutation_request()` with `Mutation.UPSERT` operation for node mutations
  - [x] 1.4.9 Implement `_build_edge_mutation_request()` with `Mutation.UPSERT` operation for edge mutations — UPSERT prevents duplicate edges on re-ingestion

- [x] **1.5 Implement EmbeddingPopulator**
  > File: `worker-service/app/ingestion/embedding_populator.py`
  > Design ref: EmbeddingPopulator class structure
  - [x] 1.5.1 Create `embedding_populator.py` with `EmbeddingPopulator` class
  - [x] 1.5.2 Implement `_process_batch()` — build `EmbeddingChunk` objects propagating `last_modified` from `c.metadata.get("last_modified")` into the embedding metadata — this field is required for freshness scoring in Task 7
  - [x] 1.5.3 Implement `_update_progress()` — UPDATE `chunks_created` and `embeddings_created` on `meta.ingestion_runs` WHERE `id = run_id`; call after every batch, not just at the end
  - [x] 1.5.4 Implement `_mark_run_failed()` — UPDATE `status = 'failed'`, `error_message = error_message`, `completed_at = NOW()` WHERE `id = run_id`
  - [x] 1.5.5 Implement `populate_embeddings()` — iterate in steps of `self.batch_size`; on exception: call `_mark_run_failed()` then `raise` to halt the pipeline; existing embeddings are preserved because there is no DELETE path
  - [x] 1.5.6 Return `(chunks_processed, embeddings_created)` tuple where `chunks_processed` is the count of chunks sent to the API and `embeddings_created` is the count returned by `upsert_chunks()`

- [x] **1.6 Implement IngestionPipeline**
  > File: `worker-service/app/ingestion/ingestion_pipeline.py`
  > Design ref: IngestionPipeline class structure and API endpoints
  - [x] 1.6.1 Create `ingestion_pipeline.py` with `IngestionResult` and `IngestionStatus` dataclasses and `IngestionPipeline` class — `dep_extractor: DependencyExtractor` must be a constructor parameter (was missing from original design)
  - [x] 1.6.2 Implement `ingest_repo()` — call `_start_run()` first, then execute in strict sequence: crawl → chunk → detect services → extract dependencies → populate graph → populate embeddings; on any exception call `_fail_run()` and return a failed `IngestionResult` with zeroed counters — do not re-raise
  - [x] 1.6.3 Implement `ingest_on_push()` — same sequence as `ingest_repo()` but passes `changed_files` to `crawler.crawl_repo()`; on exception call `_fail_run()` and re-raise (unlike full ingestion, incremental failures should surface to the caller)
  - [x] 1.6.4 Implement `get_ingestion_status()` — query `meta.ingestion_runs WHERE repo = %s ORDER BY started_at DESC LIMIT 1`; raise `HTTPException(404)` if no rows found
  - [x] 1.6.5 Implement `_start_run()` — INSERT with `status='running'`; use `run_id` as the `id` value
  - [x] 1.6.6 Implement `_complete_run()` — UPDATE with `status='success'`, `completed_at=NOW()`, and all counter fields
  - [x] 1.6.7 Implement `_fail_run()` — UPDATE with `status='failed'`, `completed_at=NOW()`, `error_message`
  - [x] 1.6.8 Implement `_emit_completion_event()` — produce to `"repo.ingestion.complete"` topic using the exact Kafka schema from Appendix C of the requirements document; include `services_detected` field
  - [x] 1.6.9 Add `POST /ingestion/trigger` — respond immediately with `{run_id, status: "running"}`; run `pipeline.ingest_repo()` in a `BackgroundTask`; generate a new `run_id` via `uuid.uuid4()` at the endpoint level
  - [x] 1.6.10 Add `GET /ingestion/status/{repo}` — call `pipeline.get_ingestion_status(repo)`
  - [x] 1.6.11 Add `GET /ingestion/runs/{repo}` — query `meta.ingestion_runs WHERE repo = %s ORDER BY started_at DESC LIMIT 20`
  - [x] 1.6.12 Add `_consume_ingestion_events()` async method to `pipeline.py` consuming the `"repo.ingestion"` Kafka topic alongside the existing `"repo.events"` consumer in `_run_loop()` — dispatch to `ingest_repo()` when `changed_files` is None, dispatch to `ingest_on_push()` when `changed_files` is a non-empty list

- [x] **1.7 Database schema**
  > Migration file: `worker-service/migrations/003_ingestion_and_gaps.sql`
  > Design ref: Database Schema section
  - [x] 1.7.1 Create `meta.ingestion_runs` — all columns per design including `services_detected INTEGER DEFAULT 0` which was missing from the original task list
  - [x] 1.7.2 Create index `idx_ingestion_runs_repo` on `(repo, started_at DESC)`
  - [x] 1.7.3 Create `meta.graph_nodes` — `properties JSONB`, PRIMARY KEY `(node_id, repo)`, `idx_graph_nodes_repo_type` on `(repo, node_type)`, `idx_graph_nodes_label` on `(repo, node_type, label)` — the label index is required for `_infer_service()` in Gap Detector
  - [x] 1.7.4 All statements must use `IF NOT EXISTS` — migration is run at startup by `ensure_schema()` and must be idempotent

- [x] **1.8 Environment configuration**
  > Requirements ref: Requirement 13
  - [x] 1.8.1 Add `GITHUB_APP_ID` — required, no default; startup must fail with exit code 1 if missing
  - [x] 1.8.2 Add `GITHUB_APP_PRIVATE_KEY` — PEM string, required, no default
  - [x] 1.8.3 Add `GITHUB_INSTALLATION_ID` — required, no default
  - [x] 1.8.4 Add `INGESTION_MAX_CONCURRENT_FETCHES` — default `10`
  - [x] 1.8.5 Add `INGESTION_MAX_FILE_SIZE_KB` — default `500`
  - [x] 1.8.6 Add `INGESTION_BATCH_SIZE` — default `50`
  - [x] 1.8.7 Add startup validation: collect all missing required variables at once, log one CRITICAL message listing all of them, then `sys.exit(1)` — do not fail on the first missing variable

---

## Task 2: Neo4j Graph Service Integration for Impact Analyzer

> **Design ref:** Component 2 (Impact Analyzer Integration)
> **Requirements ref:** Requirement 2 (all criteria)
> **Depends on:** Task 1 (graph_nodes mirror table must exist)
> **Blocks:** Task 14.4

- [x] **2.1 Update Impact Analyzer with real Neo4j queries**
  > File: `worker-service/app/simulation/impact_analyzer.py`
  - [x] 2.1.1 Add `graph_service_url: str` and `pg_cfg: dict` as constructor parameters — do not change any other constructor behavior
  - [x] 2.1.2 Initialize `grpc.aio.insecure_channel(graph_service_url)` and `GraphServiceStub` in `__init__`
  - [x] 2.1.3 Add `_cache: dict[str, tuple[Any, float]] = {}` and `_cache_ttl: int = 60` — cache entries are `(data, expiry_timestamp)` tuples where `expiry_timestamp = time.time() + 60`
  - [x] 2.1.4 Implement `_get_dependency_edges()` with cache check first, then Cypher query: `MATCH (s:Service {repo: $repo})-[r:DEPENDENCY]->(t:Service) RETURN s.service_name AS source, t.service_name AS target, r.dependency_type AS type` — transform rows to `list[tuple[str, str, str]]` matching the format the existing BFS traversal already expects; do not modify BFS logic
  - [x] 2.1.5 Implement `_get_dependency_edges_from_postgres()` — query `meta.graph_nodes` with a self-join on `(n1.properties->>'depends_on') = n2.label`; default `type` to `"runtime"` when column is NULL
  - [x] 2.1.6 Implement `_get_service_node()` with cache check, Cypher `MATCH (s:Service {service_name: $name, repo: $repo}) RETURN s`, and PostgreSQL fallback querying `meta.graph_nodes` by `label = service_name`
  - [x] 2.1.7 Implement `_get_api_nodes()` with Cypher `MATCH (a:API {repo: $repo}) WHERE a.path CONTAINS $path_fragment RETURN a` and PostgreSQL fallback using `LIKE %path_fragment%`
  - [x] 2.1.8 Implement `get_dependency_graph()` with Cypher `MATCH (n)-[r]->(m) WHERE n.repo = $repo RETURN n, r, m` — use 10s timeout; transform to `{"nodes": list, "edges": list}` dict
  - [x] 2.1.9 Implement `invalidate_cache()` — delete all keys matching `f":{repo}:"` in key or ending with `f":{repo}"`; log INFO with count of deleted entries
  - [x] 2.1.10 All gRPC calls use 5s timeout except `get_dependency_graph()` which uses 10s
  - [x] 2.1.11 Every fallback must log `WARNING` with `f"Neo4j {method_name} failed for {repo}, using PostgreSQL fallback: {e.code()} {e.details()}"` — the error code and details are required for operator debugging

- [x] **2.2 Wire cache invalidation**
  > File: `worker-service/app/policy/pipeline.py`
  - [x] 2.2.1 Add `_handle_ingestion_complete()` async method to pipeline that receives the `repo.ingestion.complete` Kafka payload
  - [x] 2.2.2 Inside `_handle_ingestion_complete()`: call `self.impact_analyzer.invalidate_cache(payload["repo"])` — this is separate from `record_ingestion_snapshot()` (Task 3) but called from the same handler
  - [x] 2.2.3 Register `_handle_ingestion_complete()` as a consumer for `"repo.ingestion.complete"` topic in `_run_loop()`

- [x] **2.3 Environment configuration**
  - [x] 2.3.1 Add `GRAPH_SERVICE_URL` — default `"graph-service:50051"`; used by both Impact Analyzer and Time Travel System
  - [x] 2.3.2 Update Impact Analyzer instantiation in `worker-service/app/main.py` to pass `graph_service_url=os.environ["GRAPH_SERVICE_URL"]`

---

## Task 3: Temporal Graph Data Population

> **Design ref:** Component 3 (Time Travel System Integration)
> **Requirements ref:** Requirement 3 (all criteria)
> **Depends on:** Task 1 (ingestion pipeline must emit `repo.ingestion.complete`), Task 2 (gRPC stub must be initialized)
> **Blocks:** Task 14.3

- [x] **3.1 Implement temporal snapshot recording**
  > File: `worker-service/app/simulation/time_travel.py`
  - [x] 3.1.1 Add `record_ingestion_snapshot(repo: str, ingestion_result: IngestionResult) -> str` method to `TemporalGraphStore`
  - [x] 3.1.2 Implement `_query_current_nodes()` using Cypher `MATCH (n {repo: $repo}) RETURN n` with 10s timeout — construct `TemporalNode` objects with `valid_from=now, valid_to=None`
  - [x] 3.1.3 Implement `_query_current_edges()` using Cypher `MATCH (n {repo: $repo})-[r]->(m) RETURN r, n.service_name AS source, m.service_name AS target`
  - [x] 3.1.4 Implement `_get_latest_snapshot_meta()` — query `meta.architecture_snapshots WHERE repo = %s AND event_type = 'ingestion' ORDER BY timestamp DESC LIMIT 1`; return `{"node_ids": json.loads(row["node_ids"])}` or `None`
  - [x] 3.1.5 Compute diff: `removed_ids = previous_node_ids - current_node_ids`; `added = [n for n in current_nodes if n.node_id not in previous_node_ids]`
  - [x] 3.1.6 Update `valid_to` for removed nodes: `UPDATE meta.architecture_nodes SET valid_to = %s WHERE repo = %s AND node_id = ANY(%s) AND valid_to IS NULL`
  - [x] 3.1.7 Insert new `TemporalNode` records via the existing `add_node()` method
  - [x] 3.1.8 Insert snapshot record into `meta.architecture_snapshots` with `snapshot_id`, `repo`, `timestamp`, `node_ids` (JSON array), `edge_count`, `services_count`, `event_type='ingestion'`
  - [x] 3.1.9 Log `INFO` with `f"Temporal snapshot {snapshot_id}: +{len(added)} nodes, -{len(removed_ids)} nodes"`
  - [x] 3.1.10 Return `snapshot_id` string

- [x] **3.2 Implement policy event recording**
  - [x] 3.2.1 Add `record_policy_event(repo: str, policy_run_id: int, findings: list[dict]) -> None` method
  - [x] 3.2.2 Filter to only `DOC_DRIFT_*` and `BREAKING_*` findings using `f.get("rule_id", "").startswith(("DOC_DRIFT_", "BREAKING_"))`; return immediately if no relevant findings
  - [x] 3.2.3 Insert one row per finding with `snapshot_id = f"policy_{repo.replace('/', '_')}_{policy_run_id}_{finding['rule_id']}"`, `event_type='policy_finding'`, `event_payload=json.dumps(finding)`, `node_ids='[]'`, `edge_count=0`, `services_count=0`
  - [x] 3.2.4 Use `ON CONFLICT (snapshot_id) DO NOTHING` — prevents duplicate events on Kafka re-delivery

- [x] **3.3 Implement temporal index verification**
  - [x] 3.3.1 Add `_verify_temporal_index()` method
  - [x] 3.3.2 Run `EXPLAIN SELECT * FROM meta.architecture_nodes WHERE repo = 'test' AND valid_from <= NOW() AND (valid_to IS NULL OR valid_to > NOW())`
  - [x] 3.3.3 Check if `"Index Scan"` or `"Index Only Scan"` appears anywhere in the plan string
  - [x] 3.3.4 If missing, log `WARNING` with the exact `CREATE INDEX` command: `CREATE INDEX idx_arch_nodes_temporal ON meta.architecture_nodes (repo, valid_from, valid_to);` so operators can copy-paste it
  - [x] 3.3.5 Call `_verify_temporal_index()` once during `_run_loop()` initialization — advisory check only, does not block startup

- [x] **3.4 Wire to pipeline.py**
  - [x] 3.4.1 Update `_handle_ingestion_complete()` (created in Task 2.2.1) to also call `await self.time_travel.record_ingestion_snapshot(payload["repo"], IngestionResult(**payload))`
  - [x] 3.4.2 Order within `_handle_ingestion_complete()`: call `record_ingestion_snapshot()` first, then `invalidate_cache()` — snapshot before stale cache is cleared
  - [x] 3.4.3 Add `_record_policy_temporal()` method called from `_handle_message()` after policy evaluation completes, passing `repo`, `run_id`, and the findings list

- [x] **3.5 Database schema additions**
  > Add to `worker-service/migrations/003_ingestion_and_gaps.sql`
  - [x] 3.5.1 Add `event_type TEXT` column to `meta.architecture_snapshots` — values: `'ingestion'`, `'policy_finding'`
  - [x] 3.5.2 Add `event_payload JSONB` column to `meta.architecture_snapshots` — NULL for ingestion snapshots, populated for policy finding events
  - [x] 3.5.3 Add unique constraint on `snapshot_id` in `meta.architecture_snapshots` — required for `ON CONFLICT` in `record_policy_event()`
  - [x] 3.5.4 Note: `idx_arch_nodes_temporal` is advisory — `_verify_temporal_index()` will prompt operators to create it; do not include in the migration to avoid errors if `meta.architecture_nodes` schema varies across deployments

---

## Task 4: GitHub Webhook for Automatic CI Triggering

> **Design ref:** Component 4 (Webhook Handler)
> **Requirements ref:** Requirement 4 (all criteria)
> **Depends on:** Task 1.6 (ingestion pipeline Kafka consumer must be running), Task 1.7 (meta.check_run_tracking must exist)
> **Blocks:** Task 14.2

- [x] **4.1 Implement webhook handler**
  > File: `agent-service/app/github_bridge.py`
  - [x] 4.1.1 Add `POST /webhooks/github` FastAPI endpoint — if this path already exists in the file, add `pull_request` handling to the existing router rather than creating a duplicate endpoint
  - [x] 4.1.2 Implement `_verify_webhook_signature()` — `body` must be raw bytes read BEFORE `json.loads()`; compute `"sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()`; use `hmac.compare_digest()` for constant-time comparison
  - [x] 4.1.3 When `GITHUB_WEBHOOK_SECRET` is not set: log `CRITICAL` and return `False` from `_verify_webhook_signature()` — fail closed, never accept unverified webhooks
  - [x] 4.1.4 Return `JSONResponse({"error": "invalid signature"}, status_code=401)` on failure — not 403, not 400
  - [x] 4.1.5 Return HTTP 200 within 500ms by passing all processing to `background_tasks.add_task()` — the 500ms target leaves safety margin within GitHub's 10-second requirement
  - [x] 4.1.6 Implement `_process_webhook_event()` dispatcher — handle `"pull_request"`, `"push"`, `"installation"`, `"installation_repositories"`; log DEBUG for unhandled event types; wrap entire function in try-except and log ERROR

- [x] **4.2 Implement pull_request handler**
  - [x] 4.2.1 Implement `_handle_pull_request_event()` — process only `action in {"opened", "synchronize"}`; return immediately for all other actions
  - [x] 4.2.2 Implement `_fetch_pr_changed_files()` — `GET /repos/{owner}/{repo}/pulls/{pr_number}/files` with 10s timeout; return `[f["filename"] for f in resp.json()]`; on failure log ERROR and return `[]` (policy check continues without file context)
  - [x] 4.2.3 Implement `_create_check_run()` — `POST /repos/{owner}/{repo}/check-runs` with `name="KA-CHOW Policy Check"`, `head_sha`, `status="in_progress"`, `started_at=now.isoformat()`; return `resp.json()["id"]`
  - [x] 4.2.4 Implement `_store_check_run_tracking()` — `INSERT INTO meta.check_run_tracking ... ON CONFLICT (repo, pr_number, head_sha) DO UPDATE SET check_run_id = EXCLUDED.check_run_id`; the ON CONFLICT handles webhook re-delivery
  - [x] 4.2.5 Check Run creation must be wrapped in its own try-except; failure logs ERROR but does NOT halt Kafka event production — policy check must proceed even if GitHub Check Run creation fails
  - [x] 4.2.6 Produce `"repo.events"` Kafka event using exact schema from Appendix C — include `event_type`, `repo`, `pr_number`, `head_sha`, `base_branch`, `changed_files`, `additions`, `deletions`, `triggered_at`
  - [x] 4.2.7 Produce `"repo.ingestion"` Kafka event only when `changed_files` is non-empty — do not produce if file list is empty
  - [x] 4.2.8 Log `INFO` with `f"PR #{pr_number} processed: {len(changed_files)} changed files, check_run_id={check_run_id}, delivery={delivery_id}"`

- [x] **4.3 Implement push handler**
  - [x] 4.3.1 Implement `_handle_push_event()` — extract `pushed_branch = ref.replace("refs/heads/", "")`; return with `log.debug()` if `pushed_branch != default_branch`
  - [x] 4.3.2 Collect changed files from `payload.get("commits", [])` — union of `added`, `modified`, `removed` across all commits; deduplicate with `list(set(...))`
  - [x] 4.3.3 Produce `"repo.ingestion"` Kafka event with `changed_files if changed_files else None` — `None` triggers full ingestion when no individual files can be identified
  - [x] 4.3.4 Push events must NEVER produce `"repo.events"` — policy checks are PR-only

- [x] **4.4 Implement Check Run update from policy pipeline**
  > File: `worker-service/app/policy/pipeline.py`
  - [x] 4.4.1 Add `_update_check_run_from_policy()` async method — query `meta.check_run_tracking WHERE repo = %s AND pr_number = %s AND head_sha = %s`; return silently if no row found
  - [x] 4.4.2 `PATCH /repos/{owner}/{repo}/check-runs/{check_run_id}` with `status="completed"`, `conclusion="success"` when `outcome == "pass"` else `"failure"`, `completed_at=now.isoformat()`
  - [x] 4.4.3 Call `_update_check_run_from_policy()` from `_handle_message()` after `pr.checks` Kafka event is emitted

- [x] **4.5 Implement PR comment posting**
  - [x] 4.5.1 Add `_post_pr_comment()` method in `github_bridge.py`
  - [x] 4.5.2 Format findings as markdown: each finding as a bullet with `rule_id` in bold, `message`, and `fix_url` as a link if present
  - [x] 4.5.3 `POST /repos/{owner}/{repo}/issues/{pr_number}/comments` with the formatted body
  - [x] 4.5.4 Call from the `pr.checks` Kafka consumer in `github_bridge.py` after Check Run update — comment only when findings array is non-empty

- [x] **4.6 Database schema**
  > Add to migration file `003_ingestion_and_gaps.sql`
  - [x] 4.6.1 Create `meta.check_run_tracking` with `PRIMARY KEY (repo, pr_number, head_sha)` and `check_run_id BIGINT NOT NULL` — `BIGINT` is required as GitHub Check Run IDs exceed INT range

- [x] **4.7 Environment configuration**
  - [x] 4.7.1 Add `GITHUB_WEBHOOK_SECRET` — required, no default; included in startup validation from Task 1.8.7

---

## Task 5: Hierarchical Intent Classification

> **Design ref:** Component 5 (Intent Classifier Enhancement)
> **Requirements ref:** Requirement 5 (all criteria)
> **Depends on:** existing `assistant.py` and `prompts.py`
> **Blocks:** Task 14.5

- [x] **5.1 Define INTENT_TREE and expanded INTENT_EVIDENCE_MAP**
  > File: `worker-service/app/qa/assistant.py`
  - [x] 5.1.1 Add `INTENT_TREE: dict[str, list[str]]` as a module-level constant with the exact structure from the design document — do not modify the existing 8 coarse intents; add them as keys mapping to sub-intent lists
  - [x] 5.1.2 `health`, `waiver`, and `general` must map to single-item lists `["health"]`, `["waiver"]`, `["general"]` — this ensures `len(candidates) <= 1` check skips Stage 2 for these intents
  - [x] 5.1.3 Expand `INTENT_EVIDENCE_MAP` by adding sub-intent entries alongside existing coarse entries — do not remove or modify existing coarse entries, only add new sub-intent keys

- [x] **5.2 Implement two-stage classification**
  > File: `worker-service/app/qa/assistant.py`
  - [x] 5.2.1 Modify `_classify_intent()` — Stage 1 (coarse classification) must remain byte-for-byte identical to existing behavior; only add Stage 2 logic after it
  - [x] 5.2.2 Stage 2 condition: `candidates = INTENT_TREE.get(coarse_intent, [coarse_intent]); if len(candidates) <= 1: return coarse result immediately`
  - [x] 5.2.3 Stage 2 LLM call: use `llm.generate_json()` with `SubIntentClassifierPrompt` and `response_schema(candidates)` — constrained output prevents hallucinated sub-intents
  - [x] 5.2.4 Validate `sub_intent` against `candidates` after Stage 2 — if not in candidates, log WARNING and fall back to coarse intent
  - [x] 5.2.5 Entire Stage 2 block wrapped in try-except — any exception returns `{"intent": coarse_intent, "confidence": base_confidence}` silently
  - [x] 5.2.6 Return dict includes `"reasoning": f"coarse={coarse_intent}, sub={sub_intent}"` only when Stage 2 succeeds

- [x] **5.3 Create SubIntentClassifierPrompt**
  > File: `worker-service/app/llm/prompts.py`
  - [x] 5.3.1 Add `SubIntentClassifierPrompt` class following the exact same pattern as `QAIntentClassifierPrompt` — `system_prompt` as class attribute, `user_prompt()` and `response_schema()` as static methods
  - [x] 5.3.2 `response_schema(candidates: list[str]) -> dict` must return `{"type": "object", "properties": {"sub_intent": {"type": "string", "enum": candidates}}, "required": ["sub_intent"]}` — the `"enum"` constraint is what prevents hallucination
  - [x] 5.3.3 `user_prompt()` must include fallback instruction: `"If unsure, select the first candidate"` — this ensures a valid output even for ambiguous questions

- [x] **5.4 Update evidence gathering**
  > File: `worker-service/app/qa/assistant.py`
  - [x] 5.4.1 In `_gather_evidence()`: check `INTENT_EVIDENCE_MAP.get(full_intent)` first using the full dot-notation intent; only fall back to coarse intent lookup if full intent is not found
  - [x] 5.4.2 Never change or replace the coarse intent entries in `INTENT_EVIDENCE_MAP` — they must remain as the fallback path

---

## Task 6: Coreference Resolution for Multi-Turn Q&A

> **Design ref:** Component 6 (Coreference Resolver)
> **Requirements ref:** Requirement 6 (all criteria)
> **Depends on:** Task 1.7.3 (meta.graph_nodes must be queryable for known services)
> **Blocks:** Task 14.6

- [x] **6.1 Implement ConversationState**
  > File: `worker-service/app/qa/coreference.py` (new file)
  - [x] 6.1.1 Create `coreference.py` with `ConversationState` dataclass — fields: `entity_registry: dict[str, list[str]]`, `subject_stack: list[str]`, `turn_count: int`
  - [x] 6.1.2 `extract_entities()` service matching must use `re.search(rf'\b{re.escape(service)}\b', text, re.IGNORECASE)` — the word boundary `\b` prevents partial matches (e.g., "payment" matching "payments service")
  - [x] 6.1.3 Endpoint pattern: `r'/[a-z][a-z0-9/_\-\{\}]+'` — only include results where `e.count('/') >= 2` to exclude single-segment paths like `/health`
  - [x] 6.1.4 Schema pattern: `r'\b[A-Z][a-zA-Z]+(?:Table|Schema|Model|Record|Entity)\b'`
  - [x] 6.1.5 Engineer pattern: `r'\b[A-Z][a-z]+ [A-Z][a-z]+\b'` — intentionally broad; false positives are acceptable as engineer entities are rarely the target of pronoun substitution
  - [x] 6.1.6 `update()` must use "move to end on re-mention" semantics: if entity already in list, `remove()` then `append()` rather than just `append()` — this ensures most recently mentioned is always `[-1]`
  - [x] 6.1.7 Primary subject from question: `(q_entities["service"] or q_entities["endpoint"] or q_entities["schema"] or [None])[0]`; only append to `subject_stack` if primary is not None
  - [x] 6.1.8 `resolve_references()` must return `question` unchanged when `self.turn_count == 0` — not when registry is empty, but specifically when turn_count is 0 (first turn)
  - [x] 6.1.9 Ambiguity check: `if len(registry) >= 2 and registry[-1] != registry[-2]: continue` — skip this entity type entirely, do not fall back to a different entity
  - [x] 6.1.10 Implement `to_dict()` and `from_dict()` — `from_dict()` must provide default empty lists for all entity types in case stored state is missing a type added in a future version
  - [x] 6.1.11 Pronoun map must include `r'\bthe microservice\b'` alongside `r'\bthe service\b'` for service entity type, and `r'\bthe route\b'` and `r'\bthe path\b'` for endpoint type

- [x] **6.2 Integrate into Q&A flow**
  > File: `worker-service/app/qa/assistant.py`
  - [x] 6.2.1 Load `ConversationState` at the start of `answer_conversation()` using `session_store.get(session_id, "conversation_state")` — initialize fresh state if None
  - [x] 6.2.2 Call `_get_known_services(repo)` to fetch service names from `meta.graph_nodes WHERE repo = %s AND node_type = 'service'` — this is separate from any gRPC call
  - [x] 6.2.3 Call `state.resolve_references(question)` before ANYTHING else — before intent classification, before RAG, before evidence gathering
  - [x] 6.2.4 Log `DEBUG f"Coreference resolved: '{question}' → '{rewritten_question}'"` only when `rewritten_question != question`
  - [x] 6.2.5 Call `state.update(question, rag_result.output, known_services)` using the ORIGINAL question (not rewritten) after generation
  - [x] 6.2.6 Persist updated state: `session_store.set(session_id, "conversation_state", state.to_dict())`
  - [x] 6.2.7 `rewritten_question` field in `QAResponse` must be `None` when no substitution occurred (when `rewritten_question == question`); never set it to the same string as `original_question`

- [x] **6.3 Update QAResponse**
  > File: `worker-service/app/qa/models.py`
  - [x] 6.3.1 Add `original_question: str` field
  - [x] 6.3.2 Add `rewritten_question: str | None = None` field
  - [x] 6.3.3 Store `original_question` in conversation history, not `rewritten_question` — history should reflect what the user actually typed

---

## Task 7: Always-On Reranking with Freshness Scoring

> **Design ref:** Component 7 (RAG Chain Enhancement)
> **Requirements ref:** Requirement 7 (all criteria)
> **Depends on:** Task 1.5 (last_modified must be propagated into embedding metadata)
> **Blocks:** Task 8 (qa_event_log must be written before gap detection can function)

- [x] **7.1 Remove enable_reranking flag**
  > File: `worker-service/app/llm/chains.py`
  - [x] 7.1.1 Remove `enable_reranking` parameter from `RAGChain.__init__()` and all call sites
  - [x] 7.1.2 Remove any `if self.enable_reranking:` conditional — reranking always executes
  - [x] 7.1.3 Update `ChainStep` logging to say `"rerank"` step always runs — remove any conditional labels

- [ ] **7.2 Implement freshness scoring**
  - [x] 7.2.1 Add `freshness_score: float = 1.0` and `final_score: float = 0.0` to `ChunkResult` dataclass
  - [x] 7.2.2 Implement `_apply_freshness_scoring()` — iterate over chunks, compute `freshness_score`, compute `final_score`, sort descending by `final_score`; return the sorted list
  - [x] 7.2.3 Freshness thresholds: `age_days <= 7 → 1.2`; `age_days <= 30 → 1.1`; `age_days <= 90 → 1.0`; `age_days > 90 → 0.9` — thresholds are inclusive on the lower bound
  - [x] 7.2.4 When `last_modified` is absent from metadata: set `freshness_score = 1.0` — neutral, not penalized
  - [x] 7.2.5 Handle both string ISO format and `datetime` objects: `if isinstance(last_modified, str): last_modified = datetime.fromisoformat(last_modified)`
  - [x] 7.2.6 Handle timezone-naive datetimes: `last_modified.replace(tzinfo=timezone.utc) if last_modified.tzinfo is None else last_modified`
  - [x] 7.2.7 `final_score = (chunk.rerank_score * 0.7) + (chunk.freshness_score * 0.3)` — these weights are fixed, not configurable
  - [x] 7.2.8 Add `ChainStep("freshness_score", ...)` with log message showing score range: `f"scores range [{scored[-1].final_score:.2f}, {scored[0].final_score:.2f}]"` — note: after sort, index 0 is highest, index -1 is lowest

- [x] **7.3 Update threshold filtering**
  - [x] 7.3.1 Apply `score_threshold = 0.3` to `final_score`: `filtered = [c for c in scored if c.final_score >= self.score_threshold]`
  - [x] 7.3.2 Minimum guarantee: `if len(filtered) < 2: filtered = scored[:3]` — always use top 3, not top 2, to provide adequate context
  - [x] 7.3.3 The threshold check runs AFTER freshness scoring — never before

- [x] **7.4 Implement QA event logging**
  - [x] 7.4.1 Implement `_log_qa_event()` — called as the LAST step in `run()`, after `RAGResult` is assembled
  - [x] 7.4.2 Parse `sub_intent` from dot-notation: `parts = intent.split(".", 1); coarse = parts[0]; sub = parts[1] if len(parts) > 1 else None`
  - [x] 7.4.3 `had_rag_results = len(filtered) > 0` — not `len(chunks) > 0`; uses the post-threshold filtered count
  - [x] 7.4.4 `top_chunk_source = filtered[0].source_ref if filtered else None`
  - [x] 7.4.5 Entire method wrapped in try-except; on exception: `log.warning(f"QA event log write failed: {e}")`; never raise or return error — the QA response must always be returned regardless of logging success

- [x] **7.5 Database schema**
  > Add to `worker-service/migrations/003_ingestion_and_gaps.sql`
  - [x] 7.5.1 Create `meta.qa_event_log` with all columns per design — `had_rag_results BOOLEAN NOT NULL DEFAULT FALSE` is critical for gap detection
  - [x] 7.5.2 Create `idx_qa_event_log_repo_created` on `(repo, created_at DESC)` — general purpose index
  - [x] 7.5.3 Create partial index `idx_qa_event_log_gap_detection` on `(repo, confidence, created_at DESC) WHERE had_rag_results = false` — partial keeps this index small and fast

---

## Task 8: Documentation Gap Detection

> **Design ref:** Component 8 (Gap Detector)
> **Requirements ref:** Requirement 8 (all criteria)
> **Depends on:** Task 7 (meta.qa_event_log must be populated), Task 1.7.3 (meta.graph_nodes must exist for service inference)
> **Blocks:** Task 14.8

- [x] **8.1 Create GapDetector**
  > File: `worker-service/app/qa/gap_detector.py` (new file)
  - [x] 8.1.1 Create `gap_detector.py` with `KnowledgeGap` and `GapReport` dataclasses
  - [x] 8.1.2 `KnowledgeGap.gap_severity` must use `Literal["critical", "high", "medium", "low"]` type annotation
  - [x] 8.1.3 `GapReport.documentation_debt_score` must be `float` — integer multiplication of frequency × weight can produce large values for busy repos
  - [x] 8.1.4 Define `SEVERITY_WEIGHTS: dict[str, int] = {"critical": 4, "high": 3, "medium": 2, "low": 1}` as class constant

- [x] **8.2 Implement gap detection SQL**
  - [x] 8.2.1 Implement `detect_gaps(repo: str, lookback_days: int = 7) -> list[KnowledgeGap]`
  - [x] 8.2.2 SQL must use `BOOL_OR(had_rag_results = false)` not `AVG(had_rag_results) < 1` — semantically distinct: the former flags groups where ANY question had no RAG results
  - [x] 8.2.3 `HAVING` clause: `BOOL_OR(had_rag_results = false) = true OR AVG(confidence) < 0.5` — both conditions are independent OR clauses
  - [x] 8.2.4 Use `INTERVAL '%s days'` with `(repo, lookback_days)` parameter binding — `lookback_days` is an int, not a string
  - [x] 8.2.5 `ORDER BY COUNT(*) DESC` — most frequent gaps first

- [x] **8.3 Implement severity computation**
  - [x] 8.3.1 Severity rules in strict priority order: critical requires BOTH `frequency > 10` AND `avg_confidence < 0.3`; high requires `frequency > 5` OR `avg_confidence < 0.4` (either condition sufficient); medium requires `frequency > 2`; low is the fallback
  - [x] 8.3.2 The priority order matters — a gap with `frequency=15` and `avg_confidence=0.1` is critical, not high, because critical is checked first

- [x] **8.4 Implement LLM title generation**
  - [x] 8.4.1 Single LLM call per gap: `self.llm.generate(f"What documentation title would best answer: {question}?", temperature=0.3, max_tokens=30)`
  - [x] 8.4.2 Strip leading/trailing whitespace AND double quotes: `result.text.strip().strip('"')` — LLM often wraps titles in quotes
  - [x] 8.4.3 Fallback: `f"Documentation for: {question[:60]}"` — 60 chars not 50 to give more context

- [x] **8.5 Implement service inference**
  - [x] 8.5.1 `_infer_service()` must use the same word-boundary regex as `ConversationState.extract_entities()`: `re.search(rf'\b{re.escape(service)}\b', question, re.IGNORECASE)` — consistency is required since both are looking for service names
  - [x] 8.5.2 Return `"general"` not `None` when no service matches — `"general"` is a valid `gaps_by_service` key

- [x] **8.6 Implement gap report**
  - [x] 8.6.1 `generate_gap_report()` defaults `lookback_days=7` — matches the default in `detect_gaps()`
  - [x] 8.6.2 `top_gaps = sorted(gaps, key=lambda g: g.frequency, reverse=True)[:10]` — top 10 by frequency, not by severity
  - [x] 8.6.3 `documentation_debt_score = float(sum(...))` — explicit `float()` cast prevents integer type in the response JSON

- [x] **8.7 Add API endpoint**
  - [x] 8.7.1 Add `GET /qa/gaps` to existing QA routes file
  - [x] 8.7.2 `days: int = Query(default=7, ge=1, le=365)` — the upper bound prevents runaway queries on large event logs
  - [x] 8.7.3 Instantiate `GapDetector(pg_cfg, get_llm_client())` per request — not a singleton, avoids stale connections

---

## Task 9: Channel-Aware Response Formatting

> **Design ref:** Component 9 (Channel Formatter)
> **Requirements ref:** Requirement 9 (all criteria)
> **Depends on:** existing `assistant.py` and `prompts.py`
> **Blocks:** Tasks 10, 11 (adapters depend on channel formatter)

- [x] **9.1 Create channel_formatter.py**
  > File: `worker-service/app/adapters/channel_formatter.py` (new file)
  - [x] 9.1.1 Create `worker-service/app/adapters/` directory with `__init__.py` if it does not exist
  - [x] 9.1.2 Define `ChannelProfile` dataclass with all six fields using exact types from the design
  - [x] 9.1.3 Define `CHANNEL_PROFILES` dict with all four channels — `"api"` profile must have `citation_style="none"` (the API consumer handles display formatting)
  - [x] 9.1.4 The `"chat"` profile `max_answer_sentences=4` and `tone_instruction` must specify the 3-4 sentence constraint in the instruction text as well — tone is injected into the LLM, so the instruction must match the post-generation truncation limit

- [x] **9.2 Implement ChannelFormatter**
  - [x] 9.2.1 `get_tone_instruction()` falls back to `CHANNEL_PROFILES["api"]` for unknown channels — never raises `KeyError`
  - [x] 9.2.2 `format_response()` applies transformations in this strict order: (1) strip markdown → (2) truncate sentences → (3) format citations → (4) remove chain_steps → (5) remove evidence; order matters because markdown stripping may affect sentence count

- [x] **9.3 Implement _strip_markdown()**
  - [x] 9.3.1 Regex order matters — process fenced code blocks (```` ``` ````) BEFORE inline code (`` ` ``) to prevent regex confusion
  - [x] 9.3.2 Use `re.DOTALL` flag for fenced code block removal: `re.sub(r'```[^`]*```', '', text, flags=re.DOTALL)`
  - [x] 9.3.3 Bullet point removal: `re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)` — handles indented bullets
  - [x] 9.3.4 Call `text.strip()` at the end to remove leading/trailing whitespace left by removed elements

- [x] **9.4 Implement _truncate_sentences()**
  - [x] 9.4.1 Split on `'. '` (period + space) not `'.'` alone — prevents splitting on decimal numbers and abbreviations
  - [x] 9.4.2 Return `text` unchanged when `len(sentences) <= max_sentences` — avoid unnecessary modification
  - [x] 9.4.3 Append `'.'` at the end: `'. '.join(sentences[:max_sentences]) + '.'`

- [x] **9.5 Implement _format_citations()**
  - [x] 9.5.1 Handle both dataclass citations (`hasattr(citation, 'source_ref')`) and dict citations (`citation.get('source_ref', '')`) — both formats exist in the codebase
  - [x] 9.5.2 For `citation_style="none"`: `continue` — skip the iteration entirely, do not set `display` field at all
  - [x] 9.5.3 `line` extraction: `getattr(citation, 'line', None) or citation.get('line', 0) if isinstance(citation, dict) else 0` — default to 0 when line is unavailable

- [x] **9.6 Integrate into Q&A flow**
  - [x] 9.6.1 Add `tone_instruction: str = ""` parameter to `QAAnswerPrompt.build()` — append to system message only when non-empty
  - [x] 9.6.2 Call `formatter.get_tone_instruction(channel)` BEFORE calling `rag_chain.run()` — the tone must influence generation, not just reshape the output
  - [x] 9.6.3 Pass `tone_instruction` through `rag_chain.run()` to `_generate_answer()` to `QAAnswerPrompt.build()` — trace the full call path and add the parameter at each level
  - [x] 9.6.4 Call `formatter.format_response(response, channel)` as the LAST step before returning from `answer_question()` and `answer_conversation()` — after ConversationState update, not before

---

## Task 10: Slack Delivery Adapter

> **Design ref:** Component 10 (Slack Adapter)
> **Requirements ref:** Requirement 10 (all criteria)
> **Depends on:** Task 9 (ChannelFormatter must exist), Task 6 (ConversationState must be session-persistent)
> **Blocks:** Task 14.10

- [x] **10.1 Implement SlackDeliveryAdapter**
  > File: `worker-service/app/adapters/slack/adapter.py`
  - [x] 10.1.1 Create `worker-service/app/adapters/slack/` directory with `__init__.py`
  - [x] 10.1.2 `verify_signature()` must check timestamp freshness FIRST — `abs(time.time() - ts) > 300` — before computing HMAC, to prevent wasted computation on replay attempts
  - [x] 10.1.3 Signature basestring format: `f"v0:{timestamp}:{body.decode('utf-8')}"` — this exact format is required by Slack, deviation will cause all verifications to fail
  - [x] 10.1.4 Use `hmac.compare_digest(computed, signature)` not `computed == signature` — constant-time comparison prevents timing attacks

- [x] **10.2 Implement build_block_kit()**
  - [x] 10.2.1 Answer section uses `"type": "plain_text"` not `"type": "mrkdwn"` — plain_text is safe from injection; the ChannelFormatter already strips markdown before this point
  - [x] 10.2.2 Citations context block: max 3 citations shown, then `f"+{len(citations) - 3} more"` appended as a string element — only add when `len(citations) > 3`
  - [x] 10.2.3 Confidence warning: `if response.confidence < 0.6` — add context block with `"type": "mrkdwn"` and `⚠️` emoji; this block is conditional, not always present
  - [x] 10.2.4 Follow-up buttons: `value = json.dumps({"question": question, "session_id": session_id})` — session_id embedded in button payload enables conversation continuity on button click
  - [x] 10.2.5 Button text truncation: `question[:75]` — Slack rejects button text exceeding 75 characters

- [x] **10.3 Implement deliver()**
  - [x] 10.3.1 Check `data.get("ok")` from Slack API JSON response — HTTP 200 does not mean delivery success; Slack returns HTTP 200 with `{"ok": false, "error": "..."}` for errors
  - [x] 10.3.2 On `ok=false`: `log.warning(f"Slack delivery failed: {data.get('error')}, channel={channel}")`; return `False`
  - [x] 10.3.3 Never retry, never raise — Slack delivery is best-effort; failed messages are logged not re-queued

- [x] **10.4 Implement get_or_create_session()**
  - [x] 10.4.1 Generate `new_session_id = str(uuid.uuid4())` before the INSERT — the INSERT may use the existing session_id on conflict, so we need a value ready
  - [x] 10.4.2 `ON CONFLICT (slack_channel, slack_user) DO UPDATE SET last_active_at = NOW() RETURNING session_id` — RETURNING ensures we always get back the actual session_id in use

- [x] **10.5 Implement webhook endpoint**
  > File: `worker-service/app/adapters/slack/routes.py`
  - [x] 10.5.1 Read raw body BEFORE json.loads: `body = await request.body()`
  - [x] 10.5.2 Return HTTP 403 (not 401) on Slack signature failure — Slack convention
  - [x] 10.5.3 `url_verification` MUST be handled synchronously and return `JSONResponse({"challenge": payload["challenge"]})` before any background task is added — Slack times out the verification handshake in 3 seconds
  - [x] 10.5.4 All other events processed in `background_tasks.add_task(_process_slack_event, payload)` — return `JSONResponse({"ok": True})` immediately

- [x] **10.6 Implement event handlers**
  - [x] 10.6.1 Bot message check: `if event.get("bot_id") or event.get("subtype") == "bot_message": return` — BOTH conditions must be checked; `subtype` check catches some bot messages that don't set `bot_id`
  - [x] 10.6.2 Strip @mention: `re.sub(r'<@[A-Z0-9]+>', '', event.get("text", "")).strip()` — return early if stripped question is empty string
  - [x] 10.6.3 Button action handler: parse `payload["actions"][0]["value"]` as JSON to extract `question` and `session_id`; use extracted `session_id` for conversation continuity — this is the multi-turn mechanism for Slack

- [x] **10.7 Database schema**
  > Add to `003_ingestion_and_gaps.sql`
  - [x] 10.7.1 Create `meta.slack_sessions` per design — `UNIQUE (slack_channel, slack_user)` is required for `ON CONFLICT` in `get_or_create_session()`

- [x] **10.8 Environment configuration**
  - [x] 10.8.1 Add `SLACK_SIGNING_SECRET` — required, no default
  - [x] 10.8.2 Add `SLACK_BOT_TOKEN` — required, no default
  - [x] 10.8.3 Both must be included in startup validation from Task 1.8.7

---

## Task 11: CLI Streaming Adapter

> **Design ref:** Component 11 (CLI Adapter)
> **Requirements ref:** Requirement 11 (all criteria)
> **Depends on:** Task 9 (ChannelFormatter), LLM client streaming capability
> **Blocks:** Task 14.11

- [x] **11.1 Implement SSE endpoint**
  > File: `worker-service/app/adapters/cli/routes.py`
  - [x] 11.1.1 Create `worker-service/app/adapters/cli/` directory with `__init__.py`
  - [x] 11.1.2 `session_id = request.session_id or str(uuid.uuid4())` — generate new UUID when absent; non-fatal, just loses conversation context
  - [x] 11.1.3 SSE response headers: `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`, `Connection: keep-alive` — all four are required; `X-Accel-Buffering: no` disables nginx proxy buffering
  - [x] 11.1.4 Token event format: `f"data: {json.dumps({'type': 'token', 'text': token})}\n\n"` — double newline terminates each SSE event
  - [x] 11.1.5 Metadata event: include `citations`, `follow_ups`, `confidence`, `intent` — apply `formatter.format_response(final, "cli")` before extracting these fields
  - [x] 11.1.6 Error event format: `f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"` followed immediately by `"data: [DONE]\n\n"` — client must always receive [DONE]
  - [x] 11.1.7 `[DONE]` marker: `"data: [DONE]\n\n"` — this exact format; client splits on `"\n\n"` and checks if `raw == "[DONE]"`

- [x] **11.2 Implement stream_answer() on QAAssistant**
  > File: `worker-service/app/qa/assistant.py`
  - [x] 11.2.1 Add `stream_answer(question, repo, session_id, tone_instruction="")` async generator method
  - [x] 11.2.2 Use `self.llm.generate_streaming()` — the existing streaming method on `LLMClient`
  - [x] 11.2.3 Store the final `QAResponse` (with citations, follow-ups, confidence) in the session store keyed by `f"last_response:{session_id}"` after streaming completes
  - [x] 11.2.4 Add `get_last_response(session_id: str) -> QAResponse` method that retrieves from session store

- [x] **11.3 Implement CLI client**
  > File: `worker-service/app/adapters/cli/client.py`
  - [x] 11.3.1 Shebang line: `#!/usr/bin/env python3` — must be the very first line
  - [x] 11.3.2 `load_session_id()` must validate that the file content is non-empty after `.strip()` before returning — a blank `~/.kachow/session` file should generate a new UUID
  - [x] 11.3.3 SSE parsing: `buffer += chunk` then `while "\n\n" in buffer: event_str, buffer = buffer.split("\n\n", 1)` — handles partial chunk delivery correctly across TCP packet boundaries
  - [x] 11.3.4 Token printing: `print(data["text"], end="", flush=True)` — `flush=True` is required for progressive terminal output
  - [x] 11.3.5 `[DONE]` check: check `if raw == "[DONE]": break` before attempting `json.loads(raw)` — `[DONE]` is not valid JSON and will cause `JSONDecodeError`
  - [x] 11.3.6 `EOFError` on `input()`: `except EOFError: pass` — handles piped input mode where stdin is not a terminal
  - [x] 11.3.7 Recursive follow-up: `await ask(selected, config, session_id)` — pass the SAME `session_id` so the recursive call continues the conversation
  - [x] 11.3.8 `KeyboardInterrupt` in `main()`: `print()` (newline) then `sys.exit(0)` — exit code 0 means intentional user stop, not error
  - [x] 11.3.9 HTTP 401 handling: check `if response.status_code == 401:` BEFORE calling `response.raise_for_status()` — provide clear token error message rather than generic HTTP error

- [x] **11.4 Mount routers in main.py**
  - [x] 11.4.1 Mount `slack_router` at `/adapters/slack` in `worker-service/app/main.py`
  - [x] 11.4.2 Mount `cli_router` at `/adapters/cli` in `worker-service/app/main.py`
  - [x] 11.4.3 Mount `ingestion_router` at `/ingestion` in `worker-service/app/main.py`

---

## Task 12: Database Migration Script

> **Design ref:** Database Schema section
> **Requirements ref:** Requirement 12 (all criteria)
> **Depends on:** nothing — must be created before all other tasks
> **Blocks:** All tasks that write to database

- [x] **12.1 Create migration file**
  > File: `worker-service/migrations/003_ingestion_and_gaps.sql`
  - [x] 12.1.1 All `CREATE TABLE` statements use `IF NOT EXISTS`
  - [x] 12.1.2 All `CREATE INDEX` statements use `IF NOT EXISTS`
  - [x] 12.1.3 No `DROP TABLE` or `DROP INDEX` statements — migrations are additive only; rollback is handled separately
  - [x] 12.1.4 Tables in dependency order: `meta.ingestion_runs` → `meta.graph_nodes` → `meta.qa_event_log` → `meta.slack_sessions` → `meta.check_run_tracking`
  - [x] 12.1.5 `meta.architecture_snapshots` modifications (adding `event_type` and `event_payload` columns) use `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` — the table already exists

- [x] **12.2 Include all tables from design**
  - [x] 12.2.1 `meta.ingestion_runs` — include `services_detected INTEGER DEFAULT 0` column
  - [x] 12.2.2 `meta.graph_nodes` — include both `idx_graph_nodes_repo_type` and `idx_graph_nodes_label` indexes
  - [x] 12.2.3 `meta.qa_event_log` — include all three indexes: `idx_qa_event_log_repo_created`, `idx_qa_event_log_gap_detection` (partial), and the standard primary key
  - [x] 12.2.4 `meta.slack_sessions` — include `UNIQUE (slack_channel, slack_user)` constraint inline on the table definition
  - [x] 12.2.5 `meta.check_run_tracking` — `check_run_id BIGINT NOT NULL` (not `INTEGER`)

- [x] **12.3 Wire migration to startup**
  - [x] 12.3.1 Add migration 003 execution to `ensure_schema()` in `pipeline.py`
  - [x] 12.3.2 Use a migration version tracking approach: check if `meta.ingestion_runs` exists before running migration 003 — if it exists, skip; if not, run
  - [x] 12.3.3 Migration must be idempotent — running it twice must produce no errors

---

## Task 13: Environment Configuration

> **Design ref:** Environment Variables section
> **Requirements ref:** Requirement 13 (all criteria)
> **Depends on:** nothing — configuration exists independently

- [x] **13.1 Create .env.example**
  > File: `worker-service/.env.example`
  - [x] 13.1.1 Document every variable with an inline comment explaining what it is and where to find the value
  - [x] 13.1.2 Mark required vs optional: use `# REQUIRED` and `# OPTIONAL (default: X)` comments
  - [x] 13.1.3 `GITHUB_APP_PRIVATE_KEY` example must show the multi-line PEM format with escaped newlines: `GITHUB_APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----"`

- [x] **13.2 Update docker-compose.yml**
  - [x] 13.2.1 Add all new env vars to `worker-service` service
  - [x] 13.2.2 Add `GITHUB_WEBHOOK_SECRET` to `agent-service` service
  - [x] 13.2.3 Ensure `graph-service` is in the `depends_on` list for `worker-service`
  - [x] 13.2.4 Use `${VAR:-default}` syntax for optional variables with defaults

- [x] **13.3 Startup validation**
  - [x] 13.3.1 Add startup validation to `worker-service/app/main.py` `lifespan` function or equivalent startup hook
  - [x] 13.3.2 Required variables: `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY`, `GITHUB_INSTALLATION_ID`, `GITHUB_WEBHOOK_SECRET`, `SLACK_SIGNING_SECRET`, `SLACK_BOT_TOKEN`
  - [x] 13.3.3 Collect ALL missing required variables before logging — emit one CRITICAL log message listing all missing variables then `sys.exit(1)` — do not fail one variable at a time

---

## Task 14: End-to-End Integration Verification

> **Design ref:** Integration Testing section, Performance Testing table
> **Requirements ref:** Requirement 14 (all criteria)
> **Depends on:** All tasks 1–13 must be complete
> **Note:** These are acceptance tests, not unit tests. Run against a live environment with real GitHub App credentials, real Kafka, real Neo4j, and real PostgreSQL.

- [ ] **14.1 Ingestion pipeline verification**
  - [x] 14.1.1 Trigger `POST /ingestion/trigger` with `{"repo": "test-org/test-repo"}` — verify HTTP 200 and `run_id` returned within 200ms
  - [x] 14.1.2 Poll `GET /ingestion/status/test-org/test-repo` — verify `status="success"` within 5 minutes
  - [ ] 14.1.3 Query Neo4j: `MATCH (s:Service {repo: "test-org/test-repo"}) RETURN COUNT(s)` — verify count > 0
  - [ ] 14.1.4 Query pgvector: `SELECT COUNT(*) FROM meta.embeddings WHERE metadata->>'repo' = 'test-org/test-repo'` — verify count > 0
  - [ ] 14.1.5 Query PostgreSQL: `SELECT * FROM meta.graph_nodes WHERE repo = 'test-org/test-repo' AND node_type = 'service'` — verify rows present
  - [ ] 14.1.6 Consume `repo.ingestion.complete` Kafka topic — verify event received with correct `run_id`
  - [ ] 14.1.7 Verify `meta.architecture_snapshots` has a row with `event_type='ingestion'` for the repo
  - [ ] 14.1.8 Verify `meta.ingestion_runs` final row has `status='success'`, `files_processed > 0`, `chunks_created > 0`, `services_detected > 0`

- [ ] **14.2 Webhook to policy check flow verification**
  - [x] 14.2.1 Compute valid HMAC-SHA256 signature over test payload using `GITHUB_WEBHOOK_SECRET`
  - [x] 14.2.2 POST to `agent-service/webhooks/github` with `X-GitHub-Event: pull_request` and `X-Hub-Signature-256: sha256={sig}` headers — verify HTTP 200 within 500ms
  - [ ] 14.2.3 Verify `meta.check_run_tracking` has row within 2 seconds of webhook
  - [ ] 14.2.4 Consume `repo.events` Kafka topic — verify `pull_request` event with correct `pr_number`, `head_sha`, `changed_files`
  - [ ] 14.2.5 Consume `repo.ingestion` Kafka topic — verify incremental ingestion event with same `changed_files`
  - [x] 14.2.6 Wait up to 60 seconds — verify GitHub Check Run status changes from `in_progress` to `completed`
  - [x] 14.2.7 Send webhook with invalid signature — verify HTTP 401 returned
  - [ ] 14.2.8 Send push event to non-default branch — verify no Kafka events produced
  - [ ] 14.2.9 Verify PR comment posted to GitHub when findings are non-empty

- [ ] **14.3 Temporal snapshot verification**
  - [ ] 14.3.1 After first ingestion: query `meta.architecture_snapshots WHERE event_type = 'ingestion'` — verify row with non-empty `node_ids` JSON array
  - [ ] 14.3.2 Modify a file in the test repo and trigger incremental ingestion via push webhook
  - [ ] 14.3.3 Verify second snapshot created — compare `node_ids` between first and second snapshot
  - [ ] 14.3.4 Delete a service directory in the test repo and trigger full ingestion
  - [ ] 14.3.5 Verify removed service node has `valid_to` set in `meta.architecture_nodes`
  - [ ] 14.3.6 Call `get_snapshot_at(timestamp_between_ingestions)` — verify it returns the state as of the first ingestion
  - [ ] 14.3.7 Trigger a policy run on a PR with a DOC_DRIFT finding — verify `meta.architecture_snapshots` row with `event_type='policy_finding'`

- [ ] **14.4 Impact Analyzer Neo4j integration verification**
  - [ ] 14.4.1 After ingestion, call `GET /simulation/impact?repo=&change=deprecate_endpoint&path=/v1/users` — verify response includes at least one affected service from Neo4j
  - [ ] 14.4.2 Stop Neo4j container temporarily — verify Impact Analyzer falls back to PostgreSQL and still returns results
  - [ ] 14.4.3 Verify WARNING log appears with gRPC error code when fallback triggers
  - [ ] 14.4.4 Restart Neo4j — trigger another `repo.ingestion.complete` event — verify cache invalidated and next call uses Neo4j again
  - [ ] 14.4.5 Make two identical calls within 60 seconds — verify second call is faster (cache hit, < 50ms)

- [ ] **14.5 Hierarchical intent classification verification**
  - [ ] 14.5.1 Send `POST /assistant/ask` with `{"question": "What does the payments service do?"}` — verify `intent == "architecture.explain_service"` in response
  - [ ] 14.5.2 Send question about dependencies — verify `intent == "architecture.trace_dependency"`
  - [ ] 14.5.3 Send question about health score — verify `intent == "health"` (no sub-intent, coarse only)
  - [ ] 14.5.4 Mock Stage 2 LLM call to raise an exception — verify response still returned with coarse intent
  - [ ] 14.5.5 Verify `meta.qa_event_log` has rows with `sub_intent` populated for architecture and impact questions, and `sub_intent=NULL` for health and waiver questions

- [ ] **14.6 Coreference resolution verification**
  - [ ] 14.6.1 Session turn 1: `POST /assistant/conversation` with `{"question": "What does the payments service do?", "session_id": "test-session-1"}`
  - [ ] 14.6.2 Session turn 2: same session, `{"question": "What services call it?"}` — verify `rewritten_question` contains "payments service" and `original_question` is "What services call it?"
  - [ ] 14.6.3 Session turn 3: same session, `{"question": "What calls it?"}` — verify same resolution
  - [ ] 14.6.4 New session turn 1: `{"question": "What calls it?"}` — verify `rewritten_question` is None (first turn, no state)
  - [ ] 14.6.5 Mention two different services in turn 1 — verify turn 2 pronoun is NOT resolved (ambiguity check)

- [ ] **14.7 Freshness scoring verification**
  - [ ] 14.7.1 Ingest a repo where some files were modified within the last 7 days and others were not modified for >90 days
  - [ ] 14.7.2 Query a topic covered by a recently modified file — verify that file appears in citations
  - [ ] 14.7.3 Query `meta.qa_event_log` for recent entries — verify `had_rag_results=true` and `chunk_count > 0`
  - [ ] 14.7.4 Verify in chain_steps that `"freshness_score"` step appears after `"rerank"` step

- [ ] **14.8 Gap detection verification**
  - [ ] 14.8.1 INSERT 15 rows into `meta.qa_event_log` with `had_rag_results=false` and matching `LEFT(question, 50)` for the test repo
  - [ ] 14.8.2 `GET /qa/gaps?repo=test-org/test-repo&days=7` — verify `total_gaps >= 1`
  - [ ] 14.8.3 Verify `top_gaps[0].gap_severity == "critical"` (frequency=15 > 10, confidence defaults to 0.0 < 0.3)
  - [ ] 14.8.4 Verify `documentation_debt_score == 15 * 4 == 60.0` (frequency 15, critical weight 4)
  - [ ] 14.8.5 Verify `suggested_doc_title` is non-empty and not the fallback format (LLM generated)
  - [ ] 14.8.6 Verify `days=365` returns more gaps than `days=1` for the same repo

- [ ] **14.9 Channel formatting verification**
  - [ ] 14.9.1 `channel="web"` — verify response contains markdown (headers `##`, code blocks `` ``` ``), `chain_steps` is non-empty, `citations[0].display` matches `r'^\[\d+\] .+#L\d+$'`
  - [ ] 14.9.2 `channel="chat"` — verify no markdown in answer, answer has ≤ 4 sentences, `chain_steps == []`, `citations[0].display` matches `r'^\(src: .+\)$'`
  - [ ] 14.9.3 `channel="cli"` — verify no markdown, `citations[0].display` matches `r'^.+:\d+$'`, `chain_steps == []`
  - [ ] 14.9.4 `channel="api"` — verify full response, `citations` have no `display` field modification, `chain_steps` non-empty
  - [ ] 14.9.5 `channel="unknown_channel"` — verify response matches "api" profile (fallback behavior)

- [ ] **14.10 Slack adapter verification**
  - [ ] 14.10.1 POST valid `url_verification` payload — verify `{"challenge": "..."}` returned synchronously within 1 second
  - [ ] 14.10.2 POST `app_mention` event with valid signature — verify HTTP 200 within 500ms
  - [ ] 14.10.3 Verify Slack `chat.postMessage` was called with Block Kit payload within 10 seconds
  - [ ] 14.10.4 Verify Block Kit has 4 blocks: section (answer), context (citations), context (confidence warning if < 0.6), actions (follow-up buttons)
  - [ ] 14.10.5 POST `app_mention` with `bot_id` present — verify no `chat.postMessage` call (loop prevention)
  - [ ] 14.10.6 POST `block_actions` event with button value `{"question": "...", "session_id": "..."}` — verify Q&A triggered with correct session_id
  - [ ] 14.10.7 Query `meta.slack_sessions` — verify row exists for the test channel/user pair

- [ ] **14.11 CLI adapter verification**
  - [ ] 14.11.1 `python client.py "What does the payments service do?"` with valid `~/.kachow/config.json` — verify progressive token output appears in terminal
  - [ ] 14.11.2 Verify first token appears within 2 seconds of invocation
  - [ ] 14.11.3 Verify citations printed in dim ANSI color after all tokens
  - [ ] 14.11.4 Verify follow-ups printed in cyan ANSI color with numbered list
  - [ ] 14.11.5 Type `1` at the follow-up prompt — verify a second Q&A round begins with the same session_id
  - [ ] 14.11.6 Press Enter at follow-up prompt — verify program exits cleanly with code 0
  - [ ] 14.11.7 Press Ctrl+C during streaming — verify clean newline printed and program exits with code 0
  - [ ] 14.11.8 Run with invalid token — verify `"Error: invalid token"` printed to stderr and exit code 1
  - [ ] 14.11.9 Run in piped mode: `echo "What does the payments service do?" | python client.py` — verify program exits without hanging on follow-up prompt