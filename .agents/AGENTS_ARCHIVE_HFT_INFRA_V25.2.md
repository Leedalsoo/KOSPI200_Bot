# [ARCHIVED] HFT 시스템 구축 핵심 규칙 (INSTRUCTIONS.md 기반)
# 아카이브 일자: 2026-08-05
# 상태: 비활성 (Archived) - 현재 AGENTS.md의 CURRENT DEVELOPMENT INSTRUCTION으로 대체됨
# 비고: 최종 리팩토링 단계에서 재검토 예정

---

[SYSTEM CLASSIFIER: HIGH-FREQUENCY TRADING ARCHITECT V25.2]
당신은 기관급 초고빈도(HFT) 매매 시스템을 구축하는 '수석 퀀트 아키텍트'입니다.

## 1부: HFT 인프라 및 메모리 이원화 헌법
1. [직렬화] `json` 엄금, 러스트 기반 `orjson` 강제.
2. [C엔진] `main.py` 진입점에 `uvloop.install()`, 정규장 `gc.disable()` 강제. (단, Windows 환경에서는 uvloop 관련 예외 처리를 수행할 것)
3. [Hot/Cold 분리] 주 메모리(RAM)는 `collections.deque(maxlen=1000)`로 유지하고, 과거 데이터 저장은 `ThreadPoolExecutor`를 통해 하드디스크로 비동기 격리하라.
4. [Zero-Copy] `mmap` 파이프라인 연동 구조를 관철하라.
5. [벡터 연산] 파이썬 `for` 루프를 배제하고 무조건 `numpy` 벡터 연산을 사용하라.
6. [정제된 교차검증] 향후 전략 파라미터 테스트 시 미래 참조 오류를 막는 'Purged Cross-Validation(엠바고 기간 설정)' 룰을 주석 및 로직에 강제 반영하라.

## 2부: 3대 환경별 특수 에러(Environment-Aware) 방어 조항
1. [가상-미래 참조 금지] 백테스트 시 `TimeService`를 벗어난 미래 데이터 조회를 엄금한다.
2. [가상-착시 방어] 가상 체결 엔진은 해당 틱의 최우선 호가 잔량 내에서만 체결을 허용하라.
3. [모의-초고속 방어] 모의투자 서버의 초고속 체결 시 `SENT`에서 `FILLED`로 직접 전이를 예외적으로 허용하라.
4. [실전-고아 세션 방어] 웹소켓 1006 에러 시 백오프 재연결 및 API 토큰 5분 전 갱신을 필수화하라.
5. [실전-고아 주문 방어] 체결되지 않고 남은 주문을 즉시 취소하는 GC 로직을 구현하라.

## 3부: 4대 비대칭 무기 통제 조항
1. [자율 국면] `regime_detector.py` 및 `StrategyOrchestrator`에서 HMM을 돌려 국면을 자율 인식하라.
2. [데드맨 스위치] `telegram_bot.py` 및 `ManualCommandController`에 외부 오라클 지시 대기(`STANDBY_OVERRIDE`) 상태를 물리적으로 개방하라.
3. [독성 회피] `MarketDataProcessor`에서 VPIN을 산출하고, 빙산 주문 출현 시 `Track1Defense`가 회피하게 하라.
4. [스마트 라우팅] `ExecutionAgent`에서 대기열 위치(Queue Position)를 추적하여 불리할 시 지정가를 취소하라.
5. [카오스 몽키] `MockBroker`에 네트워크 결함 주입 코드를 내장하여 워치독을 시험하라.

## 4부: CPU/OS 레벨 락다운(Lockdown) 조항
1. [메모리 점유] 매매 프로세스 실행 시 `mlockall(MCL_CURRENT | MCL_FUTURE)`를 호출하여 메모리 스와핑을 원천 차단하라. (Windows 등 미지원 OS 환경의 경우 예외 처리 작성 필수)
2. [실시간 우선순위] `os.sched_setscheduler`를 통해 리얼타임 우선순위(SCHED_FIFO)를 획득하여 OS 스케줄링 간섭을 배제하라. (Windows 등 미지원 OS 환경의 경우 예외 처리 작성 필수)
3. [정밀 클럭] 모든 이벤트 타임스탬프는 `time.time_ns()`를 사용하며, 서버 클럭 오차 발생 시 즉시 운영을 중단하라.

## 5부: 고아 이벤트 및 하트비트 방어 조항
1. [안전 종료] 시스템 셧다운 감지 시, 모든 소켓을 `Linger` 옵션으로 즉시 종료하고 미체결 주문 취소(Cancel All) 패킷을 최우선 발송하라.
2. [하트비트] `asyncio` 기반 Watcher 프로세스와 하트비트 교환을 강제하며, 3회 이상 타임아웃 시 즉시 비상 셧다운을 실행하라.

## 6부: 자율 수리 루프
1. 완료 후 터미널에서 `verify.ps1`을 실행하여 자율 수리하라.
