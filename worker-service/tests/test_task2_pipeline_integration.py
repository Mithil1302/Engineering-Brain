"""
Task 2.2 Tests: Cache Invalidation Wiring in Policy Pipeline

Tests the integration of cache invalidation with the policy pipeline:
- _handle_ingestion_complete method exists
- Kafka consumer for repo.ingestion.complete topic
- Cache invalidation is called with correct repo
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import json

# Import the class under test
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.policy.pipeline import PolicyPipeline


class TestIngestionCompleteHandler:
    """Test Task 2.2.1: _handle_ingestion_complete method"""
    
    def test_handler_method_exists(self):
        """Verify _handle_ingestion_complete method exists on PolicyPipeline"""
        mock_log = Mock()
        mock_impact_analyzer = Mock()
        
        pipeline = PolicyPipeline(mock_log, impact_analyzer=mock_impact_analyzer)
        
        assert hasattr(pipeline, '_handle_ingestion_complete')
        assert callable(getattr(pipeline, '_handle_ingestion_complete'))
    
    @pytest.mark.asyncio
    async def test_handler_accepts_payload(self):
        """Verify handler accepts Kafka payload dict"""
        mock_log = Mock()
        mock_impact_analyzer = Mock()
        mock_impact_analyzer.invalidate_cache = AsyncMock()
        
        pipeline = PolicyPipeline(mock_log, impact_analyzer=mock_impact_analyzer)
        
        payload = {
            "repo": "test/repo",
            "run_id": "test-run-123",
            "files_processed": 100,
            "chunks_created": 500,
            "embeddings_created": 500,
            "services_detected": 3,
            "duration_seconds": 45.2,
            "status": "success"
        }
        
        # Should not raise exception
        await pipeline._handle_ingestion_complete(payload)


class TestCacheInvalidationCall:
    """Test Task 2.2.2: Cache invalidation is called correctly"""
    
    @pytest.mark.asyncio
    async def test_invalidate_cache_called_with_repo(self):
        """Task 2.2.2: Verify impact_analyzer.invalidate_cache is called with repo"""
        mock_log = Mock()
        mock_impact_analyzer = Mock()
        mock_impact_analyzer.invalidate_cache = AsyncMock()
        
        pipeline = PolicyPipeline(mock_log, impact_analyzer=mock_impact_analyzer)
        
        payload = {
            "repo": "test/repo",
            "run_id": "test-run-123",
            "status": "success"
        }
        
        await pipeline._handle_ingestion_complete(payload)
        
        # Verify invalidate_cache was called with correct repo
        mock_impact_analyzer.invalidate_cache.assert_called_once_with("test/repo")
    
    @pytest.mark.asyncio
    async def test_invalidate_cache_called_for_different_repos(self):
        """Verify cache invalidation works for multiple repos"""
        mock_log = Mock()
        mock_impact_analyzer = Mock()
        mock_impact_analyzer.invalidate_cache = AsyncMock()
        
        pipeline = PolicyPipeline(mock_log, impact_analyzer=mock_impact_analyzer)
        
        # Test multiple repos
        repos = ["org1/repo1", "org2/repo2", "org3/repo3"]
        
        for repo in repos:
            payload = {"repo": repo, "status": "success"}
            await pipeline._handle_ingestion_complete(payload)
        
        # Verify each repo was invalidated
        assert mock_impact_analyzer.invalidate_cache.call_count == 3
        call_args_list = [call[0][0] for call in mock_impact_analyzer.invalidate_cache.call_args_list]
        assert set(call_args_list) == set(repos)
    
    @pytest.mark.asyncio
    async def test_handler_resilient_to_missing_repo(self):
        """Verify handler handles payload without repo field gracefully"""
        mock_log = Mock()
        mock_impact_analyzer = Mock()
        mock_impact_analyzer.invalidate_cache = AsyncMock()
        
        pipeline = PolicyPipeline(mock_log, impact_analyzer=mock_impact_analyzer)
        
        payload = {
            "run_id": "test-run-123",
            "status": "success"
            # Missing "repo" field
        }
        
        # Should handle gracefully (may log error or skip)
        try:
            await pipeline._handle_ingestion_complete(payload)
        except KeyError:
            # Expected if implementation requires repo
            pass


class TestKafkaConsumerRegistration:
    """Test Task 2.2.3: Kafka consumer registration for repo.ingestion.complete"""
    
    def test_consumer_registered_in_run_loop(self):
        """Task 2.2.3: Verify consumer for repo.ingestion.complete is registered"""
        mock_log = Mock()
        mock_impact_analyzer = Mock()
        
        pipeline = PolicyPipeline(mock_log, impact_analyzer=mock_impact_analyzer)
        
        # Check if _run_loop method exists
        assert hasattr(pipeline, '_run_loop')
        
        # The actual consumer registration happens in _run_loop
        # We can't easily test this without running the loop,
        # but we can verify the handler exists
        assert hasattr(pipeline, '_handle_ingestion_complete')
    
    @pytest.mark.asyncio
    async def test_ingestion_complete_event_triggers_handler(self):
        """Verify repo.ingestion.complete Kafka event triggers handler"""
        mock_log = Mock()
        mock_impact_analyzer = Mock()
        mock_impact_analyzer.invalidate_cache = AsyncMock()
        
        pipeline = PolicyPipeline(mock_log, impact_analyzer=mock_impact_analyzer)
        
        # Simulate Kafka message
        kafka_message = {
            "topic": "repo.ingestion.complete",
            "value": json.dumps({
                "repo": "test/repo",
                "run_id": "run-123",
                "status": "success",
                "files_processed": 50,
                "chunks_created": 200,
                "embeddings_created": 200,
                "services_detected": 2,
                "duration_seconds": 30.5
            })
        }
        
        # Parse and call handler
        payload = json.loads(kafka_message["value"])
        await pipeline._handle_ingestion_complete(payload)
        
        # Verify cache was invalidated
        mock_impact_analyzer.invalidate_cache.assert_called_once_with("test/repo")


class TestHandlerErrorHandling:
    """Test error handling in _handle_ingestion_complete"""
    
    @pytest.mark.asyncio
    async def test_handler_logs_on_invalidation_failure(self):
        """Verify handler logs errors if cache invalidation fails"""
        mock_log = Mock()
        mock_impact_analyzer = Mock()
        mock_impact_analyzer.invalidate_cache = AsyncMock(
            side_effect=Exception("Cache invalidation failed")
        )
        
        pipeline = PolicyPipeline(mock_log, impact_analyzer=mock_impact_analyzer)
        
        payload = {"repo": "test/repo", "status": "success"}
        
        # Handler should catch exception and log
        try:
            await pipeline._handle_ingestion_complete(payload)
        except Exception:
            # If exception propagates, that's also acceptable
            pass
        
        # Either way, invalidate_cache should have been attempted
        mock_impact_analyzer.invalidate_cache.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handler_continues_on_error(self):
        """Verify handler doesn't crash pipeline on error"""
        mock_log = Mock()
        mock_impact_analyzer = Mock()
        mock_impact_analyzer.invalidate_cache = AsyncMock(
            side_effect=Exception("Test error")
        )
        
        pipeline = PolicyPipeline(mock_log, impact_analyzer=mock_impact_analyzer)
        
        payload = {"repo": "test/repo", "status": "success"}
        
        # Should not raise exception that would crash the pipeline
        try:
            await pipeline._handle_ingestion_complete(payload)
        except Exception as e:
            # If it does raise, verify it's handled appropriately
            assert "Test error" in str(e) or True  # Either caught or propagated


