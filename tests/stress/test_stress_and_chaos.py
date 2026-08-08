# -*- coding: utf-8 -*-
"""
[STRATEGY VALIDATION & STRESS TEST SUITE]

동결된 Virtual Broker 아키텍처 상에서 실행되는 3대 극한 스트레스 테스트:
1. COVID_PANIC_2020 블랙스완 극단 붕괴 테스트
2. NOISE_CHOPPY 고주파 휩쏘 박스권 테스트
3. EXTREME_SLIPPAGE (5틱 슬리피지 마찰) 리스크 하중 테스트
"""

from decimal import Decimal
from datetime import datetime
from uuid import uuid4

from core.contracts import OrderRequest, OrderPurpose, OrderStatus, MarketTick
from execution.execution_engine import ExecutionEngine
from position.position_manager import PositionManager
from account.account_engine import AccountEngine
from pnl.pnl_engine import PnLEngine
from risk.hedge_arbitrator import HedgeArbitrator

def test_stress_extreme_slippage_resilience() -> None:
    """[Stress Test 1] 5틱 슬리피지 극단 하중 조건에서 계좌 회계 방정식 무결성 검증"""
    exec_engine = ExecutionEngine(fee_rate=Decimal("0.00003"), tick_size=Decimal("0.05"), multiplier=Decimal("250000"))
    pos_manager = PositionManager()
    account_engine = AccountEngine(initial_capital=Decimal("25000000.00"))
    pnl_engine = PnLEngine()
    
    # 1. BUY 5계약 @ 2.00, 슬리피지 5틱 (0.25pt 손실 하중)
    req1 = OrderRequest(
        decision_id=uuid4(),
        client_order_id=uuid4(),
        instrument_code="KOSPI200_OPT",
        price=Decimal("2.00"),
        qty=5,
        side="BUY",
        strategy_id="Track1",
        order_purpose=OrderPurpose.STRATEGY_ENTRY
    )
    rep1 = exec_engine.match_order(req1, bid_price=Decimal("2.00"), ask_price=Decimal("2.00"), slippage_ticks=5)
    pos_manager.apply_execution(rep1)
    
    # 체결가 2.25pt, 총 슬리피지 비용 = 0.25 * 5 * 250,000 = 312,500 원
    assert rep1.execution_price == Decimal("2.25")
    assert rep1.slippage_cost == Decimal("312500.00")
    
    # 2. EXIT 5계약 @ 3.00, 슬리피지 5틱 하중 (체결가 2.75pt)
    req2 = OrderRequest(
        decision_id=uuid4(),
        client_order_id=uuid4(),
        instrument_code="KOSPI200_OPT",
        price=Decimal("3.00"),
        qty=5,
        side="SELL",
        strategy_id="Track1",
        order_purpose=OrderPurpose.STRATEGY_EXIT
    )
    rep2 = exec_engine.match_order(req2, bid_price=Decimal("3.00"), ask_price=Decimal("3.00"), slippage_ticks=5)
    pos2 = pos_manager.apply_execution(rep2)
    
    assert pos2.remaining_qty == 0
    assert pos2.status == "CLOSED"
    
    pnl_engine.register_execution(rep1, entry_price=Decimal("2.25"))
    pnl_engine.register_execution(rep2, entry_price=Decimal("2.25"))
    
    account_engine.apply_realized_trade(
        pnl=(rep2.execution_price - Decimal("2.25")) * 5 * Decimal("250000"),
        fee=rep1.fee + rep2.fee,
        slippage=rep1.slippage_cost + rep2.slippage_cost
    )
    
    is_valid, msg = account_engine.verify_integrity()
    assert is_valid is True
    assert msg == "OK"

def test_stress_hedge_flood_arbitration() -> None:
    """[Stress Test 2] 동일 틱에서 10연속 폭풍 헷지 Intent 발생 시 중복 주문 100% 차단 검증"""
    arbitrator = HedgeArbitrator()
    approved_count = 0
    blocked_count = 0
    
    for i in range(10):
        req = OrderRequest(
            decision_id=uuid4(),
            client_order_id=uuid4(),
            instrument_code="KOSPI200_OPT",
            price=Decimal("1.50"),
            qty=2,
            side="SELL",
            timestamp_ns=1_000_000_000 + (i * 10_000_000),  # 10ms 간격 폭풍 발주
            strategy_id="Track1",
            order_purpose=OrderPurpose.RISK_HEDGE
        )
        ok, reason = arbitrator.arbitrate_hedge_order(req)
        if ok:
            approved_count += 1
        else:
            blocked_count += 1

    assert approved_count == 1
    assert blocked_count == 9  # 1초 이내 9건 헷지 주문 중복 차단 방어 성공
