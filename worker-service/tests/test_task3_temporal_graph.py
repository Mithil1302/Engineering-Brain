"""
Task 3: Temporal Graph Data Population - Comprehensive Test Suite

Tests all Task 3 requirements:
- 3.1: record_ingestion_snapshot() method
- 3.2: record_policy_event() method  
- 3.3: _verify_temporal_index() method
- 3.4: Pipeline integration (wiring)
- 3.5: Database schema additions

Run with: pytest worker-service/tests/test_task3_temporal_graph.py -v
"""

import pytest
import json
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Any, Dict, List

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.simulation.time_travel import TemporalGraphStore
from app.policy.pipeline import PolicyPipeline


# ---------------------------------------------------------------------------
# Test 3.1: record_ingestion_snapshot()
# ---------------------------------------------------------------------------

class TestRecordIngestionSnapshot:
    """Test Task 3.1: Temporal snapshot recording after ingestion."""
    
    @pytest.mark.asyncio
    async def test_record_ingestion_snapshot_basic(self):
        """Test basic snapshot recording with node additions and removals."""
        
        # Mock PostgreSQL config
        pg_cfg = {
            "host": "localhost",
            "database": "test_db",
            "user": "test_user",
            "password": "test_pass",
        }
        
        store = TemporalGraphStore(pg_cfg=pg_cfg)
        
        # Mock the helper methods
        current_nodes = [
            Mock(node_id="service:repo/test:api-gateway", node_type="service"),
            Mock(node_id="service:repo/test:backend", node_type="service"),
        ]
        current_edges = [
            Mock(edge_id="edge1"),
        ]
        
        store._query_current_nodes = AsyncMock(return_value=current_nodes)
        store._query_current_edges = AsyncMock(return_value=current_edges)
        store._get_latest_snapshot_meta = Mock(return_value={
            "node_ids": ["service:repo/test:api-gateway", "service:repo/test:old-service"]
        })
        store._update_removed_nodes = Mock()
        store.add_node = Mock()
        store._persist_ingestion_snapshot = Mock()
        
        # Mock ingestion result
        ingestion_result = Mock(
            run_id="test-run-123",
            services_detected=2,
        )
        
        # Execute
        snapshot_id = await store.record_ingestion_snapshot("repo/test", ingestion_result)
        
        # Verify snapshot_id format
        assert snapshot_id.startswith("ingestion_repo_test_")
        assert len(snapshot_id) > 20
        
        # Verify removed nodes were updated (old-service was removed)
        store._update_removed_nodes.assert_called_once()
        removed_ids = store._update_removed_nodes.call_args[0][1]
        assert "service:repo/test:old-service" in removed_ids
        
        # Verify new node was added (backend is new)
        assert store.add_node.call_count == 1
        added_node = store.add_node.call_args[0][0]
        assert added_node.node_id == "service:repo/test:backend"
        
        # Verify snapshot was persisted
        store._persist_ingestion_snapshot.assert_called_once()
        call_kwargs = store._persist_ingestion_snapshot.call_args[1]
        assert call_kwargs["snapshot_id"] == snapshot_id
        assert call_kwargs["repo"] == "repo/test"
        assert call_kwargs["services_count"] == 2
        assert call_kwargs["edge_count"] == 1
        assert set(call_kwargs["node_ids"]) == {
            "service:repo/test:api-gateway",
            "service:repo/test:backend",
        }
    
    @pytest.mark.asyncio
    async def test_record_ingestion_snapshot_first_ingestion(self):
        """Test snapshot recording when no previous snapshot exists."""
        
        
        pg_cfg = {"host": "localhost", "database": "test_db"}
        store = TemporalGraphStore(pg_cfg=pg_cfg)
        
        # Mock first ingestion (no previous snapshot)
        current_nodes = [
            Mock(node_id="service:repo/new:api", node_type="service"),
        ]
        
        store._query_current_nodes = AsyncMock(return_value=current_nodes)
        store._query_current_edges = AsyncMock(return_value=[])
        store._get_latest_snapshot_meta = Mock(return_value=None)  # No previous snapshot
        store._update_removed_nodes = Mock()
        store.add_node = Mock()
        store._persist_ingestion_snapshot = Mock()
        
        ingestion_result = Mock(run_id="first-run", services_detected=1)
        
        # Execute
        snapshot_id = await store.record_ingestion_snapshot("repo/new", ingestion_result)
        
        # Verify no nodes were marked as removed
        store._update_removed_nodes.assert_not_called()
        
        # Verify all nodes were added
        assert store.add_node.call_count == 1
        
        # Verify snapshot was persisted
        store._persist_ingestion_snapshot.assert_called_once()