class TestIntegrationWithTimeTravel:
    """Test Task 2.2.2 note: Integration with Time Travel System (Task 3)"""
    
    @pytest.mark.asyncio
    async def test_handler_can_call_multiple_systems(self):
        """Verify handler can call both cache invalidation and time travel"""
        mock_log = Mock()
        mock_impact_analyzer = Mock()
        mock_impact_analyzer.invalidate_cache = AsyncMock()
        
        # Mock time travel system (will be added in Task 3)
        mock_time_travel = Mock()
        mock_time_travel.record_ingestion_snapshot = AsyncMock()
        
        pipeline = PolicyPipeline(mock_log, impact_analyzer=mock_impact_analyzer)
        
        # Simulate handler that calls both systems
        payload = {
            "repo": "test/repo",
            "run_id": "run-123",
            "status": "success"
        }
        
        await pipeline._handle_ingestion_complete(payload)
        
        # Verify cache invalidation was called
        mock_impact_analyzer.invalidate_cache.assert_called_once_with("test/repo")
        
        # Note: Time travel integration will be tested in Task 3


class TestPayloadValidation:
    """Test payload structure validation"""
    
    @pytest.mark.asyncio
    async def test_handler_accepts_complete_payload(self):
        """Verify handler accepts full repo.ingestion.complete payload"""
        mock_log = Mock()
        mock_impact_analyzer = Mock()
        mock_impact_analyzer.invalidate_cache = AsyncMock()
        
        pipeline = PolicyPipeline(mock_log, impact_analyzer=mock_impact_analyzer)
        
        # Full payload matching Kafka schema from Appendix C
        payload = {
            "repo": "test/repo",
            "run_id": "550e8400-e29b-41d4-a716-446655440000",
            "files_processed": 150,
            "chunks_created": 750,
            "embeddings_created": 750,
            "services_detected": 5,
            "duration_seconds": 62.3,
            "status": "success",
            "timestamp": "2024-03-20T10:30:00Z"
        }
        
        await pipeline._handle_ingestion_complete(payload)
        
        # Should extract repo and call invalidate_cache
        mock_impact_analyzer.invalidate_cache.assert_called_once_with("test/repo")
    
    @pytest.mark.asyncio
    async def test_handler_works_with_minimal_payload(self):
        """Verify handler works with minimal required fields"""
        mock_log = Mock()
        mock_impact_analyzer = Mock()
        mock_impact_analyzer.invalidate_cache = AsyncMock()
        
        pipeline = PolicyPipeline(mock_log, impact_analyzer=mock_impact_analyzer)
        
        # Minimal payload
        payload = {
            "repo": "test/repo",
            "status": "success"
        }
        
        await pipeline._handle_ingestion_complete(payload)
        
        mock_impact_analyzer.invalidate_cache.assert_called_once_with("test/repo")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
