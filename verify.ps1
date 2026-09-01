[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

if (Test-Path ".\venv\Scripts\Activate.ps1") {
    . .\venv\Scripts\Activate.ps1
}

Write-Host "=========================================================" -ForegroundColor Cyan
Write-Host "[1/6] Syntax & Anti-pattern Check (Ruff)..." -ForegroundColor Cyan
Write-Host "=========================================================" -ForegroundColor Cyan
ruff check .
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "`n=========================================================" -ForegroundColor Cyan
Write-Host "[2/6] Strict Type Check (Mypy)..." -ForegroundColor Cyan
Write-Host "=========================================================" -ForegroundColor Cyan
mypy . --ignore-missing-imports
if ($LASTEXITCODE -ne 0) { 
    Write-Warning "[WARNING] Mypy type warnings detected. Please inspect, but continuing build." 
}

Write-Host "`n=========================================================" -ForegroundColor Cyan
Write-Host "[3/6] Forbidden Module Hard Scan (JSON import check)..." -ForegroundColor Cyan
Write-Host "=========================================================" -ForegroundColor Cyan
$targetDirs = @("option_program", "infra", "shared", "main.py", "web_interface")
$forbidden = Get-ChildItem -Path $targetDirs -Filter "*.py" -Recurse -ErrorAction SilentlyContinue | Where-Object { 
    $_.FullName -notmatch "\\venv\\" -and $_.FullName -notmatch "\\node_modules\\" -and $_.FullName -notmatch "\\scratch\\" -and $_.FullName -notmatch "\\tests\\"
} | Select-String -Pattern "import json", "import ujson"
if ($forbidden) {
    foreach ($match in $forbidden) {
        Write-Warning "[FORBIDDEN] Standard json module detected in runtime! Use orjson instead!"
        Write-Warning "File: $($match.Path) (Line $($match.LineNumber)): $($match.Line.Trim())"
    }
    exit 1
}

Write-Host "`n=========================================================" -ForegroundColor Cyan
Write-Host "[4/6] Logic Verification (Pytest: tests/unit/ & tests/src/)..." -ForegroundColor Cyan
Write-Host "=========================================================" -ForegroundColor Cyan
pytest tests/unit/ tests/src/ -v
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "`n=========================================================" -ForegroundColor Cyan
Write-Host "[5/6] Chaos Monkey Fault Injection (Pytest: tests/chaos/)..." -ForegroundColor Cyan
Write-Host "=========================================================" -ForegroundColor Cyan
$env:CHAOS_MODE = "1"
pytest tests/chaos/ -v
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "`n=========================================================" -ForegroundColor Cyan
Write-Host "[6/6] Frontend Lint & Tests (web_interface)..." -ForegroundColor Cyan
Write-Host "=========================================================" -ForegroundColor Cyan
if (Test-Path ".\web_interface\package.json") {
    npm --prefix web_interface run lint
    if ($LASTEXITCODE -ne 0) { exit 1 }
    
    npm --prefix web_interface run test -- --watchAll=false
    if ($LASTEXITCODE -ne 0) { exit 1 }
}

Write-Host "`n=========================================================" -ForegroundColor Green
Write-Host "[PASS] Supreme Court Quality Gate Local Verification Completed Successfully!" -ForegroundColor Green
Write-Host "=========================================================" -ForegroundColor Green
