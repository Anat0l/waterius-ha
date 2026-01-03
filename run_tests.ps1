# PowerShell script to run Waterius integration tests
# Usage: .\run_tests.ps1

Write-Host "🧪 Running Waterius Integration Tests" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""

# Check if pytest is installed
try {
    python -m pytest --version | Out-Null
    Write-Host "✓ pytest found" -ForegroundColor Green
} catch {
    Write-Host "✗ pytest not found. Installing test dependencies..." -ForegroundColor Yellow
    python -m pip install -r requirements-test.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "✗ Failed to install test dependencies" -ForegroundColor Red
        exit 1
    }
    Write-Host "✓ Test dependencies installed" -ForegroundColor Green
}

Write-Host ""
Write-Host "Running tests..." -ForegroundColor Cyan
Write-Host ""

# Run pytest with coverage
python -m pytest tests/ `
    -v `
    --tb=short `
    --cov=custom_components.waterius_ha `
    --cov-report=term-missing `
    --cov-report=html `
    --cov-branch

$exitCode = $LASTEXITCODE

Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "✓ All tests passed!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Coverage report saved to: htmlcov/index.html" -ForegroundColor Cyan
} else {
    Write-Host "✗ Some tests failed" -ForegroundColor Red
}

exit $exitCode
