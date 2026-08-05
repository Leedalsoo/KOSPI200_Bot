# 📊 KOSPI200 HFT 가상 테스트 세션 통합 분석 보고서
통합 보고서 최종 갱신 시각: 2026-08-06 02:18:32
총 구동 세션 수: 1개 세션

---


## 🔁 [SESSION #1] 상세 분석 보고서
- **적용된 실제 투자 일자 (Trading Date)**: **2025-01-10, 2025-01-13**
- **테스트 규모**: 총 1226 틱 스트리밍

### 🧪 [V2 STRESS TEST] 가상 테스트 환경 및 예산 강제 주입 현황
- **테스트 목적**: 월 단위 방어막(Insurance) 스트레스 테스트 및 비선형 맷집 검증
- **강제 할당된 보험 예산 (Track 5~8)**: **초기 자본 대비 고정 비율 주입 방식**
- **전략 3 (차익거래) 상태**: ⛔ **강제 Hold (테스트 순도 유지를 위한 캐시카우 차단)**
- **나머지 공격 트랙 (Track 2, 4) 상태**: ⛔ **비활성화 (0%)**
- **현재 유지 중인 수익 창출 트랙**: ✅ **Track1 30%**
- **월단위 독립 테스트 (Monthly Capital Reset)**: ✅ **활성화됨 (매월 초 자본금/HWM 원금 ₩25,000,000 완벽 초기화)**
- **Track 2 & 3 포지션 진입**: ⛔ **비활성화 (가상 테스트 순도 유지를 위한 강제 HOLD)**

### 📅 역사적 시장 국면 및 비상 감시(Watchdog/Risk Engine) 이벤트 로그
- **[2025-01-10 09:00:30]** Track 8 Monthly Strangle Buy: DTE 21.0 월물 초입 진입 (비대칭 스큐 2.0x) / 지출예산: ₩1,050,000
- **[2025-01-10 09:00:30]** Track 2 함정(Trap) 구축 완료: ATM: 327.5, 설치 수량: 1계약
- **[2025-01-10 09:00:30]** Track 4 Basecamp: ATM: 327.5 양매수 진입
- **[2025-01-10 09:44:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.84) exceeded upper threshold (+1.8). Selling spread. / 진입가: 327.82
- **[2025-01-10 09:54:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.18). / 실현손익: -259,348원
- **[2025-01-10 10:16:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.89) breached lower threshold (-1.8). Buying spread. / 진입가: 328.15
- **[2025-01-10 10:23:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.03). / 실현손익: +233,171원
- **[2025-01-10 10:54:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.00) breached lower threshold (-1.8). Buying spread. / 진입가: 328.87
- **[2025-01-10 10:58:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.09). / 실현손익: +157,461원
- **[2025-01-10 11:09:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.09) exceeded upper threshold (+1.8). Selling spread. / 진입가: 330.28
- **[2025-01-10 11:22:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.03). / 실현손익: -62,499원
- **[2025-01-10 11:36:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.84) breached lower threshold (-1.8). Buying spread. / 진입가: 329.70
- **[2025-01-10 11:42:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.02). / 실현손익: +308,691원
- **[2025-01-10 12:13:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.81) breached lower threshold (-1.8). Buying spread. / 진입가: 329.04
- **[2025-01-10 12:38:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.09). / 실현손익: -248,235원
- **[2025-01-10 12:48:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.57) exceeded upper threshold (+1.8). Selling spread. / 진입가: 329.00
- **[2025-01-10 13:16:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.18). / 실현손익: +148,729원
- **[2025-01-10 13:34:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.86) breached lower threshold (-1.8). Buying spread. / 진입가: 327.31
- **[2025-01-10 13:41:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.10). / 실현손익: +188,075원
- **[2025-01-10 13:54:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.19) exceeded upper threshold (+1.8). Selling spread. / 진입가: 328.55
- **[2025-01-10 14:03:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.06). / 실현손익: +180,054원
- **[2025-01-10 14:24:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.91) breached lower threshold (-1.8). Buying spread. / 진입가: 326.89
- **[2025-01-10 14:43:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.07). / 실현손익: -287,035원
- **[2025-01-10 14:59:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.10) exceeded upper threshold (+1.8). Selling spread. / 진입가: 326.59
- **[2025-01-10 15:15:00]** Track1 오버나잇 갭 방어 헷지 매입: Target: 1 (가두리 매도 2 기준) | Qty: +1, Cost: ₩75,000
- **[2025-01-10 15:21:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.11). / 실현손익: +51,693원
- **[2025-01-13 09:00:00]** 영업일 2025-01-13 개장: 평가 자산: ₩25,350,150 / Track 7 할당 자본(0.5%): ₩126,751
- **[2025-01-13 09:01:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-3.71) breached lower threshold (-1.8). Buying spread. / 진입가: 321.93
- **[2025-01-13 10:55:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.92) exceeded upper threshold (+1.8). Selling spread. / 진입가: 320.54
- **[2025-01-13 11:01:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.15). / 실현손익: +191,265원
- **[2025-01-13 11:12:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.88) breached lower threshold (-1.8). Buying spread. / 진입가: 318.52
- **[2025-01-13 11:14:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.38). / 실현손익: +279,586원
- **[2025-01-13 11:30:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.88) breached lower threshold (-1.8). Buying spread. / 진입가: 318.35
- **[2025-01-13 11:38:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.07). / 실현손익: +82,120원
- **[2025-01-13 11:59:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.87) exceeded upper threshold (+1.8). Selling spread. / 진입가: 320.36
- **[2025-01-13 12:11:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.16). / 실현손익: +52,659원
- **[2025-01-13 12:30:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.14) exceeded upper threshold (+1.8). Selling spread. / 진입가: 321.84


