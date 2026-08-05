# 📊 KOSPI200 HFT 가상 테스트 세션 통합 분석 보고서
통합 보고서 최종 갱신 시각: 2026-08-06 00:28:34
총 구동 세션 수: 1개 세션

---


## 🔁 [SESSION #1] 상세 분석 보고서
- **적용된 실제 투자 일자 (Trading Date)**: **2025-01-10, 2025-01-13**
- **테스트 규모**: 총 1023 틱 스트리밍

### 🧪 [V2 STRESS TEST] 가상 테스트 환경 및 예산 강제 주입 현황
- **테스트 목적**: 월 단위 방어막(Insurance) 스트레스 테스트 및 비선형 맷집 검증
- **강제 할당된 보험 예산 (Track 5~8)**: **초기 자본 대비 고정 비율 주입 방식**
- **전략 3 (차익거래) 상태**: ⛔ **강제 Hold (테스트 순도 유지를 위한 캐시카우 차단)**
- **나머지 공격 트랙 (Track 2, 4) 상태**: ⛔ **비활성화 (0%)**
- **현재 유지 중인 수익 창출 트랙**: ✅ **Track1 30%**
- **월단위 독립 테스트 (Monthly Capital Reset)**: ✅ **활성화됨 (매월 초 자본금/HWM 원금 ₩25,000,000 완벽 초기화)**
- **Track 2 & 3 포지션 진입**: ⛔ **비활성화 (가상 테스트 순도 유지를 위한 강제 HOLD)**

### 📅 역사적 시장 국면 및 비상 감시(Watchdog/Risk Engine) 이벤트 로그
- **[2025-01-10 09:00:30]** Track 2 함정(Trap) 구축 완료: ATM: 320.0, 설치 수량: 1계약
- **[2025-01-10 09:00:30]** Track 4 Basecamp: ATM: 320.0 양매수 진입
- **[2025-01-10 09:35:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.99) exceeded upper threshold (+1.8). Selling spread. / 진입가: 320.18
- **[2025-01-10 09:38:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.20). / 실현손익: +125,484원
- **[2025-01-10 09:48:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.37) breached lower threshold (-1.8). Buying spread. / 진입가: 317.84
- **[2025-01-10 10:10:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.19). / 실현손익: -600,024원
- **[2025-01-10 10:24:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.91) exceeded upper threshold (+1.8). Selling spread. / 진입가: 316.89
- **[2025-01-10 10:54:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.06). / 실현손익: -12,609원
- **[2025-01-10 11:30:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.87) breached lower threshold (-1.8). Buying spread. / 진입가: 314.51
- **[2025-01-10 11:34:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.18). / 실현손익: +271,704원
- **[2025-01-10 11:49:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.26) exceeded upper threshold (+1.8). Selling spread. / 진입가: 315.76
- **[2025-01-10 12:17:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.11). / 실현손익: -159,374원
- **[2025-01-10 12:57:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.93) exceeded upper threshold (+1.8). Selling spread. / 진입가: 320.14
- **[2025-01-10 13:12:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.10). / 실현손익: -309,603원
- **[2025-01-10 13:24:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.80) exceeded upper threshold (+1.8). Selling spread. / 진입가: 323.47
- **[2025-01-10 13:27:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.16). / 실현손익: +123,486원
- **[2025-01-10 13:37:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.92) breached lower threshold (-1.8). Buying spread. / 진입가: 323.09
- **[2025-01-10 14:22:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.18). / 실현손익: +4,114원
- **[2025-01-10 14:54:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.86) exceeded upper threshold (+1.8). Selling spread. / 진입가: 322.29
- **[2025-01-10 15:15:00]** Track1 오버나잇 갭 방어 헷지 매입: Target: 1 (가두리 매도 2 기준) | Qty: +1, Cost: ₩75,000
- **[2025-01-10 15:26:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.16). / 실현손익: -622,182원
- **[2025-01-13 09:00:00]** 영업일 2025-01-13 개장: 평가 자산: ₩23,707,415 / Track 7 할당 자본(0.5%): ₩118,537
- **[2025-01-13 09:27:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.86) breached lower threshold (-1.8). Buying spread. / 진입가: 327.29
- **[2025-01-13 09:59:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.15). / 실현손익: -89,659원


