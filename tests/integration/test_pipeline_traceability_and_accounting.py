import pytest
from core.contracts import OrderRequest, ExecutionReport, PositionRecord, OrderPurpose, OrderType, OrderSide
from mock_ws_server import _reset_session_state, current_capital, total_equity, portfolio_options, strategy_pnl_tracker, strategy_realized_pnl

def test_order_purpose_enumeration_distinctness():
    """ENTRY, HEDGE, EXIT 목적 구별 원칙 검증"""
    assert OrderPurpose.ENTRY != OrderPurpose.RISK_HEDGE
    assert OrderPurpose.RISK_HEDGE != OrderPurpose.PROFIT_EXIT
    assert OrderPurpose.PROFIT_EXIT != OrderPurpose.ENTRY

def test_order_traceability_chain_preservation():
    """Order Traceability 체인 상의 필수 필드 보존 검증"""
    req = OrderRequest(
        strategy_id="Track1",
        order_purpose=OrderPurpose.RISK_HEDGE,
        client_order_id="ORD-T1-001",
        symbol="KR4200000001",
        order_type=OrderType.LIMIT,
        side=OrderSide.BUY,
        price=1.50,
        qty=1,
        parent_order_id="ORD-T1-000",
        parent_position_id="POS-T1-000",
        hedge_ref_id="REF-HEDGE-001"
    )
    
    assert req.strategy_id == "Track1"
    assert req.order_purpose == OrderPurpose.RISK_HEDGE
    assert req.parent_order_id == "ORD-T1-000"
    assert req.parent_position_id == "POS-T1-000"
    assert req.hedge_ref_id == "REF-HEDGE-001"

def test_pnl_accounting_and_double_counting_immunity():
    """PnL 회계 방정식 및 이중 계상 차단 검증"""
    _reset_session_state(preserve_capital=False)
    
    # 1. Strategy PnL vs Hedge PnL 독립성
    strat_pnl = sum(v for k, v in strategy_pnl_tracker.items() if k != "Hedge")
    hedge_pnl = strategy_pnl_tracker.get("Hedge", 0.0)
    total_realized = sum(strategy_realized_pnl.values())
    
    assert total_realized >= 0.0
    assert strat_pnl + hedge_pnl == total_realized
    
    # 2. Capital & Equity 합산 회계 방정식
    net_pnl = total_equity - 25000000.0
    unrealized_pnl = total_equity - current_capital
    assert abs(net_pnl - (total_realized + unrealized_pnl)) < 1e-5
