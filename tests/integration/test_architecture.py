# -*- coding: utf-8 -*-
import asyncio
import logging
import time
from decimal import Decimal
from typing import Any, Dict, List
from uuid import uuid4

import pytest

from core.base_agent import BaseAgent
from core.bus import EventBus, EventPriority
from core.contracts import OrderStatus, RiskApprovalToken
from fsm.oms_fsm import OmsFsm
from interface.controllers import ManualCommandController

logger = logging.getLogger(__name__)


class RiskAgent(BaseAgent):
    """통합 감사용 실시간 포트폴리오 리스크 합산 에이전트"""

    def __init__(self, bus: EventBus) -> None:
        self.bus: EventBus = bus
        self.deltas: Dict[str, Decimal] = {
            "track1": Decimal("0.0"),
            "track2": Decimal("0.0"),
            "track3": Decimal("0.0"),
            "track4": Decimal("0.0"),
        }
        self.bus.subscribe("STRATEGY_DELTA", self.process_message)

    @property
    def total_portfolio_delta(self) -> Decimal:
        """4개 전략의 델타 합산 연산"""
        return sum(self.deltas.values(), Decimal("0.0"))

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def health_check(self) -> bool:
        return True

    async def process_message(self, message: Dict[str, Any]) -> None:
        strategy_id = message.get("strategy_id")
        delta_val = Decimal(str(message.get("delta", "0.0")))
        if strategy_id in self.deltas:
            self.deltas[strategy_id] = delta_val
            logger.info("RiskAgent: 델타 트래킹 - %s = %s", strategy_id, delta_val)


class MockStrategyAgent(BaseAgent):
    """테스트용 가상 전략 에이전트"""

    def __init__(self, strategy_id: str, bus: EventBus) -> None:
        self.strategy_id: str = strategy_id
        self.bus: EventBus = bus
        self.status: str = "ACTIVE"
        self.current_delta: Decimal = Decimal("0.0")

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        self.status = "STANDBY"

    async def health_check(self) -> bool:
        return True

    async def update_market_tick(self, delta_change: Decimal) -> None:
        """가상 시장 틱을 수신하여 자신의 델타를 업데이트하고 버스로 브로드캐스팅"""
        self.current_delta += delta_change
        await self.bus.publish(
            EventPriority.RISK,
            "STRATEGY_DELTA",
            {"strategy_id": self.strategy_id, "delta": float(self.current_delta)},
        )

    async def process_message(self, message: Dict[str, Any]) -> None:
        # 셧다운 이벤트 수신 시 즉시 STANDBY 전이
        if message.get("action") == "SHUTDOWN":
            await self.stop()


