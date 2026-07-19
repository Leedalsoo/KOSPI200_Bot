# -*- coding: utf-8 -*-
"""
통합 Conductor 및 uvloop/asyncio 기반 실행 엔진
"""
import asyncio
import gc
import logging
import signal
import sys
from typing import Any, Callable, Dict, Optional

# Windows 환경 대응을 위한 uvloop 임포트 예외 처리
try:
    import uvloop  # type: ignore[import-not-found]
    _HAS_UVLOOP = True
except ImportError:
    _HAS_UVLOOP = False

logger = logging.getLogger(__name__)


class TradingSystem:
    """통합 Conductor: 시스템 전체 수명 주기 및 신호 통제"""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config: Dict[str, Any] = config
        self.is_running: bool = False
        self._shutdown_event: Optional[asyncio.Event] = None
        self._main_task: Optional[asyncio.Task[None]] = None

    async def initialize(self) -> None:
        """[목표 C] 의존성 주입 및 에이전트 초기화 (에러 시 시스템 부팅 즉각 차단)"""
        try:
            logger.info("TradingSystem: 컴포넌트 초기화 및 의존성 주입 시작")
            
            # 🛡️ [4대 CPU/OS 레벨 락다운] 메모리 스와핑 방지 및 실시간 스케줄러 획득
            self._lockdown_os()

            # 🛡️ [정규장 GC 동결] 런타임 지연(Latency) 방지를 위해 GC 비활성화
            gc.disable()
            # FSM, Bus, Risk, Strategy 에이전트들의 인스턴스화 및 의존성 주입 로직을 시뮬레이션
            # 실제 초기화 오류 발생 시 즉시 시스템 부팅 차단
            self.is_running = False  # 초기화 직후에는 아직 running 상태가 아님
            logger.info("TradingSystem: 컴포넌트 초기화 완료 및 gc.disable() 설정")
        except Exception as exc:
            logger.critical("TradingSystem: 초기화 실패 — 부팅 차단: %s", exc)
            sys.exit(1)

    def _lockdown_os(self) -> None:
        """메모리 스와핑 잠금 및 리얼타임 스케줄러 설정 (HFT 헌법 4부 강제)"""
        # 1. mlockall (메모리 스와핑 차단)
        try:
            import ctypes
            # libc에서 mlockall 함수 호출 시도
            # MCL_CURRENT = 1, MCL_FUTURE = 2
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

        # 2. os.sched_setscheduler (SCHED_FIFO 실시간 우선순위 획득)
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
                # 최대로 얻을 수 있는 FIFO 우선순위 값 조회
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
        # Windows의 경우 loop.add_signal_handler가 NotImplementedError를 발생시키므로 예외 처리 필수
        def make_handler(s: int) -> Callable[[], Any]:
            def handler() -> Any:
                return asyncio.create_task(self._handle_signal(s))
            return handler

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, make_handler(sig))
            except (NotImplementedError, ValueError):
                # Windows 환경에서는 add_signal_handler가 미지원되므로, signal 모듈 수준 핸들러 등록 등으로 우회하거나 로깅 처리
                logger.warning("TradingSystem: loop.add_signal_handler 미지원 환경. 시그널 우회 처리.")

    async def _handle_signal(self, sig: int) -> None:
        """시그널 수신 시 Graceful Shutdown 트리거"""
        logger.warning("TradingSystem: 시그널 수신 (%s) — Graceful Shutdown 시작", sig)
        await self.shutdown()

    async def run_loop(self) -> None:
        """[목표 A] uvloop/asyncio 기반 메인 루프 실행"""
        self.is_running = True
        self._shutdown_event = asyncio.Event()
        logger.info("TradingSystem: 메인 루프 가동")
        try:
            # 셧다운 이벤트가 발생할 때까지 대기
            await self._shutdown_event.wait()
        except asyncio.CancelledError:
            logger.info("TradingSystem: 메인 루프 취소됨")
        finally:
            self.is_running = False

    async def shutdown(self) -> None:
        """[목표 B] 모든 태스크 안전 취소 및 리소스 해제"""
        logger.warning("TradingSystem: shutdown 시작 — 자원 회수 시퀀스")
        
        # 1. 셧다운 이벤트 셋하여 run_loop 대기 해제
        if self._shutdown_event is not None:
            self._shutdown_event.set()

        # 2. 현재 실행 중인 모든 태스크 조회 및 취소 (자신 제외)
        current_task = asyncio.current_task()
        tasks = [t for t in asyncio.all_tasks() if t is not current_task]
        
        if tasks:
            logger.info("TradingSystem: %d개 태스크 취소 진행", len(tasks))
            for task in tasks:
                task.cancel()
            
            # 취소 완료 대기
            await asyncio.gather(*tasks, return_exceptions=True)

        # 3. [GC 동결 해제 및 수동 정리] 메모리 누수 방지
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

    config: Dict[str, Any] = {}
    system = TradingSystem(config)

    # 비동기 실행 흐름 기동
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    system.register_signals(loop)

    try:
        loop.run_until_complete(system.initialize())
        loop.run_until_complete(system.run_loop())
    except KeyboardInterrupt:
        logger.warning("TradingSystem: KeyboardInterrupt 수신 — 즉각 종료")
    finally:
        loop.run_until_complete(system.shutdown())
        loop.close()


if __name__ == "__main__":
    main()
