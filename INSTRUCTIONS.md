# CURRENT DEVELOPMENT & MODIFICATION INSTRUCTION
# 버전: 2026-08-31 개정 (API 발급 후 실전 거래 인프라 완결성 및 안정성 강화 단계)
# 상태: 활성 (Active)
# 대상 브랜치: Exp_Detail_1
# 아카이브: .agents/AGENTS_ARCHIVE_HFT_INFRA_V25.2.md (초기 HFT 인프라 Instruction 보관)

---

## 1. 현재 프로젝트 단계 및 핵심 목표

현재 프로젝트는 **9단계 한국투자증권(KIS Developers) OpenAPI 연동 이후의 실전 거래 인프라 완결성 및 안정성 강화 단계 (D-01 ~ D-19 결함 보완)**이다.

현재 단계의 최우선 목적은 다음과 같다:

«전략 1~9 엔진과 결합된 REAL/PAPER Broker 인프라, 주문 FSM, 실시간 체결 수신, WAL 영속성, 장애 복구(Recovery) 및 대사(Reconciliation), 운영 검증 파이프라인의 무결성을 완성하고 검증한다.»

현재 단계에서는 최종 Virtual Broker 리팩토링으로 한 번에 대규모 전환하지 않고, 현재 가상 테스트 환경을 100% 보존하면서 결함 항목을 순차 보완한다.

---

## 2. 전체 진행 순서 및 세부 단계별 로드맵 (D-01 ~ D-19)

### [선행 보완] REAL Broker / Account 완결성 (D-01 ~ D-07) — 완료 ☑️
1. **Broker 생명주기 계약 정식화 [D-01]** — [완료/PASS] ☑️
   - `IBrokerAdapter`에 `connect()`, `disconnect()` 공식 lifecycle 계약 확립
2. **시스템 시작 시 Broker 연결 보장 [D-02]** — [완료/PASS] ☑️
   - `TradingSystem.initialize()`에서 `broker.connect()` 호출 및 인증 실패 시 거래 루프 진입 차단
3. **종료 시 Broker 안전 해제 [D-03, D-18]** — [완료/PASS] ☑️
   - `TradingSystem.shutdown()`에서 `broker.disconnect()` 및 체결 수신 리스너 안전 종료 연결
4. **REAL Account/Position Runtime 동기화 [D-04]** — [완료/PASS] ☑️
   - Broker 실제 계좌 잔고 및 포지션 상태를 `main.py sync_broker_state()`를 통해 Runtime 및 Risk Engine에 동기화
5. **계좌 조회 실패와 실제 0원 상태 분리 [D-05]** — [완료/PASS] ☑️
   - 조회 실패/미연결 시 정상 0원 계좌로 왜곡 전달되는 문제를 제거하고 예외 처리 확립
6. **계좌/포지션 Freshness 및 Staleness 관리 [D-06]** — [완료/PASS] ☑️
   - 계좌/포지션 동기화 타임스탬프 독립 기록 및 만료(Stale) 시 주문 차단 안전장치 확립
7. **실제 get_positions() 구현 및 정규화 [D-07]** — [완료/PASS] ☑️
   - KIS `inquire-balance` 기반 실전 포지션 조회 및 Canonical 포지션 딕셔너리 정규화

---

### [10단계] 주문 상태 / 체결 / Broker 실행 정확성 (D-08 ~ D-12)
1. **주문 실패 결과 세분화 [D-08]** — [완료/PASS] ☑️
   - `send_order()` 반환을 `BrokerOrderResponse`로 정규화하여 DISCONNECTED / SAFETY_BLOCKED / REJECTED / AUTH_FAILED 등 상세 상태 분리
2. **취소 요청과 실제 취소 완료 분리 [D-09]** — [완료/PASS] ☑️
   - FSM에 `CANCEL_REQUESTED` 상태를 도입하고, Broker 취소 요청 접수와 실제 취소 확정(`confirm_cancel()`)을 엄격 분리
3. **부분 체결 기존 구현의 영속성·Recovery 연결 [D-10]** — [완료/PASS] ☑️
   - 신규 로직 재개발이 아닌 기존 부분 체결 누적 상태를 `WalStore` 영속화 및 재시작 복구(`recover_from_wal()`)에 연결
4. **실제 증권사 체결 수신 계층 구현 [D-11, D-18]** — [완료/PASS] ☑️
   - KIS `inquire-ccld` 기반 `poll_execution_reports()` 실전 체결 수신, `CanonicalExecutionReport` 정규화, Idempotency 중복 방어 및 shutdown 종료 연계
5. **Broker Recovery 조회 계약 보완 [D-12]** — [진행 중]
   - `IBrokerAdapter`에 `get_open_orders()`, `get_order_status()` 공식 조회 계약 추가 및 REAL/PAPER/SHADOW 어댑터 구현
   - `OrderRouter.reconcile_with_broker()`를 통한 활성 주문 상태 대사 및 안전 동기화