@pytest.mark.asyncio
async def test_delta_and_risk_aggregation_precision() -> None:
    """[통합 검증 1] 델타/리스크 합산 무결성 검증 (오차율 0.0001 이하)"""
    bus = EventBus()
    risk_agent = RiskAgent(bus)

    # 4개 전략 에이전트 가동
    strategies = [
        MockStrategyAgent("track1", bus),
        MockStrategyAgent("track2", bus),
        MockStrategyAgent("track3", bus),
        MockStrategyAgent("track4", bus),
    ]

    # 이벤트 버스 백그라운드 태스크 기동
    bus_task = asyncio.create_task(bus.process_events())

    try:
        # 가상의 시장 틱에 의한 델타 변동 주입
        # 정밀 소수점 델타 설정
        delta_inputs = {
            "track1": Decimal("0.1234"),
            "track2": Decimal("-0.5678"),
            "track3": Decimal("0.8901"),
            "track4": Decimal("-0.4456"),
        }

        # 병렬로 버스에 델타 이벤트 전파
        await asyncio.gather(
            *[
                strategies[i].update_market_tick(delta_inputs[strategies[i].strategy_id])
                for i in range(4)
            ]
        )

        # 버스 큐의 모든 작업이 처리될 때까지 미세 양보
        await asyncio.sleep(0.05)

        # [실시간 감사] 합산 델타 검증
        calculated = risk_agent.total_portfolio_delta
        expected = sum(delta_inputs.values(), Decimal("0.0"))
        error_rate = abs(calculated - expected)

        logger.info("결과보고 - [통합 델타 오차율]: (계산값: %s vs 이론값: %s)", calculated, expected)
        assert error_rate < Decimal("0.0001"), f"델타 합산 오차 초과: {error_rate}"

    finally:
        bus._running = False
        bus_task.cancel()
        try:
            await bus_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_event_bus_throughput_tolerance() -> None:
    """[통합 검증 2] 이벤트 버스 부하 내성 (초당 1000건 메시지 누락 없는 처리)"""
    bus = EventBus()
    processed_count = 0
    futures: List[asyncio.Future[None]] = []

    async def callback(data: Any) -> None:
        nonlocal processed_count
        processed_count += 1
        if processed_count >= 1000:
            for fut in futures:
                if not fut.done():
                    fut.set_result(None)

    # 이벤트 구독 등록
    bus.subscribe("HIGH_SPEED_TICK", callback)
    bus_task = asyncio.create_task(bus.process_events())

    # 완료 시그널 대기를 위한 퓨처 구성
    done_future: asyncio.Future[None] = asyncio.Future()
    futures.append(done_future)

    try:
        start_time = time.perf_counter()

        # 4개 전략이 분할하여 초당 1,000건의 메시지를 퍼블리시하는 구조 시뮬레이션 (태스크당 250건)
        async def publish_task(task_id: int) -> None:
            for i in range(250):
                await bus.publish(
                    EventPriority.TICK,
                    "HIGH_SPEED_TICK",
                    {"task_id": task_id, "seq": i},
                )

        # 4개 퍼블리셔 병렬 기동
        await asyncio.gather(*[publish_task(i) for i in range(4)])

        # 데드락 방지 지령: 0.2초 이내에 1000건 처리가 완료되는지 타임아웃 감시
        await asyncio.wait_for(done_future, timeout=0.2)
        end_time = time.perf_counter()

        elapsed = end_time - start_time
        throughput = processed_count / elapsed
        logger.info("결과보고 - [이벤트 버스 처리량]: (초당 %d 건 메시지 처리 완료)", int(throughput))

        assert processed_count == 1000, f"메시지 누락 발생: {processed_count}/1000"

    except asyncio.TimeoutError:
        logger.error("시스템 기동 실패: 0.1초 이상 반응 없음 (Deadlock 방지 걸림)")
        raise AssertionError("EventBus Throughput Test Timed Out (Deadlock)")
    finally:
        bus._running = False
        bus_task.cancel()
        try:
            await bus_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_panic_halt_cascading_reaction() -> None:
    """[통합 검증 3] Panic Halt 연쇄 반응 (0.5초 이내 모든 에이전트 STANDBY 전이 및 주문 취소)"""
    fsm = OmsFsm()
    controller = ManualCommandController(fsm)
    bus = EventBus()

    # 4개 전략 에이전트와 버스 연동 설정
    strategies = [
        MockStrategyAgent("track1", bus),
        MockStrategyAgent("track2", bus),
        MockStrategyAgent("track3", bus),
        MockStrategyAgent("track4", bus),
    ]

    for strat in strategies:
        bus.subscribe("SHUTDOWN_BROADCAST", strat.process_message)

    bus_task = asyncio.create_task(bus.process_events())

    # 모의 미체결 주문 등록
    order_ids = [uuid4() for _ in range(10)]
    for oid in order_ids:
        # FSM에 임의 토큰 등록
        token = RiskApprovalToken(oid, time.time_ns(), "sig")
        await fsm.register_order(token)
        # 상태를 NEW 또는 SENT로 변경
        await fsm.transition(oid, OrderStatus.SENT)

    try:
        # 데드맨/Panic Halt 발동 지연 시간 측정
        start_time = time.perf_counter()

        # 1. Panic Halt 발동
        await controller.trigger_panic_halt(order_ids)

        # 2. 버스를 통한 전략 셧다운 패킷 브로드캐스팅
        await bus.publish(
            EventPriority.SYSTEM,
            "SHUTDOWN_BROADCAST",
            {"action": "SHUTDOWN"},
        )

        # 이벤트 전파 대기
        await asyncio.sleep(0.05)
        end_time = time.perf_counter()

        elapsed = end_time - start_time
        logger.info("결과보고 - [셧다운 지연 시간]: (통제 완료까지 %f 초 소요)", elapsed)

        # 0.5초 이내 처리 완료 단언
        assert elapsed < 0.5, f"셧다운 지연 규격 초과: {elapsed}s"

        # 모든 전략 에이전트가 STANDBY 상태로 전이되었는지 단언
        for strat in strategies:
            assert strat.status == "STANDBY", f"{strat.strategy_id}가 STANDBY 상태가 아닙니다."

        # 모든 주문이 FSM 상에서 CANCELLED 상태인지 단언
        for oid in order_ids:
            assert fsm.get_status(oid) == OrderStatus.CANCELLED, f"주문 {oid}가 취소되지 않았습니다."

    finally:
        bus._running = False
        bus_task.cancel()
        try:
            await bus_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_concurrency_race_condition_fsm_atomicity() -> None:
    """[통합 레드팀 방어 지령] 4개 전략이 동시에 동일 주문의 상태를 변경할 때의 FSM 원자성(Lock) 검증"""
    fsm = OmsFsm()
    order_id = uuid4()

    # 주문 사전 등록
    token = RiskApprovalToken(order_id, time.time_ns(), "sig")
    await fsm.register_order(token)

    # 4개 전략이 동시에 상태 전이를 요청하는 레이스 컨디션 시뮬레이션
    target_states = [
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.REJECTED,
        OrderStatus.STANDBY_OVERRIDE,
    ]

    async def race_transition(status: OrderStatus) -> None:
        # 약간의 지연 후 호출하여 동시 경합 유도
        await asyncio.sleep(0.01)
        await fsm.transition(order_id, status)

    # 4개 코루틴을 병렬 실행하여 FSM Double-checked Locking 및 asyncio.Lock 안정성 확인
    await asyncio.gather(*[race_transition(state) for state in target_states])

    # FSM 상의 최종 상태가 위 target_states 리스트의 상태 중 하나여야 하며, 에러가 발생하지 않아야 함
    final_status = fsm.get_status(order_id)
    assert final_status in target_states
    logger.info("FSM 원자성 검증 완료: 최종 상태 = %s", final_status)
