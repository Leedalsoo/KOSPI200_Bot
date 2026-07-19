# -*- coding: utf-8 -*-
import asyncio
import pytest
import orjson
from uuid import uuid4, UUID

from fsm.oms_fsm import OmsFsm
from core.contracts import OrderStatus
from interface.controllers import ManualCommandController


def _seed_order(fsm: OmsFsm, order_id: UUID) -> None:
    """테스트 전용: FSM states 딕셔너리에 직접 주문 등록 (토큰 없이 상태 주입)"""
    fsm.states[order_id] = OrderStatus.SENT


@pytest.mark.asyncio
async def test_panic_halt_fsm_override() -> None:
    """[목표 B 검증] Panic Halt 호출 시 주문이 CANCELLED로 강제 전이되는지 증명"""
    fsm = OmsFsm()
    controller = ManualCommandController(fsm)
    oid = uuid4()
    _seed_order(fsm, oid)

    await controller.trigger_panic_halt([oid])
    assert fsm.get_status(oid) == OrderStatus.CANCELLED


@pytest.mark.asyncio
async def test_override_payload_parsing_safety() -> None:
    """[목표 A 검증] 오염된 Payload 주입 시 크래시 없이 격리되는지 증명"""
    fsm = OmsFsm()
    controller = ManualCommandController(fsm)
    bad_payload = b"{invalid_json_data}"

    # 예외가 밖으로 던져지지 않고 내부적으로 처리(격리)되는지 확인
    try:
        await controller.override_position(bad_payload)
    except Exception:
        pytest.fail("Payload 파싱 에러가 밖으로 전파됨")


@pytest.mark.asyncio
async def test_panic_halt_idempotency() -> None:
    """[목표 B 검증] 이미 셧다운된 시스템에 중복 PANIC HALT 명령 시 무시(Idempotency) 증명"""
    fsm = OmsFsm()
    controller = ManualCommandController(fsm)
    oid = uuid4()
    _seed_order(fsm, oid)

    await controller.trigger_panic_halt([oid])
    assert fsm.get_status(oid) == OrderStatus.CANCELLED

    # 두 번째 호출은 상태 변화 없이 무시되어야 함
    await controller.trigger_panic_halt([oid])
    assert fsm.get_status(oid) == OrderStatus.CANCELLED


@pytest.mark.asyncio
async def test_override_valid_panic_halt_command() -> None:
    """[목표 A 검증] 유효한 PANIC_HALT 명령 Payload 처리 시 주문 CANCELLED 전이 증명"""
    fsm = OmsFsm()
    controller = ManualCommandController(fsm)
    oid = uuid4()
    _seed_order(fsm, oid)

    payload = orjson.dumps({"command": "PANIC_HALT", "order_ids": [str(oid)]})
    await controller.override_position(payload)

    assert fsm.get_status(oid) == OrderStatus.CANCELLED


@pytest.mark.asyncio
async def test_log_masking_sensitive_fields() -> None:
    """[목표 A 검증] api_key 등 민감 필드가 마스킹되어 시스템이 크래시되지 않음을 증명"""
    from interface.controllers import _mask_payload

    data = {"command": "PANIC_HALT", "order_ids": [], "api_key": "SECRET123", "token": "abc"}
    masked = _mask_payload(data)

    assert masked["api_key"] == "***"
    assert masked["token"] == "***"
    assert masked["command"] == "PANIC_HALT"  # 비민감 필드는 원본 유지


@pytest.mark.asyncio
async def test_deadman_switch_triggers_halt() -> None:
    """[목표 C 검증] Heartbeat 타임아웃 시 PANIC HALT 자동 발동 증명"""
    fsm = OmsFsm()
    controller = ManualCommandController(fsm)
    oid = uuid4()
    _seed_order(fsm, oid)

    # 타임아웃을 0.1초로 단축하여 테스트 속도 확보
    import interface.controllers as ctrl_mod
    original_timeout = ctrl_mod._DEADMAN_TIMEOUT
    ctrl_mod._DEADMAN_TIMEOUT = 0.1

    try:
        await controller.start_deadman_switch([oid])
        # Heartbeat 없이 타임아웃보다 긴 시간 대기
        await asyncio.sleep(0.35)
        assert fsm.get_status(oid) == OrderStatus.CANCELLED
    finally:
        ctrl_mod._DEADMAN_TIMEOUT = original_timeout
        await controller.stop_deadman_switch()
