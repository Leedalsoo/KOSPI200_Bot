"""Option Program Runtime (OptionProgram)."""
import logging
import uuid
from typing import List, Optional, Dict, Any
from shared.contracts.canonical import (
    CanonicalMarketTick,
    CanonicalOrderCommand,
    CanonicalExecutionReport,
    CanonicalOrderSide,
    CanonicalAssetType,
    CanonicalOptionType
)
from strategy.plugins.track1 import Track1
from strategy.plugins.track2 import Track2
from strategy.plugins.track3 import Track3
from strategy.plugins.track4 import Track4
from strategy.plugins.track5 import Track5
from strategy.plugins.track6 import Track6
from strategy.plugins.track7 import Track7
from strategy.plugins.track8 import Track8
from strategy.plugins.track9 import Track9

from strategy.regime_detector import RegimeDetector

logger = logging.getLogger(__name__)

class OptionProgramRuntime:
    """[OptionProgram 런타임: 센서 감지 ➔ 전략 평가 ➔ 주문 명령 생성 ➔ 체결 리포트 수신]"""
    def __init__(self):
        # 1. Regime Sensor
        self.regime_detector = RegimeDetector()

        # 2. Strategy Plugins (Track 1 ~ 9)
        self.strategies = [
            Track1(config={}),
            Track2(config={}),
            Track3(config={}),
            Track4(config={}),
            Track5(config={}),
            Track6(config={}),
            Track7(config={}),
            Track8(config={}),
            Track9(config={})
        ]
        self.received_execution_reports: List[CanonicalExecutionReport] = []

    def process_tick(self, tick: CanonicalMarketTick) -> List[CanonicalOrderCommand]:
        """[틱 수신 ➔ 센서 및 전략 평가 ➔ CanonicalOrderCommand 변환 발행]"""
        commands: List[CanonicalOrderCommand] = []
        
        # Evaluate strategies safely
        for st in self.strategies:
            try:
                if hasattr(st, "on_tick"):
                    signals = st.on_tick(tick.underlying_price, tick.timestamp)
                    if signals:
                        for sig in signals:
                            cmd = CanonicalOrderCommand(
                                client_order_id=f"ORD-{uuid.uuid4().hex[:8].upper()}",
                                track_id=getattr(st, "name", st.__class__.__name__),
                                asset_type=CanonicalAssetType.OPTION if sig.get("asset") == "OPTION" else CanonicalAssetType.FUTURES,
                                side=CanonicalOrderSide.BUY if sig.get("side") == "BUY" else CanonicalOrderSide.SELL,
                                qty=int(sig.get("qty", 1)),
                                price=float(sig.get("price", tick.last_price)),
                                option_type=CanonicalOptionType.CALL if sig.get("option_type") == "CALL" else CanonicalOptionType.PUT,
                                strike=float(sig.get("strike", tick.strike_price)),
                                tag_id=str(sig.get("tag_id", ""))
                            )
                            commands.append(cmd)
            except Exception as e:
                logger.debug(f"Strategy evaluation note: {e}")
                
        return commands

    def consume_execution_report(self, report: CanonicalExecutionReport) -> None:
        """[VSSF로부터 전송받은 체결 증명서 수신 및 전략 포지션 상태 업데이트]"""
        self.received_execution_reports.append(report)
        logger.info(f"[OptionProgram Report Received] {report.client_order_id} -> {report.executed_qty}qty @ ₩{report.executed_price}")
