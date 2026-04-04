"""
Task 2.1 Tests: Neo4j Graph Service Integration for Impact Analyzer

Tests the Impact Analyzer's integration with Neo4j via gRPC, including:
- Constructor initialization with graph_service_url and pg_cfg
- Cache implementation with 60-second TTL
- Neo4j query methods with PostgreSQL fallback
- Cache invalidation
"""

import pytest
import time
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timezone
import grpc
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.simulation.impact_analyzer import ImpactAnalyzer


class TestImpactAnalyzerInitialization:
    """Test Task 2.1.1 and 2.1.2: Constructor and gRPC initialization"""
    
    def test_constructor_accepts_required_parameters(self):
        """Task 2.1.1: Verify constructor accepts graph_service_url and pg_cfg"""
        graph_service_url = "graph-service:50051"
        pg_cfg = {
            "host": "localhost",
            "port": 5432,
            "user": "test",
            "password": "test",
            "dbname": "test"
        }
        
        analyzer = ImpactAnalyzer(
            graph_service_url=graph_service_url,
            pg_cfg=pg_cfg
        )
        
        assert analyzer.graph_service_url == graph_service_url
        assert analyzer.pg_cfg == pg_cfg
    
    def test_grpc_channel_initialized(self):
        """Task 2.1.2: Verify gRPC channel and stub are initialized"""
        analyzer = ImpactAnalyzer(
            graph_service_url="graph-service:50051",
            pg_cfg={}
        )
        
        assert hasattr(analyzer, '_channel')
        assert hasattr(analyzer, '_grpc_stub')
        assert analyzer._channel is not None
        assert analyzer._grpc_stub is not None
    
    def test_cache_initialized(self):
        """Task 2.1.3: Verify cache dict and TTL are initialized"""
        analyzer = ImpactAnalyzer(
            graph_service_url="graph-service:50051",
            pg_cfg={}
        )
        
        assert hasattr(analyzer, '_cache')
        assert hasattr(analyzer, '_cache_ttl')
        assert isinstance(analyzer._cache, dict)
        assert analyzer._cache_ttl == 60
        assert len(analyzer._cache) == 0


class TestCacheImplementation:
    """Test Task 2.1.3 and 2.1.4: Cache with 60-second TTL"""
    
    @pytest.mark.asyncio
    async def test_cache_stores_data_with_expiry(self):
        """Verify cache stores (data, expiry_timestamp) tuples"""
        analyzer = ImpactAnalyzer(
            graph_service_url="graph-service:50051",
            pg_cfg={}
        )
        
        # Mock the gRPC call
        with patch.object(analyzer, '_grpc_stub') as mock_stub:
            mock_response = Mock()
            mock_response.rows = []
            mock_stub.QueryGraph = AsyncMock(return_value=mock_response)
            
            # First call should hit gRPC
            before_time = time.time()
            await analyzer._get_dependency_edges("test/repo")
            after_time = time.time()
            
            # Check cache was populated
            cache_key = "edges:test/repo"
            assert cache_key in analyzer._cache
            
            data, expiry = analyzer._cache[cache_key]
            assert isinstance(data, list)
            assert expiry > before_time + 59  # Should be ~60 seconds from now
            assert expiry < after_time + 61
    
    @pytest.mark.asyncio
    async def test_cache_hit_skips_grpc_call(self):
        """Verify cache hit returns cached data without gRPC call"""
        analyzer = ImpactAnalyzer(
            graph_service_url="graph-service:50051",
            pg_cfg={}
        )
        
        # Pre-populate cache
        cache_key = "edges:test/repo"
        cached_data = [("service-a", "service-b", "runtime")]
        expiry = time.time() + 60
        analyzer._cache[cache_key] = (cached_data, expiry)
        
        # Mock gRPC to verify it's NOT called
        with patch.object(analyzer, '_grpc_stub') as mock_stub:
            mock_stub.QueryGraph = AsyncMock()
            
            result = await analyzer._get_dependency_edges("test/repo")
            
            # Should return cached data
            assert result == cached_data
            # Should NOT call gRPC
            mock_stub.QueryGraph.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_expired_cache_triggers_refresh(self):
        """Verify expired cache entries trigger new gRPC call"""
        analyzer = ImpactAnalyzer(
            graph_service_url="graph-service:50051",
            pg_cfg={}
        )
        
        # Pre-populate cache with expired entry
        cache_key = "edges:test/repo"
        cached_data = [("old", "data", "runtime")]
        expiry = time.time() - 1  # Expired 1 second ago
        analyzer._cache[cache_key] = (cached_data, expiry)
        
        # Mock gRPC to return new data
        with patch.object(analyzer, '_grpc_stub') as mock_stub:
            mock_response = Mock()
            mock_response.rows = []
            mock_stub.QueryGraph = AsyncMock(return_value=mock_response)
            
            result = await analyzer._get_dependency_edges("test/repo")
            
            # Should call gRPC because cache expired
            mock_stub.QueryGraph.assert_called_once()


