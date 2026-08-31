"""Unit tests for D-09 Cancel Request and Confirmation Lifecycle Separation.

Verifies:
1. cancel_stale_order() transitions order to CANCEL_REQUESTED on successful broker request
2. Order remains in _active_orders while in CANCEL_REQUESTED state
3. confirm_cancel() transitions CANCEL_REQUESTED to CANCELLED and cleans up active resources
4. Race condition: PARTIAL execution report arriving after CANCEL_REQUESTED updates status to PARTIAL
5. Race condition: FILLED execution report arriving after CANCEL_REQUESTED updates status to FILLED without being overwritten by CANCELLED
6. Direct transition to CANCELLED without CANCEL_REQUESTED is rejected by FSM
7. Broker cancel failure preserves original order state without transitioning to CANCEL_REQUESTED or CANCELLED
8. confirm_cancel() rejected if order is not in CANCEL_REQUESTED state
9. Terminal states (FILLED, CANCELLED, REJECTED) reject any cancel transitions
"""
from unittest.mock import MagicMock
import uuid
import time
import pytest

from shared.core.contracts import OrderStatus, RiskApprovalToken
from shared.contracts.canonical import (
    CanonicalOrderCommand,
    CanonicalExecutionReport,
    CanonicalAssetType,
    CanonicalOrderSide,
)
from option_program.orders.oms_fsm import OmsFsm
from option_program.orders.order_router import OrderRouter


def make_cmd(client_id: str = "ORD-D09-001", qty: int = 10, price: float = 3.5) -> CanonicalOrderCommand:
    return CanonicalOrderCommand(
        client_order_id=client_id,
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=qty,
        price=price,
        symbol="KOSPI200",
    )


def make_token(order_uuid: uuid.UUID, client_id: str = "ORD-D09-001") -> RiskApprovalToken:
    return RiskApprovalToken(
        order_id=order_uuid,
        timestamp_ns=time.time_ns(),
        signature=f"SIG-RISK-APPROVED-Track1-{client_id}",
    )


def make_report(
    client_id: str = "ORD-D09-001",
    executed_qty: int = 5,
    executed_price: float = 3.5,
) -> CanonicalExecutionReport:
    return CanonicalExecutionReport(
        exec_id=f"EXEC-{uuid.uuid4().hex[:8]}",
        client_order_id=client_id,
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        executed_qty=executed_qty,
        executed_price=executed_price,
        fee=100.0,
        slippage=0.0,
        timestamp="2026-08-31 09:00:00",
        symbol="KOSPI200",
    )


