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

        # 2. Track 1 ~ Track 9 전략 평가 (실제 고유 인터페이스 호출 및 주문 명령 생성)
        for st in self.strategies:
            st_name = getattr(st, "name", st.__class__.__name__)
            m = self.strategy_metrics[st_name]
            m["ticks_evaluated"] += 1
            signals: List[Dict[str, Any]] = []

            try:
                date_str = "2026-08-23"
                if st_name == "Track1":
                    is_bull = (self.current_regime == "BULL")
                    raw_signals = st.on_tick(
                        current_price=tick.underlying_price,
                        trend_signal=is_bull,
                        days_to_expiry=30.0,
                        current_date=date_str
                    )
                    if isinstance(raw_signals, list):
                        signals.extend(raw_signals)

                elif st_name == "Track2":
                    trap_res = st.evaluate_trap_status(tick.underlying_price)
                    if trap_res.get("signals"):
                        signals.extend(trap_res["signals"])
                    elif trap_res.get("action") in ["ENTER", "BUY", "SELL"]:
                        signals.append(trap_res)

                elif st_name == "Track3":
                    m_data = {
                        "underlying_price": tick.underlying_price,
                        "time_str": "09:30:00",
                        "atm_strike": 350.0,
                        "near_synthetic_future": tick.underlying_price + 0.05,
                        "far_synthetic_future": tick.underlying_price + 0.10,
                        "active_vol": 1.0,
                    }
                    arb_res = st.evaluate_arbitrage(m_data)
                    if arb_res.get("signals"):
                        signals.extend(arb_res["signals"])
                    elif arb_res.get("action") in ["ENTER", "BUY", "SELL"]:
                        signals.append(arb_res)

                elif st_name == "Track4":
                    sc_res = st.evaluate_scalping_basecamp_entry(
                        current_price=tick.underlying_price,
                        active_vol=1.0,
                        base_vol=1.0,
                        date_str=date_str,
                        time_str="09:15:00"
                    )
                    if sc_res.get("signals"):
                        signals.extend(sc_res["signals"])
                    elif sc_res.get("action") in ["ENTER", "BUY", "SELL"]:
                        signals.append(sc_res)

                elif st_name == "Track5":
                    m_res = st.evaluate_mean_reversion(tick.underlying_price)
                    if m_res.get("signals"):
                        signals.extend(m_res["signals"])
                    elif m_res.get("action") in ["ENTER", "BUY", "SELL"]:
                        signals.append(m_res)

                elif st_name == "Track6":
                    ins_res = st.evaluate_insurance_buy(
                        current_price=tick.underlying_price,
                        active_vol=1.0,
                        base_vol=1.0,
                        budget=1000000.0,
                        date_str=date_str,
                        time_str="09:00:00"
                    )
                    if ins_res.get("signals"):
                        signals.extend(ins_res["signals"])
                    elif ins_res.get("action") in ["ENTER", "BUY", "SELL"]:
                        signals.append(ins_res)

                elif st_name == "Track7":
                    ins7 = st.evaluate_insurance_buy(
                        current_price=tick.underlying_price,
                        budget=1000000.0,
                        date_str=date_str,
                        is_new_week_start=True,
                        active_vol=1.0,
                        time_str="09:00:00"
                    )
                    if ins7.get("signals"):
                        signals.extend(ins7["signals"])
                    elif ins7.get("action") in ["ENTER", "BUY", "SELL"]:
                        signals.append(ins7)

                elif st_name == "Track8":
                    ent8 = st.evaluate_entry(
                        dte=30.0,
                        budget=2000000.0,
                        current_price=tick.underlying_price,
                        current_regime=self.current_regime,
                        date_str=date_str
                    )
                    if ent8.get("signals"):
                        signals.extend(ent8["signals"])
                    elif ent8.get("action") in ["ENTER", "BUY", "SELL"]:
                        signals.append(ent8)

                elif st_name == "Track9":
                    ins9 = st.evaluate_insurance(
                        current_price=tick.underlying_price,
                        active_sell_qty=2,
                        current_ins_qty=0,
                        date_str=date_str
                    )
                    if ins9.get("signals"):
                        signals.extend(ins9["signals"])
                    elif ins9.get("action") in ["ENTER", "BUY", "SELL"]:
                        signals.append(ins9)

                # 시그널 변환 및 명령 적재
                if signals:
                    m["signals_generated"] += len(signals)
                    for local_seq, sig in enumerate(signals, start=1):
                        seq_num = tick.seq_id if tick.seq_id > 0 else self.tick_counter
                        det_order_id = f"ORD-T{seq_num}-{st_name}-{local_seq}"
                        
                        cmd = CanonicalOrderCommand(
                            client_order_id=det_order_id,
                            track_id=st_name,
                            asset_type=CanonicalAssetType.OPTION if sig.get("asset") == "OPTION" or sig.get("type") in ["CALL", "PUT"] else CanonicalAssetType.FUTURES,
                            side=CanonicalOrderSide.BUY if sig.get("side", "BUY") == "BUY" else CanonicalOrderSide.SELL,
                            qty=int(sig.get("qty", 1)),
                            price=float(sig.get("price", tick.last_price)),
                            option_type=CanonicalOptionType.CALL if sig.get("option_type") == "CALL" or sig.get("type") == "CALL" else CanonicalOptionType.PUT,
                            strike=float(sig.get("strike", tick.strike_price)),
                            tag_id=str(sig.get("tag_id", ""))
                        )
                        commands.append(cmd)
                        m["orders_created"] += 1

            except Exception as e:
                m["exceptions"] += 1
                logger.error(f"Strategy {st_name} execution error: {e}", exc_info=True)

        return commands



    def consume_execution_report(self, report: CanonicalExecutionReport) -> None:
        """[VSSF 체결 증명서 수신 및 전략 포지션 장부 업데이트]"""
        self.received_execution_reports.append(report)
