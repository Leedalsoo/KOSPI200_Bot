# -*- coding: utf-8 -*-
from typing import Dict, Any
import orjson
from core.bus import EventBus, EventPriority

class SensorFeedback:
    """전략 매매 파라미터 동적 튜닝을 위한 피드백 센서"""
    
    def __init__(self, bus: EventBus) -> None:
        self.bus: EventBus = bus

    async def emit_insight(
        self,
        target_strategy_id: str,
        average_slippage: float,
        latency_ms: float
    ) -> None:
        """[목표 A, B, C] SensorInsight 봉투 생성, orjson 직렬화, 최하위 우선순위 전파"""
        # 🛡️ [타입 안전성] 호출부에서 float 오차를 최소화하기 위해 소수 6자리 반올림 처리
        safe_slippage = round(average_slippage, 6)
        safe_latency = round(latency_ms, 6)

        # [목표 A, B] SensorInsight 봉투 구성 (타겟 전략 ID 포함)
        envelope: Dict[str, Any] = {
            "target_strategy_id": target_strategy_id,
            "average_slippage": safe_slippage,
            "latency_ms": safe_latency,
        }

        # [목표 C] orjson 초고속 직렬화 후 다시 dict 로 역직렬화하여 payload 전달
        # → bytes를 불필요하게 가공하지 않고 원시 dict 구조로 전달하여 직렬화 병목 0 유지
        payload: Dict[str, Any] = orjson.loads(orjson.dumps(envelope))

        # [목표 A] 최하위 우선순위(SYSTEM)로 퍼블리시하여 핵심 흐름 비간섭 보장
        await self.bus.publish(EventPriority.SYSTEM, f"SENSOR_INSIGHT:{target_strategy_id}", payload)