# ---------------------------------------------------------------------------
# Test 3.2: record_policy_event()
# ---------------------------------------------------------------------------

class TestRecordPolicyEvent:
    """Test Task 3.2: Policy event recording."""
    
    def test_record_policy_event_filters_relevant_findings(self):
        """Test that only DOC_DRIFT_* and BREAKING_* findings are recorded."""
        
        
        pg_cfg = {"host": "localhost", "database": "test_db"}
        store = TemporalGraphStore(pg_cfg=pg_cfg)
        
        # Mock PostgreSQL connection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)
        
        with patch('psycopg2.connect', return_value=mock_conn):
            findings = [
                {"rule_id": "DOC_DRIFT_MISSING_ENDPOINT", "message": "Missing docs"},
                {"rule_id": "BREAKING_SCHEMA_CHANGE", "message": "Breaking change"},
                {"rule_id": "STYLE_VIOLATION", "message": "Style issue"},  # Should be filtered
                {"rule_id": "DOC_DRIFT_STALE", "message": "Stale docs"},
            ]
            
            store.record_policy_event("repo/test", 42, findings)
            
            # Verify only 3 findings were inserted (2 DOC_DRIFT + 1 BREAKING)
            assert mock_cursor.execute.call_count == 3
            
            # Verify snapshot_id format for each call
            for call in mock_cursor.execute.call_args_list:
                sql, params = call[0]
                snapshot_id = params[0]
                assert snapshot_id.startswith("policy_repo_test_42_")
                assert any(rule in snapshot_id for rule in ["DOC_DRIFT_", "BREAKING_"])
    
    def test_record_policy_event_empty_findings(self):
        """Test that no database operations occur when no relevant findings."""
        
        
        pg_cfg = {"host": "localhost", "database": "test_db"}
        store = TemporalGraphStore(pg_cfg=pg_cfg)
        
        mock_conn = MagicMock()
        
        with patch('psycopg2.connect', return_value=mock_conn):
            # Only non-relevant findings
            findings = [
                {"rule_id": "STYLE_VIOLATION", "message": "Style issue"},
                {"rule_id": "LINT_ERROR", "message": "Lint error"},
            ]
            
            store.record_policy_event("repo/test", 42, findings)
            
            # Verify no database connection was made
            mock_conn.cursor.assert_not_called()
    
    def test_record_policy_event_on_conflict_handling(self):
        """Test that ON CONFLICT DO NOTHING prevents duplicate events."""
        
        
        pg_cfg = {"host": "localhost", "database": "test_db"}
        store = TemporalGraphStore(pg_cfg=pg_cfg)
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)
        
        with patch('psycopg2.connect', return_value=mock_conn):
            findings = [
                {"rule_id": "DOC_DRIFT_MISSING", "message": "Missing docs"},
            ]
            
            store.record_policy_event("repo/test", 42, findings)
            
            # Verify SQL contains ON CONFLICT clause
            sql = mock_cursor.execute.call_args[0][0]
            assert "ON CONFLICT (snapshot_id) DO NOTHING" in sql


# ---------------------------------------------------------------------------
# Test 3.3: _verify_temporal_index()
# ---------------------------------------------------------------------------

class TestVerifyTemporalIndex:
    """Test Task 3.3: Temporal index verification."""
    
    def test_verify_temporal_index_present(self):
        """Test that index verification passes when index exists."""
        
        
        pg_cfg = {"host": "localhost", "database": "test_db"}
        store = TemporalGraphStore(pg_cfg=pg_cfg)
        
        # Mock PostgreSQL connection with index present
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)
        
        # Simulate EXPLAIN output with Index Scan
        mock_cursor.fetchall.return_value = [
            ("Index Scan using idx_arch_nodes_temporal on meta.architecture_nodes",),
            ("  Index Cond: ((repo = 'test'::text) AND ...)",),
        ]
        
        with patch('psycopg2.connect', return_value=mock_conn):
            with patch('worker_service.app.simulation.time_travel.log') as mock_log:
                store._verify_temporal_index()
                
                # Verify INFO log was called (index present)
                mock_log.info.assert_called_once()
                assert "passed" in mock_log.info.call_args[0][0].lower()
    
    def test_verify_temporal_index_missing(self):
        """Test that WARNING is logged when index is missing."""
        
        
        pg_cfg = {"host": "localhost", "database": "test_db"}
        store = TemporalGraphStore(pg_cfg=pg_cfg)
        
        # Mock PostgreSQL connection without index
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)
        
        # Simulate EXPLAIN output with Seq Scan (no index)
        mock_cursor.fetchall.return_value = [
            ("Seq Scan on meta.architecture_nodes",),
            ("  Filter: ((repo = 'test'::text) AND ...)",),
        ]
        
        with patch('psycopg2.connect', return_value=mock_conn):
            with patch('worker_service.app.simulation.time_travel.log') as mock_log:
                store._verify_temporal_index()
                
                # Verify WARNING log was called with CREATE INDEX command
                mock_log.warning.assert_called_once()
                warning_msg = mock_log.warning.call_args[0][0]
                assert "CREATE INDEX idx_arch_nodes_temporal" in warning_msg
                assert "meta.architecture_nodes" in warning_msg
                assert "(repo, valid_from, valid_to)" in warning_msg
    
    def test_verify_temporal_index_no_pg_config(self):
        """Test that verification is skipped when no PostgreSQL config."""
        
        
        store = TemporalGraphStore(pg_cfg=None)
        
        # Should not raise exception
        store._verify_temporal_index()


