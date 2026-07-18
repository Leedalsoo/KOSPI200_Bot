Write-Output "🔍 1. 문법 및 안티패턴 검사 (Ruff)..."
ruff check .
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Output "🔍 2. 엄격한 타입 검사 (Mypy)..."
mypy . --strict --disallow-untyped-defs
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Output "🔍 3. 헌법 위반 하드 스캔..."
# Python 파일 중에서 import json, import ujson이 들어있는지 검색
$forbidden = Get-ChildItem -Path "KOSPI200_Bot" -Filter "*.py" -Recurse | Select-String -Pattern "import json", "import ujson"
if ($forbidden) {
    foreach ($match in $forbidden) {
        Write-Warning "❌ 싸구려 json 모듈 발견! orjson을 사용하라!"
        Write-Warning "위치: $($match.Path) (줄 $($match.LineNumber)): $($match.Line.Trim())"
    }
    exit 1
}

Write-Output "🔍 4. Pytest (로직 검증: tests/unit/)..."
$env:CHAOS_MODE="1"
pytest tests/unit/ -v
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Output "✅ 로컬 단두대 통과! GitHub Push 자격 획득."
