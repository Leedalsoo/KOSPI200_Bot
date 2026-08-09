#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
전략 이름 Track1~Track9 완전 통일 스크립트
실행: python .agents/rename_tracks.py
"""
import re
import os
from pathlib import Path

ROOT = Path(r"c:\Users\white\KOSPI200_Bot")

# ──────────────────────────────────────────────────────────────
# 치환 규칙: (패턴, 대체문자열) 순서가 중요 (구체적인 것 먼저)
# ──────────────────────────────────────────────────────────────
REPLACEMENTS = [
    # 따옴표 안 "track1_defense", "track2_trap" 등 (orchestrator 스타일)
    (r'"track1_defense"', '"Track1"'),
    (r'"track2_trap"',    '"Track2"'),
    (r'"track3_arbitrage"', '"Track3"'),
    (r'"track4_gamma"',   '"Track4"'),
    (r'"track5_gap"',     '"Track5"'),
    (r'"track6_daily_insurance"', '"Track6"'),
    (r'"track7_weekly_insurance"', '"Track7"'),
    (r'"track8_monthly_strangle"', '"Track8"'),
    (r'"track9_overnight_insurance"', '"Track9"'),

    # 따옴표 안 "Track1 (Defense)" 등 (괄호 포함 변형들)
    (r'"Track1\s*\([^"]*\)"', '"Track1"'),
    (r'"Track2\s*\([^"]*\)"', '"Track2"'),
    (r'"Track3\s*\([^"]*\)"', '"Track3"'),
    (r'"Track4\s*\([^"]*\)"', '"Track4"'),
    (r'"Track5\s*\([^"]*\)"', '"Track5"'),
    (r'"Track6\s*\([^"]*\)"', '"Track6"'),
    (r'"Track7\s*\([^"]*\)"', '"Track7"'),
    (r'"Track8\s*\([^"]*\)"', '"Track8"'),
    (r'"Track9\s*\([^"]*\)"', '"Track9"'),

    # 따옴표 안 "T1 (Defense)" 등 단축 표기
    (r'"T1\s*\([^"]*\)"', '"Track1"'),
    (r'"T2\s*\([^"]*\)"', '"Track2"'),
    (r'"T3\s*\([^"]*\)"', '"Track3"'),
    (r'"T4\s*\([^"]*\)"', '"Track4"'),
    (r'"T5\s*\([^"]*\)"', '"Track5"'),
    (r'"T6\s*\([^"]*\)"', '"Track6"'),
    (r'"T7\s*\([^"]*\)"', '"Track7"'),
    (r'"T8\s*\([^"]*\)"', '"Track8"'),
    (r'"T9\s*\([^"]*\)"', '"Track9"'),

    # 따옴표 안 소문자 "track1"~"track9"
    (r'"track1"', '"Track1"'),
    (r'"track2"', '"Track2"'),
    (r'"track3"', '"Track3"'),
    (r'"track4"', '"Track4"'),
    (r'"track5"', '"Track5"'),
    (r'"track6"', '"Track6"'),
    (r'"track7"', '"Track7"'),
    (r'"track8"', '"Track8"'),
    (r'"track9"', '"Track9"'),

    # 작은따옴표 안 'track1'~'track9' (HTML/JS)
    (r"'track1'", "'Track1'"),
    (r"'track2'", "'Track2'"),
    (r"'track3'", "'Track3'"),
    (r"'track4'", "'Track4'"),
    (r"'track5'", "'Track5'"),
    (r"'track6'", "'Track6'"),
    (r"'track7'", "'Track7'"),
    (r"'track8'", "'Track8'"),
    (r"'track9'", "'Track9'"),

    # 주석/문서 내 "Track 1 (xxx)" → Track1 (공백 제거, 괄호 제거)
    (r'Track\s+1\s*\([^)\n]*\)', 'Track1'),
    (r'Track\s+2\s*\([^)\n]*\)', 'Track2'),
    (r'Track\s+3\s*\([^)\n]*\)', 'Track3'),
    (r'Track\s+4\s*\([^)\n]*\)', 'Track4'),
    (r'Track\s+5\s*\([^)\n]*\)', 'Track5'),
    (r'Track\s+6\s*\([^)\n]*\)', 'Track6'),
    (r'Track\s+7\s*\([^)\n]*\)', 'Track7'),
    (r'Track\s+8\s*\([^)\n]*\)', 'Track8'),
    (r'Track\s+9\s*\([^)\n]*\)', 'Track9'),

    # 주석/문서 내 "[Track 1]" → [Track1]
    (r'\[Track\s+1\]', '[Track1]'),
    (r'\[Track\s+2\]', '[Track2]'),
    (r'\[Track\s+3\]', '[Track3]'),
    (r'\[Track\s+4\]', '[Track4]'),
    (r'\[Track\s+5\]', '[Track5]'),
    (r'\[Track\s+6\]', '[Track6]'),
    (r'\[Track\s+7\]', '[Track7]'),
    (r'\[Track\s+8\]', '[Track8]'),
    (r'\[Track\s+9\]', '[Track9]'),

    # "[전략 N]" → [TrackN]
    (r'\[전략\s*1\]', '[Track1]'),
    (r'\[전략\s*2\]', '[Track2]'),
    (r'\[전략\s*3\]', '[Track3]'),
    (r'\[전략\s*4\]', '[Track4]'),
    (r'\[전략\s*5\]', '[Track5]'),
    (r'\[전략\s*6\]', '[Track6]'),
    (r'\[전략\s*7\]', '[Track7]'),
    (r'\[전략\s*8\]', '[Track8]'),
    (r'\[전략\s*9\]', '[Track9]'),

    # log 메시지 내 "Strategy N" → TrackN (따옴표 내)
    (r'Strategy\s+1\b', 'Track1'),
    (r'Strategy\s+2\b', 'Track2'),
    (r'Strategy\s+3\b', 'Track3'),
    (r'Strategy\s+4\b', 'Track4'),
    (r'Strategy\s+5\b', 'Track5'),
    (r'Strategy\s+6\b', 'Track6'),
    (r'Strategy\s+7\b', 'Track7'),
    (r'Strategy\s+8\b', 'Track8'),
    (r'Strategy\s+9\b', 'Track9'),

    # 주석 내 "Track 1~8" → "Track1~Track8"
    (r'Track\s+1~8\b', 'Track1~Track8'),
    (r'Track\s+1~9\b', 'Track1~Track9'),

    # "track1: true" 등 JS 객체 키 (공백 없는 소문자 단독)
    # 이미 위에서 따옴표 버전을 처리했으므로, 여기서는 dict key 형태 처리
    # 예: track1: true, track2: true 등
    (r'\btrack1\s*:', 'Track1:'),
    (r'\btrack2\s*:', 'Track2:'),
    (r'\btrack3\s*:', 'Track3:'),
    (r'\btrack4\s*:', 'Track4:'),
    (r'\btrack5\s*:', 'Track5:'),
    (r'\btrack6\s*:', 'Track6:'),
    (r'\btrack7\s*:', 'Track7:'),
    (r'\btrack8\s*:', 'Track8:'),
    (r'\btrack9\s*:', 'Track9:'),

    # HTML id/key 속성 내 'Track1' (이미 대문자이지만 공백 제거)
    (r"'Track1\s*\([^']*\)'", "'Track1'"),
    (r"'Track2\s*\([^']*\)'", "'Track2'"),
    (r"'Track3\s*\([^']*\)'", "'Track3'"),
    (r"'Track4\s*\([^']*\)'", "'Track4'"),
    (r"'Track5\s*\([^']*\)'", "'Track5'"),
    (r"'Track6\s*\([^']*\)'", "'Track6'"),
    (r"'Track7\s*\([^']*\)'", "'Track7'"),
    (r"'Track8\s*\([^']*\)'", "'Track8'"),
    (r"'Track9\s*\([^']*\)'", "'Track9'"),
]

# 처리 대상 파일 목록
TARGET_FILES = [
    # 전략 플러그인
    "strategy/plugins/track1_defense.py",
    "strategy/plugins/track2_trap.py",
    "strategy/plugins/track3_arbitrage.py",
    "strategy/plugins/track4_gamma.py",
    "strategy/plugins/track5_gap.py",
    "strategy/plugins/track6_daily_insurance.py",
    "strategy/plugins/track7_weekly_insurance.py",
    "strategy/plugins/track8_monthly_strangle.py",
    "strategy/plugins/track9_overnight_insurance.py",
    # 핵심 엔진
    "hft/core/strategy_engine.py",
    "mock_ws_server.py",
    "main.py",
    "strategy/orchestrator.py",
    "strategy/loader.py",
    # 센서/분석
    "sensor/graph_strategy.py",
    "sensor/report_agent.py",
    "sensor/analyzer.py",
    "sensor/feedback.py",
    "sensor/trade_replay_analyzer.py",
    # 문서/설정
    "strategy_docs.json",
    "test_report.md",
    # 프론트엔드
    "web_interface/HFT_Control_Panel.html",
    "web_interface/src/store/rootStore.js",
    "web_interface/src/components/dashboard/ProfitChart.js",
    "web_interface/src/components/dashboard/PayoffDiagram.js",
    "web_interface/src/tests/store/rootStore.test.js",
    "web_interface/src/tests/components/dashboard/ProfitChart.test.js",
    "web_interface/src/tests/components/dashboard/PayoffDiagram.test.js",
    # 테스트
    "tests/unit/test_strategy_plugins_track1_defense.py",
    "tests/unit/test_strategy_plugins_track2_trap.py",
    "tests/unit/test_strategy_plugins_track3_arbitrage.py",
    "tests/unit/test_strategy_plugins_track4_gamma.py",
    "tests/unit/test_strategy_orchestrator.py",
]

def apply_replacements(content: str) -> tuple[str, int]:
    """치환 적용, (새 내용, 변경 횟수) 반환"""
    total_changes = 0
    for pattern, replacement in REPLACEMENTS:
        new_content, n = re.subn(pattern, replacement, content)
        if n > 0:
            total_changes += n
        content = new_content
    return content, total_changes

def process_file(filepath: Path) -> bool:
    """단일 파일 처리"""
    if not filepath.exists():
        print(f"  [SKIP] 파일 없음: {filepath.relative_to(ROOT)}")
        return False
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            original = f.read()
    except UnicodeDecodeError:
        try:
            with open(filepath, 'r', encoding='cp949') as f:
                original = f.read()
        except Exception as e:
            print(f"  [ERROR] 인코딩 오류: {filepath.relative_to(ROOT)} - {e}")
            return False
    
    new_content, changes = apply_replacements(original)
    
    if changes == 0:
        print(f"  [OK] 변경 없음: {filepath.relative_to(ROOT)}")
        return False
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"  [CHANGED] {filepath.relative_to(ROOT)} ({changes}건 변경)")
    return True

def main():
    print("=" * 60)
    print("Track1~Track9 전략 이름 통일 스크립트")
    print("=" * 60)
    
    changed_count = 0
    skip_count = 0
    
    for rel_path in TARGET_FILES:
        filepath = ROOT / rel_path
        if process_file(filepath):
            changed_count += 1
        else:
            skip_count += 1
    
    print()
    print("=" * 60)
    print(f"완료: {changed_count}개 파일 변경, {skip_count}개 파일 변경 없음")
    print("=" * 60)

if __name__ == "__main__":
    main()
