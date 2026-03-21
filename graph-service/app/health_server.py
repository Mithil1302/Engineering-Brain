import grpc
import os
import json
import hashlib
from datetime import datetime, timezone
from concurrent import futures
from neo4j import GraphDatabase
from app.generated import services_pb2, services_pb2_grpc


ALLOWED_MUTATION_TYPES = {
    "create_node",
    "update_node",
    "delete_node",
    "create_edge",
    "update_edge",
    "delete_edge",
}


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _safe_label(entity_kind: str) -> str:
    if not entity_kind:
        return "Entity"
    cleaned = "".join(ch for ch in entity_kind if ch.isalnum() or ch == "_")
    if not cleaned:
        return "Entity"
    return cleaned[0].upper() + cleaned[1:]


def _is_primitive(value):
    return isinstance(value, (str, int, float, bool)) or value is None


def _is_primitive_array(value):
    return isinstance(value, list) and all(_is_primitive(v) for v in value)


def _sanitize_props(payload: dict):
    sanitized = {}
    for key, value in (payload or {}).items():
        if _is_primitive(value) or _is_primitive_array(value):
            sanitized[key] = value
    return sanitized


class GraphStore:
    def __init__(self):
        self.uri = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
        self.user = os.getenv("NEO4J_USER", "neo4j")
        self.password = os.getenv("NEO4J_PASSWORD", "testtest")
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        self._ready = False
        self.ensure_schema()

    def ensure_schema(self):
        with self.driver.session() as session:
            session.run(
                "CREATE CONSTRAINT mutation_batch_id IF NOT EXISTS FOR (b:MutationBatch) REQUIRE b.id IS UNIQUE"
            )
            session.run(
                "CREATE CONSTRAINT mutation_record_id IF NOT EXISTS FOR (m:MutationRecord) REQUIRE m.id IS UNIQUE"
            )
            session.run(
                "CREATE CONSTRAINT repo_node_id IF NOT EXISTS FOR (r:Repo) REQUIRE r.id IS UNIQUE"
            )
            session.run(
                "CREATE CONSTRAINT file_node_id IF NOT EXISTS FOR (f:File) REQUIRE f.id IS UNIQUE"
            )
            session.run(
                "RETURN 1"
            )
        self._ready = True

    def is_ready(self):
        if not self._ready:
            return False
        try:
            with self.driver.session() as session:
                session.run("RETURN 1").single()
            return True
        except Exception:
            return False

    def apply_mutations(self, mutations, idempotency_key: str, correlation_id: str):
        now = _utc_now()
        batch_seed = f"{idempotency_key}:{len(mutations)}:{correlation_id}"
        batch_id = hashlib.sha256(batch_seed.encode("utf-8")).hexdigest()[:32]

        with self.driver.session() as session:
            session.run(
                """
                MERGE (b:MutationBatch {id: $batch_id})
                ON CREATE SET
                  b.idempotency_key = $idempotency_key,
                  b.correlation_id = $correlation_id,
                  b.created_at = datetime($now),
                  b.applied_count = $applied_count,
                  b.status = 'applied'
                ON MATCH SET
                  b.last_seen_at = datetime($now)
                """,
                batch_id=batch_id,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
                applied_count=len(mutations),
                now=now,
            )

            for idx, mutation in enumerate(mutations):
                payload = {}
                if mutation.payload_json:
                    try:
                        payload = json.loads(mutation.payload_json)
                    except Exception:
                        payload = {"raw_payload": mutation.payload_json}

                mutation_hash = hashlib.sha256(
                    f"{batch_id}:{idx}:{mutation.entity_id}:{mutation.type}".encode("utf-8")
                ).hexdigest()[:40]

                payload_json = json.dumps(payload)
                session.run(
                    """
                    MERGE (m:MutationRecord {id: $mutation_id})
                    ON CREATE SET
                      m.batch_id = $batch_id,
                      m.type = $type,
                      m.entity_kind = $entity_kind,
                      m.entity_id = $entity_id,
                      m.valid_from = CASE WHEN $valid_from = '' THEN null ELSE datetime($valid_from) END,
                      m.valid_to = CASE WHEN $valid_to = '' THEN null ELSE datetime($valid_to) END,
                      m.payload_json = $payload_json,
                      m.created_at = datetime($now)
                    WITH m
                    MATCH (b:MutationBatch {id: $batch_id})
                    MERGE (b)-[:CONTAINS]->(m)
                    """,
                    mutation_id=mutation_hash,
                    batch_id=batch_id,
                    type=mutation.type,
                    entity_kind=mutation.entity_kind,
                    entity_id=mutation.entity_id,
                    valid_from=mutation.valid_from or "",
                    valid_to=mutation.valid_to or "",
                    payload_json=payload_json,
                    now=now,
                )

                label = _safe_label(mutation.entity_kind)
                node_props = _sanitize_props(payload)
                if mutation.type in {"create_node", "update_node"}:
                    query = (
                        f"MERGE (n:{label} {{id: $entity_id}}) "
                        f"SET n += $payload, n.updated_at = datetime($now), n.entity_kind = $entity_kind"
                    )
                    session.run(
                        query,
                        entity_id=mutation.entity_id,
                        payload=node_props,
                        now=now,
                        entity_kind=mutation.entity_kind,
                    )
                elif mutation.type == "delete_node":
                    query = (
                        f"MERGE (n:{label} {{id: $entity_id}}) "
                        f"SET n.deleted = true, n.deleted_at = datetime($now), n.entity_kind = $entity_kind"
                    )
                    session.run(
                        query,
                        entity_id=mutation.entity_id,
                        now=now,
                        entity_kind=mutation.entity_kind,
                    )

        return batch_id


graph_store = GraphStore()


class HealthServicer(services_pb2_grpc.HealthServiceServicer):
    def Check(self, request, context):
        status = "SERVING" if graph_store.is_ready() else "NOT_SERVING"
        return services_pb2.HealthCheckResponse(status=status)


class GraphServicer(services_pb2_grpc.GraphServiceServicer):
    def ApplyMutations(self, request, context):
        meta = {k: v for k, v in context.invocation_metadata()}
        idempotency_key = meta.get("x-idempotency-key") or hashlib.sha256(_utc_now().encode("utf-8")).hexdigest()[:24]
        correlation_id = meta.get("x-correlation-id") or hashlib.sha256((idempotency_key + _utc_now()).encode("utf-8")).hexdigest()[:16]

        mutations = list(request.mutations)
        if not mutations:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("No mutations provided")
            return services_pb2.ApplyMutationsResponse(accepted=False)

        for mutation in mutations:
            if mutation.type not in ALLOWED_MUTATION_TYPES:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details(f"Invalid mutation type: {mutation.type}")
                return services_pb2.ApplyMutationsResponse(accepted=False)

        try:
            graph_store.apply_mutations(mutations, idempotency_key, correlation_id)
            return services_pb2.ApplyMutationsResponse(accepted=True)
        except Exception as exc:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(exc))
            return services_pb2.ApplyMutationsResponse(accepted=False)


def serve(port=50051):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    services_pb2_grpc.add_HealthServiceServicer_to_server(HealthServicer(), server)
    services_pb2_grpc.add_GraphServiceServicer_to_server(GraphServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    return server

if __name__ == "__main__":
    srv = serve()
    srv.wait_for_termination()
