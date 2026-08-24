"""Unit Test: OMS FSM, Order Router & Stale Order Lifecycle Comprehensive Verification."""
import pytest
import uuid
import time
from unittest.mock import MagicMock

from shared.contracts.canonical import (
    CanonicalOrderCommand,
    CanonicalExecutionReport,
    CanonicalAssetType,
    CanonicalOrderSide
)
from shared.core.contracts import OrderStatus, RiskApprovalToken
from option_program.orders.oms_fsm import OmsFsm
from option_program.orders.order_router import OrderRouter

def test_oms_fsm_full_lifecycle_filled():
    """Validates complete order lifecycle from NEW -> VALIDATED -> SENT -> FILLED."""
    fsm = OmsFsm()
    router = OrderRouter(fsm=fsm)
    order_uuid = uuid.uuid4()

    cmd = CanonicalOrderCommand(
        client_order_id="ORD-TRACK1-001",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=2,
        price=2.50,
        tag_id="T1"
    )
    token = RiskApprovalToken(
        order_id=order_uuid,
        timestamp_ns=time.time_ns(),
        signature="SIG-TEST"
    )

    mock_broker = MagicMock()
    # 1. Register & Route -> SENT
    routed_id = router.register_and_route(cmd, token, mock_broker, mode_str="PAPER")
    assert routed_id == order_uuid
    assert fsm.get_status(order_uuid) == OrderStatus.SENT

    # 2. Execution Report -> FILLED
    exec_report = CanonicalExecutionReport(
        exec_id="EXEC-001",
        client_order_id="ORD-TRACK1-001",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        executed_qty=2,
        executed_price=2.50,
        fee=10.0,
        slippage=0.0,
        timestamp="2026-08-24 10:00:00"
    )
    router.handle_execution_report(order_uuid, exec_report)
    assert fsm.get_status(order_uuid) == OrderStatus.FILLED

def test_oms_fsm_rejection_lifecycle():
    """Validates order transition to REJECTED when broker reports zero executed qty."""
    fsm = OmsFsm()
    router = OrderRouter(fsm=fsm)
    order_uuid = uuid.uuid4()

    cmd = CanonicalOrderCommand(
        client_order_id="ORD-TRACK2-002",
        track_id="Track2",
        asset_type=CanonicalAssetType.FUTURES,
        side=CanonicalOrderSide.BUY,
        qty=1,
        price=350.0,
        tag_id="T2"
    )
    token = RiskApprovalToken(order_id=order_uuid, timestamp_ns=time.time_ns(), signature="SIG-T2")

    router.register_and_route(cmd, token, MagicMock())
    assert fsm.get_status(order_uuid) == OrderStatus.SENT

    # Rejection report
    rej_report = CanonicalExecutionReport(
        exec_id="EXEC-REJ",
        client_order_id="ORD-TRACK2-002",
        track_id="Track2",
        asset_type=CanonicalAssetType.FUTURES,
        side=CanonicalOrderSide.BUY,
        executed_qty=0,
        executed_price=0.0,
        fee=0.0,
        slippage=0.0,
        timestamp="2026-08-24 10:00:00"
    )
    router.handle_execution_report(order_uuid, rej_report)
    assert fsm.get_status(order_uuid) == OrderStatus.REJECTED

def test_stale_order_detection_and_cancel():
    """Validates that orders pending longer than stale_timeout_sec are detected and cancelled."""
    fsm = OmsFsm()
    router = OrderRouter(fsm=fsm, stale_timeout_sec=10.0)
    order_uuid = uuid.uuid4()

    cmd = CanonicalOrderCommand(
        client_order_id="ORD-STALE-001",
        track_id="Track3",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=1,
        price=2.0,
        tag_id="T3"
    )
    token = RiskApprovalToken(order_id=order_uuid, timestamp_ns=time.time_ns(), signature="SIG-STALE")

    t0 = 1000.0
    router.register_and_route(cmd, token, MagicMock())
    # Override submission timestamp to t0
    router._active_orders[order_uuid] = (cmd, t0)

    # Check at t0 + 5s -> Not stale
    assert len(router.scan_stale_orders(current_time=t0 + 5.0)) == 0

    # Check at t0 + 15s -> Stale detected
    stale_list = router.scan_stale_orders(current_time=t0 + 15.0)
    assert len(stale_list) == 1
    assert stale_list[0] == order_uuid

    # Auto Cancel
    cancelled = router.cancel_stale_order(order_uuid)
    assert cancelled is True
    assert fsm.get_status(order_uuid) == OrderStatus.CANCELLED