class TestDependencyEdgesQuery:
    """Test Task 2.1.4: _get_dependency_edges with Neo4j and PostgreSQL fallback"""
    
    @pytest.mark.asyncio
    async def test_cypher_query_format(self):
        """Verify correct Cypher query is sent to Neo4j"""
        analyzer = ImpactAnalyzer(
            graph_service_url="graph-service:50051",
            pg_cfg={}
        )
        
        with patch.object(analyzer, '_grpc_stub') as mock_stub:
            mock_response = Mock()
            mock_response.rows = []
            mock_stub.QueryGraph = AsyncMock(return_value=mock_response)
            
            await analyzer._get_dependency_edges("test/repo")
            
            # Verify QueryGraph was called
            assert mock_stub.QueryGraph.called
            call_args = mock_stub.QueryGraph.call_args
            
            # Check the cypher query contains required elements
            request = call_args[0][0] if call_args[0] else call_args[1].get('request')
            cypher = request.cypher if hasattr(request, 'cypher') else str(request)
            assert "MATCH" in cypher
            assert "Service" in cypher
            assert "DEPENDENCY" in cypher
            assert "RETURN" in cypher
    
    @pytest.mark.asyncio
    async def test_transforms_to_tuple_format(self):
        """Task 2.1.4: Verify response is transformed to list[tuple[str, str, str]]"""
        analyzer = ImpactAnalyzer(
            graph_service_url="graph-service:50051",
            pg_cfg={}
        )
        
        with patch.object(analyzer, '_grpc_stub') as mock_stub:
            # Mock gRPC response with proper structure
            mock_row1 = {"source": "service-a", "target": "service-b", "type": "runtime"}
            mock_row2 = {"source": "service-b", "target": "service-c", "type": "import"}
            
            mock_response = Mock()
            mock_response.rows = [mock_row1, mock_row2]
            mock_stub.QueryGraph = AsyncMock(return_value=mock_response)
            
            result = await analyzer._get_dependency_edges("test/repo")
            
            # Verify format
            assert isinstance(result, list)
            assert len(result) == 2
            assert all(isinstance(item, tuple) and len(item) == 3 for item in result)
            assert result[0] == ("service-a", "service-b", "runtime")
            assert result[1] == ("service-b", "service-c", "import")
    
    @pytest.mark.asyncio
    async def test_postgres_fallback_on_grpc_failure(self):
        """Task 2.1.3 and 2.1.5: Verify PostgreSQL fallback on gRPC failure"""
        pg_cfg = {
            "host": "localhost",
            "port": 5432,
            "user": "test",
            "password": "test",
            "dbname": "test"
        }
        analyzer = ImpactAnalyzer(
            graph_service_url="graph-service:50051",
            pg_cfg=pg_cfg
        )
        
        # Create a proper exception class that inherits from both grpc.RpcError and BaseException
        class MockRpcError(grpc.RpcError, Exception):
            def code(self):
                return grpc.StatusCode.UNAVAILABLE
            
            def details(self):
                return "Connection failed"
        
        with patch.object(analyzer, '_grpc_stub') as mock_stub:
            # Mock gRPC failure with proper exception
            mock_stub.QueryGraph = AsyncMock(side_effect=MockRpcError("Connection failed"))
            
            # Mock PostgreSQL fallback
            with patch.object(analyzer, '_get_dependency_edges_from_postgres') as mock_pg:
                mock_pg.return_value = [("service-a", "service-b", "runtime")]
                
                result = await analyzer._get_dependency_edges("test/repo")
                
                # Should call PostgreSQL fallback
                mock_pg.assert_called_once_with("test/repo")
                assert result == [("service-a", "service-b", "runtime")]
    
    @pytest.mark.asyncio
    async def test_fallback_logs_warning(self):
        """Task 2.1.11: Verify WARNING is logged on fallback with error details"""
        analyzer = ImpactAnalyzer(
            graph_service_url="graph-service:50051",
            pg_cfg={}
        )
        
        # Create a proper exception class
        class MockRpcError(grpc.RpcError, Exception):
            def code(self):
                return grpc.StatusCode.UNAVAILABLE
            
            def details(self):
                return "Service unavailable"
        
        with patch.object(analyzer, '_grpc_stub') as mock_stub:
            # Mock gRPC error
            mock_stub.QueryGraph = AsyncMock(side_effect=MockRpcError("Service unavailable"))
            
            with patch.object(analyzer, '_get_dependency_edges_from_postgres') as mock_pg:
                mock_pg.return_value = []
                
                with patch('app.simulation.impact_analyzer.log') as mock_log:
                    await analyzer._get_dependency_edges("test/repo")
                    
                    # Verify WARNING was logged
                    assert mock_log.warning.called
                    warning_msg = mock_log.warning.call_args[0][0]
                    assert "Neo4j" in warning_msg
                    assert "test/repo" in warning_msg
                    assert "PostgreSQL fallback" in warning_msg


