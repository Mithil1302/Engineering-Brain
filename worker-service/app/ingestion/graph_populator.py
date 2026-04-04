"""
GraphPopulator: Write service, API, schema nodes and dependency edges to Neo4j.

Communicates with graph-service via gRPC ApplyMutations endpoint and mirrors
service/API nodes to PostgreSQL meta.graph_nodes for fallback queries.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import grpc
import psycopg2

# Import generated protobuf stubs
from ..generated import services_pb2, services_pb2_grpc
from ..generated.services_pb2 import ApplyMutationsRequest, Mutation

from .chunker import Chunk
from .service_detector import ServiceManifest

log = logging.getLogger(__name__)


class GraphPopulator:
    """Populates Neo4j graph and PostgreSQL mirror with service architecture data."""

    def __init__(self, graph_service_url: str, pg_cfg: dict[str, Any]):
        """
        Initialize gRPC channel and stub for graph service communication.
        
        Args:
            graph_service_url: gRPC endpoint (e.g., "graph-service:50051")
            pg_cfg: PostgreSQL connection config for meta.graph_nodes mirror
        """
        self.graph_service_url = graph_service_url
        self.pg_cfg = pg_cfg
        self.rpc_timeout_sec = float(os.getenv("GRAPH_POPULATOR_RPC_TIMEOUT_SEC", "60"))
        self.mutation_batch_size = int(os.getenv("GRAPH_POPULATOR_MUTATION_BATCH_SIZE", "200"))
        # Channel and stub are created lazily on first gRPC call (inside async context).
        self._channel: "grpc.aio.Channel | None" = None
        self._stub: "services_pb2_grpc.GraphServiceStub | None" = None

    def _get_stub(self) -> "services_pb2_grpc.GraphServiceStub":
        """Recreate the gRPC async channel since asyncio.run() creates and destroys loops per ingestion run."""
        if self._channel is not None:
            # Try to close old channel cleanly
            try:
                import asyncio
                if not asyncio.get_event_loop().is_closed():
                    pass # We could try to close but it's simpler to just overwrite
            except Exception:
                pass
                
        self._channel = grpc.aio.insecure_channel(self.graph_service_url)
        self._stub = services_pb2_grpc.GraphServiceStub(self._channel)
        return self._stub

    async def _apply_mutations_batched(
        self,
        mutations: list[Mutation],
        *,
        context_label: str,
        fatal_on_error: bool,
    ) -> bool:
        """
        Apply mutations in batches to avoid gRPC deadline/timeouts on large payloads.

        Returns True when all batches were accepted, False otherwise.
        """
        if not mutations:
            return True

        batch_size = max(1, self.mutation_batch_size)
        accepted_all = True

        for start in range(0, len(mutations), batch_size):
            batch = mutations[start:start + batch_size]
            request = ApplyMutationsRequest(mutations=batch)
            try:
                response = await self._get_stub().ApplyMutations(
                    request,
                    timeout=self.rpc_timeout_sec,
                )
                if not response.accepted:
                    accepted_all = False
                    msg = (
                        f"Graph service rejected {context_label} mutations "
                        f"(batch {start // batch_size + 1}, size={len(batch)})"
                    )
                    if fatal_on_error:
                        raise RuntimeError(msg)
                    log.warning(msg)
            except grpc.RpcError as e:
                accepted_all = False
                msg = (
                    f"gRPC error applying {context_label} mutations "
                    f"(batch {start // batch_size + 1}, size={len(batch)}): {e.code()} {e.details()}"
                )
                if fatal_on_error:
                    log.error(msg)
                    raise
                log.warning(msg)

        return accepted_all

    async def populate_graph(
        self,
        repo: str,
        services: list[ServiceManifest],
        chunks: list[Chunk],
        dependencies: list[tuple[str, str, str]],
        is_incremental: bool = False,
    ) -> None:
        """
        Populate graph with service architecture data in dependency order.
        
        Order is critical: service nodes → API nodes → schema nodes → dependency edges.
        This ensures service nodes exist before edges reference them.
        
        Args:
            repo: Repository full name (owner/repo)
            services: Detected service manifests
            chunks: All code chunks (filtered for spec/migration types)
            dependencies: (source, target, type) tuples
        
        Raises:
            grpc.RpcError: On service node creation failure (fatal)
        """
        log.info(f"Populating graph for {repo}: {len(services)} services, {len(dependencies)} dependencies")
        
        # Step 1: Create service nodes (fatal on failure)
        await self._create_service_nodes(repo, services, is_incremental)
        
        # Step 2: Create API nodes from OpenAPI chunks (non-fatal)
        spec_chunks = [c for c in chunks if c.source_type == "spec" and c.metadata.get("http_method")]
        await self._create_api_nodes(repo, spec_chunks)
        
        # Step 3: Create schema nodes from migration and proto chunks (non-fatal)
        migration_chunks = [c for c in chunks if c.source_type == "migration" and c.metadata.get("object_name")]
        proto_chunks = [c for c in chunks if c.source_type == "spec" and c.metadata.get("proto_type") == "service"]
        await self._create_schema_nodes(repo, migration_chunks + proto_chunks)
        
        # Step 4: Create dependency edges (non-fatal)
        await self._create_dependency_edges(repo, dependencies)
        
        log.info(f"Graph population complete for {repo}")

    async def _create_service_nodes(self, repo: str, services: list[ServiceManifest], is_incremental: bool = False) -> None:
        """
        Create Neo4j service nodes and mirror to PostgreSQL.
        
        Node ID format: service:{repo}:{service_name}
        Raises on gRPC error (fatal - pipeline marks run as failed).
        """
        # First, delete services that no longer exist (only during full ingestion)
        if not is_incremental:
            await self._delete_removed_services(repo, services)
        
        mutations = []
        for svc in services:
            node_id = f"service:{repo}:{svc.service_name}"
            payload = {
                "service_name": svc.service_name,
                "language": svc.language,
                "root_path": svc.root_path,
                "has_dockerfile": svc.has_dockerfile,
                "has_openapi": svc.has_openapi,
                "has_proto": svc.has_proto,
                "owner_hint": svc.owner_hint or "",  # gRPC proto fields cannot be None
                "health_score": 50.0,
                "last_ingested": datetime.now(timezone.utc).isoformat(),
                "repo": repo,
            }
            
            mutation = self._build_mutation_request(
                mutation_type="create_node",
                entity_kind="service",
                entity_id=node_id,
                payload=payload,
            )
            mutations.append(mutation)
        
        if mutations:
            try:
                await self._apply_mutations_batched(
                    mutations,
                    context_label=f"service nodes for {repo}",
                    fatal_on_error=True,
                )
                log.info(f"Created {len(mutations)} service nodes for {repo}")
                
                # Mirror to PostgreSQL (non-fatal)
                await self._mirror_to_postgres(repo, services, mutations)
            except grpc.RpcError as e:
                log.error(f"gRPC error creating service nodes for {repo}: {e.code()} {e.details()}")
                raise  # Fatal - pipeline must fail

    async def _delete_removed_services(self, repo: str, current_services: list[ServiceManifest]) -> None:
        """
        Delete service nodes that no longer exist in the repository.
        
        Compares current detected services with existing services in the database
        and removes any that are no longer present.
        
        Also updates meta.architecture_nodes to set valid_to for removed services.
        """
        try:
            # Get current service names from detection
            current_service_names = {svc.service_name for svc in current_services}
            
            # Get existing service names from PostgreSQL
            with psycopg2.connect(**self.pg_cfg) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT node_id FROM meta.graph_nodes
                        WHERE repo = %s AND node_type = 'service'
                        """,
                        (repo,),
                    )
                    existing_node_ids = [row[0] for row in cur.fetchall()]
            
            # Find services to delete
            services_to_delete = []
            for node_id in existing_node_ids:
                # Extract service name from node_id format: service:{repo}:{service_name}
                parts = node_id.split(":")
                if len(parts) >= 3:
                    service_name = ":".join(parts[2:])  # Handle service names with colons
                    if service_name not in current_service_names:
                        services_to_delete.append((node_id, service_name))
            
            if not services_to_delete:
                return
            
            log.info(f"Deleting {len(services_to_delete)} removed services from {repo}")
            
            # Delete from PostgreSQL and update temporal graph
            with psycopg2.connect(**self.pg_cfg) as conn:
                with conn.cursor() as cur:
                    for node_id, service_name in services_to_delete:
                        # Delete from graph_nodes
                        cur.execute(
                            """
                            DELETE FROM meta.graph_nodes
                            WHERE node_id = %s AND repo = %s
                            """,
                            (node_id, repo),
                        )
                        
                        # Update architecture_nodes to set valid_to (for temporal graph)
                        cur.execute(
                            """
                            UPDATE meta.architecture_nodes
                            SET valid_to = NOW()
                            WHERE node_id = %s AND repo = %s AND valid_to IS NULL
                            """,
                            (node_id, repo),
                        )
                        
                        log.info(f"Deleted service node {service_name} from PostgreSQL and set valid_to in temporal graph")
                conn.commit()
            
            # Delete from Neo4j via gRPC
            mutations = []
            for node_id, service_name in services_to_delete:
                mutation = Mutation(
                    type="delete_node",
                    entity_kind="service",
                    entity_id=node_id,
                    payload_json="{}",
                    valid_from=datetime.now(timezone.utc).isoformat(),
                    valid_to="",
                )
                mutations.append(mutation)
            
            if mutations:
                try:
                    await self._apply_mutations_batched(
                        mutations,
                        context_label=f"delete removed services for {repo}",
                        fatal_on_error=False,
                    )
                    log.info(f"Deleted {len(mutations)} service nodes from Neo4j for {repo}")
                except grpc.RpcError as e:
                    log.warning(f"gRPC error deleting service nodes for {repo}: {e.code()} {e.details()}")
        
        except Exception as e:
            log.warning(f"Failed to delete removed services for {repo}: {e}")



    async def _create_api_nodes(self, repo: str, spec_chunks: list[Chunk]) -> None:
        """
        Create Neo4j API nodes from OpenAPI spec chunks.
        
        Node ID format: api:{repo}:{method}:{path}
        Service name inferred from first path segment.
        Logs WARNING on gRPC error (non-fatal).
        """
        mutations = []
        for chunk in spec_chunks:
            method = chunk.metadata.get("http_method", "").upper()
            path = chunk.metadata.get("path", "")
            if not method or not path:
                continue
            
            node_id = f"api:{repo}:{method}:{path}"
            service_name = Path(chunk.file_path).parts[0] if "/" in chunk.file_path else "unknown"
            
            payload = {
                "http_method": method,
                "path": path,
                "operation_id": chunk.metadata.get("operation_id", ""),
                "service_name": service_name,
                "tags": json.dumps(chunk.metadata.get("tags", [])),  # Serialize list to JSON string
                "deprecated": chunk.metadata.get("deprecated", False),
                "repo": repo,
            }
            
            mutation = self._build_mutation_request(
                mutation_type="create_node",
                entity_kind="api",
                entity_id=node_id,
                payload=payload,
            )
            mutations.append(mutation)
        
        if mutations:
            try:
                accepted = await self._apply_mutations_batched(
                    mutations,
                    context_label=f"API nodes for {repo}",
                    fatal_on_error=False,
                )
                if accepted:
                    log.info(f"Created {len(mutations)} API nodes for {repo}")
                else:
                    log.warning(f"Some API node mutation batches were not accepted for {repo}")
            except grpc.RpcError as e:
                log.warning(f"gRPC error creating API nodes for {repo}: {e.code()} {e.details()}")

    async def _create_schema_nodes(self, repo: str, schema_chunks: list[Chunk]) -> None:
        """
        Create Neo4j schema nodes from migration and proto chunks.
        
        Two conditions:
        1. Migration chunks: source_type == "migration" and metadata.get("object_name")
        2. Proto service chunks: source_type == "spec" and metadata.get("proto_type") == "service"
        
        Logs WARNING on gRPC error (non-fatal).
        """
        mutations = []
        for chunk in schema_chunks:
            if chunk.source_type == "migration":
                # SQL migration: CREATE TABLE, CREATE INDEX, etc.
                object_name = chunk.metadata.get("object_name", "")
                if not object_name:
                    continue
                
                node_id = f"schema:{repo}:sql:{object_name}"
                payload = {
                    "object_name": object_name,
                    "statement_type": chunk.metadata.get("statement_type", "CREATE"),
                    "repo": repo,
                }
                
                mutation = self._build_mutation_request(
                    mutation_type="create_node",
                    entity_kind="schema",
                    entity_id=node_id,
                    payload=payload,
                )
                mutations.append(mutation)
            
            elif chunk.source_type == "spec" and chunk.metadata.get("proto_type") == "service":
                # Proto service definition
                proto_name = chunk.metadata.get("name", "")
                if not proto_name:
                    continue
                
                node_id = f"schema:{repo}:proto:{proto_name}"
                payload = {
                    "proto_service_name": proto_name,
                    "proto_type": "service",
                    "repo": repo,
                }
                
                mutation = self._build_mutation_request(
                    mutation_type="create_node",
                    entity_kind="schema",
                    entity_id=node_id,
                    payload=payload,
                )
                mutations.append(mutation)
        
        if mutations:
            try:
                accepted = await self._apply_mutations_batched(
                    mutations,
                    context_label=f"schema nodes for {repo}",
                    fatal_on_error=False,
                )
                if accepted:
                    log.info(f"Created {len(mutations)} schema nodes for {repo}")
                else:
                    log.warning(f"Some schema node mutation batches were not accepted for {repo}")
            except grpc.RpcError as e:
                log.warning(f"gRPC error creating schema nodes for {repo}: {e.code()} {e.details()}")

    async def _create_dependency_edges(self, repo: str, dependencies: list[tuple[str, str, str]]) -> None:
        """
        Create Neo4j dependency edges between services.
        
        Source/target ID format: service:{repo}:{name}
        Edge type: DEPENDENCY
        Logs WARNING on gRPC error (non-fatal, partial dependency graph acceptable).
        """
        mutations = []
        for source, target, dep_type in dependencies:
            source_id = f"service:{repo}:{source}"
            target_id = f"service:{repo}:{target}"
            edge_id = f"{source_id}→{target_id}"
            
            payload = {
                "source_id": source_id,
                "target_id": target_id,
                "dependency_type": dep_type,
                "repo": repo,
            }
            
            mutation = self._build_edge_mutation_request(
                mutation_type="create_edge",
                edge_type="DEPENDENCY",
                edge_id=edge_id,
                payload=payload,
            )
            mutations.append(mutation)
        
        if mutations:
            try:
                accepted = await self._apply_mutations_batched(
                    mutations,
                    context_label=f"dependency edges for {repo}",
                    fatal_on_error=False,
                )
                if accepted:
                    log.info(f"Created {len(mutations)} dependency edges for {repo}")
                else:
                    log.warning(f"Some dependency edge mutation batches were not accepted for {repo}")
            except grpc.RpcError as e:
                log.warning(f"gRPC error creating dependency edges for {repo}: {e.code()} {e.details()}")

    async def _mirror_to_postgres(
        self,
        repo: str,
        services: list[ServiceManifest],
        mutations: list[Mutation],
    ) -> None:
        """
        Mirror service nodes to PostgreSQL meta.graph_nodes for fallback queries.
        
        Uses ON CONFLICT (node_id, repo) DO UPDATE for upsert semantics.
        Wraps in try-except, logs WARNING, never raises (explicitly non-fatal).
        """
        try:
            with psycopg2.connect(**self.pg_cfg) as conn:
                with conn.cursor() as cur:
                    for svc, mutation in zip(services, mutations):
                        node_id = f"service:{repo}:{svc.service_name}"
                        payload = json.loads(mutation.payload_json)
                        
                        cur.execute(
                            """
                            INSERT INTO meta.graph_nodes (node_id, repo, node_type, label, properties, created_at)
                            VALUES (%s, %s, %s, %s, %s::jsonb, NOW())
                            ON CONFLICT (node_id, repo) DO UPDATE SET
                                properties = EXCLUDED.properties,
                                label = EXCLUDED.label
                            """,
                            (
                                node_id,
                                repo,
                                "service",
                                svc.service_name,
                                json.dumps(payload),
                            ),
                        )
                conn.commit()
                log.info(f"Mirrored {len(services)} service nodes to PostgreSQL for {repo}")
        except Exception as e:
            log.warning(f"Failed to mirror service nodes to PostgreSQL for {repo}: {e}")

    def _build_mutation_request(
        self,
        mutation_type: str,
        entity_kind: str,
        entity_id: str,
        payload: dict[str, Any],
    ) -> Mutation:
        """
        Build a Mutation protobuf message for node operations.
        
        Args:
            mutation_type: "create_node" or "update_node"
            entity_kind: "service", "api", "schema"
            entity_id: Unique node identifier
            payload: Node properties as dict
        
        Returns:
            Mutation protobuf message
        """
        return Mutation(
            type=mutation_type,
            entity_kind=entity_kind,
            entity_id=entity_id,
            payload_json=json.dumps(payload),
            valid_from=datetime.now(timezone.utc).isoformat(),
            valid_to="",  # Empty string for currently valid nodes
        )

    def _build_edge_mutation_request(
        self,
        mutation_type: str,
        edge_type: str,
        edge_id: str,
        payload: dict[str, Any],
    ) -> Mutation:
        """
        Build a Mutation protobuf message for edge operations.
        
        Uses create_edge to prevent duplicate edges on re-ingestion.
        
        Args:
            mutation_type: "create_edge" or "update_edge"
            edge_type: "DEPENDENCY"
            edge_id: Unique edge identifier (source→target)
            payload: Edge properties including source_id, target_id, dependency_type
        
        Returns:
            Mutation protobuf message
        """
        return Mutation(
            type=mutation_type,
            entity_kind=edge_type,
            entity_id=edge_id,
            payload_json=json.dumps(payload),
            valid_from=datetime.now(timezone.utc).isoformat(),
            valid_to="",  # Empty string for currently valid edges
        )
