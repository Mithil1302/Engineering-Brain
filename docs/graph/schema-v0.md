# Graph Schema v0 (Temporal)

## Nodes (core)
- **Service**: id, name, repo, path, owner_ref, tags, lifecycle (active/deprecated), created_at, language, description.
- **Endpoint/API**: id (opId or method+path+service), method, path, version, status (active/deprecated), spec_hash, service_ref, operationId, summary.
- **DataModel**: id, name, schema_hash, namespace, kind (request/response/db/message), description.
- **Field**: id, name, type, format, required, parent_model_ref, description.
- **SchemaVersion**: id (hash), source (openapi/db/asyncapi), version, captured_at.
- **Repo**: id, url, default_branch.
- **File**: id (repo+path), path, repo_ref, hash.
- **LineRange**: id (file+start+end), start, end.
- **TestCase**: id, name, framework, file_ref, line_range_ref, status (optional), last_run_at (optional).
- **Incident**: id, title, severity, opened_at, closed_at?, summary, link.
- **ADR/Decision**: id, title, status, date, context, decision, consequences, doc_ref, tags.
- **Owner/Team**: id, name, contact, oncall_ref.
- **DeploymentTarget**: id, type (service/app/container), env, region, runtime, url.
- **MessageTopic/Schema**: id, name, broker, schema_hash, type (event/command/stream), format (avro/json/proto), version.

## Edges (directed)
- **service-OWNS-endpoint** (temporal)
- **service-CALLS-service** (temporal; may include protocol + path)
- **endpoint-USES-model**
- **model-HAS-field**
- **service-DEPLOYS-TO-deploymentTarget**
- **doc-DOCUMENTS-endpoint** (doc = ADR/Decision or doc file)
- **test-COVERS-endpoint**
- **incident-IMPACTS-service**
- **decision-GOVERNS-service**
- **client-CONSUMES-endpoint** (client is another service)
- **message-PRODUCED-BY-service**; **message-CONSUMED-BY-service**
- **file-CONTAINS-lineRange**

## Temporal Modeling
- All mutable relationships carry `valid_from`, `valid_to` (null = open).
- As-of queries: filter edges where `valid_from <= t AND (valid_to IS NULL OR valid_to > t)`.
- Snapshots: no full snapshot tables; rely on versioned edges.

## Identifiers (stable keys)
- Service: repo + service_path (or manifest id).
- Endpoint: service_id + opId (preferred) else method+path.
- DataModel/Field: namespace + name (+ parent model for field).
- File: repo + file_path.
- LineRange: file_id + start + end.
- SchemaVersion: content hash.
- MessageTopic: broker + topic name.

## Indexes/Constraints (Neo4j)
- Unique on node ids (service, endpoint, model, field, file, lineRange, schemaVersion, messageTopic).
- Index on `valid_from`, `valid_to` for edges that are temporal.
- Index on endpoint.method, endpoint.path for lookup.

## Sample As-Of Queries (Cypher sketches)
- Service view as of time `t` (endpoint listing)
	- MATCH (s:Service {id:$serviceId})- [r:OWNS]->(e:Endpoint)
		WHERE r.valid_from <= $t AND (r.valid_to IS NULL OR r.valid_to > $t)
		RETURN s, e

- Impact traversal as of time `t` for an endpoint
	- MATCH (e:Endpoint {id:$endpointId})
	- OPTIONAL MATCH (c:Service)-[consumes:CONSUMES_ENDPOINT]->(e)
		WHERE consumes.valid_from <= $t AND (consumes.valid_to IS NULL OR consumes.valid_to > $t)
	- OPTIONAL MATCH (e)<-[covers:COVERS]-(tcase:TestCase)
		WHERE covers.valid_from <= $t AND (covers.valid_to IS NULL OR covers.valid_to > $t)
	- OPTIONAL MATCH (doc:Doc)-[docs:DOCUMENTS]->(e)
		WHERE docs.valid_from <= $t AND (docs.valid_to IS NULL OR docs.valid_to > $t)
	- RETURN collect(DISTINCT c) AS impacted_services,
					 collect(DISTINCT tcase) AS impacted_tests,
					 collect(DISTINCT doc) AS impacted_docs

- Upstream dependency traversal (service calls) as of time `t`
	- MATCH (s:Service {id:$serviceId})-[calls:CALLS]->(dep:Service)
		WHERE calls.valid_from <= $t AND (calls.valid_to IS NULL OR calls.valid_to > $t)
		RETURN dep

- Service dependency path with depth (as of `t`)
	- MATCH p = (s:Service {id:$serviceId})-[calls:CALLS*1..3]->(dep:Service)
		WHERE ALL(rel IN calls WHERE rel.valid_from <= $t AND (rel.valid_to IS NULL OR rel.valid_to > $t))
		RETURN p

- Docs coverage check for a service as of `t`
	- MATCH (s:Service {id:$serviceId})-[owns:OWNS]->(e:Endpoint)
		WHERE owns.valid_from <= $t AND (owns.valid_to IS NULL OR owns.valid_to > $t)
	- OPTIONAL MATCH (doc:Doc)-[docs:DOCUMENTS]->(e)
		WHERE docs.valid_from <= $t AND (docs.valid_to IS NULL OR docs.valid_to > $t)
	- RETURN e.id AS endpoint_id, COUNT(doc) AS doc_count

## Open Items
- Exact Cypher snippets to be added once runtime constraints (Neo4j version) are confirmed.
- Confirm additional node properties for SLOs/metrics linkage.
