import orjson
import logging
from typing import Callable, Awaitable
from .state import SessionContext

logger = logging.getLogger(__name__)

class TelemetryPublisher:
    """
    프론트엔드 대시보드(HFT_Control_Panel.html)와의 WebSocket 통신을 담당
    """
    def __init__(self, broadcast_callback: Callable[[bytes], Awaitable[None]]):
        self.broadcast_callback = broadcast_callback
        
    async def publish_snapshot(self, ctx: SessionContext) -> None:
        """
        SessionContext를 받아 프론트엔드와 약속된 스키마에 맞춰 JSON 직렬화 후 전송
        """
        # 틱 데이터를 HFT_Control_Panel이 인식할 수 있는 규격으로 패키징
        packet = {
            "sessionId": ctx.session_id,
            "type": "tick",
            "date": getattr(ctx, "sim_date", "2025-01-01"),
            "time": getattr(ctx, "sim_time", "09:00:00"),
            "underlyingPrice": ctx.current_price,
            "regime": ctx.current_regime,
            "bidAskSpread": 0.25,
            
            # 자본 및 증거금
            "capital": ctx.account.current_capital,
            "reserve": ctx.account.accumulated_reserve,
            "usedMargin": ctx.account.used_margin,
            "marginRatio": ctx.account.margin_ratio,
            "budgetPool": getattr(ctx, "insurance_budget_pool", 0.0),
            
            # 포트폴리오
            "portfolioOptions": ctx.portfolio.options,
            "futuresQty": ctx.portfolio.current_position_qty,
            
            # UI 전용 필드들
            "coord": {
                "x": getattr(ctx, "seq", 0),
                "y": ctx.account.total_equity,
                "date": getattr(ctx, "sim_date", "2025-01-01"),
                "dte": f"D-{int(getattr(ctx, 'days_to_expiry', 15))}",
                "dayLabel": getattr(ctx, "sim_date", "2025-01-01")
            },
            "strategyWeights": getattr(ctx, "strategy_weights", {
                "Track 1 (Defense)": 100, 
                "Track 2 (Trap)": 0,
                "Track 3 (Arbitrage)": 0,
                "Track 4 (Gamma)": 0,
                "Track 5 (Gap)": 0,
                "Track 6 (Daily)": 0,
                "Track 7 (Weekly)": 0,
                "Track 8 (Monthly)": 0
            }),
            "strategyPnL": getattr(ctx, "strategy_pnl", {}),
            "payoffCoords": [],
            
            # 상태 플래그
            "autobotActive": getattr(ctx, "autobot_active", True),
            "circuitBreaker": getattr(ctx.risk, "circuit_breaker", False),
            "mainEngineBroken": ctx.risk.main_engine_broken,
            "daysToExpiry": getattr(ctx, 'days_to_expiry', 15.0),
            "is_market_open": True,
            "simStartDateTime": "2025-01-01 09:00:00",
            "simEndDateTime": "2025-12-31 15:45:00",
            "eventLogs": getattr(ctx, "event_logs", [])
        }
        
        try:
            # 딕셔너리를 orjson으로 직렬화 후 문자열로 변환
            msg_bytes = orjson.dumps(packet)
            msg_str = msg_bytes.decode('utf-8')
            await self.broadcast_callback(msg_str)
        except Exception as e:
            logger.error(f"Error serializing telemetry packet: {e}")
