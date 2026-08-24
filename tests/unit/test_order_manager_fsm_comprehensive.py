"""Unit Test: Order Manager & OMS FSM Comprehensive Verification."""
import pytest
import uuid
import asyncio
from shared.core.contracts import OrderStatus, RiskApprovalToken
from option_program.orders.oms_fsm import OmsFsm
from option_program.orders.order_router import OrderRouter
from shared.contracts.canonical import CanonicalOrderCommand, CanonicalAssetType, CanonicalOrderSide

@pytest.mark.asyncio
async def test_fsm_lifecycle_full_flow():
    """Validates sequential FSM state progression from NEW to FILLED."""
    fsm = OmsFsm()
    order_id = uuid.uuid4()
    token = RiskApprovalToken(order_id=order_id, timestamp_ns=1000000, signature="SIG_TEST")

    # 1. Register
    await fsm.register_order(token)
    assert fsm.get_status(order_id) == OrderStatus.NEW

    # 2. VALIDATED
    await fsm.transition(order_id, OrderStatus.VALIDATED)
    assert fsm.get_status(order_id) == OrderStatus.VALIDATED

    # 3. SENT
    await fsm.transition(order_id, OrderStatus.SENT)
    assert fsm.get_status(order_id) == OrderStatus.SENT

    # 4. ACCEPTED / PENDING
    await fsm.transition(order_id, OrderStatus.ACCEPTED)
    assert fsm.get_status(order_id) == OrderStatus.ACCEPTED

    # 5. PARTIAL
    await fsm.transition(order_id, OrderStatus.PARTIAL)
    assert fsm.get_status(order_id) == OrderStatus.PARTIAL

    # 6. FILLED
    await fsm.transition(order_id, OrderStatus.FILLED)
    assert fsm.get_status(order_id) == OrderStatus.FILLED

@pytest.mark.asyncio
async def test_fsm_cancellation_and_rejection_paths():
    """Validates safe terminal state transitions for cancellation and rejection."""
    fsm = OmsFsm()

    # Cancelled path
    oid_cancel = uuid.uuid4()
    token_cancel = RiskApprovalToken(order_id=oid_cancel, timestamp_ns=1000000, signature="SIG_CANCEL")
    await fsm.register_order(token_cancel)
    await fsm.transition(oid_cancel, OrderStatus.SENT)
    await fsm.transition(oid_cancel, OrderStatus.CANCELLED)
    assert fsm.get_status(oid_cancel) == OrderStatus.CANCELLED

    # Rejected path
    oid_reject = uuid.uuid4()
    token_reject = RiskApprovalToken(order_id=oid_reject, timestamp_ns=1000000, signature="SIG_REJECT")
    await fsm.register_order(token_reject)
    await fsm.transition(oid_reject, OrderStatus.REJECTED)
    assert fsm.get_status(oid_reject) == OrderStatus.REJECTED

@pytest.mark.asyncio
async def test_fsm_idempotency_guard():
    """Validates idempotency check on duplicate registrations and state updates."""
    fsm = OmsFsm()
    order_id = uuid.uuid4()
    token = RiskApprovalToken(order_id=order_id, timestamp_ns=1000000, signature="SIG_TEST")

    assert not fsm.is_idempotent(order_id)
    await fsm.register_order(token)
    assert fsm.is_idempotent(order_id)

    # Double registration must not alter state if already advanced
    await fsm.transition(order_id, OrderStatus.SENT)
    await fsm.register_order(token)
    assert fsm.get_status(order_id) == OrderStatus.SENT

@pytest.mark.asyncio
async def test_fsm_lock_cleanup_on_terminal_states():
    """Validates orphaned locks are cleaned up when terminal state is reached."""
    fsm = OmsFsm()
    order_id = uuid.uuid4()
    token = RiskApprovalToken(order_id=order_id, timestamp_ns=1000000, signature="SIG_TEST")

    await fsm.register_order(token)
    assert order_id in fsm._locks

    await fsm.transition(order_id, OrderStatus.FILLED)
    fsm.clear_completed_locks()
    assert order_id not in fsm._locks

@pytest.mark.asyncio
async def test_order_router_and_fsm_integration():
    """Validates OrderRouter execution with internal FSM coordination."""
    fsm = OmsFsm()
    router = OrderRouter(fsm=fsm)
    cmd = CanonicalOrderCommand(
        client_order_id="ORD_FSM_001",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=2,
        price=2.50
    )
    oid = uuid.uuid4()
    token = RiskApprovalToken(order_id=oid, timestamp_ns=1000000, signature="SIG_ROUTER")

    class MockBroker:
        def send_order(self, cmd, mode):
            return {"status": "SUCCESS"}

    routed_id = router.register_and_route(cmd, token, MockBroker(), mode_str="PAPER")
    assert routed_id == oid
    assert router.fsm.get_status(oid) == OrderStatus.SENT