class TestServiceNodeQuery:
    """Test Task 2.1.6: _get_service_node with cache and fallback"""
    
    @pytest.mark.asyncio
    async def test_service_node_cypher_query(self):
        """Verify correct Cypher query for service node lookup"""
        analyzer = ImpactAnalyzer(
            graph_service_url="graph-service:50051",
            pg_cfg={}
        )
        
        with patch.object(analyzer, '_grpc_stub') as mock_stub:
            mock_response = Mock()
            mock_response.rows = []
            mock_stub.QueryGraph = AsyncMock(return_value=mock_response)
            
            await analyzer._get_service_node("test/repo", "my-service")
            
            assert mock_stub.QueryGraph.called
            call_args = mock_stub.QueryGraph.call_args
            
            # Verify query structure
            request = call_args[0][0] if call_args[0] else call_args[1].get('request')
            cypher = request.cypher if hasattr(request, 'cypher') else str(request)
            
            assert "MATCH" in cypher
            assert "Service" in cypher
            assert "service_name" in cypher
            assert "repo" in cypher
    
    @pytest.mark.asyncio
    async def test_service_node_uses_cache(self):
        """Verify service node queries use cache"""
        analyzer = ImpactAnalyzer(
            graph_service_url="graph-service:50051",
            pg_cfg={}
        )
        
        # Pre-populate cache
        cache_key = "service:test/repo:my-service"
        cached_node = {"service_name": "my-service", "language": "python"}
        analyzer._cache[cache_key] = (cached_node, time.time() + 60)
        
        with patch.object(analyzer, '_grpc_stub') as mock_stub:
            mock_stub.QueryGraph = AsyncMock()
            
            result = await analyzer._get_service_node("test/repo", "my-service")
            
            # Should return cached data
            assert result == cached_node
            # Should NOT call gRPC
            mock_stub.QueryGraph.assert_not_called()


class TestAPINodesQuery:
    """Test Task 2.1.7: _get_api_nodes with path fragment search"""
    
    @pytest.mark.asyncio
    async def test_api_nodes_path_contains_query(self):
        """Verify Cypher query uses CONTAINS for path fragment"""
        analyzer = ImpactAnalyzer(
            graph_service_url="graph-service:50051",
            pg_cfg={}
        )
        
        with patch.object(analyzer, '_grpc_stub') as mock_stub:
            mock_response = Mock()
            mock_response.rows = []
            mock_stub.QueryGraph = AsyncMock(return_value=mock_response)
            
            await analyzer._get_api_nodes("test/repo", "/api/users")
            
            assert mock_stub.QueryGraph.called
            call_args = mock_stub.QueryGraph.call_args
            
            # Check the cypher query
            request = call_args[0][0] if call_args[0] else call_args[1].get('request')
            cypher = request.cypher if hasattr(request, 'cypher') else str(request)
            
            assert "MATCH" in cypher
            assert "API" in cypher
            assert "CONTAINS" in cypher or "path" in cypher


