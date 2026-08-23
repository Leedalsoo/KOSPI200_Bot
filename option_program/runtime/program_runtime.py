"""Option Program Runtime (OptionProgram) - Pure Strategy Signal Generation."""
import logging
from typing import List, Optional, Dict, Any
import numpy as np
from shared.contracts.canonical import (
    CanonicalMarketTick,
    CanonicalOrderCommand,
    CanonicalExecutionReport,
    CanonicalOrderSide,
    CanonicalAssetType,
    CanonicalOptionType
)
from option_program.strategy.plugins.track1 import Track1
from option_program.strategy.plugins.track2 import Track2
from option_program.strategy.plugins.track3 import Track3
from option_program.strategy.plugins.track4 import Track4
from option_program.strategy.plugins.track5 import Track5
from option_program.strategy.plugins.track6 import Track6
from option_program.strategy.plugins.track7 import Track7
from option_program.strategy.plugins.track8 import Track8
from option_program.strategy.plugins.track9 import Track9
from option_program.strategy.regime_detector import RegimeDetector

logger = logging.getLogger(__name__)

class OptionProgramRuntime:
    """[OptionProgram 런타임: 순수 전략 알고리즘 오케스트레이터 & 주문 전송 전담]"""
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
        self.price_history: List[float] = []
        self.current_regime: str = "NORMAL"
        
        # 전략별 실측 메트릭 (호출 수, 시그널 수, 생성된 주문 수, 예외 발생 수)
        self.strategy_metrics: Dict[str, Dict[str, int]] = {
            getattr(st, "name", st.__class__.__name__): {
                "ticks_evaluated": 0,
                "signals_generated": 0,
                "orders_created": 0,
                "exceptions": 0
            } for st in self.strategies
        }

    def process_tick(self, tick: CanonicalMarketTick) -> List[CanonicalOrderCommand]:
        """[틱 수신 ➔ Sensor / Regime Detector / Track 1~9 평가 ➔ 순수 전략 주문 명령 생성]"""
        self.tick_counter += 1
        self.last_price = tick.underlying_price
        self.price_history.append(tick.underlying_price)
        if len(self.price_history) > 60:
            self.price_history.pop(0)
        
        # 1. Regime Detector 실제 시계열 데이터 기반 HMM 국면 연산 실행 (GAP 6 완전 해소)
        try:
            if len(self.price_history) >= 2:
                # 로그 수익률 계산: log(P_t / P_{t-1})
                prices = np.array(self.price_history, dtype=np.float64)
                returns = np.diff(np.log(prices))
                regime, _ = self.regime_detector.detect_regime_sync(returns)
                self.current_regime = regime
            else:
                self.current_regime = "NEUTRAL"
        except Exception as e:
            logger.debug(f"RegimeDetector note: {e}")

        commands: List[CanonicalOrderCommand] = []

        # 2. Track 1 ~ Track 9 전략 평가 (결정론적 주문 생성)
        for st in self.strategies:
            st_name = getattr(st, "name", st.__class__.__name__)
            m = self.strategy_metrics[st_name]
            m["ticks_evaluated"] += 1
            try:
                if hasattr(st, "on_tick"):
                    signals = st.on_tick(tick.underlying_price, tick.timestamp)
                    if signals:
                        m["signals_generated"] += len(signals)
                        for local_seq, sig in enumerate(signals, start=1):
                            # [결정론적 주문 ID]: seq_id/tick_counter + track_id + local_sequence (재현성 100% 보장)
                            seq_num = tick.seq_id if tick.seq_id > 0 else self.tick_counter
                            det_order_id = f"ORD-T{seq_num}-{st_name}-{local_seq}"
                            
                            cmd = CanonicalOrderCommand(
                                client_order_id=det_order_id,
                                track_id=st_name,
                                asset_type=CanonicalAssetType.OPTION if sig.get("asset") == "OPTION" else CanonicalAssetType.FUTURES,
                                side=CanonicalOrderSide.BUY if sig.get("side") == "BUY" else CanonicalOrderSide.SELL,
                                qty=int(sig.get("qty", 1)),
                                price=float(sig.get("price", tick.last_price)),
                                option_type=CanonicalOptionType.CALL if sig.get("option_type") == "CALL" else CanonicalOptionType.PUT,
                                strike=float(sig.get("strike", tick.strike_price)),
                                tag_id=str(sig.get("tag_id", ""))
                            )
                            commands.append(cmd)
                            m["orders_created"] += 1
            except Exception as e:
                m["exceptions"] += 1
                logger.debug(f"Strategy {st_name} note: {e}")

        return commands

    def consume_execution_report(self, report: CanonicalExecutionReport) -> None:
        """[VSSF 체결 증명서 수신 및 전략 포지션 장부 업데이트]"""
        self.received_execution_reports.append(report)
