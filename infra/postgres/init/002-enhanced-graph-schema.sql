-- KA-CHOW Enhanced Graph Schema
-- Extends base schema with:
--   - Temporal graph nodes/edges with valid_from/valid_to
--   - Enhanced edge types for test coverage, incidents, deployments
--   - Time-travel snapshots
--   - Failure cascade tracking
--   - Architecture projections

-- Required for GiST indexes on timestamptz columns
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE SCHEMA IF NOT EXISTS meta;

-- ---------------------------------------------------------------------------
-- Temporal Architecture Nodes
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS meta.architecture_nodes (
    node_id TEXT NOT NULL,
    node_type TEXT NOT NULL,
    name TEXT NOT NULL,
    repo TEXT NOT NULL,
    metadata JSONB,
    valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (node_id, valid_from)
);

CREATE INDEX IF NOT EXISTS idx_arch_nodes_repo ON meta.architecture_nodes (repo);
CREATE INDEX IF NOT EXISTS idx_arch_nodes_type ON meta.architecture_nodes (node_type);
CREATE INDEX IF NOT EXISTS idx_arch_nodes_valid_from ON meta.architecture_nodes (valid_from);
CREATE INDEX IF NOT EXISTS idx_arch_nodes_valid_to ON meta.architecture_nodes (valid_to);
CREATE INDEX IF NOT EXISTS idx_arch_nodes_current ON meta.architecture_nodes (repo, node_type) WHERE valid_to IS NULL;

COMMENT ON TABLE meta.architecture_nodes IS 'Temporal nodes in the architecture graph with validity periods';
COMMENT ON COLUMN meta.architecture_nodes.node_type IS 'Type: service|endpoint|database|cache|queue|topic|infrastructure|test|incident|deployment|team|documentation';

-- ---------------------------------------------------------------------------
-- Temporal Architecture Edges
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS meta.architecture_edges (
    edge_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    edge_type TEXT NOT NULL,
    repo TEXT NOT NULL,
    metadata JSONB,
    valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (edge_id, valid_from)
);

CREATE INDEX IF NOT EXISTS idx_arch_edges_repo ON meta.architecture_edges (repo);
CREATE INDEX IF NOT EXISTS idx_arch_edges_type ON meta.architecture_edges (edge_type);
CREATE INDEX IF NOT EXISTS idx_arch_edges_source ON meta.architecture_edges (source_id);
CREATE INDEX IF NOT EXISTS idx_arch_edges_target ON meta.architecture_edges (target_id);
CREATE INDEX IF NOT EXISTS idx_arch_edges_valid_from ON meta.architecture_edges (valid_from);
CREATE INDEX IF NOT EXISTS idx_arch_edges_valid_to ON meta.architecture_edges (valid_to);
CREATE INDEX IF NOT EXISTS idx_arch_edges_current ON meta.architecture_edges (repo, edge_type) WHERE valid_to IS NULL;

COMMENT ON TABLE meta.architecture_edges IS 'Temporal edges in the architecture graph with validity periods';
COMMENT ON COLUMN meta.architecture_edges.edge_type IS 'Type: depends_on|calls|produces|consumes|deploys_to|test_covers|incident_tracks|documents|owned_by|implements|migrates_from|migrates_to';

-- ---------------------------------------------------------------------------
-- Architecture Snapshots (for time-travel)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS meta.architecture_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    repo TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    nodes JSONB NOT NULL DEFAULT '[]',
    edges JSONB NOT NULL DEFAULT '[]',
    metrics JSONB,
    health_score NUMERIC(6,4),
    drift_score NUMERIC(6,4),
    drift_analysis JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_arch_snapshots_repo ON meta.architecture_snapshots (repo);
CREATE INDEX IF NOT EXISTS idx_arch_snapshots_ts ON meta.architecture_snapshots (timestamp DESC);

COMMENT ON TABLE meta.architecture_snapshots IS 'Point-in-time snapshots of the architecture graph for time-travel queries';

