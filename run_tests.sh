#!/bin/bash
# Shell script to run Waterius integration tests
# Usage: ./run_tests.sh

set -e

echo "🧪 Running Waterius Integration Tests"
echo "====================================="
echo ""

# Check if pytest is installed
if ! python -m pytest --version &> /dev/null; then
    echo "✗ pytest not found. Installing test dependencies..."
    python -m pip install -r requirements-test.txt
    echo "✓ Test dependencies installed"
else
    echo "✓ pytest found"
fi

echo ""
echo "Running tests..."
echo ""

# Run pytest with coverage
python -m pytest tests/ \
    -v \
    --tb=short \
    --cov=custom_components.waterius_ha \
    --cov-report=term-missing \
    --cov-report=html \
    --cov-branch

echo ""
echo "✓ All tests passed!"
echo ""
echo "Coverage report saved to: htmlcov/index.html"
