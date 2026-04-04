# Task 2 Quick Test Guide

## Quick Test Commands

### Run All Task 2 Tests
```bash
cd worker-service
python -m pytest tests/test_task2_*.py -v
```

### Run Individual Test Files
```bash
# Impact Analyzer tests
python -m pytest tests/test_task2_impact_analyzer.py -v

# Pipeline integration tests
python -m pytest tests/test_task2_pipeline_integration.py -v

# Environment config tests
python -m pytest tests/test_task2_environment_config.py -v
```

### Run Specific Test Class
```bash
python -m pytest tests/test_task2_impact_analyzer.py::TestCacheImplementation -v
```

## What Task 2 Tests Cover

### ✅ Task 2.1: Impact Analyzer Neo4j Integration
- Constructor with `graph_service_url` and `pg_cfg`
- gRPC channel and stub initialization
- 60-second TTL cache
- `_get_dependency_edges()` with Cypher query
- PostgreSQL fallback on gRPC failure
- `_get_service_node()` with cache
- `_get_api_nodes()` with path search
- `get_dependency_graph()` with 10s timeout
- `invalidate_cache()` for repo-specific clearing
- WARNING logging on fallback

### ✅ Task 2.2: Pipeline Cache Invalidation
- `_handle_ingestion_complete()` method
- Cache invalidation called with correct repo
- Kafka consumer for `repo.ingestion.complete`
- Error handling and resilience

### ✅ Task 2.3: Environment Configuration
- `GRAPH_SERVICE_URL` default: "graph-service:50051"
- Impact Analyzer instantiation
- GraphPopulator instantiation
- Consistent URL usage

## Test Files

1. **test_task2_impact_analyzer.py** - 20+ tests for Impact Analyzer
2. **test_task2_pipeline_integration.py** - 15+ tests for pipeline integration
3. **test_task2_environment_config.py** - 18+ tests for configuration

## Expected Output

```
tests/test_task2_impact_analyzer.py::TestImpactAnalyzerInitialization::test_constructor_accepts_required_parameters PASSED
tests/test_task2_impact_analyzer.py::TestImpactAnalyzerInitialization::test_grpc_channel_initialized PASSED
tests/test_task2_impact_analyzer.py::TestImpactAnalyzerInitialization::test_cache_initialized PASSED
...
======================== XX passed in X.XXs ========================
```

## Troubleshooting

### Import Errors
If you see `ModuleNotFoundError`, the tests handle path setup automatically. Make sure you're running from the `worker-service` directory.

### Missing Dependencies
```bash
pip install pytest pytest-asyncio grpcio
```

## Task 2 Status

✅ Task 2.1 - Impact Analyzer Neo4j integration  
✅ Task 2.2 - Cache invalidation wiring  
✅ Task 2.3 - Environment configuration  

All implementation complete and tested!
