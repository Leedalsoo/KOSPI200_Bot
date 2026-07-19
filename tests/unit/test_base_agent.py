import pytest
from typing import Any, Dict
from core.base_agent import BaseAgent

def test_base_agent_instantiation_failure() -> None:
    """[목표 A, B, C 검증] 추상 클래스 직접 인스턴스화 시도 시 TypeError 차단 증명"""
    with pytest.raises(TypeError):
        BaseAgent() # type: ignore [abstract]

def test_incomplete_agent_implementation() -> None:
    """[경계값 오류 검증] 일부 메서드만 구현한 자식 클래스 인스턴스화 차단 증명"""
    class IncompleteAgent(BaseAgent):
        async def start(self) -> None:
            pass
        # stop, health_check, process_message 누락

    with pytest.raises(TypeError) as exc_info:
        IncompleteAgent() # type: ignore [abstract]
    
    assert "Can't instantiate abstract class" in str(exc_info.value)

@pytest.mark.asyncio
async def test_complete_agent_implementation() -> None:
    """[해피 패스] 모든 메서드를 완벽히 구현한 자식 클래스 정상 작동 증명"""
    class CompleteAgent(BaseAgent):
        async def start(self) -> None:
            pass
        async def stop(self) -> None:
            pass
        async def health_check(self) -> bool:
            return True
        async def process_message(self, message: Dict[str, Any]) -> None:
            pass

    agent = CompleteAgent()
    assert await agent.health_check() is True
