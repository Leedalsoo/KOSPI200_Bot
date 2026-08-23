# -*- coding: utf-8 -*-
import asyncio
import random
import uuid
from datetime import datetime

from core.contracts import OrderRequest, ExecutionReport, OrderStatus

class MockBrokerAdapter:
    """종이 매매(Paper Trading)를 지원하기 위한 무결점 가상 거래소 어댑터"""
    
    def __init__(self, chaos_mode: bool = False, simulated_liquidity: int = 100) -> None:
        self.chaos_mode: bool = chaos_mode
        self.simulated_liquidity: int = simulated_liquidity

    async def _inject_chaos_monkey(self) -> None:
        """[목표 C] 무작위 네트워크 지연 및 타임아웃 예외 주입"""
        if not self.chaos_mode:
            return
            
        prob = random.random()
        if prob < 0.025: # 2.5% 확률로 임의 지연
            delay = random.uniform(0.5, 3.0)
            await asyncio.sleep(delay)
        elif prob < 0.05: # 2.5% 확률로 타임아웃 예외
            raise asyncio.TimeoutError("Chaos Monkey injected TimeoutError")

    async def send_order(self, request: OrderRequest) -> ExecutionReport:
        """[목표 A, B] 무한 체결 착시 방어 및 100% 완벽한 체결 객체 조립"""
        await self._inject_chaos_monkey()
        
        filled_qty = min(request.qty, self.simulated_liquidity)
        remaining_qty = request.qty - filled_qty
        
        status = OrderStatus.FILLED if remaining_qty == 0 else OrderStatus.PARTIAL
        
        # OBI/BBO에서 온 가격이라 가정하고 그대로 체결 (Mocking)
        filled_price = request.price
        
        report = ExecutionReport(
            client_order_id=request.client_order_id,
            broker_order_id=str(uuid.uuid4()),
            fill_id=str(uuid.uuid4()),
            status=status,
            filled_qty=filled_qty,
            filled_price=filled_price,
            remaining_qty=remaining_qty,
            timestamp=datetime.now(),
            raw_response={"mock_status": "ok"} # orjson 호환 가능한 순수 dict
        )
        
        return report
