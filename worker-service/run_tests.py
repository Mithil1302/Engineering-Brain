#!/usr/bin/env python3
"""
Test runner script for Task 1 components
"""
import sys
import subprocess
import os


def run_command(cmd, description):
    """Run a command and report results"""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"{'='*60}")
    
    result = subprocess.run(cmd, shell=True, capture_output=False)
    
    if result.returncode != 0:
        print(f"❌ FAILED: {description}")
        return False
    else:
        print(f"✅ PASSED: {description}")
        return True


def main():
    """Run all Task 1 tests"""
    print("Task 1 - GitHub Repository Ingestion Pipeline Tests")
    print("=" * 60)
    
    # Change to worker-service directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # Set PYTHONPATH
    os.environ['PYTHONPATH'] = os.getcwd()
    
    results = []
    
    # Test 1: Environment Validation
    results.append(run_command(
        "python -m pytest tests/test_ingestion_env_validation.py -v",
        "Environment Validation Tests (Task 1.8)"
    ))
    
    # Test 2: GitHubRepoCrawler
    results.append(run_command(
        "python -m pytest tests/test_ingestion_crawler.py -v",
        "GitHubRepoCrawler Tests (Task 1.1)"
    ))
    
    # Test 3: CodeChunker
    results.append(run_command(
        "python -m pytest tests/test_ingestion_chunker.py -v",
        "CodeChunker Tests (Task 1.2)"
    ))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    total = len(results)
    passed = sum(results)
    failed = total - passed
    
    print(f"Total Test Suites: {total}")
    print(f"Passed: {passed} ✅")
    print(f"Failed: {failed} ❌")
    
    if failed == 0:
        print("\n🎉 All Task 1 tests passed!")
        return 0
    else:
        print(f"\n⚠️  {failed} test suite(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
