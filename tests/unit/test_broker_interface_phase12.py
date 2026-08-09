# -*- coding: utf-8 -*-
from interface.broker_interface import BrokerInterface, REAL_TRADING_ENABLED

def test_broker_interface_safety_switch() -> None:
    # 실계좌 발주 안전 스위치는 무조건 False로 고정되어야 함
    assert REAL_TRADING_ENABLED is False
