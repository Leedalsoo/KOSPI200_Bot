# -*- coding: utf-8 -*-
from abc import ABC, abstractmethod
from typing import Any, Dict

class BaseAgent(ABC):
    """
    HFT 마이크로서비스 컴포넌트의 최상위 비동기 추상 클래스.
    모든 에이전트는 uvloop 기반의 논블로킹 라이프사이클을 준수해야 한다.
    
    경고: 자식 클래스 구현 시 start()나 stop() 내부에서 절대 동기식 I/O (time.sleep, os.fsync 등)를 
    사용하지 말 것. 이는 uvloop 전체를 블로킹하여 시스템을 치명적인 지연 상태로 몰아넣는다.
    """

    @abstractmethod
    async def start(self) -> None:
        """[목표 A] 에이전트 비동기 구동 및 자원 할당"""
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        """[목표 A] 에이전트 안전 정지 및 자원 반납"""
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> bool:
        """[목표 B] 에이전트 활성 상태 및 메모리 헬스 체크"""
        raise NotImplementedError

    @abstractmethod
    async def process_message(self, message: Dict[str, Any]) -> None:
        """[목표 C] 중앙 이벤트 버스로부터 전달받은 메시지 비동기 처리"""
        raise NotImplementedError
