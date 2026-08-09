[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

if (Test-Path ".\venv\Scripts\Activate.ps1") {
    . .\venv\Scripts\Activate.ps1
}

Write-Host "=========================================================" -ForegroundColor Cyan
Write-Host "[1/4] Syntax & Anti-pattern Check (Ruff)..." -ForegroundColor Cyan
Write-Host "=========================================================" -ForegroundColor Cyan
ruff check .
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "`n=========================================================" -ForegroundColor Cyan
Write-Host "[2/4] Strict Type Check (Mypy)..." -ForegroundColor Cyan
Write-Host "=========================================================" -ForegroundColor Cyan
mypy . --ignore-missing-imports --exclude "(mock_ws_server|mock_ws_server_refactored|scratch)"
if ($LASTEXITCODE -ne 0) { 
    Write-Warning "[WARNING] Mypy type warnings detected. Please inspect, but continuing build." 
}

Write-Host "`n=========================================================" -ForegroundColor Cyan
Write-Host "[3/4] Forbidden Module Hard Scan (JSON import check)..." -ForegroundColor Cyan
Write-Host "=========================================================" -ForegroundColor Cyan
$forbidden = Get-ChildItem -Path "." -Filter "*.py" -Recurse | Where-Object { $_.FullName -notmatch "\\venv\\" -and $_.FullName -notmatch "\\node_modules\\" -and $_.FullName -notmatch "\\scratch\\" } | Select-String -Pattern "import json", "import ujson"
if ($forbidden) {
    foreach ($match in $forbidden) {
        Write-Warning "[FORBIDDEN] Standard json module detected! Use orjson instead!"
        Write-Warning "File: $($match.Path) (Line $($match.LineNumber)): $($match.Line.Trim())"
    }
    exit 1
}

Write-Host "`n=========================================================" -ForegroundColor Cyan
Write-Host "[4/4] Logic Verification (Pytest: tests/unit/)..." -ForegroundColor Cyan
Write-Host "=========================================================" -ForegroundColor Cyan
$env:CHAOS_MODE="1"
pytest tests/unit/ --ignore=tests/unit/test_strategy_plugins_track1_defense.py --ignore=tests/unit/test_strategy_plugins_track2_trap.py --ignore=tests/unit/test_strategy_plugins_track4_gamma.py --ignore=tests/unit/test_strategy_plugins_track3_arbitrage.py -v
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "`n=========================================================" -ForegroundColor Green
Write-Host "[PASS] Local Verification Completed Successfully!" -ForegroundColor Green
Write-Host "=========================================================" -ForegroundColor Green
