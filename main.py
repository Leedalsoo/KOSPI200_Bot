# -*- coding: utf-8 -*-
"""
통합 Conductor 및 uvloop/asyncio 기반 실행 엔진
"""
import asyncio
import gc
import logging
import signal
import sys
from typing import Any, Callable, Dict, Optional, List

from shared.contracts.canonical import CanonicalMarketTick, CanonicalOrderCommand, CanonicalExecutionReport
from virtual_market_simulator.runtime.simulator_runtime import VirtualMarketSimulatorRuntime
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime
from option_program.broker.broker_interface import BrokerFactory, BrokerMode, IBrokerAdapter
from option_program.runtime.program_runtime import OptionProgramRuntime
from infra.wal_store import WalStore
from web_interface.server import TargetArchitectureUIServer, UIWebSocketHub

# Windows 환경 대응을 위한 uvloop 임포트 예외 처리
try:
    import uvloop  # type: ignore[import-not-found, unused-ignore]
    _HAS_UVLOOP = True
except ImportError:
    _HAS_UVLOOP = False

logger = logging.getLogger(__name__)


class TradingSystem:
    """통합 Conductor: VMS -> OptionProgram -> Broker -> VSSF 전체 파이프라인 수명 주기 통제"""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config: Dict[str, Any] = config or {}
        self.is_running: bool = False
        self._shutdown_event: Optional[asyncio.Event] = None
        self._main_task: Optional[asyncio.Task[None]] = None
        
        # 4대 핵심 런타임 컴포넌트 선언
        self.vms: Optional[VirtualMarketSimulatorRuntime] = None
        self.vssf: Optional[VirtualSecuritiesFirmRuntime] = None
        self.broker: Optional[IBrokerAdapter] = None
        self.op_runtime: Optional[OptionProgramRuntime] = None
        
        self.ticks_processed: int = 0
        self.orders_routed: int = 0
        self.executions_handled: int = 0
        self.last_tick: Optional[CanonicalMarketTick] = None
        self.broker_mode: str = str(self.config.get("broker_mode", "PAPER")).upper()
        self.ui_server = TargetArchitectureUIServer(self)
        self.ui_ws = UIWebSocketHub(self.ui_server)

    async def initialize(self) -> None:
        """[통합 의존성 주입] VMS, VSSF, Broker Adapter, OptionProgramRuntime 초기화 및 바인딩"""
        try:
            logger.info("TradingSystem: 컴포넌트 초기화 및 의존성 주입 시작")
            
            # 🛡️ [4대 CPU/OS 레벨 락다운] 메모리 스와핑 방지 및 실시간 스케줄러 획득
            self._lockdown_os()

            # 🛡️ [정규장 GC 동결] 런타임 지연(Latency) 방지를 위해 GC 비활성화
            gc.disable()

            # 1. Broker Mode 결정 (PAPER / SHADOW / REAL)
            mode_str = str(self.config.get("broker_mode", "PAPER")).upper()
            broker_mode = BrokerMode.PAPER if mode_str == "PAPER" else (BrokerMode.SHADOW if mode_str == "SHADOW" else BrokerMode.REAL)
            self.broker_mode = mode_str

            # 2. Virtual Securities Firm Runtime (VSSF) 초기화 (PAPER / SHADOW 전용, REAL은 상태 완전 분리)
            if self.broker_mode in ("PAPER", "SHADOW"):
                init_cap = float(self.config.get("initial_capital", 50_000_000.0))
                self.vssf = VirtualSecuritiesFirmRuntime(initial_capital=init_cap)
            else:
                self.vssf = None  # REAL 모드에서는 simulated VSSF 상태 미생성 및 완전 분리

            # 3. Broker Adapter 생성 및 라이프사이클 연결
            self.broker = BrokerFactory.create_broker(mode=broker_mode, vssf_runtime=self.vssf)
            if not self.broker.connect():
                raise RuntimeError(f"Broker connection failed for mode: {broker_mode.value}")

            # 4. Virtual Market Simulator Runtime (VMS) 초기화
            self.vms = VirtualMarketSimulatorRuntime()

            # 5. Option Program Runtime (전략, 신호, 리스크, FSM) 및 WalStore 연결
            if self.vssf is not None:
                initial_summary = self.vssf.get_account_snapshot()
            elif self.broker is not None:
                initial_summary = self.broker.get_account_summary()
                positions = self.broker.get_positions()
                if positions:
                    initial_summary.positions = dict(positions)
            else:
                initial_summary = None

            wal_store = self.config.get("wal_store")
            wal_log_path = self.config.get("wal_log_path")
            if wal_store is None:
                import os
                default_path = str(wal_log_path) if wal_log_path else os.path.join("data", "wal", "orders.wal")
                wal_store = WalStore(log_path=default_path)

            self.op_runtime = OptionProgramRuntime(account_summary=initial_summary, wal_store=wal_store)

            # 6. [D-13] Startup Recovery 실행 (WAL 로드 -> 상태 복원 -> Broker 대사)
            try:
                recovery_summary = self.op_runtime.startup_recovery(broker_adapter=self.broker)
                logger.info("TradingSystem: [STARTUP RECOVERY] 완료: %s", recovery_summary)
            except Exception as rec_exc:
                logger.critical("TradingSystem: [STARTUP RECOVERY] 실패 — 부팅 차단: %s", rec_exc, exc_info=True)
                sys.exit(1)

            self.is_running = False
            logger.info(f"TradingSystem: 전체 파이프라인 컴포넌트 초기화 완료 (Broker Mode: {broker_mode.value})")
        except Exception as exc:
            logger.critical("TradingSystem: 초기화 실패 — 부팅 차단: %s", exc, exc_info=True)
            sys.exit(1)

    def sync_broker_state(self) -> None:
        """Broker의 최신 계좌 및 포지션 상태를 OptionProgramRuntime 및 RiskEngine에 독립적으로 동기화."""
        if self.broker is None or self.op_runtime is None:
            return

        # 1. 계좌 상태 독립 동기화 (성공 시에만 타임스탬프 갱신)
        try:
            summary = self.broker.get_account_summary()
            if summary is not None:
                self.op_runtime.update_account_summary(summary)
        except Exception as exc:
            logger.warning("TradingSystem: Broker get_account_summary 동기화 실패 (기존 성공 타임스탬프 유지): %s", exc)

        # 2. 포지션 상태 독립 동기화 (성공 시에만 타임스탬프 갱신)
        try:
            positions = self.broker.get_positions()
            if positions is not None:
                self.op_runtime.update_positions(positions)
        except Exception as exc:
            logger.warning("TradingSystem: Broker get_positions 동기화 실패 (기존 성공 타임스탬프 유지): %s", exc)

    def _lockdown_os(self) -> None:
        """메모리 스와핑 잠금 및 리얼타임 스케줄러 설정 (HFT 헌법 4부 강제)"""
        try:
            import ctypes
            MCL_CURRENT = 1
            MCL_FUTURE = 2
            try:
                libc = ctypes.CDLL(None)
            except (OSError, TypeError, ValueError):
                libc = None

            if libc is not None and hasattr(libc, "mlockall"):
                res = libc.mlockall(MCL_CURRENT | MCL_FUTURE)
                if res == 0:
                    logger.info("OS Lockdown: mlockall 메모리 스와핑 잠금 성공")
                else:
                    logger.warning("OS Lockdown: mlockall 실패 (code: %s)", res)
            else:
                logger.info("OS Lockdown: mlockall 미지원 OS 환경 (Windows 등)")
        except Exception as exc:
            logger.warning("OS Lockdown: mlockall 설정 중 예외 발생: %s", exc)

        try:
            import os
            sched_get_priority_max = getattr(os, "sched_get_priority_max", None)
            SCHED_FIFO = getattr(os, "SCHED_FIFO", None)
            sched_setscheduler = getattr(os, "sched_setscheduler", None)
            sched_param = getattr(os, "sched_param", None)

            if (
                sched_get_priority_max is not None
                and SCHED_FIFO is not None
                and sched_setscheduler is not None
                and sched_param is not None
            ):
                pid = os.getpid()
                max_priority = sched_get_priority_max(SCHED_FIFO)
                param = sched_param(max_priority)
                sched_setscheduler(pid, SCHED_FIFO, param)
                logger.info("OS Lockdown: SCHED_FIFO 실시간 우선순위 획득 성공")
            else:
                logger.info("OS Lockdown: sched_setscheduler 미지원 OS 환경 (Windows 등)")
        except Exception as exc:
            logger.warning("OS Lockdown: sched_setscheduler 설정 중 예외 발생: %s", exc)

    def register_signals(self, loop: asyncio.AbstractEventLoop) -> None:
        """[목표 B] 시그널 핸들러 등록 및 Graceful Shutdown 바인딩"""
        def make_handler(s: int) -> Callable[[], Any]:
            def handler() -> Any:
                return asyncio.create_task(self._handle_signal(s))
            return handler

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, make_handler(sig))
            except (NotImplementedError, ValueError):
                logger.warning("TradingSystem: loop.add_signal_handler 미지원 환경. 시그널 우회 처리.")

    async def _handle_signal(self, sig: int) -> None:
        """시그널 수신 시 Graceful Shutdown 트리거"""
        logger.warning("TradingSystem: 시그널 수신 (%s) — Graceful Shutdown 시작", sig)
        await self.shutdown()

    async def run_loop(self, max_ticks: Optional[int] = None) -> None:
        """[전체 통합 파이프라인 가동] VMS 틱 스트림 -> OptionProgram -> RiskGate -> Broker -> VSSF -> Ledger"""
        if self.vms is None or self.broker is None or self.op_runtime is None:
            raise RuntimeError("TradingSystem must be initialized before run_loop.")
        if not getattr(self.op_runtime, "recovery_completed", False):
            raise RuntimeError("TradingSystem: startup recovery must be completed before starting run_loop.")
        if self.broker_mode in ("PAPER", "SHADOW") and self.vssf is None:
            raise RuntimeError(f"TradingSystem in {self.broker_mode} mode must have vssf initialized.")

        self.is_running = True
        self._shutdown_event = asyncio.Event()
        logger.info(f"TradingSystem: 메인 실시간 파이프라인 루프 가동 (Mode: {self.broker_mode})")

        try:
            tick_generator = self.vms.generate_tick_stream(total_days=1, ticks_per_day=max_ticks or 1000)
            
            for tick in tick_generator:
                if self._shutdown_event.is_set():
                    break
                
                self.last_tick = tick

                # 1. [체결 사이클] 이전 틱에서 접수된 주문의 체결 이벤트 수신 및 처리 (선행 체결 처리)
                if hasattr(self.broker, "poll_execution_reports"):
                    exec_reports = self.broker.poll_execution_reports()
                    for report in exec_reports:
                        self.executions_handled += 1
                        self.op_runtime.consume_execution_report(report)

                # 2. [시세/계좌 사이클] PAPER/SHADOW의 경우 VSSF에 최신 틱 시세 반영 및 OptionProgram 계좌 스냅샷 동기화
                if self.vssf is not None:
                    self.vssf.process_market_data(tick)
                    self.op_runtime.update_account_summary(self.vssf.get_account_snapshot())

                # 3. [전략/리스크 사이클] OptionProgram 틱 평가 및 파이프라인 주문 명령 생성
                commands = self.op_runtime.process_tick(tick)

                # 4. [주문 접수 사이클] Broker 인터페이스를 통한 주문 접수 (체결 이벤트와 명확히 분리된 접수/식별자 확보)
                for cmd in commands:
                    # [D-16] 미해결 UNKNOWN 주문이 존재할 경우 신규 실주문 전송 안전 차단
                    if self.op_runtime.has_unresolved_unknown_orders():
                        logger.critical(
                            "TradingSystem: [SAFETY BLOCK] 미해결 UNKNOWN 주문이 존재하여 신규 주문 발주 차단 (Client: %s)",
                            cmd.client_order_id,
                        )
                        continue

                    self.orders_routed += 1

                    # [D-15] Broker 전송 직전 BROKER_SEND_STARTED WAL 영속화 (실패 시 발주 차단)
                    wal_ok = self.op_runtime.persist_broker_send_started(cmd)
                    if not wal_ok:
                        logger.error(
                            "TradingSystem: WAL 저장 실패로 인해 주문 전송 차단 (Client: %s)",
                            cmd.client_order_id,
                        )
                        continue

                    ack = self.broker.send_order(cmd)
                    if ack is not None and getattr(ack, "success", False):
                        self.op_runtime.register_broker_order_ack(ack)
                        logger.info(
                            "TradingSystem: 주문 접수 성공 (Client: %s, Broker: %s)",
                            getattr(ack, "client_order_id", cmd.client_order_id),
                            getattr(ack, "broker_order_id", "N/A"),
                        )
                    else:
                        status = getattr(ack, "status", "UNKNOWN") if ack else "NO_RESPONSE"
                        msg = getattr(ack, "message", "No response") if ack else "send_order returned None"

                        # [D-16] TIMEOUT_UNKNOWN 시 일반 실패와 분리하여 UNKNOWN 전환 및 Recovery 시도
                        if status == "TIMEOUT_UNKNOWN":
                            logger.warning(
                                "TradingSystem: 주문 응답 타임아웃 발생 -> UNKNOWN 상태 격리 (Client: %s)",
                                cmd.client_order_id,
                            )
                            self.op_runtime.mark_order_unknown(cmd.client_order_id, reason="TIMEOUT_UNKNOWN")
                            # Broker Recovery 즉시 시도
                            rec_result = self.op_runtime.recover_unknown_orders(self.broker)
                            logger.info(
                                "TradingSystem: Timeout 주문 Broker Recovery 결과: %s",
                                rec_result,
                            )
                        else:
                            logger.warning(
                                "TradingSystem: 주문 발주 실패 (Client: %s, Status: %s, Msg: %s)",
                                cmd.client_order_id,
                                status,
                                msg,
                            )

                self.ticks_processed += 1
                await self.ui_ws.broadcast()

                if max_ticks is not None and self.ticks_processed >= max_ticks:
                    break

                # 협력적 스케줄링을 위한 초소형 yield
                if self.ticks_processed % 100 == 0:
                    await asyncio.sleep(0)

            # EOD 일일 정산 및 대조(Reconciliation) 수행 (PAPER / SHADOW 전용)
            if self.vssf is not None:
                self.vssf.run_settlement(final_settlement_price=self.op_runtime.last_price)
                rec = self.vssf.run_reconciliation()
                logger.info(f"TradingSystem: 파이프라인 실행 완료 (Ticks: {self.ticks_processed}, Orders: {self.orders_routed}, Execs: {self.executions_handled}, Reconcil: {rec.get('is_healthy')})")
            else:
                logger.info(f"TradingSystem: REAL 파이프라인 실행 완료 (Ticks: {self.ticks_processed}, Orders: {self.orders_routed}, Execs: {self.executions_handled})")

        except asyncio.CancelledError:
            logger.info("TradingSystem: 메인 루프 취소됨")
        finally:
            self.is_running = False

    async def shutdown(self) -> None:
        """[목표 B] 모든 태스크 안전 취소 및 리소스 해제"""
        logger.warning("TradingSystem: shutdown 시작 — 자원 회수 시퀀스")
        
        if self._shutdown_event is not None:
            self._shutdown_event.set()

        try:
            await self.ui_ws.stop()
        except Exception:
            pass

        current_task = asyncio.current_task()
        tasks = [t for t in asyncio.all_tasks() if t is not current_task]
        
        if tasks:
            logger.info("TradingSystem: %d개 태스크 취소 진행", len(tasks))
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        # [Broker 연결 안전 해제]
        if self.broker is not None:
            try:
                self.broker.disconnect()
                logger.info("TradingSystem: Broker disconnect 완료")
            except Exception as exc:
                logger.warning("TradingSystem: Broker disconnect 중 예외 발생 (무시하고 종료 진행): %s", exc)

        # [GC 동결 해제 및 수동 정리]
        gc.enable()
        collected = gc.collect()
        logger.info("TradingSystem: gc.enable() 복구 및 수동 가비지 컬렉션 완료 (수집된 객체 수: %d)", collected)
        logger.warning("TradingSystem: shutdown 완료")


def main() -> None:
    """엔트리 포인트"""
    if _HAS_UVLOOP:
        uvloop.install()
        logger.info("TradingSystem: C-level uvloop 이벤트 루프 적용 완료")
    else:
        logger.info("TradingSystem: 표준 asyncio 이벤트 루프 사용 (uvloop 미지원 환경)")

    config: Dict[str, Any] = {"broker_mode": "PAPER", "initial_capital": 50_000_000.0}
    system = TradingSystem(config)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    system.register_signals(loop)

    try:
        loop.run_until_complete(system.initialize())
        loop.run_until_complete(system.ui_ws.start())
        loop.run_until_complete(system.run_loop(max_ticks=500))
    except KeyboardInterrupt:
        logger.warning("TradingSystem: KeyboardInterrupt 수신 — 즉각 종료")
    finally:
        loop.run_until_complete(system.shutdown())
        loop.close()


if __name__ == "__main__":
    main()

