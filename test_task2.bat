@echo off
REM Task 2 Test Runner for Windows
REM Tests Neo4j Graph Service Integration for Impact Analyzer

echo ========================================
echo Task 2: Neo4j Graph Service Integration
echo ========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    exit /b 1
)

REM Check if pytest is installed
python -m pytest --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: pytest is not installed
    echo Installing pytest...
    python -m pip install pytest pytest-asyncio
)

echo Running Task 2 Tests...
echo.

REM Set PYTHONPATH to include worker-service
set PYTHONPATH=%CD%\worker-service;%PYTHONPATH%

REM Run all Task 2 tests
echo ----------------------------------------
echo Test Suite 1: Impact Analyzer (Task 2.1)
echo ----------------------------------------
python -m pytest worker-service/tests/test_task2_impact_analyzer.py -v --tb=short

if errorlevel 1 (
    echo.
    echo FAILED: Impact Analyzer tests failed
    set TEST_FAILED=1
) else (
    echo.
    echo PASSED: Impact Analyzer tests
)

echo.
echo ----------------------------------------
echo Test Suite 2: Pipeline Integration (Task 2.2)
echo ----------------------------------------
python -m pytest worker-service/tests/test_task2_pipeline_integration.py -v --tb=short

if errorlevel 1 (
    echo.
    echo FAILED: Pipeline Integration tests failed
    set TEST_FAILED=1
) else (
    echo.
    echo PASSED: Pipeline Integration tests
)

echo.
echo ----------------------------------------
echo Test Suite 3: Environment Config (Task 2.3)
echo ----------------------------------------
python -m pytest worker-service/tests/test_task2_environment_config.py -v --tb=short

if errorlevel 1 (
    echo.
    echo FAILED: Environment Config tests failed
    set TEST_FAILED=1
) else (
    echo.
    echo PASSED: Environment Config tests
)

echo.
echo ========================================
echo Task 2 Test Summary
echo ========================================

if defined TEST_FAILED (
    echo.
    echo RESULT: Some tests FAILED
    echo Please review the output above for details
    exit /b 1
) else (
    echo.
    echo RESULT: All tests PASSED
    echo Task 2 implementation is verified
    exit /b 0
)
