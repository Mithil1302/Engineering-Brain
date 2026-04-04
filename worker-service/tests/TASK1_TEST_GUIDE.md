# Task 1 Testing Guide

This guide explains how to test all components of Task 1: GitHub Repository Ingestion Pipeline.

## Prerequisites

1. Install test dependencies:
```bash
cd worker-service
pip install -r requirements.txt
```

2. Set up test environment variables (optional for unit tests):
```bash
export GITHUB_APP_ID="test_app_id"
export GITHUB_APP_PRIVATE_KEY="test_private_key"
export GITHUB_INSTALLATION_ID="test_installation_id"
```

## Running Tests

### Run All Task 1 Tests
```bash
cd worker-service
chmod +x tests/run_task1_tests.sh
./tests/run_task1_tests.sh
```

### Run Individual Test Suites

#### 1. GitHubRepoCrawler Tests (Task 1.1)
```bash
python -m pytest tests/test_ingestion_crawler.py -v
```

Tests covered:
- Extension whitelist validation
- Path blacklist validation
- File inclusion/exclusion logic
- JWT creation
- Installation token caching
- Rate limit handling
- File content fetching
- Exponential backoff on 429 errors
- Full repository crawl
- Incremental crawl with changed files

#### 2. CodeChunker Tests (Task 1.2)
```bash
python -m pytest tests/test_ingestion_chunker.py -v
```

Tests covered:
- Chunk ID computation (SHA-256 consistency)
- Python AST extraction (functions, classes)
- Python syntax error fallback
- TypeScript/JavaScript declaration extraction
- Go function and type extraction
- Markdown section splitting
- OpenAPI spec extraction from YAML
- Kubernetes manifest extraction
- Protocol Buffer service extraction
- SQL statement extraction
- Terraform resource extraction
- Sliding window chunking
- Large chunk subdivision
- Repo and chunk_id assignment

#### 3. Environment Validation Tests (Task 1.8)
```bash
python -m pytest tests/test_ingestion_env_validation.py -v
```

Tests covered:
- All required variables present
- Missing GITHUB_APP_ID detection
- Missing GITHUB_APP_PRIVATE_KEY detection
- Missing GITHUB_INSTALLATION_ID detection
- Multiple missing variables collection
- Empty string handling
- Optional variables with defaults
- Environment variable usage in dependencies

### Run Specific Test
```bash
python -m pytest tests/test_ingestion_crawler.py::TestGitHubRepoCrawler::test_extension_whitelist -v
```

### Run with Coverage
```bash
pip install pytest-cov
python -m pytest tests/test_ingestion_*.py --cov=worker_service.app.ingestion --cov-report=html
```

## Test Structure

### test_ingestion_crawler.py
- **Purpose**: Tests GitHubRepoCrawler component
- **Fixtures**: `mock_private_key`, `crawler`
- **Test Classes**: `TestGitHubRepoCrawler`
- **Key Tests**:
  - File filtering logic
  - GitHub API authentication
  - Rate limiting
  - Error handling
  - Full vs incremental crawl

### test_ingestion_chunker.py
- **Purpose**: Tests CodeChunker component
- **Fixtures**: `chunker`
- **Test Classes**: `TestCodeChunker`
- **Key Tests**:
  - Language-specific extraction
  - Fallback mechanisms
  - Chunk subdivision
  - Metadata extraction

### test_ingestion_env_validation.py
- **Purpose**: Tests environment variable validation
- **Test Classes**: `TestEnvironmentValidation`, `TestEnvironmentVariableUsage`
- **Key Tests**:
  - Required variable validation
  - Startup failure on missing vars
  - Default value handling

## Manual Testing

### 1. Test Environment Validation

Start the worker-service without required env vars:
```bash
cd worker-service
python -m worker_service.app.main
```

Expected: Application should exit with code 1 and log CRITICAL message listing missing variables.

### 2. Test with Valid Environment

Set all required variables:
```bash
export GITHUB_APP_ID="your_app_id"
export GITHUB_APP_PRIVATE_KEY="$(cat your_private_key.pem)"
export GITHUB_INSTALLATION_ID="your_installation_id"
python -m worker_service.app.main
```

Expected: Application should start successfully.

### 3. Test Ingestion API Endpoints

Once the service is running:

```bash
# Trigger full ingestion
curl -X POST http://localhost:8000/ingestion/trigger \
  -H "Content-Type: application/json" \
  -d '{"repo": "owner/repo"}'

# Check ingestion status
curl http://localhost:8000/ingestion/status/owner/repo

# List recent ingestion runs
curl http://localhost:8000/ingestion/runs/owner/repo
```

## Expected Test Results

All tests should pass with the following coverage:

- **test_ingestion_crawler.py**: 15+ tests
- **test_ingestion_chunker.py**: 20+ tests
- **test_ingestion_env_validation.py**: 8+ tests

Total: 43+ test cases covering Task 1 implementation.

## Troubleshooting

### Import Errors
If you see `ModuleNotFoundError: No module named 'worker_service'`:
```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

### Async Test Warnings
If you see warnings about async tests, ensure pytest-asyncio is installed:
```bash
pip install pytest-asyncio==0.23.0
```

### Mock Errors
If mocks aren't working, ensure you're using the correct import paths:
- Use `worker_service.app.ingestion.crawler` not `app.ingestion.crawler`

## Integration Testing

For full integration testing with real GitHub API:

1. Set up a test GitHub App
2. Configure real credentials in `.env`
3. Run integration tests:
```bash
python -m pytest tests/test_ingestion_integration.py -v --integration
```

Note: Integration tests are not included in the standard test suite to avoid API rate limits.

## CI/CD Integration

Add to your CI pipeline:
```yaml
- name: Run Task 1 Tests
  run: |
    cd worker-service
    pip install -r requirements.txt
    python -m pytest tests/test_ingestion_*.py -v --junitxml=test-results.xml
```

## Test Coverage Goals

- **GitHubRepoCrawler**: 85%+ coverage
- **CodeChunker**: 90%+ coverage
- **Environment Validation**: 100% coverage

Run coverage report:
```bash
python -m pytest tests/test_ingestion_*.py --cov=worker_service.app.ingestion --cov-report=term-missing
```