-- ---------------------------------------------------------------------------
-- Architecture Diffs (change tracking)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS meta.architecture_diffs (
    diff_id TEXT PRIMARY KEY,
    repo TEXT NOT NULL,
    before_snapshot_id TEXT REFERENCES meta.architecture_snapshots(snapshot_id),
    after_snapshot_id TEXT REFERENCES meta.architecture_snapshots(snapshot_id),
    before_timestamp TIMESTAMPTZ NOT NULL,
    after_timestamp TIMESTAMPTZ NOT NULL,
    nodes_added JSONB DEFAULT '[]',
    nodes_removed JSONB DEFAULT '[]',
    nodes_modified JSONB DEFAULT '[]',
    edges_added JSONB DEFAULT '[]',
    edges_removed JSONB DEFAULT '[]',
    edges_modified JSONB DEFAULT '[]',
    llm_analysis JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_arch_diffs_repo ON meta.architecture_diffs (repo);
CREATE INDEX IF NOT EXISTS idx_arch_diffs_ts ON meta.architecture_diffs (after_timestamp DESC);

COMMENT ON TABLE meta.architecture_diffs IS 'Recorded differences between architecture snapshots with LLM analysis';

-- ---------------------------------------------------------------------------
-- Failure Cascades (incident replay)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS meta.failure_cascades (
    cascade_id TEXT PRIMARY KEY,
    repo TEXT NOT NULL,
    root_cause TEXT NOT NULL,
    root_service_id TEXT NOT NULL,
    trigger_timestamp TIMESTAMPTZ NOT NULL,
    cascade_sequence JSONB NOT NULL,
    total_affected_services INT,
    total_duration_seconds INT,
    incident_id TEXT,
    llm_analysis JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_failure_cascades_repo ON meta.failure_cascades (repo);
CREATE INDEX IF NOT EXISTS idx_failure_cascades_ts ON meta.failure_cascades (trigger_timestamp DESC);

COMMENT ON TABLE meta.failure_cascades IS 'Recorded and simulated failure cascades through the architecture';

-- ---------------------------------------------------------------------------
-- Architecture Projections (future state modeling)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS meta.architecture_projections (
    projection_id TEXT PRIMARY KEY,
    repo TEXT NOT NULL,
    current_state_snapshot_id TEXT REFERENCES meta.architecture_snapshots(snapshot_id),
    proposed_changes JSONB NOT NULL,
    future_state JSONB,
    change_analysis JSONB,
    migration_plan JSONB,
    risk_assessment JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_arch_projections_repo ON meta.architecture_projections (repo);

COMMENT ON TABLE meta.architecture_projections IS 'Future state projections based on proposed architectural changes';

-- ---------------------------------------------------------------------------
-- Scaffolding Runs (autonomous generation)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS meta.scaffolding_runs (
    scaffold_id TEXT PRIMARY KEY,
    repo TEXT NOT NULL,
    requirements TEXT NOT NULL,
    target_platform TEXT,
    blueprint JSONB NOT NULL,
    services JSONB NOT NULL,
    files JSONB NOT NULL,
    infrastructure JSONB,
    adrs JSONB,
    llm_model TEXT,
    tokens_used INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scaffolding_repo ON meta.scaffolding_runs (repo);

COMMENT ON TABLE meta.scaffolding_runs IS 'Autonomous scaffolding generation runs from natural language requirements';

-- ---------------------------------------------------------------------------
-- Enhanced Edge Type Reference Data
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS meta.edge_type_definitions (
    edge_type TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    source_types TEXT[] NOT NULL,
    target_types TEXT[] NOT NULL,
    metadata_schema JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Populate edge type definitions
INSERT INTO meta.edge_type_definitions (edge_type, description, source_types, target_types) VALUES
    ('depends_on', 'Service dependency relationship', ARRAY['service'], ARRAY['service']),
    ('calls', 'Synchronous RPC/HTTP call', ARRAY['service', 'endpoint'], ARRAY['service', 'endpoint']),
    ('produces', 'Produces messages to topic/queue', ARRAY['service'], ARRAY['topic', 'queue']),
    ('consumes', 'Consumes messages from topic/queue', ARRAY['service'], ARRAY['topic', 'queue']),
    ('deploys_to', 'Service deployment target', ARRAY['service'], ARRAY['infrastructure']),
    ('test_covers', 'Test coverage relationship', ARRAY['test'], ARRAY['service', 'endpoint']),
    ('incident_tracks', 'Incident affected service', ARRAY['incident'], ARRAY['service']),
    ('documents', 'Documentation relationship', ARRAY['documentation'], ARRAY['service', 'endpoint', 'database']),
    ('owned_by', 'Team ownership', ARRAY['service', 'database', 'infrastructure'], ARRAY['team']),
    ('implements', 'Interface implementation', ARRAY['service'], ARRAY['endpoint']),
    ('migrates_from', 'Migration source', ARRAY['service'], ARRAY['service']),
    ('migrates_to', 'Migration target', ARRAY['service'], ARRAY['service'])
ON CONFLICT (edge_type) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Node Type Reference Data
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS meta.node_type_definitions (
    node_type TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    metadata_schema JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO meta.node_type_definitions (node_type, description) VALUES
    ('service', 'Microservice or application component'),
    ('endpoint', 'API endpoint (REST/gRPC)'),
    ('database', 'Database instance'),
    ('cache', 'Cache system (Redis, Memcached)'),
    ('queue', 'Message queue'),
    ('topic', 'Kafka/pub-sub topic'),
    ('infrastructure', 'Infrastructure resource (K8s cluster, VM, etc.)'),
    ('test', 'Test suite or test file'),
    ('incident', 'Production incident'),
    ('deployment', 'Deployment record'),
    ('team', 'Engineering team'),
    ('documentation', 'Documentation artifact')
ON CONFLICT (node_type) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Health Dashboard Aggregations
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS meta.dashboard_health_snapshots (
    id BIGSERIAL PRIMARY KEY,
    repo TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    overall_health_score NUMERIC(6,4),
    overall_grade TEXT,
    service_count INT,
    endpoint_count INT,
    dependency_count INT,
    test_coverage_pct NUMERIC(5,2),
    doc_coverage_pct NUMERIC(5,2),
    active_incidents INT,
    architecture_drift_score NUMERIC(6,4),
    dimensions JSONB,
    trends JSONB,
    alerts JSONB
);

CREATE INDEX IF NOT EXISTS idx_dashboard_health_repo ON meta.dashboard_health_snapshots (repo);
CREATE INDEX IF NOT EXISTS idx_dashboard_health_ts ON meta.dashboard_health_snapshots (timestamp DESC);

COMMENT ON TABLE meta.dashboard_health_snapshots IS 'Aggregated health metrics for dashboard visualization';

-- ---------------------------------------------------------------------------
-- View: Current Architecture Graph
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW meta.current_architecture_graph AS
SELECT
    n.node_id,
    n.node_type,
    n.name,
    n.repo,
    n.metadata,
    n.valid_from,
    n.created_at,
    array_agg(
        jsonb_build_object(
            'edge_id', e.edge_id,
            'source_id', e.source_id,
            'target_id', e.target_id,
            'edge_type', e.edge_type,
            'metadata', e.metadata
        )
    ) FILTER (WHERE e.edge_id IS NOT NULL) as outgoing_edges
FROM meta.architecture_nodes n
LEFT JOIN meta.architecture_edges e ON n.node_id = e.source_id AND e.valid_to IS NULL
WHERE n.valid_to IS NULL
GROUP BY n.node_id, n.node_type, n.name, n.repo, n.metadata, n.valid_from, n.created_at;

COMMENT ON VIEW meta.current_architecture_graph IS 'Current state of architecture graph (nodes with valid_to IS NULL)';

-- ---------------------------------------------------------------------------
-- View: Service Dependency Matrix
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW meta.service_dependency_matrix AS
SELECT
    src.name as source_service,
    tgt.name as target_service,
    e.edge_type,
    e.metadata,
    e.created_at
FROM meta.architecture_edges e
JOIN meta.architecture_nodes src ON e.source_id = src.node_id AND src.valid_to IS NULL
JOIN meta.architecture_nodes tgt ON e.target_id = tgt.node_id AND tgt.valid_to IS NULL
WHERE e.valid_to IS NULL
  AND src.node_type = 'service'
  AND tgt.node_type = 'service';

COMMENT ON VIEW meta.service_dependency_matrix IS 'Service-to-service dependency matrix for impact analysis';

-- ---------------------------------------------------------------------------
-- Function: Get Architecture at Timestamp
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION meta.get_architecture_at_time(
    p_repo TEXT,
    p_timestamp TIMESTAMPTZ
)
RETURNS TABLE (
    node_id TEXT,
    node_type TEXT,
    name TEXT,
    metadata JSONB,
    edge_id TEXT,
    source_id TEXT,
    target_id TEXT,
    edge_type TEXT,
    edge_metadata JSONB
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        n.node_id,
        n.node_type,
        n.name,
        n.metadata,
        e.edge_id,
        e.source_id,
        e.target_id,
        e.edge_type,
        e.metadata
    FROM meta.architecture_nodes n
    LEFT JOIN meta.architecture_edges e
        ON n.node_id = e.source_id
        AND e.valid_from <= p_timestamp
        AND (e.valid_to IS NULL OR e.valid_to > p_timestamp)
    WHERE n.repo = p_repo
      AND n.valid_from <= p_timestamp
      AND (n.valid_to IS NULL OR n.valid_to > p_timestamp);
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION meta.get_architecture_at_time IS 'Reconstruct architecture graph at a specific point in time (time-travel)';

-- ---------------------------------------------------------------------------
-- Function: Calculate Architecture Drift Score
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION meta.calculate_drift_score(
    p_repo TEXT,
    p_intended_state JSONB
)
RETURNS NUMERIC(6,4) AS $$
DECLARE
    v_actual_services TEXT[];
    v_planned_services TEXT[];
    v_unplanned_count INT;
    v_missing_count INT;
    v_actual_deps INT;
    v_unexpected_deps INT;
    v_drift_factors NUMERIC[];
    v_drift_score NUMERIC(6,4);
BEGIN
    -- Get actual services
    SELECT array_agg(DISTINCT name)
    INTO v_actual_services
    FROM meta.architecture_nodes
    WHERE repo = p_repo AND node_type = 'service' AND valid_to IS NULL;

    -- Get planned services
    SELECT array_agg(DISTINCT s)
    INTO v_planned_services
    FROM jsonb_array_elements_text(p_intended_state->'services') s;

    -- Calculate unplanned services
    SELECT COUNT(*)
    INTO v_unplanned_count
    FROM unnest(v_actual_services) a
    WHERE a NOT IN (SELECT unnest(v_planned_services));

    -- Calculate missing services
    SELECT COUNT(*)
    INTO v_missing_count
    FROM unnest(v_planned_services) p
    WHERE p NOT IN (SELECT unnest(v_actual_services));

    -- Calculate unexpected dependencies
    SELECT COUNT(*)
    INTO v_actual_deps
    FROM meta.architecture_edges
    WHERE repo = p_repo AND edge_type = 'depends_on' AND valid_to IS NULL;

    -- TODO: Calculate unexpected deps based on intended state
    v_unexpected_deps := 0;

    -- Build drift factors array
    v_drift_factors := ARRAY[]::NUMERIC[];

    IF array_length(v_actual_services, 1) > 0 THEN
        v_drift_factors := array_append(v_drift_factors, v_unplanned_count::NUMERIC / array_length(v_actual_services, 1));
    END IF;

    IF array_length(v_planned_services, 1) > 0 THEN
        v_drift_factors := array_append(v_drift_factors, v_missing_count::NUMERIC / array_length(v_planned_services, 1));
    END IF;

    IF array_length(v_drift_factors, 1) > 0 THEN
        v_drift_score := (SELECT AVG(v) FROM unnest(v_drift_factors) v);
    ELSE
        v_drift_score := 0.0;
    END IF;

    RETURN v_drift_score;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION meta.calculate_drift_score IS 'Calculate architecture drift score (0.0 = aligned, 1.0 = completely drifted)';

-- ---------------------------------------------------------------------------
-- Trigger: Update timestamps
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION meta.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_architecture_nodes_updated_at
    BEFORE UPDATE ON meta.architecture_nodes
    FOR EACH ROW
    EXECUTE FUNCTION meta.update_updated_at_column();

CREATE TRIGGER update_architecture_edges_updated_at
    BEFORE UPDATE ON meta.architecture_edges
    FOR EACH ROW
    EXECUTE FUNCTION meta.update_updated_at_column();
