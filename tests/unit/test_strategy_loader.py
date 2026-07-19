# -*- coding: utf-8 -*-
import pytest
import os
import tempfile
import sys
from typing import Generator
from core.base_agent import BaseAgent
from strategy.loader import PluginLoader

@pytest.fixture
def fake_plugins_env() -> Generator[str, None, None]:
    """테스트용 가짜 플러그인 디렉토리 및 파일 생성 픽스쳐"""
    with tempfile.TemporaryDirectory() as temp_dir:
        sys.path.insert(0, temp_dir)
        
        # 1. 정상적인 Concrete 클래스
        with open(os.path.join(temp_dir, "valid_strat.py"), "w", encoding="utf-8") as f:
            f.write("from core.base_agent import BaseAgent\n")
            f.write("class ValidStrategy(BaseAgent):\n")
            f.write("    async def start(self) -> None: pass\n")
            f.write("    async def stop(self) -> None: pass\n")
            f.write("    async def health_check(self) -> bool: return True\n")
            f.write("    async def process_message(self, msg) -> None: pass\n")

        # 2. 미구현된 Abstract 클래스 (유령 주문 유발자)
        with open(os.path.join(temp_dir, "abstract_strat.py"), "w", encoding="utf-8") as f:
            f.write("from core.base_agent import BaseAgent\n")
            f.write("class GhostStrategy(BaseAgent):\n")
            f.write("    pass\n") # 추상 메서드 미구현

        # 3. 문법 에러가 있는 파일 (크래시 유발자)
        with open(os.path.join(temp_dir, "broken_strat.py"), "w", encoding="utf-8") as f:
            f.write("this is invalid python syntax !!!\n")

        yield temp_dir
        if temp_dir in sys.path:
            sys.path.remove(temp_dir)

def test_plugin_loader_discovery_and_isolation(fake_plugins_env: str) -> None:
    """[목표 A, B, C 검증] 정상 적재, 추상 클래스 배제, 크래시 파일 격리 증명"""
    loader = PluginLoader(fake_plugins_env)
    
    # 임시 디렉토리를 패키지로 인식하게끔 처리 (테스트용)
    loader.plugins_dir = fake_plugins_env
    
    strategies = loader.discover_and_load()
    
    # 1. 유효한 전략은 로드되어야 함
    assert "ValidStrategy" in strategies
    assert issubclass(strategies["ValidStrategy"], BaseAgent)
    
    # 2. 추상 클래스는 로드되지 않아야 함
    assert "GhostStrategy" not in strategies
    
    # 3. 문법 에러 파일이 있어도 시스템이 크래시되지 않고 위 검증들을 통과해야 함
    # (discover_and_load가 예외 없이 반환되었다는 것 자체가 목표 C 증명)
