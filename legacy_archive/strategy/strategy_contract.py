# -*- coding: utf-8 -*-
from typing import Dict, Any, List, Optional
from core.contracts import OrderRequest, ExecutionReport, PositionRecord

class StrategyContract:
    """[Phase 9 & 10 Strategy Contract Base Class]
    
    전략 1~9가 Virtual Broker 및 외부 브로커 계층과 상호작용하기 위한
    표준 계약 인터페이스. 전략 내부에서 Account/Position/PnL 직접 변이를
    금지하고 OrderRequest 생성에 집중하도록 격리하며, 기존 플러그인의 
    기존 평가 메서드와의 100% 하위 호환성을 보장함.
    """
    def on_market_data(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """시세 및 기술 지표 업데이트 수신 콜백 (기본 구현)"""
        return {"status": "OK"}

    def generate_signals(self, market_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """시그널 발생 판단 콜백 (기본 구현)"""
        return []

    def generate_orders(self, signals: List[Dict[str, Any]]) -> List[OrderRequest]:
        """시그널을 표준 OrderRequest 주문 요청으로 변환 (기본 구현)"""
        return []

    def on_execution(self, execution: ExecutionReport) -> None:
        """체결 이벤트 수신 콜백"""
        pass

    def on_position_update(self, position: PositionRecord) -> None:
        """포지션 갱신 수신 콜백"""
        pass