# ---------------------------------------------------------------------------
# Test 3.4: Pipeline Integration
# ---------------------------------------------------------------------------

class TestPipelineIntegration:
    """Test Task 3.4: Wiring to pipeline.py."""
    
    @pytest.mark.asyncio
    async def test_handle_ingestion_complete_calls_record_snapshot(self):
        """Test that _handle_ingestion_complete calls record_ingestion_snapshot."""
        
        
        # Mock dependencies
        mock_log = Mock()
        mock_time_travel = Mock()
        mock_time_travel.record_ingestion_snapshot = AsyncMock(return_value="snapshot_123")
        mock_impact_analyzer = Mock()
        mock_impact_analyzer.invalidate_cache = Mock()
        
        pipeline = PolicyPipeline(mock_log, impact_analyzer=mock_impact_analyzer)
        pipeline.time_travel = mock_time_travel
        
        # Simulate repo.ingestion.complete event
        payload = {
            "repo": "test/repo",
            "run_id": "run-123",
            "files_processed": 100,
            "chunks_created": 500,
            "embeddings_created": 500,
            "services_detected": 3,
            "duration_seconds": 45.2,
            "status": "success",
        }
        
        await pipeline._handle_ingestion_complete(payload)
        
        # Verify record_ingestion_snapshot was called BEFORE invalidate_cache
        mock_time_travel.record_ingestion_snapshot.assert_called_once()
        call_args = mock_time_travel.record_ingestion_snapshot.call_args
        assert call_args[0][0] == "test/repo"
        assert call_args[0][1].run_id == "run-123"
        
        # Verify cache was invalidated after snapshot
        mock_impact_analyzer.invalidate_cache.assert_called_once_with("test/repo")
    
    def test_record_policy_temporal_filters_findings(self):
        """Test that _record_policy_temporal only records relevant findings."""
        
        
        mock_log = Mock()
        mock_time_travel = Mock()
        mock_time_travel.record_policy_event = Mock()
        
        pipeline = PolicyPipeline(mock_log)
        pipeline.time_travel = mock_time_travel
        
        findings = [
            {"rule_id": "DOC_DRIFT_MISSING", "message": "Missing docs"},
            {"rule_id": "BREAKING_CHANGE", "message": "Breaking change"},
            {"rule_id": "STYLE_ISSUE", "message": "Style problem"},
        ]
        
        pipeline._record_policy_temporal("test/repo", 42, findings)
        
        # Verify record_policy_event was called with all findings
        # (filtering happens inside record_policy_event)
        mock_time_travel.record_policy_event.assert_called_once_with(
            "test/repo", 42, findings
        )
    
    def test_run_loop_calls_verify_temporal_index(self):
        """Test that _run_loop calls _verify_temporal_index at startup."""
        
        
        mock_log = Mock()
        mock_time_travel = Mock()
        mock_time_travel._verify_temporal_index = Mock()
        
        pipeline = PolicyPipeline(mock_log)
        pipeline.time_travel = mock_time_travel
        
        # Mock Kafka consumer to prevent actual connection
        with patch('worker_service.app.policy.pipeline.KafkaConsumer') as mock_consumer:
            with patch('worker_service.app.policy.pipeline.KafkaProducer') as mock_producer:
                with patch('worker_service.app.policy.pipeline.ensure_schema'):
                    # Mock consumer to raise exception after setup to exit loop
                    mock_consumer.return_value.__iter__ = Mock(side_effect=KeyboardInterrupt)
                    
                    try:
                        pipeline._run_loop()
                    except KeyboardInterrupt:
                        pass
                    
                    # Verify _verify_temporal_index was called during startup
                    mock_time_travel._verify_temporal_index.assert_called_once()


# ---------------------------------------------------------------------------
# Test 3.5: Database Schema
# ---------------------------------------------------------------------------

