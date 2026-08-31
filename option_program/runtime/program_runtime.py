"""Option Program Runtime (OptionProgram) - Pure Strategy Signal Generation."""
import logging
import time
from typing import List, Optional, Dict, Any
import numpy as np
from shared.contracts.canonical import (
    CanonicalMarketTick,
    CanonicalOrderCommand,
    CanonicalExecutionReport,
    CanonicalOrderSide,
    CanonicalAssetType,
    CanonicalOptionType,
    CanonicalStrategySignal,
    CanonicalAccountSummary
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
from option_program.strategy.signal_generator import SignalGenerator
from option_program.strategy.decision_arbiter import DecisionArbiter
from option_program.risk_control.risk_engine import RiskConfig, RiskSensor, RiskEngine, RiskGate
from option_program.orders.oms_fsm import OmsFsm
from option_program.orders.order_router import OrderRouter
from option_program.market_analysis.market_condition_analyzer import MarketConditionAnalyzer
from option_program.market_analysis.market_condition_models import MarketConditionSnapshot

logger = logging.getLogger(__name__)

class OptionProgramRuntime:
    """[OptionProgram 런타임: 순수 전략 알고리즘 -> SignalGenerator -> DecisionArbiter -> RiskGate -> OrderRouter FSM 오케스트레이터]"""
    def __init__(
        self,
        risk_config: Optional[RiskConfig] = None,
        account_summary: Optional[CanonicalAccountSummary] = None,
        wal_store: Optional[Any] = None,
    ):
        self.regime_detector = RegimeDetector()
        self.strategies: List[Any] = [
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
        
        # 완전한 파이프라인 컴포넌트 실체화
        self.signal_generator = SignalGenerator(debounce_window_sec=0.0) # 결정론적 틱 단위 파이프라인
        self.decision_arbiter = DecisionArbiter()
        self.risk_config = risk_config or RiskConfig()
        self.risk_sensor = RiskSensor(self.risk_config)
        self.risk_engine = RiskEngine(config=self.risk_config, risk_sensor=self.risk_sensor)
        self.risk_gate = RiskGate(self.risk_engine)
        self.oms_fsm = OmsFsm()
        self.wal_store = wal_store
        self.order_router = OrderRouter(fsm=self.oms_fsm, wal_store=self.wal_store)
        self.market_analyzer = MarketConditionAnalyzer()
        self.market_condition: Optional[MarketConditionSnapshot] = None
        self.last_risk_snapshot = None
        self.last_orders: List[Dict[str, Any]] = []
        self.last_signals: List[Any] = []
        self.enabled_strategies: Dict[str, bool] = {f"Track{i}": True for i in range(1, 10)}
        
        self.account_summary: CanonicalAccountSummary = account_summary or CanonicalAccountSummary(
            account_id="ACC-VSSF-001",
            total_balance=50_000_000.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            used_margin=0.0,
            free_margin=50_000_000.0
        )
        
        # 계좌 및 포지션의 마지막 성공 동기화 시각 (초 단위 timestamp)
        self.last_account_sync_time: Optional[float] = time.time() if account_summary is not None else None
        self.last_position_sync_time: Optional[float] = time.time() if (account_summary is not None and bool(account_summary.positions)) else None

        self.received_execution_reports: List[CanonicalExecutionReport] = []
        self.tick_counter: int = 0
        self.last_price: float = 350.0
        self.price_history: List[float] = []
        self.current_regime: str = "NORMAL"
        
        # client_order_id -> order_uuid 매핑 (체결 시 FSM 전이용)
        self._order_id_to_uuid: Dict[str, Any] = {}
        
        # 전략별 실측 메트릭 (호출 수, 시그널 수, 생성된 주문 수, 예외 발생 수)
        self.strategy_metrics: Dict[str, Dict[str, int]] = {
            getattr(st, "name", st.__class__.__name__): {
                "ticks_evaluated": 0,
                "signals_generated": 0,
                "orders_created": 0,
                "exceptions": 0
            } for st in self.strategies
        }

    def update_account_summary(self, summary: CanonicalAccountSummary, sync_time: Optional[float] = None) -> None:
        """VSSF / Broker로부터 최신 계좌 현황 동기화 (성공 시각 갱신)"""
        self.account_summary = summary
        self.last_account_sync_time = sync_time if sync_time is not None else time.time()

    def update_positions(self, positions: Dict[str, Any], sync_time: Optional[float] = None) -> None:
        """VSSF / Broker로부터 최신 보유 포지션 동기화 (성공 시각 갱신)"""
        self.account_summary.positions = dict(positions)
        self.last_position_sync_time = sync_time if sync_time is not None else time.time()

    def is_account_state_stale(self, current_time: Optional[float] = None, timeout_sec: Optional[float] = None) -> bool:
        """계좌 상태의 Freshness/Staleness 판정"""
        if self.last_account_sync_time is None:
            return True
        now = current_time if current_time is not None else time.time()
        timeout = timeout_sec if timeout_sec is not None else self.risk_config.account_stale_timeout_sec
        return (now - self.last_account_sync_time) > timeout

    def is_position_state_stale(self, current_time: Optional[float] = None, timeout_sec: Optional[float] = None) -> bool:
        """포지션 상태의 Freshness/Staleness 판정"""
        if self.last_position_sync_time is None:
            return True
        now = current_time if current_time is not None else time.time()
        timeout = timeout_sec if timeout_sec is not None else self.risk_config.position_stale_timeout_sec
        return (now - self.last_position_sync_time) > timeout

    def process_tick(self, tick: CanonicalMarketTick) -> List[CanonicalOrderCommand]:
        """[틱 수신 ➔ Sensor / Regime ➔ Track 1~9 ➔ SignalGen ➔ Arbiter ➔ RiskGate ➔ FSM 파이프라인]"""
        self.tick_counter += 1
        self.last_price = tick.underlying_price
        self.price_history.append(tick.underlying_price)
        if len(self.price_history) > 60:
            self.price_history.pop(0)
        
        # 1. 실제 틱을 MarketConditionAnalyzer가 관찰하여 현재 시장상태를 계산
        self.market_condition = self.market_analyzer.analyze(tick)
        self.current_regime = self.market_condition.regime

        # 2. Regime Detector 기존 호환 경로 유지
        try:
            if len(self.price_history) >= 2:
                prices = np.array(self.price_history, dtype=np.float64)
                returns = np.diff(np.log(prices))
                regime, _ = self.regime_detector.detect_regime_sync(returns)
                if not self.market_condition:
                    self.current_regime = regime
            else:
                self.current_regime = "NEUTRAL"
        except Exception as e:
            logger.debug(f"RegimeDetector note: {e}")

        # 3. Risk Sensor는 Analyzer가 관측한 실제 변동성과 국면, 계좌/포지션 Stale 상태를 사용
        condition = self.market_condition
        sensor_snapshot = self.risk_sensor.scan_risk(
            active_vol=condition.volatility if condition else 0.0,
            base_vol=condition.baseline_volatility if condition else 0.0,
            current_regime=condition.regime if condition else self.current_regime,
            account_margin_ratio=(self.account_summary.used_margin / self.account_summary.total_balance) if self.account_summary.total_balance > 0 else 0.0,
            is_account_stale=self.is_account_state_stale(),
            is_position_stale=self.is_position_state_stale()
        )

        raw_signals_collected: List[CanonicalStrategySignal] = []
        self.last_signals = []

        # 3. Track 1 ~ Track 9 전략 평가 및 CanonicalStrategySignal 수집
        for st in self.strategies:
            st_name = getattr(st, "name", st.__class__.__name__)
            if not self.enabled_strategies.get(st_name, True):
                continue
            m = self.strategy_metrics[st_name]
            m["ticks_evaluated"] += 1
            signals_dicts: List[Dict[str, Any]] = []

            try:
                date_str = (tick.timestamp or "2026-08-23").split(" ")[0]
                if st_name == "Track1":
                    if st.active_fence is None:
                        atm = round(tick.underlying_price / 2.5) * 2.5
                        t1_init = st.evaluate_strategy(tick.underlying_price, atm, {})
                        if t1_init.get("signals"):
                            signals_dicts.extend(t1_init["signals"])
                    is_bull = (condition.regime == "BULL") if condition else False
                    raw_signals = st.on_tick(
                        current_price=tick.underlying_price,
                        trend_signal=is_bull,
                        days_to_expiry=30.0,
                        current_date=date_str
                    )
                    if isinstance(raw_signals, list):
                        signals_dicts.extend(raw_signals)

                elif st_name == "Track2":
                    if not st.trap_state.get("is_active"):
                        atm_2 = round(tick.underlying_price / 2.5) * 2.5
                        t2_init = st.build_asymmetric_trap(current_atm=atm_2, active_vol=(condition.volatility if condition else 0.0), base_vol=(condition.baseline_volatility if condition else 0.0))
                        if t2_init.get("signals"):
                            signals_dicts.extend(t2_init["signals"])
                    trap_res = st.evaluate_trap_status(tick.underlying_price)
                    if trap_res.get("signals"):
                        signals_dicts.extend(trap_res["signals"])
                    elif trap_res.get("action") in ["ENTER", "BUY", "SELL"]:
                        signals_dicts.append(trap_res)

                elif st_name == "Track3":
                    dislocation = condition.basis if condition else 0.0
                    m_data = {
                        "underlying_price": tick.underlying_price,
                        "time_str": "09:30:00",
                        "atm_strike": round(tick.underlying_price / 2.5) * 2.5,
                        "near_synthetic_future": tick.underlying_price + (condition.basis if condition else 0.0),
                        "far_synthetic_future": tick.underlying_price,
                        "active_vol": condition.volatility if condition else 0.0,
                    }
                    arb_res = st.evaluate_arbitrage(m_data)
                    if arb_res.get("signals"):
                        signals_dicts.extend(arb_res["signals"])
                    elif arb_res.get("action") in ["ENTER", "BUY", "SELL"]:
                        signals_dicts.append(arb_res)

                elif st_name == "Track4":
                    sc_vol = condition.volatility if condition else 0.0
                    sc_res = st.evaluate_scalping_basecamp_entry(
                        current_price=tick.underlying_price,
                        active_vol=sc_vol,
                        base_vol=1.0,
                        date_str=date_str,
                        time_str="09:05:00"
                    )
                    if sc_res.get("signals"):
                        signals_dicts.extend(sc_res["signals"])
                    elif sc_res.get("action") in ["ENTER", "BUY", "SELL"]:
                        signals_dicts.append(sc_res)

                elif st_name == "Track5":
                    gap_amt = abs(condition.price_change) if condition and condition.gap_detected else 0.0
                    gap_res = st.evaluate_gap_divergence(
                        open_price=tick.underlying_price + gap_amt,
                        prev_close_price=tick.underlying_price,
                        active_vol=condition.volatility if condition else 0.0,
                        current_regime=condition.regime if condition else self.current_regime,
                        date_str=date_str
                    )
                    if gap_res.get("signals"):
                        signals_dicts.extend(gap_res["signals"])
                    elif gap_res.get("action") in ["ENTER", "BUY", "SELL"]:
                        signals_dicts.append(gap_res)
                    m_res = st.evaluate_mean_reversion(tick.underlying_price)
                    if m_res.get("signals"):
                        signals_dicts.extend(m_res["signals"])
                    elif m_res.get("action") in ["ENTER", "BUY", "SELL"]:
                        signals_dicts.append(m_res)

                elif st_name == "Track6":
                    vol_ratio = condition.volatility_ratio if condition else 1.0
                    ins_res = st.evaluate_insurance_buy(
                        current_price=tick.underlying_price,
                        active_vol=vol_ratio,
                        base_vol=1.0,
                        budget=1000000.0,
                        date_str=date_str,
                        time_str="09:00:00"
                    )
                    if ins_res.get("signals"):
                        signals_dicts.extend(ins_res["signals"])
                    elif ins_res.get("action") in ["ENTER", "BUY", "SELL"]:
                        signals_dicts.append(ins_res)

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
                        signals_dicts.extend(ins7["signals"])
                    elif ins7.get("action") in ["ENTER", "BUY", "SELL"]:
                        signals_dicts.append(ins7)

                elif st_name == "Track8":
                    ent8 = st.evaluate_entry(
                        dte=30.0,
                        budget=2000000.0,
                        current_price=tick.underlying_price,
                        current_regime=self.current_regime,
                        date_str=date_str
                    )
                    if ent8.get("signals"):
                        signals_dicts.extend(ent8["signals"])
                    elif ent8.get("action") in ["ENTER", "BUY", "SELL"]:
                        signals_dicts.append(ent8)

                elif st_name == "Track9":
                    ins9 = st.evaluate_insurance(
                        current_price=tick.underlying_price,
                        active_sell_qty=2,
                        current_ins_qty=0,
                        date_str=date_str
                    )
                    if ins9.get("signals"):
                        signals_dicts.extend(ins9["signals"])
                    elif ins9.get("action") in ["ENTER", "BUY", "SELL"]:
                        signals_dicts.append(ins9)

                # 전략별 딕셔너리 신호를 CanonicalStrategySignal DTO로 변환
                if signals_dicts:
                    m["signals_generated"] += len(signals_dicts)
                    for local_seq, sig in enumerate(signals_dicts, start=1):
                        seq_num = tick.seq_id if tick.seq_id > 0 else self.tick_counter
                        sig_id = f"SIG-{seq_num}-{st_name}-{local_seq}"
                        
                        asset_t = CanonicalAssetType.OPTION if sig.get("asset") == "OPTION" or sig.get("type") in ["CALL", "PUT"] else CanonicalAssetType.FUTURES
                        side_t = CanonicalOrderSide.BUY if sig.get("side", "BUY") == "BUY" else CanonicalOrderSide.SELL
                        opt_t = CanonicalOptionType.CALL if sig.get("option_type") == "CALL" or sig.get("type") == "CALL" else (CanonicalOptionType.PUT if sig.get("option_type") == "PUT" or sig.get("type") == "PUT" else (CanonicalOptionType.CALL if asset_t == CanonicalAssetType.OPTION else None))
                        
                        c_sig = CanonicalStrategySignal(
                            signal_id=sig_id,
                            track_id=st_name,
                            asset_type=asset_t,
                            side=side_t,
                            qty=int(sig.get("qty", 1)),
                            price=float(sig.get("price", tick.last_price)),
                            option_type=opt_t,
                            strike=float(sig.get("strike", tick.strike_price if tick.strike_price > 0 else round(tick.underlying_price / 2.5) * 2.5)),
                            tag_id=str(sig.get("tag_id", st_name))
                        )
                        
                        # 4. SignalGenerator 유효성 검증
                        valid, reason = self.signal_generator.validate_signal(c_sig)
                        if valid:
                            raw_signals_collected.append(c_sig)
                        else:
                            logger.warning(f"[OptionProgram] Signal validation failed: {reason} for {c_sig}")

            except Exception as e:
                m["exceptions"] += 1
                logger.error(f"Strategy {st_name} execution error: {e}", exc_info=True)

        self.last_signals = [s.__dict__ for s in raw_signals_collected]
        if not raw_signals_collected:
            return []

        # 5. DecisionArbiter: 다중 전략 신호 상충 해소 및 우선순위 중재
        arb_res = self.decision_arbiter.arbitrate(raw_signals_collected, self.account_summary)
        approved_signals = arb_res.approved_signals

        commands: List[CanonicalOrderCommand] = []

        # 6. SignalGenerator 변환 -> RiskGate 사전 심사 -> OrderRouter FSM 등록
        for approved_sig in approved_signals:
            st_name = approved_sig.track_id
            m = self.strategy_metrics.get(st_name, {})
            
            # CanonicalOrderCommand 생성
            cmd = CanonicalOrderCommand(
                client_order_id=f"ORD-T{tick.seq_id if tick.seq_id > 0 else self.tick_counter}-{approved_sig.track_id}-{approved_sig.signal_id.split('-')[-1]}",
                track_id=approved_sig.track_id,
                asset_type=approved_sig.asset_type,
                side=approved_sig.side,
                qty=approved_sig.qty,
                price=approved_sig.price,
                option_type=approved_sig.option_type,
                strike=approved_sig.strike,
                tag_id=approved_sig.tag_id
            )

            # 7. RiskGate 사전 거래 리스크 심사 및 RiskApprovalToken 획득
            is_approved, token, rej_reason = self.risk_gate.admit_order(
                command=cmd,
                account=self.account_summary,
                positions=self.account_summary.positions,
                sensor_snapshot=sensor_snapshot
            )

            if is_approved and token is not None:
                eval_res = getattr(self.risk_gate, "last_evaluation_result", None)
                effective_cmd = eval_res.reduced_command if (eval_res and eval_res.reduced_command) else cmd

                # 8. OrderRouter & OMS FSM 주문 상태 전이 등록 (NEW -> VALIDATED -> SENT)
                order_uuid = self.order_router.register_and_route(
                    command=effective_cmd,
                    token=token,
                    broker_adapter=None,
                    mode_str="PIPELINE"
                )
                self._order_id_to_uuid[effective_cmd.client_order_id] = order_uuid
                commands.append(effective_cmd)
                self.last_orders.append({"client_order_id": effective_cmd.client_order_id, "track_id": effective_cmd.track_id, "side": effective_cmd.side.value, "qty": effective_cmd.qty, "price": effective_cmd.price})
                self.last_orders = self.last_orders[-50:]
                if "orders_created" in m:
                    m["orders_created"] += 1
            else:
                logger.warning(f"[OptionProgram RiskGate] Blocked order {cmd.client_order_id}: {rej_reason}")

        return commands

    def consume_execution_report(self, report: CanonicalExecutionReport) -> None:
        """[VSSF 체결 증명서 수신 및 OrderRouter / OMS FSM 수명주기 완료 전이]"""
        self.received_execution_reports.append(report)
        client_id = getattr(report, "client_order_id", None)
        order_uuid = self._order_id_to_uuid.get(client_id) if client_id else None

        # [8단계-3] 체결 이벤트가 broker_order_id만 제공하는 경우 8단계-2 매핑을 통해 내부 주문 역추적
        if order_uuid is None and hasattr(report, "broker_order_id") and report.broker_order_id:
            mapped_client_id = self.order_router.get_client_order_id_by_broker_id(report.broker_order_id)
            if mapped_client_id:
                order_uuid = self._order_id_to_uuid.get(mapped_client_id)

        if order_uuid is not None:
            self.order_router.handle_execution_report(order_uuid, report)
            self.oms_fsm.clear_completed_locks()

    def get_order_executed_qty(self, client_order_id: str) -> int:
        """[8단계-3] client_order_id로부터 실제 체결수량 조회."""
        return self.order_router.get_executed_qty(client_order_id)

    def set_strategy_enabled(self, track_id: str, enabled: bool) -> None:
        if track_id in self.enabled_strategies:
            self.enabled_strategies[track_id] = bool(enabled)

    def register_broker_order_ack(self, ack: Any) -> None:
        """[8단계-2] Broker 접수 ACK(BrokerOrderResponse)를 수신하여 OrderRouter 주문 추적 권위 저장소에 매핑 등록."""
        if ack is None or not getattr(ack, "success", False):
            return
        client_id = getattr(ack, "client_order_id", None)
        broker_id = getattr(ack, "broker_order_id", None)
        if client_id and broker_id:
            self.order_router.register_broker_order_id(client_id, broker_id)
            order_uuid = self._order_id_to_uuid.get(client_id)
            if order_uuid:
                self.order_router.register_broker_order_id(order_uuid, broker_id)

    def get_broker_order_id(self, client_order_id: str) -> Optional[str]:
        """[8단계-2] client_order_id로부터 broker_order_id 조회."""
        return self.order_router.get_broker_order_id(client_order_id)




