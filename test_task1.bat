@echo off
REM Quick test runner for Task 1 from project root (Windows)

echo 🧪 Task 1 Test Suite
echo ====================
echo.

REM Check if we're in the right directory
if not exist "worker-service" (
    echo ❌ Error: Must run from project root directory
    exit /b 1
)

REM Install dependencies
echo 📦 Installing test dependencies...
cd worker-service
pip install -q -r requirements.txt

if %ERRORLEVEL% neq 0 (
    echo ❌ Failed to install dependencies
    exit /b 1
)

echo ✅ Dependencies installed
echo.

REM Run the tests
echo 🚀 Running Task 1 tests...
echo.
python run_tests.py

exit /b %ERRORLEVEL%
