import asyncio
import logging
import os
from datetime import datetime
import orjson
import websockets
from typing import Set

from .core.state import SessionContext
from .core.market_feed import VirtualMarketFeed
from .core.strategy_engine import StrategyOrchestrator
from .core.execution_agent import ExecutionAgent
from .core.telemetry import TelemetryPublisher

logger = logging.getLogger(__name__)

class MockSimulationServer:
    """
    모놀리식 구조(mock_ws_server.py)를 해체하여, 
    핵심 계층(Feed, Strategy, Execution, Telemetry)을 조립하는 새로운 진입점 서버
    """
    def __init__(self):
        self.connected_clients: Set[websockets.WebSocketServerProtocol] = set()
        self.context = SessionContext()
        
        self.feed = VirtualMarketFeed()
        self.orchestrator = StrategyOrchestrator()
        self.execution = ExecutionAgent()
        
        # Telemetry는 브로드캐스트 콜백 주입
        self.telemetry = TelemetryPublisher(self.broadcast)
        
        self.is_running = False

    async def broadcast(self, message: bytes) -> None:
        """웹소켓 클라이언트 전체에게 메시지 브로드캐스트"""
        if not self.connected_clients:
            return
        
        disconnected = set()
        for ws in self.connected_clients:
            try:
                await ws.send(message)
            except websockets.ConnectionClosed:
                disconnected.add(ws)
                
        for ws in disconnected:
            self.connected_clients.remove(ws)

    async def simulation_loop(self):
        """Phase 4: 순수 함수형 코어 루프"""
        logger.info("Starting pure functional simulation loop...")
        self.context.seq = 0
        self.is_running = True
        last_sim_date = ""
        
        while self.is_running:
            try:
                # 1. Market Data Ingestion
                price, regime, is_halted = self.feed.next_tick()
                current_date_str = self.feed.sim_date.strftime("%Y-%m-%d")
                date_changed = (last_sim_date != "" and last_sim_date != current_date_str)
                last_sim_date = current_date_str
                
                self.context.current_price = price
                self.context.current_regime = regime
                self.context.seq += 1
                
                # 캘린더 동기화
                self.context.sim_date = self.feed.sim_date.strftime("%Y-%m-%d")
                self.context.sim_time = self.feed.sim_date.strftime("%H:%M:%S")
                self.context.days_to_expiry = getattr(self.feed, 'days_to_expiry', 15.0)
                
                # 15:45 마감 및 일자 변경(롤오버) 처리
                if date_changed:
                    is_expiry = (self.context.days_to_expiry <= 0.1 or self.feed.calendar.remaining_days <= 1)
                    self.execution.process_settlement(self.context, is_expiry=is_expiry)
                
                # 이벤트 로그 리셋
                if not hasattr(self.context, "event_logs"):
                    self.context.event_logs = []
                
                # 2. Risk Management (Pre-trade)
                self.execution.check_risk_lockdown(self.context)
                
                # 3. Strategy Evaluation (Pure Function)
                if getattr(self.context, "autobot_active", True):
                    orders = self.orchestrator.process_tick(self.context)
                else:
                    orders = []
                
                # 4. Order Execution & State Update
                self.execution.execute_orders(self.context, orders)
                
                # 5. Telemetry Broadcast
                await self.telemetry.publish_snapshot(self.context)
                
                # 틱 지연 (모의 100ms)
                await asyncio.sleep(0.1)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in simulation loop: {e}")
                await asyncio.sleep(1)
        
        # 루프 종료 시 보고서 생성 (Ctrl+C 등)
        self.generate_report()

    def generate_report(self):
        """시뮬레이션 종료 시 결과 보고서 마크다운 출력"""
        try:
            report_text = "# KOSPI200 HFT Simulation Report\n\n"
            report_text += f"- **End Time:** {self.context.sim_date} {self.context.sim_time}\n"
            report_text += f"- **Final Capital:** ₩{self.context.account.current_capital:,.0f}\n"
            report_text += f"- **Final Equity:** ₩{self.context.account.total_equity:,.0f}\n"
            report_text += f"- **Positions:** {self.context.portfolio.current_position_qty} Futures, {len(self.context.portfolio.options)} Options\n\n"
            
            with open("test_report.md", "w", encoding="utf-8") as f:
                f.write(report_text)
            logger.info("📄 test_report.md 생성 완료!")
        except Exception as e:
            logger.error(f"보고서 생성 실패: {e}")

    async def ws_handler(self, websocket: websockets.WebSocketServerProtocol):
        """클라이언트 접속 및 메시지 처리"""
        self.connected_clients.add(websocket)
        logger.info("Client connected to V2 server")
        
        try:
            async for message in websocket:
                try:
                    data = orjson.loads(message)
                    action = data.get("action")
                    
                    if action == "start_bot":
                        self.context.autobot_active = True
                        logger.info("Autobot ACTIVATED")
                    elif action == "stop_bot":
                        self.context.autobot_active = False
                        logger.info("Autobot DEACTIVATED")
                    elif action == "update_settings":
                        # 기존 설정 주입 로직
                        settings = data.get("settings", {})
                        logger.info(f"Settings updated: {settings}")
                        
                except Exception as e:
                    logger.error(f"Message parsing error: {e}")
        finally:
            if websocket in self.connected_clients:
                self.connected_clients.remove(websocket)

async def main():
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    log_filename = os.path.join(log_dir, f"simulation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    server = MockSimulationServer()
    
    # 웹소켓 서버 구동
    await websockets.serve(server.ws_handler, "0.0.0.0", 8082)
    logger.info("V2 Server started on ws://0.0.0.0:8082/ws")
    
    # 메인 시뮬레이션 루프 구동
    await server.simulation_loop()

if __name__ == "__main__":
    asyncio.run(main())
