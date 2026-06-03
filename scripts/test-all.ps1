<#
.SYNOPSIS
    Run all project tests on Windows: Python (pytest).
.EXAMPLE
    .\scripts\test-all.ps1
#>

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path "$PSScriptRoot\.."
$PASS = 0
$FAIL = 0

function Run-TestSuite {
    param([string]$Name, [scriptblock]$ScriptBlock)
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  $Name" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    try {
        & $ScriptBlock
        Write-Host "  PASS  $Name" -ForegroundColor Green
        $script:PASS++
    } catch {
        Write-Host "  FAIL  $Name — $($_.Exception.Message)" -ForegroundColor Red
        $script:FAIL++
    }
}

Run-TestSuite -Name "Python tests (pytest)" -ScriptBlock {
    Push-Location $ProjectRoot
    try {
        python -m pytest -v
        if ($LASTEXITCODE -ne 0) { throw "pytest exit code: $LASTEXITCODE" }
    } finally {
        Pop-Location
    }
}

Write-Host ""
Write-Host "==============================" -ForegroundColor Cyan
Write-Host "  Suites: $PASS passed, $FAIL failed" -ForegroundColor Cyan
Write-Host "==============================" -ForegroundColor Cyan

exit $(if ($FAIL -gt 0) { 1 } else { 0 })