---

### [11단계] WAL / Recovery / Reconciliation (D-13 ~ D-17)
1. **기존 WalStore를 주문 상태와 연결 [D-14]**
   - 신규 WAL 시스템을 만들지 않고 기존 `WalStore`를 활용하여 주문 생성, 전송, 상태 전이를 완벽 기록
2. **Broker 전송 전 ORDER_INTENT / SEND_STARTED WAL 기록 [D-15]**
   - 네트워크 전송 직전 의도 로그를 WAL에 영속화하여 비정상 다운 시 유실 방지
3. **UNKNOWN 주문 상태 도입 및 Timeout 후 실제 주문 조회 Recovery [D-16]**
   - 응답 타임아웃 발생 시 즉시 실패 처리하지 않고 `UNKNOWN` 상태로 격리 후 Broker 조회로 실제 접수 여부 확인
4. **체결 이벤트 WAL 기록 및 중복 체결 상태 복구 [D-17]**
   - 체결 이벤트 영속화 및 재시작 시 멱등성 보장과 정확한 누적 체결 수량 복원
5. **재시작 Recovery 및 Broker ↔ 내부 OMS Reconciliation 구현 [D-13, D-16]**
   - 시스템 재시작 시: WAL 재생 ➔ OMS FSM 상태 복원 ➔ Broker 실제 Open Orders/Status 조회 ➔ 불일치 대사 및 자동 보정
6. **Recovery + Reconciliation 통합 검증 [D-13~D-17]**

---

### [12단계] 운영 검증 체계 (D-18 ~ D-19 및 최종 검증)
1. **CI와 verify.ps1 검증 범위 통일 [D-19]**
   - 로컬 검증 스크립트(`verify.ps1`)와 GitHub Actions CI 워크플로우의 테스트 스위트 완전 일치
2. **D-01~D-17 전체 통합 테스트 [D-01~D-17]**
   - 전체 브로커 모드(REAL / PAPER / SHADOW) 및 전 전략(Track 1~9) E2E 파이프라인 무결성 실측
3. **최종 감사(Final Audit) [D-01~D-19]**
4. **실제 배포 전 운영 검증 (Pre-Production / Paper Trading) [D-01~D-19]**

---

## 3. 향후 최종 리팩토링 방향

향후 최종 리팩토링에서는 다음과 같은 구조를 목표로 한다:

Strategy 1~9
→ Strategy Contract
→ Order / Signal Interface
→ Virtual Broker
→ Account / Order / Execution / Slippage / Margin / Position / Settlement / PnL
→ 향후 Real Broker Adapter

따라서 현재 단계에서 전략, Risk, Sensor, 진입/청산, Hedge 및 기타 기능을 수정·추가할 때에는 위의 향후 구조와 불필요하게 충돌하는 구조를 새롭게 만들지 않는다.

단, 현재 단계에서는 위 구조를 현재 코드에 강제로 선반영하지 않는다.

---

## 4. 현재 테스트 환경 보존 원칙

현재 가상 테스트 환경(PAPER / SHADOW / VSSF)과 기존 실행 구조를 최대한 유지한다.

반드시 지켜야 할 사항:
1. 현재 가상 테스트(279개 단위/src 테스트)가 100% 정상 실행되는 상태를 유지한다.
2. 현재 테스트에 필요한 기존 인터페이스, 데이터 흐름 및 실행 구조를 AI가 임의로 변경하지 않는다.
3. 현재 테스트를 유지하기 위해 필요한 기존 구현은 유지한다.
4. 단순히 미래 Virtual Broker 구조와 맞추기 위해 현재 정상적으로 동작하는 코드를 불필요하게 리팩토링하지 않는다.
5. 현재 단계에서 대규모 아키텍처 변경, 계층 재배치 또는 전체 구조 전환을 수행하지 않는다.
6. 기능 개선은 현재 단계에서 수행하되, 최종 아키텍처 전환은 리팩토링 단계에서 수행한다.

---

## 5. 미래 구조를 고려한 신규 코드 작성 원칙

현재 구조를 유지하면서도 향후 분리하기 쉬운 형태로 신규 코드를 작성한다:

Strategy → Strategy Contract → Order / Signal → Broker

전략 내부 로직과 Broker의 역할을 새롭게 뒤섞지 않는다. 전략 수정 시 다음 기능을 전략 코드 안에 새롭게 직접 구현하지 않는다:
- 계좌 관리
- 주문 체결
- 증거금 관리
- 슬리피지 처리
- 포지션 관리
- 정산
- Ledger 관리

현재 코드에 이미 존재하는 이러한 기능은 현재 테스트를 위해 유지하되, 신규 작성 시 향후 분리를 어렵게 만드는 결합을 생성하지 않는다.

---

## 6. 전략 및 파라미터 보존 원칙

