import pytest
import os
import sys

# 프로젝트 루트 및 legacy_archive 경로를 sys.path에 등록하여 테스트 호환성 보장
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_legacy_dir = os.path.join(_root, "legacy_archive")

if _root not in sys.path:
    sys.path.insert(0, _root)

if os.path.exists(_legacy_dir) and _legacy_dir not in sys.path:
    sys.path.insert(0, _legacy_dir)

@pytest.fixture(autouse=True)
def clean_default_wal():
    """테스트 간 기본 WAL 파일 격리 및 정리"""
    wal_path = os.path.join(_root, "data", "wal", "orders.wal")
    if os.path.exists(wal_path):
        try:
            os.remove(wal_path)
        except Exception:
            pass
    yield
    if os.path.exists(wal_path):
        try:
            os.remove(wal_path)
        except Exception:
            pass
