#!/bin/bash
# Quick test runner for Task 1 from project root

echo "🧪 Task 1 Test Suite"
echo "===================="
echo ""

# Check if we're in the right directory
if [ ! -d "worker-service" ]; then
    echo "❌ Error: Must run from project root directory"
    exit 1
fi

# Install dependencies
echo "📦 Installing test dependencies..."
cd worker-service
pip install -q -r requirements.txt

if [ $? -ne 0 ]; then
    echo "❌ Failed to install dependencies"
    exit 1
fi

echo "✅ Dependencies installed"
echo ""

# Run the tests
echo "🚀 Running Task 1 tests..."
echo ""
python run_tests.py

exit $?