기존 전략 1~9의 조건, 파라미터 및 테스트 결과를 AI가 임의로 변경하지 않는다.

변경이 필요한 경우 반드시 다음을 명시한다:
- 변경 이유
- 변경 대상
- 변경 전
- 변경 후
- 변경으로 인한 영향
- 기존 테스트에 미치는 영향

사용자가 명시적으로 변경을 요청한 경우에만 해당 변경을 수행한다.

---

## 7. 신규 기능 추가 및 충돌 처리 원칙

신규 기능을 추가할 때 다음을 확인한다:
1. 현재 테스트 환경에 미치는 영향
2. 기존 전략과의 호환성
3. 기존 인터페이스와의 호환성
4. 향후 Strategy Contract 및 Broker Interface와의 충돌 가능성

충돌 가능성이 발견되면 AI가 임의로 구조를 변경하지 않고 다음 형식으로 보고한다:

[FUTURE_REFACTORING_CONFLICT]
현재 구조:
변경하려는 부분:
향후 구조와의 충돌 가능성:
권장 해결 방법:
현재 테스트에 미치는 영향:
리팩토링 단계에서 필요한 작업:

---

## 8. 미래 구조의 선제적 구현 금지

«미래 구조를 고려한다»와 «미래 구조를 현재 코드에 선제적으로 구현한다»를 엄격히 구분한다.

현재 단계에서는:
- Virtual Broker를 미리 강제 구현하지 않는다.
- 현재 전략을 새로운 Broker 구조로 강제 이전하지 않는다.
- 전체 아키텍처를 미리 재구성하지 않는다.
- 현재 정상 작동하는 코드를 미래 구조에 맞추기 위해 불필요하게 이동하지 않는다.

---

## 9. AI의 임의 설계 변경 금지

AI는 현재 작업의 범위를 넘어 시스템 구조를 임의로 변경하지 않는다.

필요하다고 판단되는 경우 먼저 다음 형식으로 제안한다:

[DESIGN_CHANGE_PROPOSAL]
변경이 필요한 이유:
현재 구조:
제안하는 변경:
예상되는 장점:
예상되는 위험:
현재 테스트 영향:
향후 리팩토링 영향:
사용자 승인 필요 여부:

---

## 10. 현재 단계에서 허용되는 작업

다음 작업은 현재 단계에서 수행할 수 있다:
- D-01 ~ D-19 결함 보완 로드맵에 따른 순차적 인프라 수정
- 전략 1~9 분석 및 개선
- 전략 진입/청산 조건 개선
- Hedge / Risk 로직 개선
- Sensor 추가 및 개선
- 지표 및 데이터 처리 개선
- 테스트 로직 개선 및 버그 수정
- 예외 처리 및 로그/검증 기능 개선

---

## 11. 작업 후 필수 보고 양식

각 수정 작업이 끝나면 다음을 반드시 보고한다:

**변경 파일** - 수정한 파일:

**변경 위치** - 수정한 클래스/함수/모듈:

**변경 내용** - 무엇을 변경했는가:

**변경 이유** - 왜 변경했는가:

**기존 테스트 영향** - 기존 테스트에 미치는 영향:

**현재 가상 테스트** - 현재 가상 테스트 유지 여부:

**미래 구조 호환성** - 향후 Virtual Broker 리팩토링과의 호환성:

**충돌 여부** - Strategy Contract / Broker Interface와의 충돌 여부:

**리팩토링 작업** - 최종 리팩토링 시 별도로 처리해야 할 항목:

---

## 12. 자율 수리 루프 및 Quality Gate

1. 작업 완료 후 로컬 터미널에서 `verify.ps1` 또는 동등 테스트 스위트를 실행하여 자율 수리한다:
   - Ruff 린트 검사
   - Mypy 정적 타입 검사
   - Pytest 전체 단위/src 회귀 테스트 (279건 이상)
   - Chaos Monkey 장애 주입 테스트
   - Frontend 린트 및 테스트
2. 명시적 Git staging 및 커밋/푸시 후 원격 GitHub Actions Supreme Court Quality Gate의 통과를 확인한다.
3. **태스크 실행 안전 규칙 준수**:
   - 사용자 규칙(`10분 이상 지속 시 검토 및 실행 중단 및 재시작`)을 철저히 준수하도록 백그라운드 태스크 실행 시 대화형 모드를 원천 차단하는 옵션(예: React/Jest 프론트엔드 테스트 시 `--watchAll=false` 등)을 필수로 적용한다.
   - 무한 루프 또는 장기 블로킹(Hang)이 발생하지 않도록 비대화형 일괄 실행 모드와 타임아웃 관리를 엄격히 유지한다.

---

## 13. 핵심 원칙

**«"미래 구조를 고려하되 현재 테스트 환경을 보존하고, 기능과 전략은 충분히 개선하되 최종 아키텍처 전환은 리팩토링 단계에서 수행한다."»**
