# -*- coding: utf-8 -*-
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

from core.contracts import OrderRequest, ExecutionReport

REAL_TRADING_ENABLED: bool = False  # 🛡️ [CRITICAL SAFETY SWITCH] 실계좌 주문 자동 발주 절대 방지 락

class BrokerInterface(ABC):
    """[Phase 12 Broker Interface Base Class]
    
    Virtual Broker 및 향후 Real Broker Adapter가 구현할 동일 공통 브로커 인터페이스.
    """
    @abstractmethod
    def submit_order(self, order: OrderRequest) -> ExecutionReport:
        """주문 발주 및 체결 보고서 반환"""
        pass

    @abstractmethod
    def cancel_order(self, client_order_id: str) -> bool:
        """주문 취소 요청"""
        pass

    @abstractmethod
    def get_account_state(self) -> Dict[str, Any]:
        """계좌 잔고 및 가용 자금 상태 반환"""
        pass
