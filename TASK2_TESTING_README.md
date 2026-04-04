# Task 2 Testing Guide

## Overview

This guide covers testing for **Task 2: Neo4j Graph Service Integration for Impact Analyzer**.

Task 2 integrates the Impact Analyzer with Neo4j via gRPC, implements caching with PostgreSQL fallback, and wires cache invalidation into the policy pipeline.

## What Was Implemented

### Task 2.1: Update Impact Analyzer with Real Neo4j Queries
- Added `graph_service_url` and `pg_cfg` constructor parameters
- Initialized gRPC channel and stub for Graph Service communication
- Implemented 60-second TTL cache for query results
- Implemented `_get_dependency_edges()` with Neo4j Cypher query and PostgreSQL fallback
- Implemented `_get_service_node()` with cache and fallback
- Implemented `_get_api_nodes()` with path fragment search
- Implemented `get_dependency_graph()` with 10-second timeout
- Implemented `invalidate_cache()` for repo-specific cache clearing
- All gRPC calls use 5s timeout except `get_dependency_graph()` (10s)
- All fallbacks log WARNING with error details

**Files Modified:**
- `worker-service/app/simulation/impact_analyzer.py`

### Task 2.2: Wire Cache Invalidation
- Added `_handle_ingestion_complete()` method to PolicyPipeline
- Integrated with Kafka consumer for `repo.ingestion.complete` topic
- Calls `impact_analyzer.invalidate_cache(repo)` on ingestion completion

**Files Modified:**
- `worker-service/app/policy/pipeline.py`

### Task 2.3: Environment Configuration
- `GRAPH_SERVICE_URL` environment variable with default `"graph-service:50051"`
- Impact Analyzer instantiated with `graph_service_url` parameter
- GraphPopulator also uses the same environment variable

**Files Modified:**
- `worker-service/app/dependencies.py` (already had the configuration)

## Test Files

### 1. `test_task2_impact_analyzer.py`
Tests the Impact Analyzer implementation:

**Test Classes:**
- `TestImpactAnalyzerInitialization` - Constructor and gRPC setup
- `TestCacheImplementation` - 60-second TTL cache behavior
- `TestDependencyEdgesQuery` - Neo4j queries and PostgreSQL fallback
- `TestServiceNodeQuery` - Service node lookup with cache
- `TestAPINodesQuery` - API node search with path fragments
- `TestDependencyGraph` - Full graph query with 10s timeout
- `TestCacheInvalidation` - Cache clearing by repo
- `TestGRPCTimeouts` - Timeout verification

**Key Test Cases:**
- ✅ Constructor accepts `graph_service_url` and `pg_cfg`
- ✅ gRPC channel and stub initialized
- ✅ Cache stores (data, expiry) tuples with 60s TTL
- ✅ Cache hit skips gRPC call
- ✅ Expired cache triggers refresh
- ✅ Cypher queries formatted correctly
- ✅ Response transformed to tuple format
- ✅ PostgreSQL fallback on gRPC failure
- ✅ Fallback logs WARNING with error details
- ✅ Cache invalidation removes repo entries
- ✅ 5s timeout for standard queries, 10s for dependency graph

### 2. `test_task2_pipeline_integration.py`
Tests the policy pipeline integration:

**Test Classes:**
- `TestIngestionCompleteHandler` - Handler method existence
- `TestCacheInvalidationCall` - Cache invalidation wiring
- `TestKafkaConsumerRegistration` - Kafka consumer setup
- `TestHandlerErrorHandling` - Error resilience
- `TestIntegrationWithTimeTravel` - Preparation for Task 3
- `TestPayloadValidation` - Kafka payload handling

**Key Test Cases:**
- ✅ `_handle_ingestion_complete()` method exists
- ✅ Handler accepts Kafka payload
- ✅ `invalidate_cache()` called with correct repo
- ✅ Works for multiple repos
- ✅ Handles missing repo field gracefully
- ✅ Kafka consumer registered for `repo.ingestion.complete`
- ✅ Handler logs errors without crashing
- ✅ Accepts full and minimal payloads

### 3. `test_task2_environment_config.py`
Tests environment configuration:

**Test Classes:**
- `TestGraphServiceURLEnvironmentVariable` - Environment variable behavior
- `TestImpactAnalyzerInstantiation` - Impact Analyzer setup
- `TestGraphPopulatorInstantiation` - GraphPopulator setup
- `TestConsistentURLUsage` - Consistent configuration
- `TestTimeTravelSystemPreparation` - Task 3 preparation
- `TestConfigurationDocumentation` - Spec compliance
- `TestBackwardCompatibility` - Existing code preserved
- `TestErrorHandling` - Invalid configuration handling

**Key Test Cases:**
- ✅ Default value is `"graph-service:50051"`
- ✅ Can be overridden via environment
- ✅ Impact Analyzer uses `GRAPH_SERVICE_URL`
- ✅ GraphPopulator uses `GRAPH_SERVICE_URL`
- ✅ Both components use same URL source
- ✅ URL format validation (host:port)
- ✅ Backward compatibility maintained

## Running the Tests

### Quick Start (Windows)
```bash
test_task2.bat
```

### Manual Execution

#### Run All Task 2 Tests
```bash
cd worker-service
python -m pytest tests/test_task2_*.py -v
```

