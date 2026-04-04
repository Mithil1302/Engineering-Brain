#!/bin/bash
# Test runner for Task 1 - GitHub Repository Ingestion Pipeline

echo "Running Task 1 Tests..."
echo "======================="

# Run crawler tests
echo -e "\n1. Testing GitHubRepoCrawler (Task 1.1)..."
python -m pytest tests/test_ingestion_crawler.py -v

# Run chunker tests
echo -e "\n2. Testing CodeChunker (Task 1.2)..."
python -m pytest tests/test_ingestion_chunker.py -v

# Run environment validation tests
echo -e "\n3. Testing Environment Configuration (Task 1.8)..."
python -m pytest tests/test_ingestion_env_validation.py -v

echo -e "\n======================="
echo "Task 1 Tests Complete!"
