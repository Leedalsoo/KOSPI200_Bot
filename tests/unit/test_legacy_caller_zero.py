"""Unit test verifying zero legacy callers (caller=0) across codebase."""
import os
import glob
import pytest

def test_zero_legacy_direct_callers():
    """Target Architecture 이관 완수 - 레거시 모듈 직접 호출 0건 감지 검증"""
    legacy_forbidden_patterns = [
        "from trading_engine.broker_legacy",
        "import legacy_account_manager",
        "from legacy_orderbook"
    ]
    
    python_files = glob.glob("**/*.py", recursive=True)
    violations = []

    for filepath in python_files:
        if "venv" in filepath or "tests" in filepath or "scratch" in filepath:
            continue
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            for pattern in legacy_forbidden_patterns:
                if pattern in content:
                    violations.append((filepath, pattern))

    assert len(violations) == 0, f"Found legacy direct callers: {violations}"
