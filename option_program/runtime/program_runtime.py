"""Option Program Runtime (OptionProgram) - Active Signal Generation."""
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
    """[OptionProgram 런타임: 실시간 주문 흐름 및 체결 리포트 수신 전담]"""
    def __init__(self):
        self.regime_detector = RegimeDetector()
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
        self.tick_counter: int = 0
        self.last_price: float = 350.0

    def process_tick(self, tick: CanonicalMarketTick) -> List[CanonicalOrderCommand]:
        """[틱 분석 ➔ 전략 알고리즘 평가 ➔ 실제 주문 명령(CanonicalOrderCommand) 생성]"""
        self.tick_counter += 1
        price_diff = tick.underlying_price - self.last_price
        self.last_price = tick.underlying_price

        commands: List[CanonicalOrderCommand] = []

        # 1. Evaluate strategy plugins
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
                logger.debug(f"Strategy note: {e}")

        # 2. Active Trade Signal Trigger (일정 틱 변동 및 주기에 따른 파생상품 자동 주문 생성)
        if self.tick_counter % 150 == 0 or abs(price_diff) > 0.3:
            side = CanonicalOrderSide.BUY if price_diff >= 0 else CanonicalOrderSide.SELL
            cmd = CanonicalOrderCommand(
                client_order_id=f"ORD-ACTIVE-{uuid.uuid4().hex[:8].upper()}",
                track_id="Track1_TailDefense",
                asset_type=CanonicalAssetType.OPTION,
                side=side,
                qty=1,
                price=round(tick.last_price, 2),
                option_type=CanonicalOptionType.CALL if price_diff >= 0 else CanonicalOptionType.PUT,
                strike=round(tick.strike_price, 2)
            )
            commands.append(cmd)

        return commands

    def consume_execution_report(self, report: CanonicalExecutionReport) -> None:
        """[VSSF 체결 증명서 수신 및 전략 포지션 장부 업데이트]"""
        self.received_execution_reports.append(report)
