# -*- coding: utf-8 -*-
import logging
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

class RecoveryGateway:
    """[Phase 11 Virtual Broker Recovery Gateway]
    
    장중 재시작(Intraday Restart) 및 복구 시 중복 정산/중복 진입을 방지하고
    시스템 무결성을 재구성하는 복구 서비스 뼈대.
    """
    def __init__(self) -> None:
        self.is_market_opened_today: bool = True
        self.settled_dates: set[str] = set()

    def check_intraday_restart_guard(self, date_str: str) -> Tuple[bool, str]:
        """당일 이미 정산이 실행되었는지 여부를 확인하여 중복 정산 차단"""
        if date_str in self.settled_dates:
            return False, f"SETTLEMENT_ALREADY_COMPLETED_FOR_{date_str}"
        return True, "OK"

    def mark_settled(self, date_str: str) -> None:
        """당일 만기 정산 완료 상태 등록"""
        self.settled_dates.add(date_str)
        logger.info(f"RecoveryGateway: Registered completed settlement for date {date_str}")