### 💰 1. 자산 및 자본 종합 요약
- **시작 총자산 (Starting Equity)**: ₩25,014,423
- **종료 총자산 (Ending Equity)**: ₩25,944,533
- **실현/평가 순손익 (Net Profit)**: **₩+930,110 (+3.718%)**
- **최대 낙폭 (Max Drawdown, MDD)**: ₩763,279 (2.933%)
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
- **HIGH_VOL** 국면: 81.3%
- **NOISE_CHOPPY** 국면: 18.7%

### 🌋 4. Self-Tuning Guard (리스크 미세조정) 성능 지표
- **평균 수량 조절 계수 (Avg Tuning Factor)**: **40.0%**
- **최저 수량 조절 계수 (Min Tuning Factor)**: **40.0%**
- **평균 매칭 딜레이 (Avg Slippage Latency)**: **50.0 ms**
- **최대 매칭 딜레이 (Max Slippage Latency)**: **50 ms**

### 🛡️ 5. 전략별 국면 및 PnL 성과분석 (Strategy Breakdown)
| 전략 (Strategy) | 총 누적 손익 (Total PnL) | 스트레스 국면 손익 (Stress PnL) | 평균 비중 | 방어 동작 방식 |
| :--- | :--- | :--- | :--- | :--- |
| **Track1 (Defense)** | ₩+1,731 | ₩+0 | 30.0% | 리스크 급증 시 100% 비중으로 증거금 제한 및 숏옵션 커버 |
| **Track2 (Trap)** | ₩+629 | ₩+0 | 10.0% | ⛔ **[V2 HOLD]** 박스권 내 역추세 포지션 진입 중단 |
| **Track3 (Arbitrage)** | ₩+157 | ₩+0 | 5.0% | ⛔ **[V2 HOLD]** 시뮬레이션 순도 유지를 위한 차익 진입 전면 차단 |
| **Track4 (Gamma)** | ₩+315 | ₩+0 | 5.0% | ⛔ **[V2 HOLD]** 현물 델타 헤징 및 스켈핑 중단 |
| **Track5 (Gap)** | ₩+0 | ₩+0 | 0.0% | 시가 갭 감지 시 역방향 진입 및 펜스 압축 회귀 저격 |
| **Track6 (Daily)** | ₩+0 | ₩+0 | 0.0% | 변동성 급증 시 당일 만기 극외가 양매수(0DTE) 가입 |
| **Track7 (Weekly)** | ₩+0 | ₩+0 | 0.0% | 매주 위클리 옵션 상장 첫날 주간 트렌드 저격 양매수 가입 |
| **Track8 (Monthly)** | ₩+315 | ₩+0 | 5.0% | 만기 초입 비대칭 외가격 양매수 및 D-3 감마이양 출구 |

### 🚨 6. 리스크 가드 발동 및 본전 청산 이력
- **비상 청산 가드 발동 횟수 (Emergency Guards Triggered)**: **0 회**

### 📅 7. 월물 전환(롤오버) 및 만기 정산 이력
- **세션 중 만기 도달 횟수 (Expiry Events)**: **0 회**
- **만기 정산 누적 손익 합계**: **₩+0**

> 이번 세션에서는 만기 도달 없이 종료되었습니다.

---

*본 보고서는 헌법 V25.2 가상 붕괴 시나리오에 따른 자율 대응 통합 결과를 반영하고 있습니다.*