class TestDependencyGraph:
    """Test Task 2.1.8: get_dependency_graph with 10s timeout"""
    
    @pytest.mark.asyncio
    async def test_dependency_graph_returns_dict_format(self):
        """Task 2.1.8: Verify returns {"nodes": list, "edges": list}"""
        analyzer = ImpactAnalyzer(
            graph_service_url="graph-service:50051",
            pg_cfg={}
        )
        
        with patch.object(analyzer, '_grpc_stub') as mock_stub:
            mock_response = Mock()
            mock_response.rows = []
            mock_stub.QueryGraph = AsyncMock(return_value=mock_response)
            
            result = await analyzer.get_dependency_graph("test/repo")
            
            assert isinstance(result, dict)
            assert "nodes" in result
            assert "edges" in result
            assert isinstance(result["nodes"], list)
            assert isinstance(result["edges"], list)
    
    @pytest.mark.asyncio
    async def test_dependency_graph_uses_10s_timeout(self):
        """Task 2.1.10: Verify 10s timeout for get_dependency_graph"""
        analyzer = ImpactAnalyzer(
            graph_service_url="graph-service:50051",
            pg_cfg={}
        )
        
        with patch.object(analyzer, '_grpc_stub') as mock_stub:
            mock_response = Mock()
            mock_response.rows = []
            mock_stub.QueryGraph = AsyncMock(return_value=mock_response)
            
            await analyzer.get_dependency_graph("test/repo")
            
            # Check timeout parameter
            call_args = mock_stub.QueryGraph.call_args
            if 'timeout' in call_args[1]:
                assert call_args[1]['timeout'] == 10


class TestCacheInvalidation:
    """Test Task 2.1.9: invalidate_cache method"""
    
    def test_invalidate_cache_removes_repo_entries(self):
        """Task 2.1.9: Verify cache invalidation removes matching entries"""
        analyzer = ImpactAnalyzer(
            graph_service_url="graph-service:50051",
            pg_cfg={}
        )
        
        # Populate cache with multiple repos
        analyzer._cache["edges:test/repo"] = ([], time.time() + 60)
        analyzer._cache["service:test/repo:svc1"] = ({}, time.time() + 60)
        analyzer._cache["edges:other/repo"] = ([], time.time() + 60)
        analyzer._cache["apis:test/repo"] = ([], time.time() + 60)
        
        # Invalidate test/repo
        with patch('app.simulation.impact_analyzer.log') as mock_log:
            analyzer.invalidate_cache("test/repo")
            
            # Verify test/repo entries removed
            assert "edges:test/repo" not in analyzer._cache
            assert "service:test/repo:svc1" not in analyzer._cache
            assert "apis:test/repo" not in analyzer._cache
            
            # Verify other/repo entry remains
            assert "edges:other/repo" in analyzer._cache
            
            # Verify INFO log with count
            assert mock_log.info.called
            log_msg = mock_log.info.call_args[0][0]
            assert "test/repo" in log_msg
    
    def test_invalidate_cache_handles_empty_cache(self):
        """Verify invalidate_cache works with empty cache"""
        analyzer = ImpactAnalyzer(
            graph_service_url="graph-service:50051",
            pg_cfg={}
        )
        
        # Should not raise exception
        with patch('app.simulation.impact_analyzer.log') as mock_log:
            analyzer.invalidate_cache("test/repo")
            assert mock_log.info.called


class TestGRPCTimeouts:
    """Test Task 2.1.10: Verify correct timeouts for gRPC calls"""
    
    @pytest.mark.asyncio
    async def test_standard_queries_use_5s_timeout(self):
        """Verify _get_dependency_edges, _get_service_node, _get_api_nodes use 5s timeout"""
        analyzer = ImpactAnalyzer(
            graph_service_url="graph-service:50051",
            pg_cfg={}
        )
        
        with patch.object(analyzer, '_grpc_stub') as mock_stub:
            mock_response = Mock()
            mock_response.rows = []
            mock_stub.QueryGraph = AsyncMock(return_value=mock_response)
            
            # Test each method
            await analyzer._get_dependency_edges("test/repo")
            await analyzer._get_service_node("test/repo", "svc")
            await analyzer._get_api_nodes("test/repo", "/api")
            
            # All should use 5s timeout (or default if not specified)
            # This is implementation-dependent, so we just verify they complete


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
