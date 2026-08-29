"""6단계-5: Execution -> Position -> PnL / Margin / Ledger E2E 검증 테스트"""
import pytest
from shared.contracts.canonical import (
    CanonicalAssetType,
    CanonicalOrderCommand,
    CanonicalOrderSide,
)
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime


def test_execution_position_pnl_margin_ledger_e2e_lifecycle():
    # 1. VSSF Runtime 초기화 (초기 자본금 25,000,000)
    initial_capital = 25_000_000.0
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=initial_capital)
    account = vssf.account

    # 2. 필요한 OrderBook 상태 구성
    vssf.order_book.update_bid_ask(bid_price=2.0, ask_price=2.05)

    # 3. CanonicalOrderCommand 생성 (BUY 2 @ 2.05)
    order_cmd = CanonicalOrderCommand(
        client_order_id="ORD-E2E-001",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=2,
        price=2.05,
        symbol="KOSPI200",
    )

    # 4. vssf.process_order(command) 실제 호출
    report = vssf.process_order(order_cmd)

    # 5. 반환된 CanonicalExecutionReport 확인
    assert report is not None, "process_order should return a valid ExecutionReport"
    assert report.executed_qty == 2

    # 6 & 7. ExecutionReport 주요 필드 및 입력 주문 보존 검증
    assert report.exec_id.startswith("EXEC-")
    assert report.client_order_id == "ORD-E2E-001"
    assert report.track_id == "Track1"
    assert report.executed_qty == 2
    assert report.executed_price > 0
    assert report.fee >= 0
    assert report.slippage >= 0
    assert report.symbol == "KOSPI200"

    # 8 & 9. PositionManager 포지션 반영 검증
    instrument_key = report.get_instrument_key()
    assert instrument_key in account.positions
    pos = account.positions[instrument_key]
    assert pos["qty"] == 2
    assert pos["side"] == "BUY"
    assert pos["avg_price"] == pytest.approx(report.executed_price)

    # 주문별 귀속 포지션 확인
    ord_pos = account.get_order_position("ORD-E2E-001")
    assert ord_pos["qty"] == 2
    assert ord_pos["avg_price"] == pytest.approx(report.executed_price)

    # 10 & 19. PnLEngine 상태와 독립적 손익 대조
    expected_realized = 0.0
    assert account.realized_pnl == pytest.approx(expected_realized)
    assert account.pnl_engine.realized_pnl == pytest.approx(expected_realized)
    assert account.unrealized_pnl == pytest.approx(account.pnl_engine.unrealized_pnl)

    # 11, 12 & 20. MarginEngine과 Account 마진 결과 직접 대조
    multiplier = 250000.0
    expected_used_margin = round(pos["avg_price"] * pos["qty"] * multiplier, 2)
    assert account.used_margin == pytest.approx(expected_used_margin)
    assert account.used_margin == pytest.approx(vssf.margin_engine.calculate_used_margin(account.positions))

    expected_total_equity = account.balance + account.realized_pnl + account.unrealized_pnl
    expected_free_margin = vssf.margin_engine.calculate_free_margin(expected_total_equity, account.used_margin)
    assert account.free_margin == pytest.approx(expected_free_margin)

    # 13 & 14. LedgerEngine 거래 내역 기록 검증
    assert len(account.ledger_engine.transactions) == 1
    tx = account.ledger_engine.transactions[0]
    assert tx["exec_id"] == report.exec_id
    assert tx["order_id"] == report.client_order_id
    assert tx["side"] == "BUY"
    assert tx["qty"] == report.executed_qty
    assert tx["price"] == report.executed_price
    assert tx["fee"] == report.fee
    assert tx["slippage"] == report.slippage

    # 15 & 16. Canonical Account Summary 일치성 검증
    summary = account.get_canonical_summary()
    assert summary.total_balance == pytest.approx(round(expected_total_equity, 2))
    assert summary.realized_pnl == pytest.approx(round(account.realized_pnl, 2))
    assert summary.unrealized_pnl == pytest.approx(round(account.unrealized_pnl, 2))
    assert summary.used_margin == pytest.approx(round(account.used_margin, 2))
    assert summary.free_margin == pytest.approx(round(account.free_margin, 2))
    assert summary.positions[instrument_key]["qty"] == pos["qty"]
    assert summary.positions[instrument_key]["avg_price"] == pytest.approx(pos["avg_price"])

    # 17 & 18. 동일 ExecutionReport 재수신 시 Idempotency (중복 반영 방지) 검증
    pos_qty_before = account.positions[instrument_key]["qty"]
    balance_before = account.balance
    tx_count_before = len(account.ledger_engine.transactions)

    account.apply_execution(report)

    assert account.positions[instrument_key]["qty"] == pos_qty_before, "Duplicate execution must not alter position"
    assert account.balance == balance_before, "Duplicate execution must not alter balance"
    assert len(account.ledger_engine.transactions) == tx_count_before, "Duplicate execution must not create ledger transaction"


def test_execution_e2e_exit_reduction_realized_pnl_and_ledger():
    # 반대방향 청산 주문을 통한 Realized PnL 및 마진/장부 갱신 E2E 검증
    initial_capital = 25_000_000.0
    vssf = VirtualSecuritiesFirmRuntime(initial_capital=initial_capital)
    account = vssf.account

    # 1. BUY 1 진입 (OrderBook best_ask=2.0)
    vssf.order_book.update_bid_ask(bid_price=1.95, ask_price=2.0)
    buy_cmd = CanonicalOrderCommand(
        client_order_id="ORD-BUY-1",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=1,
        price=2.0,
        symbol="KOSPI200",
    )
    buy_report = vssf.process_order(buy_cmd)
    assert buy_report is not None
    entry_price = buy_report.executed_price
    instrument_key = buy_report.get_instrument_key()

    # 2. SELL 1 청산 (OrderBook best_bid=2.5)
    vssf.order_book.update_bid_ask(bid_price=2.5, ask_price=2.55)
    sell_cmd = CanonicalOrderCommand(
        client_order_id="ORD-SELL-1",
        track_id="Track2",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.SELL,
        qty=1,
        price=2.5,
        symbol="KOSPI200",
    )
    sell_report = vssf.process_order(sell_cmd)
    assert sell_report is not None
    exit_price = sell_report.executed_price

    # 3. 독립적 Realized PnL 계산 대조: (exit_price - entry_price) * 1 * 250,000
    multiplier = 250000.0
    expected_realized_pnl = (exit_price - entry_price) * 1 * multiplier
    assert account.realized_pnl == pytest.approx(expected_realized_pnl)
    assert account.pnl_engine.realized_pnl == pytest.approx(expected_realized_pnl)

    # 4. 포지션 전량 청산 확인
    assert instrument_key not in account.positions or account.positions[instrument_key]["qty"] == 0
    assert account.used_margin == pytest.approx(0.0)

    # 5. Ledger에 진입/청산 2개 트랜잭션 정상 기록 확인
    assert len(account.ledger_engine.transactions) == 2
    assert account.ledger_engine.transactions[0]["order_id"] == "ORD-BUY-1"
    assert account.ledger_engine.transactions[1]["order_id"] == "ORD-SELL-1"