class TestDatabaseSchema:
    """Test Task 3.5: Database schema additions."""
    
    def test_migration_file_has_event_type_column(self):
        """Test that migration adds event_type column."""
        with open("migrations/003_ingestion_and_gaps.sql", "r") as f:
            migration_sql = f.read()
        
        # Verify event_type column is added
        assert "ADD COLUMN IF NOT EXISTS event_type TEXT" in migration_sql
        assert "meta.architecture_snapshots" in migration_sql
    
    def test_migration_file_has_event_payload_column(self):
        """Test that migration adds event_payload column."""
        with open("migrations/003_ingestion_and_gaps.sql", "r") as f:
            migration_sql = f.read()
        
        # Verify event_payload column is added
        assert "ADD COLUMN IF NOT EXISTS event_payload JSONB" in migration_sql
        assert "meta.architecture_snapshots" in migration_sql
    
    def test_migration_file_documents_unique_constraint(self):
        """Test that migration documents snapshot_id unique constraint."""
        with open("migrations/003_ingestion_and_gaps.sql", "r") as f:
            migration_sql = f.read()
        
        # Verify comment about PRIMARY KEY satisfying ON CONFLICT requirement
        assert "snapshot_id" in migration_sql
        assert "ON CONFLICT" in migration_sql or "PRIMARY KEY" in migration_sql
    
    def test_migration_file_documents_advisory_index(self):
        """Test that migration documents idx_arch_nodes_temporal as advisory."""
        with open("migrations/003_ingestion_and_gaps.sql", "r") as f:
            migration_sql = f.read()
        
        # Verify advisory note about idx_arch_nodes_temporal
        assert "idx_arch_nodes_temporal" in migration_sql
        assert "advisory" in migration_sql.lower()
        assert "_verify_temporal_index" in migration_sql


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------

class TestTask3Integration:
    """Integration tests for Task 3 end-to-end flow."""
    
    @pytest.mark.asyncio
    async def test_full_ingestion_to_snapshot_flow(self):
        """Test complete flow from ingestion event to snapshot recording."""
        
        
        
        # Setup
        pg_cfg = {"host": "localhost", "database": "test_db"}
        store = TemporalGraphStore(pg_cfg=pg_cfg)
        
        # Mock all database operations
        store._query_current_nodes = AsyncMock(return_value=[
            Mock(node_id="service:test:api", node_type="service"),
        ])
        store._query_current_edges = AsyncMock(return_value=[])
        store._get_latest_snapshot_meta = Mock(return_value=None)
        store._update_removed_nodes = Mock()
        store.add_node = Mock()
        store._persist_ingestion_snapshot = Mock()
        
        # Create pipeline with mocked time_travel
        mock_log = Mock()
        pipeline = PolicyPipeline(mock_log)
        pipeline.time_travel = store
        pipeline.impact_analyzer = Mock()
        pipeline.impact_analyzer.invalidate_cache = Mock()
        
        # Simulate ingestion complete event
        payload = {
            "repo": "test/repo",
            "run_id": "run-123",
            "files_processed": 50,
            "chunks_created": 200,
            "embeddings_created": 200,
            "services_detected": 1,
            "duration_seconds": 30.0,
            "status": "success",
        }
        
        # Execute
        await pipeline._handle_ingestion_complete(payload)
        
        # Verify snapshot was recorded
        store._persist_ingestion_snapshot.assert_called_once()
        
        # Verify cache was invalidated
        pipeline.impact_analyzer.invalidate_cache.assert_called_once_with("test/repo")
    
    def test_policy_finding_to_snapshot_flow(self):
        """Test complete flow from policy evaluation to snapshot recording."""
        
        
        
        # Setup
        pg_cfg = {"host": "localhost", "database": "test_db"}
        store = TemporalGraphStore(pg_cfg=pg_cfg)
        
        # Mock database operations
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)
        
        # Create pipeline
        mock_log = Mock()
        pipeline = PolicyPipeline(mock_log)
        pipeline.time_travel = store
        
        findings = [
            {"rule_id": "DOC_DRIFT_MISSING_ENDPOINT", "message": "Missing docs", "severity": "high"},
            {"rule_id": "BREAKING_SCHEMA_CHANGE", "message": "Breaking change", "severity": "critical"},
        ]
        
        with patch('psycopg2.connect', return_value=mock_conn):
            # Execute
            pipeline._record_policy_temporal("test/repo", 42, findings)
            
            # Verify 2 snapshot records were inserted
            assert mock_cursor.execute.call_count == 2
            
            # Verify snapshot_ids are unique
            snapshot_ids = [call[0][1][0] for call in mock_cursor.execute.call_args_list]
            assert len(set(snapshot_ids)) == 2
            assert all("policy_test_repo_42_" in sid for sid in snapshot_ids)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