#### Run Specific Test Suite
```bash
# Impact Analyzer tests
python -m pytest tests/test_task2_impact_analyzer.py -v

# Pipeline integration tests
python -m pytest tests/test_task2_pipeline_integration.py -v

# Environment config tests
python -m pytest tests/test_task2_environment_config.py -v
```

#### Run Specific Test Class
```bash
python -m pytest tests/test_task2_impact_analyzer.py::TestCacheImplementation -v
```

#### Run Specific Test
```bash
python -m pytest tests/test_task2_impact_analyzer.py::TestCacheImplementation::test_cache_stores_data_with_expiry -v
```

### With Coverage
```bash
python -m pytest tests/test_task2_*.py --cov=app.simulation.impact_analyzer --cov=app.policy.pipeline --cov-report=html
```

## Prerequisites

### Required Python Packages
```bash
pip install pytest pytest-asyncio pytest-mock pytest-cov
```

### Required for Full Integration Tests
- PostgreSQL with `meta.graph_nodes` table
- Neo4j or mock gRPC service
- Kafka (for pipeline integration tests)

## Test Environment Setup

### Minimal Setup (Unit Tests Only)
```bash
# Set PYTHONPATH
set PYTHONPATH=%CD%\worker-service

# Run tests with mocks
python -m pytest tests/test_task2_*.py -v
```

### Full Integration Setup
```bash
# Set environment variables
set GRAPH_SERVICE_URL=localhost:50051
set POSTGRES_HOST=localhost
set POSTGRES_PORT=5432
set POSTGRES_USER=brain
set POSTGRES_PASSWORD=brain
set POSTGRES_DB=brain

# Run tests
python -m pytest tests/test_task2_*.py -v --integration
```

## Expected Results

### All Tests Passing
```
test_task2_impact_analyzer.py::TestImpactAnalyzerInitialization::test_constructor_accepts_required_parameters PASSED
test_task2_impact_analyzer.py::TestImpactAnalyzerInitialization::test_grpc_channel_initialized PASSED
test_task2_impact_analyzer.py::TestImpactAnalyzerInitialization::test_cache_initialized PASSED
test_task2_impact_analyzer.py::TestCacheImplementation::test_cache_stores_data_with_expiry PASSED
test_task2_impact_analyzer.py::TestCacheImplementation::test_cache_hit_skips_grpc_call PASSED
test_task2_impact_analyzer.py::TestCacheImplementation::test_expired_cache_triggers_refresh PASSED
...

test_task2_pipeline_integration.py::TestIngestionCompleteHandler::test_handler_method_exists PASSED
test_task2_pipeline_integration.py::TestCacheInvalidationCall::test_invalidate_cache_called_with_repo PASSED
...

test_task2_environment_config.py::TestGraphServiceURLEnvironmentVariable::test_default_graph_service_url PASSED
test_task2_environment_config.py::TestGraphServiceURLEnvironmentVariable::test_custom_graph_service_url PASSED
...

======================== XX passed in X.XXs ========================
```

## Troubleshooting

### Import Errors
```
ModuleNotFoundError: No module named 'worker_service'
```
**Solution:** Set PYTHONPATH correctly
```bash
set PYTHONPATH=%CD%\worker-service
```

### gRPC Import Errors
```
ModuleNotFoundError: No module named 'grpc'
```
**Solution:** Install gRPC
```bash
pip install grpcio grpcio-tools
```

### Async Test Errors
```
RuntimeError: no running event loop
```
**Solution:** Install pytest-asyncio
```bash
pip install pytest-asyncio
```

### Mock Errors
```
AttributeError: Mock object has no attribute 'QueryGraph'
```
**Solution:** Check mock setup in test - ensure proper patching

## Test Coverage Goals

- **Impact Analyzer**: 90%+ coverage
  - All public methods tested
  - Cache behavior verified
  - Fallback logic tested
  - Error handling validated

- **Pipeline Integration**: 85%+ coverage
  - Handler registration verified
  - Cache invalidation wired correctly
  - Error resilience tested

- **Environment Config**: 95%+ coverage
  - Default values verified
  - Override behavior tested
  - Consistency validated

## Integration with CI/CD

### GitHub Actions Example
```yaml
- name: Run Task 2 Tests
  run: |
    cd worker-service
    python -m pytest tests/test_task2_*.py -v --junitxml=task2-results.xml
  
- name: Upload Test Results
  uses: actions/upload-artifact@v3
  with:
    name: task2-test-results
    path: worker-service/task2-results.xml
```

## Next Steps

After Task 2 tests pass:
1. ✅ Task 2.1: Impact Analyzer Neo4j integration complete
2. ✅ Task 2.2: Cache invalidation wired to pipeline
3. ✅ Task 2.3: Environment configuration verified
4. ➡️ **Task 3**: Temporal Graph Data Population (uses same `GRAPH_SERVICE_URL`)

## Related Documentation

- [Task 1 Testing Guide](TASK1_TESTING_README.md)
- [Requirements Document](.kiro/specs/ka-chow-production-completion/requirements.md)
- [Design Document](.kiro/specs/ka-chow-production-completion/design.md)
- [Tasks Document](.kiro/specs/ka-chow-production-completion/tasks.md)

## Support

For issues or questions:
1. Check test output for specific error messages
2. Review the implementation files
3. Verify environment variables are set correctly
4. Check that all dependencies are installed