class TestCancelRequestAndConfirmationLifecycle:
    """D-09 취소 요청과 실제 취소 완료 분리 라이프사이클 검증."""

    def test_cancel_request_success_transitions_to_cancel_requested(self):
        """1. 취소 요청 성공 시 CANCEL_REQUESTED로 전이하며 active_orders에 보존됨을 검증."""
        router = OrderRouter(stale_timeout_sec=30.0)
        cmd = make_cmd("ORD-CR-001", qty=10)
        oid = uuid.uuid4()
        token = make_token(oid, "ORD-CR-001")

        mock_broker = MagicMock()
        mock_broker.cancel_order.return_value = True

        router.register_and_route(command=cmd, token=token, broker_adapter=mock_broker)
        assert router.fsm.get_status(oid) == OrderStatus.SENT

        # 취소 요청 실행
        req_ok = router.cancel_stale_order(oid)
        assert req_ok is True
        mock_broker.cancel_order.assert_called_once_with("ORD-CR-001")

        # FSM은 CANCEL_REQUESTED 상태이며, 아직 CANCELLED가 아님
        assert router.fsm.get_status(oid) == OrderStatus.CANCEL_REQUESTED
        assert oid in router._active_orders

    def test_cancel_confirmation_transitions_to_cancelled_and_cleans_resources(self):
        """2. 실제 취소 확정(confirm_cancel) 수신 시 CANCELLED로 전이되고 active 자원이 정리됨을 검증."""
        router = OrderRouter()
        cmd = make_cmd("ORD-CR-002", qty=10)
        oid = uuid.uuid4()
        token = make_token(oid, "ORD-CR-002")

        mock_broker = MagicMock()
        mock_broker.cancel_order.return_value = True

        router.register_and_route(command=cmd, token=token, broker_adapter=mock_broker)
        router.cancel_stale_order(oid)
        assert router.fsm.get_status(oid) == OrderStatus.CANCEL_REQUESTED

        # 취소 확정 수신
        confirm_ok = router.confirm_cancel(oid)
        assert confirm_ok is True
        assert router.fsm.get_status(oid) == OrderStatus.CANCELLED
        assert oid not in router._active_orders
        assert oid not in router._order_brokers
        assert oid not in router._cum_executed_qty

    def test_cancel_confirmation_by_client_order_id_string(self):
        """2-1. client_order_id 문자열로 confirm_cancel 호출 시에도 정상 확정 처리 검증."""
        router = OrderRouter()
        cmd = make_cmd("ORD-STR-001", qty=10)
        oid = uuid.uuid4()
        token = make_token(oid, "ORD-STR-001")

        mock_broker = MagicMock()
        mock_broker.cancel_order.return_value = True

        router.register_and_route(command=cmd, token=token, broker_adapter=mock_broker)
        router.cancel_stale_order(oid)

        confirm_ok = router.confirm_cancel("ORD-STR-001")
        assert confirm_ok is True
        assert router.fsm.get_status(oid) == OrderStatus.CANCELLED
        assert oid not in router._active_orders

    def test_race_condition_partial_fill_after_cancel_requested(self):
        """3. 취소 요청(CANCEL_REQUESTED) 상태에서 부분 체결 보고서 도착 시 PARTIAL로 안전 전이 검증."""
        router = OrderRouter()
        cmd = make_cmd("ORD-RACE-001", qty=10)
        oid = uuid.uuid4()
        token = make_token(oid, "ORD-RACE-001")

        mock_broker = MagicMock()
        mock_broker.cancel_order.return_value = True

        router.register_and_route(command=cmd, token=token, broker_adapter=mock_broker)
        router.cancel_stale_order(oid)
        assert router.fsm.get_status(oid) == OrderStatus.CANCEL_REQUESTED

        # 체결 보고서 도착 (4주 부분 체결)
        rep = make_report("ORD-RACE-001", executed_qty=4)
        router.handle_execution_report(oid, rep)

        # 상태는 CANCELLED로 덮어씌워지지 않고 PARTIAL로 전이됨
        assert router.fsm.get_status(oid) == OrderStatus.PARTIAL
        assert router._cum_executed_qty[oid] == 4
        assert oid in router._active_orders

        # 이후 남은 6주에 대해 다시 취소 요청 및 취소 확정 가능
        router.cancel_stale_order(oid)
        assert router.fsm.get_status(oid) == OrderStatus.CANCEL_REQUESTED
        router.confirm_cancel(oid)
        assert router.fsm.get_status(oid) == OrderStatus.CANCELLED

    def test_race_condition_full_fill_after_cancel_requested(self):
        """4. 취소 요청(CANCEL_REQUESTED) 상태에서 전량 체결 보고서 도착 시 FILLED로 전이 검증."""
        router = OrderRouter()
        cmd = make_cmd("ORD-RACE-002", qty=10)
        oid = uuid.uuid4()
        token = make_token(oid, "ORD-RACE-002")

        mock_broker = MagicMock()
        mock_broker.cancel_order.return_value = True

        router.register_and_route(command=cmd, token=token, broker_adapter=mock_broker)
        router.cancel_stale_order(oid)
        assert router.fsm.get_status(oid) == OrderStatus.CANCEL_REQUESTED

        # 전량 체결(10주) 도착
        rep = make_report("ORD-RACE-002", executed_qty=10)
        router.handle_execution_report(oid, rep)

        # FILLED로 전이되며 자원 정리 완료
        assert router.fsm.get_status(oid) == OrderStatus.FILLED
        assert oid not in router._active_orders

        # 이후 confirm_cancel 시도는 이미 FILLED이므로 거부됨
        assert router.confirm_cancel(oid) is False

    def test_direct_transition_to_cancelled_without_cancel_requested_is_blocked(self):
        """5. SENT, ACCEPTED, PENDING, PARTIAL에서 CANCEL_REQUESTED 없이 직접 CANCELLED로 전이 시도 시 차단 검증."""
        fsm = OmsFsm()
        for initial_status in [OrderStatus.SENT, OrderStatus.ACCEPTED, OrderStatus.PENDING, OrderStatus.PARTIAL]:
            oid = uuid.uuid4()
            fsm.states[oid] = initial_status
            assert fsm.can_transition(initial_status, OrderStatus.CANCELLED) is False
            assert fsm.transition_sync(oid, OrderStatus.CANCELLED) is False
            assert fsm.get_status(oid) == initial_status

            # CANCEL_REQUESTED는 허용됨
            assert fsm.can_transition(initial_status, OrderStatus.CANCEL_REQUESTED) is True

    def test_broker_cancel_failure_preserves_original_state(self):
        """6. 브로커 취소 요청 실패 시 기존 상태가 보존되고 CANCEL_REQUESTED로 전이되지 않음을 검증."""
        router = OrderRouter()
        cmd = make_cmd("ORD-FAIL-001", qty=10)
        oid = uuid.uuid4()
        token = make_token(oid, "ORD-FAIL-001")

        mock_broker = MagicMock()
        mock_broker.cancel_order.return_value = False  # 취소 실패

        router.register_and_route(command=cmd, token=token, broker_adapter=mock_broker)
        assert router.fsm.get_status(oid) == OrderStatus.SENT

        res = router.cancel_stale_order(oid)
        assert res is False
        # 상태는 SENT로 유지됨
        assert router.fsm.get_status(oid) == OrderStatus.SENT
        assert oid in router._active_orders

    def test_confirm_cancel_rejected_when_not_cancel_requested(self):
        """7. CANCEL_REQUESTED 상태가 아닐 때 confirm_cancel 호출 시 거부됨을 검증."""
        router = OrderRouter()
        cmd = make_cmd("ORD-NOT-REQ-001", qty=10)
        oid = uuid.uuid4()
        token = make_token(oid, "ORD-NOT-REQ-001")

        router.register_and_route(command=cmd, token=token)
        assert router.fsm.get_status(oid) == OrderStatus.SENT

        # 취소 요청 없이 바로 confirm_cancel 호출 시 거부
        assert router.confirm_cancel(oid) is False
        assert router.fsm.get_status(oid) == OrderStatus.SENT

    def test_terminal_states_cannot_transition_to_cancel_requested_or_cancelled(self):
        """8. 종료 상태(FILLED, CANCELLED, REJECTED)에서 CANCEL_REQUESTED 또는 재전이 불가 검증."""
        fsm = OmsFsm()
        for term_status in [OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED]:
            oid = uuid.uuid4()
            fsm.states[oid] = term_status
            assert fsm.can_transition(term_status, OrderStatus.CANCEL_REQUESTED) is False
            assert fsm.can_transition(term_status, OrderStatus.CANCELLED) is False
            assert fsm.transition_sync(oid, OrderStatus.CANCEL_REQUESTED) is False
            assert fsm.transition_sync(oid, OrderStatus.CANCELLED) is False
