# -*- coding: utf-8 -*-
from recovery.recovery_gateway import RecoveryGateway

def test_recovery_gateway_settlement_guard() -> None:
    gateway = RecoveryGateway()
    date_str = "2026-08-07"
    
    # 1. 미정산 상태 확인
    ok1, msg1 = gateway.check_intraday_restart_guard(date_str)
    assert ok1 is True
    assert msg1 == "OK"

    # 2. 정산 완료 등록 후 재시작 시 중복 정산 차단 검증
    gateway.mark_settled(date_str)
    ok2, msg2 = gateway.check_intraday_restart_guard(date_str)
    assert ok2 is False
    assert "SETTLEMENT_ALREADY_COMPLETED" in msg2
