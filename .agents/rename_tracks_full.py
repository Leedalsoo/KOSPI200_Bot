#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Track1~Track9 완전 통일 2단계 스크립트
- 클래스명 변경, import 수정, 변수명 정리, 파일 rename
- 상태 변수(track3_entry_price 등)는 소문자 유지
"""
import re
import os
import shutil
from pathlib import Path

ROOT = Path(r"c:\Users\white\KOSPI200_Bot")

# ──────────────────────────────────────────────
# 1. 클래스명 매핑 (구 → 신)
# ──────────────────────────────────────────────
CLASS_MAP = {
    "DetailedProductionFenceEngine":  "Track1",
    "AdvancedDualSideDynamicStrangleStrategy": "Track1",  # 오류 상태 클래스도 동일하게
    "AsymmetricTrapStrategy":         "Track2",
    "Track2Trap":                     "Track2",
    "StatisticalArbitrageStrategy":   "Track3",
    "SmartGammaScalpingStrategy":     "Track4",
    "Track4Gamma":                    "Track4",
    "GapProtocolStrategy":            "Track5",
    "DailyTailInsuranceBot":          "Track6",
    "WeeklyTailInsuranceBot":         "Track7",
    "MonthlyWideStrangleStrategy":    "Track8",
    "OvernightInsuranceBot":          "Track9",
}

# ──────────────────────────────────────────────
# 2. 파일명 매핑 (구 → 신), strategy/plugins 기준
# ──────────────────────────────────────────────
FILE_MAP = {
    "track1_defense": "track1",
    "track2_trap":    "track2",
    "track3_arbitrage": "track3",
    "track4_gamma":   "track4",
    "track5_gap":     "track5",
    "track6_daily_insurance": "track6",
    "track7_weekly_insurance": "track7",
    "track8_monthly_strangle": "track8",
    "track9_overnight_insurance": "track9",
}

# ──────────────────────────────────────────────
# 3. 변수명 패턴 (trackN_strategy → trackN)
#    단, track3_entry_price 등 상태 변수는 제외
# ──────────────────────────────────────────────
VAR_REPLACEMENTS = [
    # 타입 어노테이션: Optional[OldClass]
    (r'Optional\[DetailedProductionFenceEngine\]',  'Optional[Track1]'),
    (r'Optional\[AsymmetricTrapStrategy\]',         'Optional[Track2]'),
    (r'Optional\[StatisticalArbitrageStrategy\]',   'Optional[Track3]'),
    (r'Optional\[SmartGammaScalpingStrategy\]',     'Optional[Track4]'),
    (r'Optional\[GapProtocolStrategy\]',            'Optional[Track5]'),
    (r'Optional\[DailyTailInsuranceBot\]',          'Optional[Track6]'),
    (r'Optional\[WeeklyTailInsuranceBot\]',         'Optional[Track7]'),
    (r'Optional\[MonthlyWideStrangleStrategy\]',    'Optional[Track8]'),
    (r'Optional\[OvernightInsuranceBot\]',          'Optional[Track9]'),
    # 변수명: trackN_strategy → trackN (상태 변수는 _strategy 접미사만 있음)
    (r'\btrack1_strategy\b', 'track1'),
    (r'\btrack2_strategy\b', 'track2'),
    (r'\btrack3_strategy\b', 'track3'),
    (r'\btrack4_strategy\b', 'track4'),
    (r'\btrack5_strategy\b', 'track5'),
    (r'\btrack6_strategy\b', 'track6'),
    (r'\btrack7_strategy\b', 'track7'),
    (r'\btrack8_strategy\b', 'track8'),
    (r'\btrack9_strategy\b', 'track9'),
]

# ──────────────────────────────────────────────
# strategy_docs.json key 매핑
# ──────────────────────────────────────────────
DOCS_KEY_MAP = {
    '"track1_defense.py"': '"track1.py"',
    '"track2_trap.py"':    '"track2.py"',
    '"track3_arbitrage.py"': '"track3.py"',
    '"track4_gamma.py"':   '"track4.py"',
    '"track5_gap.py"':     '"track5.py"',
    '"track6_daily_insurance.py"': '"track6.py"',
    '"track7_weekly_insurance.py"': '"track7.py"',
    '"track8_monthly_strangle.py"': '"track8.py"',
    '"track9_overnight_insurance.py"': '"track9.py"',
}

# ──────────────────────────────────────────────
# import 치환 패턴
# ──────────────────────────────────────────────
IMPORT_MAP = [
    ("from strategy.plugins.track1_defense import DetailedProductionFenceEngine",
     "from strategy.plugins.track1 import Track1"),
    ("from strategy.plugins.track1_defense import AdvancedDualSideDynamicStrangleStrategy",
     "from strategy.plugins.track1 import Track1"),
    ("from strategy.plugins.track2_trap import AsymmetricTrapStrategy",
     "from strategy.plugins.track2 import Track2"),
    ("from strategy.plugins.track3_arbitrage import StatisticalArbitrageStrategy",
     "from strategy.plugins.track3 import Track3"),
    ("from strategy.plugins.track4_gamma import SmartGammaScalpingStrategy",
     "from strategy.plugins.track4 import Track4"),
    ("from strategy.plugins.track5_gap import GapProtocolStrategy",
     "from strategy.plugins.track5 import Track5"),
    ("from strategy.plugins.track6_daily_insurance import DailyTailInsuranceBot",
     "from strategy.plugins.track6 import Track6"),
    ("from strategy.plugins.track7_weekly_insurance import WeeklyTailInsuranceBot",
     "from strategy.plugins.track7 import Track7"),
    ("from strategy.plugins.track8_monthly_strangle import MonthlyWideStrangleStrategy",
     "from strategy.plugins.track8 import Track8"),
    ("from strategy.plugins.track9_overnight_insurance import OvernightInsuranceBot",
     "from strategy.plugins.track9 import Track9"),
]

# alias 제거 패턴 (라인 자체를 제거)
ALIAS_LINES_TO_REMOVE = [
    "AsymmetricTrapStrategy = Track2Trap",
    "AsymmetricTrapStrategy = Track2",
    "SmartGammaScalpingStrategy = Track4Gamma",
    "SmartGammaScalpingStrategy = Track4",
]

def read_file(path: Path) -> str:
    for enc in ['utf-8', 'cp949']:
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, Exception):
            continue
    raise RuntimeError(f"인코딩 실패: {path}")

def write_file(path: Path, content: str):
    path.write_text(content, encoding='utf-8')

def apply_class_renames(content: str) -> tuple[str, int]:
    """클래스명을 전체 교체 (class 정의 + 사용 모두)"""
    n = 0
    for old, new in CLASS_MAP.items():
        if old in content:
            count = content.count(old)
            content = content.replace(old, new)
            n += count
    return content, n

def apply_var_replacements(content: str) -> tuple[str, int]:
    n = 0
    for pattern, replacement in VAR_REPLACEMENTS:
        new_content, count = re.subn(pattern, replacement, content)
        n += count
        content = new_content
    return content, n

def remove_alias_lines(content: str) -> tuple[str, int]:
    """alias 라인 제거"""
    lines = content.splitlines(keepends=True)
    new_lines = []
    removed = 0
    for line in lines:
        stripped = line.strip()
        if any(alias in stripped for alias in ALIAS_LINES_TO_REMOVE):
            removed += 1
            continue
        new_lines.append(line)
    return ''.join(new_lines), removed

def apply_imports(content: str) -> tuple[str, int]:
    n = 0
    for old, new in IMPORT_MAP:
        if old in content:
            content = content.replace(old, new)
            n += 1
    return content, n

def process_plugin_file(filepath: Path) -> bool:
    """플러그인 파일 내 클래스명 변경 + alias 제거"""
    content = read_file(filepath)
    content, c1 = apply_class_renames(content)
    content, c2 = remove_alias_lines(content)
    total = c1 + c2
    if total:
        write_file(filepath, content)
        print(f"  [PLUGIN] {filepath.name}: 클래스명 {c1}건, alias 제거 {c2}건")
    return total > 0

def process_general_file(filepath: Path, *, do_vars=False, do_imports=False, do_docs=False) -> bool:
    """일반 파일: import 수정 + 클래스명 + 변수명"""
    content = read_file(filepath)
    total = 0
    if do_imports:
        content, n = apply_imports(content)
        total += n
    content, n = apply_class_renames(content)
    total += n
    if do_vars:
        content, n = apply_var_replacements(content)
        total += n
    if do_docs:
        for old, new in DOCS_KEY_MAP.items():
            if old in content:
                content = content.replace(old, new)
                total += 1
    if total:
        write_file(filepath, content)
        print(f"  [FILE] {filepath.name}: {total}건 변경")
    return total > 0


def rename_file(old_path: Path, new_path: Path):
    if old_path.exists() and not new_path.exists():
        shutil.move(str(old_path), str(new_path))
        print(f"  [RENAME] {old_path.name} → {new_path.name}")
    elif new_path.exists():
        print(f"  [SKIP-RENAME] {new_path.name} 이미 존재")
    else:
        print(f"  [SKIP-RENAME] {old_path.name} 없음")


def main():
    print("=" * 60)
    print("Step 1: 플러그인 파일 내부 수정 (클래스명, alias 제거)")
    print("=" * 60)
    plugins_dir = ROOT / "strategy" / "plugins"
    for old_name, new_name in FILE_MAP.items():
        old_path = plugins_dir / f"{old_name}.py"
        if old_path.exists():
            process_plugin_file(old_path)

    print()
    print("=" * 60)
    print("Step 2: 외부 파일 수정 (import, 클래스명, 변수명)")
    print("=" * 60)

    # strategy_engine.py
    f = ROOT / "hft" / "core" / "strategy_engine.py"
    process_general_file(f, do_imports=True, do_vars=True)

    # mock_ws_server.py
    f = ROOT / "mock_ws_server.py"
    process_general_file(f, do_imports=True, do_vars=True)

    # main.py (혹시 import 있으면)
    f = ROOT / "main.py"
    process_general_file(f, do_imports=True)

    # strategy_docs.json
    f = ROOT / "strategy_docs.json"
    process_general_file(f, do_docs=True)

    # test files
    test_dir = ROOT / "tests" / "unit"
    for test_file in [
        "test_strategy_plugins_track1_defense.py",
        "test_strategy_plugins_track2_trap.py",
        "test_strategy_plugins_track3_arbitrage.py",
        "test_strategy_plugins_track4_gamma.py",
        "test_strategy_orchestrator.py",
    ]:
        f = test_dir / test_file
        if f.exists():
            process_general_file(f, do_imports=True, do_vars=True)

    # sensor 파일들
    for sensor_file in [
        "sensor/graph_strategy.py",
        "sensor/report_agent.py",
        "sensor/analyzer.py",
        "sensor/feedback.py",
        "sensor/trade_replay_analyzer.py",
    ]:
        f = ROOT / sensor_file
        if f.exists():
            process_general_file(f, do_imports=True)

    print()
    print("=" * 60)
    print("Step 3: 플러그인 파일 rename")
    print("=" * 60)
    for old_name, new_name in FILE_MAP.items():
        old_path = plugins_dir / f"{old_name}.py"
        new_path = plugins_dir / f"{new_name}.py"
        rename_file(old_path, new_path)

    print()
    print("=" * 60)
    print("Step 4: 테스트 파일 rename")
    print("=" * 60)
    test_file_map = {
        "test_strategy_plugins_track1_defense.py": "test_strategy_plugins_track1.py",
        "test_strategy_plugins_track2_trap.py":    "test_strategy_plugins_track2.py",
        "test_strategy_plugins_track3_arbitrage.py": "test_strategy_plugins_track3.py",
        "test_strategy_plugins_track4_gamma.py":   "test_strategy_plugins_track4.py",
    }
    for old_name, new_name in test_file_map.items():
        old_path = test_dir / old_name
        new_path = test_dir / new_name
        rename_file(old_path, new_path)

    print()
    print("=" * 60)
    print("완료!")
    print("=" * 60)


if __name__ == "__main__":
    main()