### 💰 1. 자산 및 자본 종합 요약
- **시작 총자산 (Starting Equity)**: ₩25,037,389
- **종료 총자산 (Ending Equity)**: ₩23,574,378
- **실현/평가 순손익 (Net Profit)**: **₩-1,463,011 (-5.843%)**
- **최대 낙폭 (Max Drawdown, MDD)**: ₩2,941,713 (11.114%)
- **안전 유보금 (Ending Reserve)**: ₩0 (전체 자산의 0.0%)

### 📦 2. 주문 집행 및 체결 성적
| 구분 | 건수 / 비율 | 비고 |
| :--- | :--- | :--- |
| **총 주문 요청 건수** | 0 건 | 틱당 평균 0.00회 |
| **완전 체결 (FILLED)** | 0 건 | 전체 주문의 0.0% |
| **부분 체결 (PARTIAL)** | 0 건 | 전체 주문의 0.0% (GC 회수 대상) |
| **주문 거부 (REJECTED)** | 0 건 | 전체 주문의 0.0% (백오프 유도) |
| **대기/미체결 (SENT)** | 0 건 | 전체 주문의 0.0% |
| **최종 체결 성공률** | **0.00%** | (FILLED + PARTIAL) / Total |
| **총 발생 거래수수료** | **₩0** | 선물 0.003% / 옵션 0.15% 기준 |

### 📈 3. 시장 국면(Regime)별 분포
- **HIGH_VOL** 국면: 80.1%
- **NOISE_CHOPPY** 국면: 19.9%

### 🌋 4. Self-Tuning Guard (리스크 미세조정) 성능 지표
- **평균 수량 조절 계수 (Avg Tuning Factor)**: **40.0%**
- **최저 수량 조절 계수 (Min Tuning Factor)**: **40.0%**
- **평균 매칭 딜레이 (Avg Slippage Latency)**: **50.0 ms**
- **최대 매칭 딜레이 (Max Slippage Latency)**: **50 ms**

### 🛡️ 5. 전략별 국면 및 PnL 성과분석 (Strategy Breakdown)
| 전략 (Strategy) | 총 누적 손익 (Total PnL) | 스트레스 국면 손익 (Stress PnL) | 평균 비중 | 방어 동작 방식 |
| :--- | :--- | :--- | :--- | :--- |
| **Track1 (Defense)** | ₩-44,132 | ₩+0 | 30.0% | 리스크 급증 시 100% 비중으로 증거금 제한 및 숏옵션 커버 |
| **Track2 (Trap)** | ₩-25,218 | ₩+0 | 10.0% | ⛔ **[V2 HOLD]** 박스권 내 역추세 포지션 진입 중단 |
| **Track3 (Arbitrage)** | ₩+0 | ₩+0 | 5.0% | ⛔ **[V2 HOLD]** 시뮬레이션 순도 유지를 위한 차익 진입 전면 차단 |
| **Track4 (Gamma)** | ₩-12,609 | ₩+0 | 5.0% | ⛔ **[V2 HOLD]** 현물 델타 헤징 및 스켈핑 중단 |
| **Track5 (Gap)** | ₩+0 | ₩+0 | 0.0% | 시가 갭 감지 시 역방향 진입 및 펜스 압축 회귀 저격 |
| **Track6 (Daily)** | ₩+0 | ₩+0 | 0.0% | 변동성 급증 시 당일 만기 극외가 양매수(0DTE) 가입 |
| **Track7 (Weekly)** | ₩+0 | ₩+0 | 0.0% | 매주 위클리 옵션 상장 첫날 주간 트렌드 저격 양매수 가입 |
| **Track8 (Monthly)** | ₩+0 | ₩+0 | 5.0% | 만기 초입 비대칭 외가격 양매수 및 D-3 감마이양 출구 |

### 🚨 6. 리스크 가드 발동 및 본전 청산 이력
- **비상 청산 가드 발동 횟수 (Emergency Guards Triggered)**: **0 회**

### 📅 7. 월물 전환(롤오버) 및 만기 정산 이력
- **세션 중 만기 도달 횟수 (Expiry Events)**: **0 회**
- **만기 정산 누적 손익 합계**: **₩+0**

> 이번 세션에서는 만기 도달 없이 종료되었습니다.

---

*본 보고서는 헌법 V25.2 가상 붕괴 시나리오에 따른 자율 대응 통합 결과를 반영하고 있습니다.*
