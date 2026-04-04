"""
Task 3: Temporal Graph Data Population - Simple Test Suite

Tests Task 3 requirements without heavy dependencies:
- 3.3: _verify_temporal_index() method
- 3.5: Database schema additions

Run with: pytest worker-service/tests/test_task3_simple.py -v
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Test 3.3: _verify_temporal_index()
# ---------------------------------------------------------------------------

class TestVerifyTemporalIndex:
    """Test Task 3.3: Temporal index verification."""
    
    def test_verify_temporal_index_present(self):
        """Test that index verification passes when index exists."""
        from app.simulation.time_travel import TemporalGraphStore
        
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
            with patch('app.simulation.time_travel.log') as mock_log:
                store._verify_temporal_index()
                
                # Verify INFO log was called (index present)
                mock_log.info.assert_called_once()
                assert "passed" in mock_log.info.call_args[0][0].lower()
    
    def test_verify_temporal_index_missing(self):
        """Test that WARNING is logged when index is missing."""
        from app.simulation.time_travel import TemporalGraphStore
        
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
            with patch('app.simulation.time_travel.log') as mock_log:
                store._verify_temporal_index()
                
                # Verify WARNING log was called with CREATE INDEX command
                mock_log.warning.assert_called_once()
                warning_msg = mock_log.warning.call_args[0][0]
                assert "CREATE INDEX idx_arch_nodes_temporal" in warning_msg
                assert "meta.architecture_nodes" in warning_msg
                assert "(repo, valid_from, valid_to)" in warning_msg
    
    def test_verify_temporal_index_no_pg_config(self):
        """Test that verification is skipped when no PostgreSQL config."""
        from app.simulation.time_travel import TemporalGraphStore
        
        store = TemporalGraphStore(pg_cfg=None)
        
        # Should not raise exception
        store._verify_temporal_index()


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
# Test Implementation Verification
# ---------------------------------------------------------------------------

class TestTask3Implementation:
    """Verify Task 3 implementation exists."""
    
    def test_record_ingestion_snapshot_exists(self):
        """Verify record_ingestion_snapshot method exists."""
        from app.simulation.time_travel import TemporalGraphStore
        
        store = TemporalGraphStore(pg_cfg=None)
        assert hasattr(store, 'record_ingestion_snapshot')
        assert callable(store.record_ingestion_snapshot)
    
    def test_record_policy_event_exists(self):
        """Verify record_policy_event method exists."""
        from app.simulation.time_travel import TemporalGraphStore
        
        store = TemporalGraphStore(pg_cfg=None)
        assert hasattr(store, 'record_policy_event')
        assert callable(store.record_policy_event)
    
    def test_verify_temporal_index_exists(self):
        """Verify _verify_temporal_index method exists."""
        from app.simulation.time_travel import TemporalGraphStore
        
        store = TemporalGraphStore(pg_cfg=None)
        assert hasattr(store, '_verify_temporal_index')
        assert callable(store._verify_temporal_index)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
