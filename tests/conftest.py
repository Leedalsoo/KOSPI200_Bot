import os
import sys

# 프로젝트 루트 및 legacy_archive 경로를 sys.path에 등록하여 테스트 호환성 보장
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_legacy_dir = os.path.join(_root, "legacy_archive")

if _root not in sys.path:
    sys.path.insert(0, _root)

if os.path.exists(_legacy_dir) and _legacy_dir not in sys.path:
    sys.path.insert(0, _legacy_dir)
