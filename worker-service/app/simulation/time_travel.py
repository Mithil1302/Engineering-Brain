"""
KA-CHOW Time-Travel / Architecture Timeline System.

Advanced features:
  1. Temporal graph snapshots with valid_from/valid_to semantics
  2. Architecture state reconstruction at any point in time
  3. Timeline slider support for historical visualization
  4. Architecture drift detection (implementation vs. planned)
  5. Future state modeling for proposed refactors
  6. Failure cascade replay with root cause analysis
  7. LLM-enhanced architecture diff explanations
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict
from enum import Enum

from ..llm import get_llm_client
from ..llm.prompts import ArchitectureDiffPrompt, FailureReplayPrompt, FutureStatePrompt

log = logging.getLogger("ka-chow.time-travel")


# ---------------------------------------------------------------------------
# Temporal Data Models
# ---------------------------------------------------------------------------

class TemporalEdgeType(str, Enum):
    """Types of edges in the temporal architecture graph."""
    DEPENDS_ON = "depends_on"
    CALLS = "calls"
    PRODUCES = "produces"
    CONSUMES = "consumes"
    DEPLOYS_TO = "deploys_to"
    TEST_COVERS = "test_covers"
    INCIDENT_TRACKS = "incident_tracks"
    DOCUMENTS = "documents"
    OWNED_BY = "owned_by"
    IMPLEMENTS = "implements"
    MIGRATES_FROM = "migrates_from"
    MIGRATES_TO = "migrates_to"


class NodeType(str, Enum):
    """Types of nodes in the architecture graph."""
    SERVICE = "service"
    ENDPOINT = "endpoint"
    DATABASE = "database"
    CACHE = "cache"
    QUEUE = "queue"
    TOPIC = "topic"
    INFRASTRUCTURE = "infrastructure"
    TEST = "test"
    INCIDENT = "incident"
    DEPLOYMENT = "deployment"
    TEAM = "team"
    DOCUMENTATION = "documentation"


@dataclass
class TemporalNode:
    """A node in the architecture graph with temporal validity."""
    node_id: str
    node_type: NodeType
    name: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    valid_from: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    valid_to: Optional[datetime] = None  # None = still valid
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_valid_at(self, timestamp: datetime) -> bool:
        """Check if this node was valid at a given point in time."""
        if timestamp < self.valid_from:
            return False
        if self.valid_to is not None and timestamp >= self.valid_to:
            return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type.value,
            "name": self.name,
            "metadata": self.metadata,
            "valid_from": self.valid_from.isoformat(),
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class TemporalEdge:
    """An edge in the architecture graph with temporal validity."""
    edge_id: str
    source_id: str
    target_id: str
    edge_type: TemporalEdgeType
    metadata: Dict[str, Any] = field(default_factory=dict)
    valid_from: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    valid_to: Optional[datetime] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_valid_at(self, timestamp: datetime) -> bool:
        """Check if this edge was valid at a given point in time."""
        if timestamp < self.valid_from:
            return False
        if self.valid_to is not None and timestamp >= self.valid_to:
            return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "edge_type": self.edge_type.value,
            "metadata": self.metadata,
            "valid_from": self.valid_from.isoformat(),
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
        }


@dataclass
class ArchitectureSnapshot:
    """A point-in-time snapshot of the architecture graph."""
    snapshot_id: str
    timestamp: datetime
    nodes: List[TemporalNode]
    edges: List[TemporalEdge]
    metrics: Dict[str, Any] = field(default_factory=dict)
    health_score: Optional[float] = None
    drift_score: Optional[float] = None  # Deviation from intended architecture

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "timestamp": self.timestamp.isoformat(),
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "metrics": self.metrics,
            "health_score": self.health_score,
            "drift_score": self.drift_score,
        }


@dataclass
class ArchitectureDiff:
    """The difference between two architecture states."""
    before_timestamp: datetime
    after_timestamp: datetime
    nodes_added: List[TemporalNode] = field(default_factory=list)
    nodes_removed: List[TemporalNode] = field(default_factory=list)
    nodes_modified: List[Tuple[TemporalNode, TemporalNode]] = field(default_factory=list)
    edges_added: List[TemporalEdge] = field(default_factory=list)
    edges_removed: List[TemporalEdge] = field(default_factory=list)
    edges_modified: List[Tuple[TemporalEdge, TemporalEdge]] = field(default_factory=list)
    llm_analysis: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "before_timestamp": self.before_timestamp.isoformat(),
            "after_timestamp": self.after_timestamp.isoformat(),
            "nodes_added": [n.to_dict() for n in self.nodes_added],
            "nodes_removed": [n.to_dict() for n in self.nodes_removed],
            "nodes_modified": [
                {"before": b.to_dict(), "after": a.to_dict()}
                for b, a in self.nodes_modified
            ],
            "edges_added": [e.to_dict() for e in self.edges_added],
            "edges_removed": [e.to_dict() for e in self.edges_removed],
            "edges_modified": [
                {"before": b.to_dict(), "after": a.to_dict()}
                for b, a in self.edges_modified
            ],
            "llm_analysis": self.llm_analysis,
        }


@dataclass
class FailureCascade:
    """A recorded or simulated failure cascade through the architecture."""
    cascade_id: str
    root_cause: str
    root_service_id: str
    trigger_timestamp: datetime
    cascade_sequence: List[Dict[str, Any]] = field(default_factory=list)
    total_affected_services: int = 0
    total_duration_seconds: int = 0
    llm_analysis: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cascade_id": self.cascade_id,
            "root_cause": self.root_cause,
            "root_service_id": self.root_service_id,
            "trigger_timestamp": self.trigger_timestamp.isoformat(),
            "cascade_sequence": self.cascade_sequence,
            "total_affected_services": self.total_affected_services,
            "total_duration_seconds": self.total_duration_seconds,
            "llm_analysis": self.llm_analysis,
        }


@dataclass
class FutureStateProjection:
    """A projected future architecture state given proposed changes."""
    projection_id: str
    created_at: datetime
    current_state_snapshot_id: str
    proposed_changes: List[Dict[str, Any]] = field(default_factory=list)
    future_state: Optional[ArchitectureSnapshot] = None
    change_analysis: List[Dict[str, Any]] = field(default_factory=list)
    migration_plan: List[Dict[str, Any]] = field(default_factory=list)
    risk_assessment: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "projection_id": self.projection_id,
            "created_at": self.created_at.isoformat(),
            "current_state_snapshot_id": self.current_state_snapshot_id,
            "proposed_changes": self.proposed_changes,
            "future_state": self.future_state.to_dict() if self.future_state else None,
            "change_analysis": self.change_analysis,
            "migration_plan": self.migration_plan,
            "risk_assessment": self.risk_assessment,
        }


# ---------------------------------------------------------------------------
# Temporal Graph Store
# ---------------------------------------------------------------------------

class TemporalGraphStore:
    """
    In-memory temporal graph store with PostgreSQL persistence.

    In production, this would use:
    - Neo4j with temporal plugins for graph storage
    - PostgreSQL with temporal tables for metadata
    """

    def __init__(self, pg_cfg: Optional[Dict[str, Any]] = None):
        self.pg_cfg = pg_cfg or {}
        self._nodes: Dict[str, TemporalNode] = {}
        self._edges: Dict[str, TemporalEdge] = {}
        self._snapshots: Dict[str, ArchitectureSnapshot] = {}
        self._failure_cascades: Dict[str, FailureCascade] = {}
        self._projections: Dict[str, FutureStateProjection] = {}
        self._ensure_schema()

    def _ensure_schema(self):
        """Ensure PostgreSQL schema exists for temporal data."""
        if not self.pg_cfg:
            return

        import psycopg2
        from psycopg2.extras import RealDictCursor

        schema_sql = """
        CREATE SCHEMA IF NOT EXISTS meta;

        CREATE TABLE IF NOT EXISTS meta.architecture_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            repo TEXT NOT NULL,
            timestamp TIMESTAMPTZ NOT NULL,
            nodes JSONB NOT NULL DEFAULT '[]',
            edges JSONB NOT NULL DEFAULT '[]',
            metrics JSONB,
            health_score NUMERIC(6,4),
            drift_score NUMERIC(6,4),
            node_ids JSONB,
            edge_count INTEGER DEFAULT 0,
            services_count INTEGER DEFAULT 0,
            event_type TEXT DEFAULT 'ingestion',
            event_payload JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS meta.architecture_nodes (
            node_id TEXT NOT NULL,
            node_type TEXT NOT NULL,
            name TEXT NOT NULL,
            repo TEXT NOT NULL,
            metadata JSONB,
            valid_from TIMESTAMPTZ NOT NULL,
            valid_to TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (node_id, valid_from)
        );

        CREATE TABLE IF NOT EXISTS meta.architecture_edges (
            edge_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            edge_type TEXT NOT NULL,
            repo TEXT NOT NULL,
            metadata JSONB,
            valid_from TIMESTAMPTZ NOT NULL,
            valid_to TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (edge_id, valid_from)
        );

        CREATE TABLE IF NOT EXISTS meta.failure_cascades (
            cascade_id TEXT PRIMARY KEY,
            repo TEXT NOT NULL,
            root_cause TEXT NOT NULL,
            root_service_id TEXT NOT NULL,
            trigger_timestamp TIMESTAMPTZ NOT NULL,
            cascade_sequence JSONB NOT NULL,
            total_affected_services INT,
            total_duration_seconds INT,
            llm_analysis JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS meta.architecture_projections (
            projection_id TEXT PRIMARY KEY,
            repo TEXT NOT NULL,
            current_state_snapshot_id TEXT,
            proposed_changes JSONB NOT NULL,
            future_state JSONB,
            change_analysis JSONB,
            migration_plan JSONB,
            risk_assessment JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_arch_nodes_repo_valid ON meta.architecture_nodes (repo, valid_from, valid_to);
        CREATE INDEX IF NOT EXISTS idx_arch_edges_repo_valid ON meta.architecture_edges (repo, valid_from, valid_to);
        CREATE INDEX IF NOT EXISTS idx_arch_snapshots_repo_ts ON meta.architecture_snapshots (repo, timestamp);
        """

        try:
            with psycopg2.connect(**self.pg_cfg) as conn:
                with conn.cursor() as cur:
                    cur.execute(schema_sql)
                conn.commit()
            log.info("Temporal graph schema ensured")
        except Exception as exc:
            log.warning("Temporal graph schema setup failed: %s", exc)

    def _verify_temporal_index(self) -> None:
        """
        Verify that the temporal index exists on meta.architecture_nodes.
        This is an advisory check only - logs a WARNING with the CREATE INDEX command if missing.
        Does not block startup.
        """
        if not self.pg_cfg:
            return

        import psycopg2

        try:
            with psycopg2.connect(**self.pg_cfg) as conn:
                with conn.cursor() as cur:
                    # Run EXPLAIN to check if index is being used
                    cur.execute("""
                        EXPLAIN SELECT * FROM meta.architecture_nodes 
                        WHERE repo = 'test' 
                        AND valid_from <= NOW() 
                        AND (valid_to IS NULL OR valid_to > NOW())
                    """)
                    plan = "\n".join([row[0] for row in cur.fetchall()])
                    
                    # Check if Index Scan or Index Only Scan appears in the plan
                    if "Index Scan" in plan or "Index Only Scan" in plan:
                        log.info("Temporal index verification passed: index is being used")
                    else:
                        log.warning(
                            "Temporal index missing or not being used. "
                            "To create the index, run: "
                            "CREATE INDEX idx_arch_nodes_temporal ON meta.architecture_nodes (repo, valid_from, valid_to);"
                        )
        except Exception as exc:
            log.warning("Temporal index verification failed: %s", exc)

    def add_node(self, node: TemporalNode) -> None:
        """Add or update a node in the graph."""
        self._nodes[node.node_id] = node
        self._persist_node(node)

    def add_edge(self, edge: TemporalEdge) -> None:
        """Add or update an edge in the graph."""
        self._edges[edge.edge_id] = edge
        self._persist_edge(edge)

    def remove_node(self, node_id: str, end_time: Optional[datetime] = None) -> None:
        """Mark a node as removed (end-dating it)."""
        end_time = end_time or datetime.now(timezone.utc)
        if node_id in self._nodes:
            node = self._nodes[node_id]
            node.valid_to = end_time
            node.updated_at = end_time
            self._persist_node(node)

    def remove_edge(self, edge_id: str, end_time: Optional[datetime] = None) -> None:
        """Mark an edge as removed (end-dating it)."""
        end_time = end_time or datetime.now(timezone.utc)
        if edge_id in self._edges:
            edge = self._edges[edge_id]
            edge.valid_to = end_time
            edge.updated_at = end_time
            self._persist_edge(edge)

    def get_snapshot_at(self, timestamp: datetime, repo: Optional[str] = None) -> ArchitectureSnapshot:
        """Reconstruct the architecture graph at a specific point in time."""
        valid_nodes = [
            n for n in self._nodes.values()
            if n.is_valid_at(timestamp) and (repo is None or n.metadata.get("repo") == repo)
        ]
        valid_edges = [
            e for e in self._edges.values()
            if e.is_valid_at(timestamp) and (repo is None or e.metadata.get("repo") == repo)
        ]

        node_ids = {n.node_id for n in valid_nodes}
        # Filter edges to only those connecting valid nodes
        valid_edges = [e for e in valid_edges if e.source_id in node_ids and e.target_id in node_ids]

        metrics = self._compute_metrics(valid_nodes, valid_edges)

        snapshot_id = f"snap_{timestamp.strftime('%Y%m%d_%H%M%S')}"
        return ArchitectureSnapshot(
            snapshot_id=snapshot_id,
            timestamp=timestamp,
            nodes=valid_nodes,
            edges=valid_edges,
            metrics=metrics,
        )

    def get_diff(
        self,
        before_ts: datetime,
        after_ts: datetime,
        repo: Optional[str] = None,
        use_llm: bool = True,
    ) -> ArchitectureDiff:
        """Compute the difference between two architecture states."""
        before = self.get_snapshot_at(before_ts, repo)
        after = self.get_snapshot_at(after_ts, repo)

        diff = ArchitectureDiff(before_timestamp=before_ts, after_timestamp=after_ts)

        # Node changes
        before_nodes = {n.node_id: n for n in before.nodes}
        after_nodes = {n.node_id: n for n in after.nodes}

        for node_id, node in after_nodes.items():
            if node_id not in before_nodes:
                diff.nodes_added.append(node)
            elif node.metadata != before_nodes[node_id].metadata:
                diff.nodes_modified.append((before_nodes[node_id], node))

        for node_id, node in before_nodes.items():
            if node_id not in after_nodes:
                diff.nodes_removed.append(node)

        # Edge changes
        before_edges = {e.edge_id: e for e in before.edges}
        after_edges = {e.edge_id: e for e in after.edges}

        for edge_id, edge in after_edges.items():
            if edge_id not in before_edges:
                diff.edges_added.append(edge)
            elif edge.metadata != before_edges[edge_id].metadata:
                diff.edges_modified.append((before_edges[edge_id], edge))

        for edge_id, edge in before_edges.items():
            if edge_id not in after_edges:
                diff.edges_removed.append(edge)

        # LLM-enhanced analysis
        if use_llm:
            diff.llm_analysis = self._analyze_diff_with_llm(diff, before, after)

        return diff

    def record_failure_cascade(
        self,
        root_cause: str,
        root_service_id: str,
        cascade_sequence: List[Dict[str, Any]],
        trigger_timestamp: Optional[datetime] = None,
        use_llm: bool = True,
    ) -> FailureCascade:
        """Record a failure cascade (from incident or simulation)."""
        trigger_timestamp = trigger_timestamp or datetime.now(timezone.utc)

        cascade = FailureCascade(
            cascade_id=f"cascade_{trigger_timestamp.strftime('%Y%m%d_%H%M%S')}",
            root_cause=root_cause,
            root_service_id=root_service_id,
            trigger_timestamp=trigger_timestamp,
            cascade_sequence=cascade_sequence,
            total_affected_services=len(set(c.get("service_id") for c in cascade_sequence)),
            total_duration_seconds=sum(c.get("duration_seconds", 0) for c in cascade_sequence),
        )

        if use_llm:
            cascade.llm_analysis = self._analyze_cascade_with_llm(cascade)

        self._failure_cascades[cascade.cascade_id] = cascade
        self._persist_cascade(cascade)
        return cascade

    def project_future_state(
        self,
        current_snapshot_id: str,
        proposed_changes: List[Dict[str, Any]],
        use_llm: bool = True,
    ) -> FutureStateProjection:
        """Project a future architecture state given proposed changes."""
        projection = FutureStateProjection(
            projection_id=f"proj_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
            created_at=datetime.now(timezone.utc),
            current_state_snapshot_id=current_snapshot_id,
            proposed_changes=proposed_changes,
        )

        if use_llm:
            current_state = self._snapshots.get(current_snapshot_id)
            if current_state:
                result = self._analyze_future_state_with_llm(current_state, proposed_changes)
                projection.change_analysis = result.get("change_analysis", [])
                projection.migration_plan = result.get("migration_plan", [])
                projection.risk_assessment = result.get("risk_assessment")

        self._projections[projection.projection_id] = projection
        self._persist_projection(projection)
        return projection

    def compute_drift_score(self, snapshot: ArchitectureSnapshot, intended_state: Dict[str, Any]) -> float:
        """
        Compute how much the current architecture has drifted from intended design.

        Returns a score from 0.0 (perfectly aligned) to 1.0 (completely drifted).
        """
        drift_factors = []

        # Factor 1: Services that exist but weren't planned
        actual_services = {n.name for n in snapshot.nodes if n.node_type == NodeType.SERVICE}
        planned_services = set(intended_state.get("services", []))
        unplanned = actual_services - planned_services
        if planned_services:
            drift_factors.append(len(unplanned) / len(actual_services))

        # Factor 2: Missing planned services
        missing = planned_services - actual_services
        if planned_services:
            drift_factors.append(len(missing) / len(planned_services))

        # Factor 3: Unexpected dependencies
        actual_deps = set()
        for edge in snapshot.edges:
            if edge.edge_type == TemporalEdgeType.DEPENDS_ON:
                actual_deps.add((edge.source_id, edge.target_id))

        planned_deps = set(tuple(d) for d in intended_state.get("dependencies", []))
        unexpected_deps = actual_deps - planned_deps
        if actual_deps:
            drift_factors.append(len(unexpected_deps) / len(actual_deps))

        return sum(drift_factors) / len(drift_factors) if drift_factors else 0.0

    def _compute_metrics(
        self,
        nodes: List[TemporalNode],
        edges: List[TemporalEdge],
    ) -> Dict[str, Any]:
        """Compute architecture metrics for a snapshot."""
        services = [n for n in nodes if n.node_type == NodeType.SERVICE]
        databases = [n for n in nodes if n.node_type == NodeType.DATABASE]
        queues = [n for n in nodes if n.node_type == NodeType.QUEUE]

        dep_edges = [e for e in edges if e.edge_type == TemporalEdgeType.DEPENDS_ON]

        # Compute coupling metrics
        service_deps: Dict[str, int] = defaultdict(int)
        for edge in dep_edges:
            service_deps[edge.source_id] += 1

        avg_coupling = sum(service_deps.values()) / len(services) if services else 0
        max_coupling = max(service_deps.values()) if service_deps else 0

        # Detect potential cycles (simplified)
        has_cycles = self._detect_cycles(services, dep_edges)

        return {
            "service_count": len(services),
            "database_count": len(databases),
            "queue_count": len(queues),
            "edge_count": len(edges),
            "avg_service_coupling": round(avg_coupling, 2),
            "max_service_coupling": max_coupling,
            "has_dependency_cycles": has_cycles,
            "node_count": len(nodes),
        }

    def _detect_cycles(
        self,
        services: List[TemporalNode],
        dep_edges: List[TemporalEdge],
    ) -> bool:
        """Detect if there are dependency cycles in the graph."""
        service_ids = {s.node_id for s in services}
        adj: Dict[str, List[str]] = defaultdict(list)

        for edge in dep_edges:
            if edge.source_id in service_ids and edge.target_id in service_ids:
                adj[edge.source_id].append(edge.target_id)

        # DFS-based cycle detection
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {sid: WHITE for sid in service_ids}

        def dfs(node: str) -> bool:
            color[node] = GRAY
            for neighbor in adj[node]:
                if color[neighbor] == GRAY:
                    return True
                if color[neighbor] == WHITE and dfs(neighbor):
                    return True
            color[node] = BLACK
            return False

        for sid in service_ids:
            if color[sid] == WHITE:
                if dfs(sid):
                    return True
        return False

    def _analyze_diff_with_llm(
        self,
        diff: ArchitectureDiff,
        before: ArchitectureSnapshot,
        after: ArchitectureSnapshot,
    ) -> Optional[Dict[str, Any]]:
        """Use LLM to analyze architecture changes."""
        llm = get_llm_client()

        before_state = {
            "services": [n.name for n in before.nodes if n.node_type == NodeType.SERVICE],
            "node_count": len(before.nodes),
            "edge_count": len(before.edges),
            "metrics": before.metrics,
        }
        after_state = {
            "services": [n.name for n in after.nodes if n.node_type == NodeType.SERVICE],
            "node_count": len(after.nodes),
            "edge_count": len(after.edges),
            "metrics": after.metrics,
        }

        time_delta = (diff.after_timestamp - diff.before_timestamp).days

        prompt = ArchitectureDiffPrompt.user_prompt(before_state, after_state, time_delta)

        try:
            result = llm.generate(
                prompt,
                system_prompt=ArchitectureDiffPrompt.system_prompt,
                json_mode=True,
                json_schema=ArchitectureDiffPrompt.response_schema(),
                temperature=0.3,
            )
            return result.as_json()
        except Exception as exc:
            log.error("LLM architecture diff analysis failed: %s", exc)
            return None

    def _analyze_cascade_with_llm(self, cascade: FailureCascade) -> Optional[Dict[str, Any]]:
        """Use LLM to analyze failure cascade."""
        llm = get_llm_client()

        dep_graph = {
            "nodes": list(set(c.get("service_id") for c in cascade.cascade_sequence)),
            "edges": [
                {"from": c.get("source"), "to": c.get("service_id")}
                for c in cascade.cascade_sequence
                if c.get("source")
            ],
        }

        prompt = FailureReplayPrompt.user_prompt(
            cascade.root_cause,
            [c.get("service_id") for c in cascade.cascade_sequence],
            dep_graph,
            {"duration_seconds": cascade.total_duration_seconds},
        )

        try:
            result = llm.generate(
                prompt,
                system_prompt=FailureReplayPrompt.system_prompt,
                json_mode=True,
                json_schema=FailureReplayPrompt.response_schema(),
                temperature=0.3,
            )
            return result.as_json()
        except Exception as exc:
            log.error("LLM failure cascade analysis failed: %s", exc)
            return None

    def _analyze_future_state_with_llm(
        self,
        current_state: ArchitectureSnapshot,
        proposed_changes: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Use LLM to analyze future state projection."""
        llm = get_llm_client()

        current_state_dict = {
            "services": [
                {"name": n.name, "metadata": n.metadata}
                for n in current_state.nodes if n.node_type == NodeType.SERVICE
            ],
            "dependencies": [
                {"from": e.source_id, "to": e.target_id, "type": e.edge_type.value}
                for e in current_state.edges
            ],
            "metrics": current_state.metrics,
        }

        prompt = FutureStatePrompt.user_prompt(current_state_dict, proposed_changes)

        try:
            result = llm.generate(
                prompt,
                system_prompt=FutureStatePrompt.system_prompt,
                json_mode=True,
                json_schema=FutureStatePrompt.response_schema(),
                temperature=0.3,
            )
            return result.as_json()
        except Exception as exc:
            log.error("LLM future state analysis failed: %s", exc)
            return {
                "change_analysis": [],
                "migration_plan": [],
                "risk_assessment": {"overall_risk": "unknown"},
            }

    # Persistence methods
    def _persist_node(self, node: TemporalNode) -> None:
        if not self.pg_cfg:
            return
        import psycopg2
        from psycopg2.extras import Json

        try:
            with psycopg2.connect(**self.pg_cfg) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO meta.architecture_nodes
                        (node_id, node_type, name, repo, metadata, valid_from, valid_to, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (node_id, valid_from) DO UPDATE SET
                            metadata = EXCLUDED.metadata,
                            valid_to = EXCLUDED.valid_to,
                            updated_at = EXCLUDED.updated_at
                        """,
                        (
                            node.node_id,
                            node.node_type.value,
                            node.name,
                            node.metadata.get("repo", "unknown"),
                            Json(node.metadata),
                            node.valid_from,
                            node.valid_to,
                            node.created_at,
                            node.updated_at,
                        ),
                    )
                conn.commit()
        except Exception as exc:
            log.warning("Node persistence failed: %s", exc)

    def _persist_edge(self, edge: TemporalEdge) -> None:
        if not self.pg_cfg:
            return
        import psycopg2
        from psycopg2.extras import Json

        try:
            with psycopg2.connect(**self.pg_cfg) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO meta.architecture_edges
                        (edge_id, source_id, target_id, edge_type, repo, metadata, valid_from, valid_to, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (edge_id, valid_from) DO UPDATE SET
                            metadata = EXCLUDED.metadata,
                            valid_to = EXCLUDED.valid_to,
                            updated_at = EXCLUDED.updated_at
                        """,
                        (
                            edge.edge_id,
                            edge.source_id,
                            edge.target_id,
                            edge.edge_type.value,
                            edge.metadata.get("repo", "unknown"),
                            Json(edge.metadata),
                            edge.valid_from,
                            edge.valid_to,
                            edge.created_at,
                            edge.updated_at,
                        ),
                    )
                conn.commit()
        except Exception as exc:
            log.warning("Edge persistence failed: %s", exc)

    def _persist_snapshot(self, snapshot: ArchitectureSnapshot) -> None:
        if not self.pg_cfg:
            return
        import psycopg2
        from psycopg2.extras import Json

        try:
            with psycopg2.connect(**self.pg_cfg) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO meta.architecture_snapshots
                        (snapshot_id, repo, timestamp, nodes, edges, metrics, health_score, drift_score, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        """,
                        (
                            snapshot.snapshot_id,
                            "repo",  # Would be parameterized in production
                            snapshot.timestamp,
                            Json([n.to_dict() for n in snapshot.nodes]),
                            Json([e.to_dict() for e in snapshot.edges]),
                            Json(snapshot.metrics),
                            snapshot.health_score,
                            snapshot.drift_score,
                        ),
                    )
                conn.commit()
        except Exception as exc:
            log.warning("Snapshot persistence failed: %s", exc)

    def _persist_cascade(self, cascade: FailureCascade) -> None:
        if not self.pg_cfg:
            return
        import psycopg2
        from psycopg2.extras import Json

        try:
            with psycopg2.connect(**self.pg_cfg) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO meta.failure_cascades
                        (cascade_id, repo, root_cause, root_service_id, trigger_timestamp,
                         cascade_sequence, total_affected_services, total_duration_seconds,
                         llm_analysis, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        """,
                        (
                            cascade.cascade_id,
                            "repo",
                            cascade.root_cause,
                            cascade.root_service_id,
                            cascade.trigger_timestamp,
                            Json(cascade.cascade_sequence),
                            cascade.total_affected_services,
                            cascade.total_duration_seconds,
                            Json(cascade.llm_analysis),
                        ),
                    )
                conn.commit()
        except Exception as exc:
            log.warning("Cascade persistence failed: %s", exc)

    def _persist_projection(self, projection: FutureStateProjection) -> None:
        if not self.pg_cfg:
            return
        import psycopg2
        from psycopg2.extras import Json

        try:
            with psycopg2.connect(**self.pg_cfg) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO meta.architecture_projections
                        (projection_id, repo, current_state_snapshot_id, proposed_changes,
                         future_state, change_analysis, migration_plan, risk_assessment, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        """,
                        (
                            projection.projection_id,
                            "repo",
                            projection.current_state_snapshot_id,
                            Json(projection.proposed_changes),
                            Json(projection.future_state.to_dict() if projection.future_state else None),
                            Json(projection.change_analysis),
                            Json(projection.migration_plan),
                            Json(projection.risk_assessment),
                        ),
                    )
                conn.commit()
        except Exception as exc:
            log.warning("Projection persistence failed: %s", exc)

    # ---------------------------------------------------------------------------
    # Temporal Snapshot Recording (Task 3.1)
    # ---------------------------------------------------------------------------

    async def record_ingestion_snapshot(self, repo: str, ingestion_result: Any) -> str:
        """
        Record a temporal snapshot after ingestion completes.
        
        Queries current Neo4j state, computes diff from previous snapshot,
        updates valid_to for removed nodes, inserts new nodes, and persists snapshot.
        
        Args:
            repo: Repository name
            ingestion_result: IngestionResult with run_id, services_detected, etc.
            
        Returns:
            snapshot_id string
        """
        now = datetime.now(timezone.utc)
        
        # Query current state from Neo4j
        current_nodes = await self._query_current_nodes(repo, now)
        current_edges = await self._query_current_edges(repo, now)
        
        # Get previous snapshot metadata
        previous_snapshot = self._get_latest_snapshot_meta(repo)
        
        # Compute diff
        current_node_ids = {n.node_id for n in current_nodes}
        previous_node_ids = set(previous_snapshot.get("node_ids", [])) if previous_snapshot else set()
        
        removed_ids = previous_node_ids - current_node_ids
        added = [n for n in current_nodes if n.node_id not in previous_node_ids]
        
        # Update valid_to for removed nodes
        if removed_ids:
            self._update_removed_nodes(repo, list(removed_ids), now)
        
        # Insert new nodes via existing add_node() method
        for node in added:
            self.add_node(node)
        
        # Create snapshot record
        snapshot_id = f"ingestion_{repo.replace('/', '_')}_{now.strftime('%Y%m%d_%H%M%S')}"
        
        # Count services
        services_count = sum(1 for n in current_nodes if n.node_type == NodeType.SERVICE)
        
        # Persist snapshot to meta.architecture_snapshots
        self._persist_ingestion_snapshot(
            snapshot_id=snapshot_id,
            repo=repo,
            timestamp=now,
            node_ids=list(current_node_ids),
            edge_count=len(current_edges),
            services_count=services_count,
        )
        
        # Log summary
        log.info(f"Temporal snapshot {snapshot_id}: +{len(added)} nodes, -{len(removed_ids)} nodes")
        
        return snapshot_id

    async def _query_current_nodes(self, repo: str, now: datetime) -> List[TemporalNode]:
        """
        Query all current nodes for repo from Neo4j via gRPC.
        
        Cypher: MATCH (n {repo: $repo}) RETURN n
        Timeout: 10s
        
        Constructs TemporalNode objects with valid_from=now, valid_to=None.
        """
        if not hasattr(self, '_grpc_stub'):
            # Initialize gRPC stub if not already present
            import grpc
            from ...generated import services_pb2_grpc
            
            graph_service_url = self.pg_cfg.get("graph_service_url", "graph-service:50051")
            self._grpc_channel = grpc.aio.insecure_channel(graph_service_url)
            self._grpc_stub = services_pb2_grpc.GraphServiceStub(self._grpc_channel)
        
        # For now, return empty list as QueryGraph is not yet implemented in proto
        # This will be populated when QueryGraph is added to services.proto
        log.warning(f"QueryGraph not yet implemented in proto, returning empty node list for {repo}")
        return []

    async def _query_current_edges(self, repo: str, now: datetime) -> List[TemporalEdge]:
        """
        Query all current edges for repo from Neo4j via gRPC.
        
        Cypher: MATCH (n {repo: $repo})-[r]->(m) RETURN r, n.service_name AS source, m.service_name AS target
        Timeout: 10s
        
        Constructs TemporalEdge objects with valid_from=now, valid_to=None.
        """
        # For now, return empty list as QueryGraph is not yet implemented in proto
        log.warning(f"QueryGraph not yet implemented in proto, returning empty edge list for {repo}")
        return []

    def _get_latest_snapshot_meta(self, repo: str) -> Optional[Dict[str, Any]]:
        """
        Query latest ingestion snapshot metadata from PostgreSQL.
        
        Query: SELECT node_ids FROM meta.architecture_snapshots 
               WHERE repo = %s AND event_type = 'ingestion' 
               ORDER BY timestamp DESC LIMIT 1
               
        Returns: {"node_ids": list} or None if no previous snapshot
        """
        if not self.pg_cfg:
            return None
        
        import psycopg2
        from psycopg2.extras import RealDictCursor
        
        try:
            with psycopg2.connect(**self.pg_cfg) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT node_ids
                        FROM meta.architecture_snapshots
                        WHERE repo = %s AND event_type = 'ingestion'
                        ORDER BY timestamp DESC
                        LIMIT 1
                        """,
                        (repo,),
                    )
                    row = cur.fetchone()
                    if row:
                        return {"node_ids": json.loads(row["node_ids"]) if isinstance(row["node_ids"], str) else row["node_ids"]}
                    return None
        except Exception as exc:
            log.warning(f"Failed to get latest snapshot meta for {repo}: {exc}")
            return None

    def _update_removed_nodes(self, repo: str, removed_ids: List[str], valid_to: datetime) -> None:
        """
        Update valid_to for removed nodes.
        
        UPDATE meta.architecture_nodes 
        SET valid_to = %s 
        WHERE repo = %s AND node_id = ANY(%s) AND valid_to IS NULL
        """
        if not self.pg_cfg:
            return
        
        import psycopg2
        
        try:
            with psycopg2.connect(**self.pg_cfg) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE meta.architecture_nodes
                        SET valid_to = %s
                        WHERE repo = %s AND node_id = ANY(%s) AND valid_to IS NULL
                        """,
                        (valid_to, repo, removed_ids),
                    )
                conn.commit()
        except Exception as exc:
            log.warning(f"Failed to update removed nodes for {repo}: {exc}")

    def _persist_ingestion_snapshot(
        self,
        snapshot_id: str,
        repo: str,
        timestamp: datetime,
        node_ids: List[str],
        edge_count: int,
        services_count: int,
    ) -> None:
        """
        Insert snapshot record into meta.architecture_snapshots.
        
        Includes: snapshot_id, repo, timestamp, node_ids (JSON array), 
                  edge_count, services_count, event_type='ingestion'
        """
        if not self.pg_cfg:
            return
        
        import psycopg2
        from psycopg2.extras import Json
        
        try:
            with psycopg2.connect(**self.pg_cfg) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO meta.architecture_snapshots
                        (snapshot_id, repo, timestamp, node_ids, edge_count, services_count, 
                         event_type, nodes, edges, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        """,
                        (
                            snapshot_id,
                            repo,
                            timestamp,
                            Json(node_ids),
                            edge_count,
                            services_count,
                            'ingestion',
                            Json([]),  # nodes array (empty for now)
                            Json([]),  # edges array (empty for now)
                        ),
                    )
                conn.commit()
        except Exception as exc:
            log.warning(f"Failed to persist ingestion snapshot {snapshot_id}: {exc}")

    # ---------------------------------------------------------------------------
    # Policy Event Recording (Task 3.2)
    # ---------------------------------------------------------------------------

    def record_policy_event(self, repo: str, policy_run_id: int, findings: list[dict]) -> None:
        """
        Record policy findings as temporal snapshot events.
        
        Filters to only DOC_DRIFT_* and BREAKING_* findings and inserts one row per finding
        into meta.architecture_snapshots with event_type='policy_finding'.
        
        Uses ON CONFLICT (snapshot_id) DO NOTHING to prevent duplicate events on Kafka re-delivery.
        
        Args:
            repo: Repository name
            policy_run_id: Policy run ID
            findings: List of finding dictionaries with rule_id, message, etc.
        """
        # Filter to only DOC_DRIFT_* and BREAKING_* findings
        relevant_findings = [
            f for f in findings
            if f.get("rule_id", "").startswith(("DOC_DRIFT_", "BREAKING_"))
        ]
        
        # Return immediately if no relevant findings
        if not relevant_findings:
            return
        
        if not self.pg_cfg:
            log.warning(f"Cannot record policy events for {repo}: no PostgreSQL config")
            return
        
        import psycopg2
        from psycopg2.extras import Json
        
        try:
            with psycopg2.connect(**self.pg_cfg) as conn:
                with conn.cursor() as cur:
                    for finding in relevant_findings:
                        # Generate snapshot_id per finding
                        snapshot_id = f"policy_{repo.replace('/', '_')}_{policy_run_id}_{finding['rule_id']}"
                        
                        # Insert one row per finding with ON CONFLICT DO NOTHING
                        cur.execute(
                            """
                            INSERT INTO meta.architecture_snapshots
                            (snapshot_id, repo, timestamp, event_type, event_payload, 
                             node_ids, edge_count, services_count, nodes, edges, created_at)
                            VALUES (%s, %s, NOW(), %s, %s, %s, %s, %s, %s, %s, NOW())
                            ON CONFLICT (snapshot_id) DO NOTHING
                            """,
                            (
                                snapshot_id,
                                repo,
                                'policy_finding',
                                Json(finding),
                                Json([]),  # node_ids = []
                                0,  # edge_count = 0
                                0,  # services_count = 0
                                Json([]),  # nodes array (empty)
                                Json([]),  # edges array (empty)
                            ),
                        )
                conn.commit()
                log.info(f"Recorded {len(relevant_findings)} policy findings for {repo} run {policy_run_id}")
        except Exception as exc:
            log.warning(f"Failed to record policy events for {repo} run {policy_run_id}: {exc}")


# ---------------------------------------------------------------------------
# Legacy compatibility (original function)
# ---------------------------------------------------------------------------

def simulate_health(history: List[Dict[str, Any]], horizon: int = 5) -> Dict[str, Any]:
    """Legacy health simulation function."""
    points = list(reversed(history))
    scores = [float(p.get("score") or 0.0) for p in points]
    if len(scores) < 2:
        slope = 0.0
    else:
        slope = (scores[-1] - scores[0]) / max(1, len(scores) - 1)

    future = []
    base = scores[-1] if scores else 0.0
    for i in range(1, max(1, horizon) + 1):
        val = max(0.0, min(100.0, round(base + slope * i, 2)))
        future.append({"step": i, "projected_score": val})

    return {
        "history_points": len(scores),
        "current_score": round(base, 2),
        "trend_slope": round(slope, 4),
        "projection": future,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
