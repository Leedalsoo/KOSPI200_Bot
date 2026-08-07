# 📊 KOSPI200 HFT 가상 테스트 세션 통합 분석 보고서
통합 보고서 최종 갱신 시각: 2026-08-07 18:53:54
총 구동 세션 수: 1개 세션

---


## 🔁 [SESSION #1] 상세 분석 보고서
- **적용된 실제 투자 일자 (Trading Date)**: **2025-01-10, 2025-01-13, 2025-01-14**
- **테스트 규모**: 총 2141 틱 스트리밍

### 🧪 [V2 STRESS TEST] 가상 테스트 환경 및 예산 강제 주입 현황
- **테스트 목적**: 월 단위 방어막(Insurance) 스트레스 테스트 및 비선형 맷집 검증
- **강제 할당된 보험 예산 (Track 5~8)**: **초기 자본 대비 고정 비율 주입 방식**
- **전략 3 (차익거래) 상태**: ⛔ **강제 Hold (테스트 순도 유지를 위한 캐시카우 차단)**
- **나머지 공격 트랙 (Track 2, 4) 상태**: ⛔ **비활성화 (0%)**
- **현재 유지 중인 수익 창출 트랙**: ✅ **Track1 30%**
- **월단위 독립 테스트 (Monthly Capital Reset)**: ✅ **활성화됨 (매월 초 자본금/HWM 원금 ₩25,000,000 완벽 초기화)**
- **Track 2 & 3 포지션 진입**: ⛔ **비활성화 (가상 테스트 순도 유지를 위한 강제 HOLD)**

### 📅 역사적 시장 국면 및 비상 감시(Watchdog/Risk Engine) 이벤트 로그
- **[2025-01-10 09:00:30]** Track 4 Basecamp: ATM: 365.0 양매수 진입
- **[2025-01-10 09:49:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.91) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 367.45
- **[2025-01-10 10:06:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.86) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 367.79
- **[2025-01-10 10:22:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.20) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 367.59
- **[2025-01-10 10:37:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.05). / 실현손익: +101,751원
- **[2025-01-10 11:21:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.83) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 366.39
- **[2025-01-10 11:37:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.96) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 366.60
- **[2025-01-10 11:56:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.15). / 실현손익: -878원
- **[2025-01-10 12:11:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.02) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 365.80
- **[2025-01-10 12:58:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.95) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 365.88
- **[2025-01-10 13:14:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.45) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 365.95
- **[2025-01-10 13:27:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.13). / 실현손익: -1,310원
- **[2025-01-10 13:54:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.99) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 367.14
- **[2025-01-10 14:43:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.91) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 368.04
- **[2025-01-10 15:07:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.15). / 실현손익: -167,513원
- **[2025-01-10 15:15:00]** Track1 오버나잇 갭 방어 헷지 매입: Target: 1 (가두리 매도 1 기준) | Qty: +1, Cost: ₩75,000
- **[2025-01-13 09:00:00]** 영업일 2025-01-13 개장: 평가 자산: ₩24,826,006 / Track 7 할당 자본(0.5%): ₩124,130
- **[2025-01-13 09:00:00]** Track 7 Weekly Insurance Buy: New trading week started. Setting up weekly limit queue strangle protection via Mid-Price Adapter. / 지출예산: ₩350,000
- **[2025-01-13 09:02:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.94) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 367.33
- **[2025-01-13 09:13:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.34) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 368.14
- **[2025-01-13 09:41:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.87) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 369.32
- **[2025-01-13 09:55:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.81) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 367.84
- **[2025-01-13 10:41:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.91) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 366.77
- **[2025-01-13 10:53:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.26). / 실현손익: -25,141원
- **[2025-01-13 11:27:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.98) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 368.46
- **[2025-01-13 12:11:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.24) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 370.04
- **[2025-01-13 12:28:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.06). / 실현손익: -331,972원
- **[2025-01-13 12:40:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.91) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 370.66
- **[2025-01-13 13:54:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.33) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 369.57
- **[2025-01-13 14:16:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.10) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 366.75
- **[2025-01-13 14:40:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.87) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 367.05
- **[2025-01-13 14:58:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.03). / 실현손익: +177,892원
- **[2025-01-14 09:00:00]** 영업일 2025-01-14 개장: 평가 자산: ₩24,677,020 / Track 7 할당 자본(0.5%): ₩123,385
- **[2025-01-14 09:36:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.01) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 367.27
- **[2025-01-14 09:50:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.03) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 368.83
- **[2025-01-14 10:25:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.06) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 369.06
- **[2025-01-14 10:36:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-3.03) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 367.08
- **[2025-01-14 11:23:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.81) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 365.00
- **[2025-01-14 11:41:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.06) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 364.84
- **[2025-01-14 11:59:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.14). / 실현손익: -64,822원
- **[2025-01-14 12:51:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.84) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 365.42
- **[2025-01-14 13:06:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.12). / 실현손익: +25,610원
- **[2025-01-14 13:25:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.92) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 363.66
- **[2025-01-14 13:43:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.02). / 실현손익: -236,801원


### 💰 1. 자산 및 자본 종합 요약
- **시작 총자산 (Starting Equity)**: ₩25,012,023
- **종료 총자산 (Ending Equity)**: ₩24,408,271
- **실현/평가 순손익 (Net Profit)**: **₩-603,752 (-2.414%)**
- **최대 낙폭 (Max Drawdown, MDD)**: ₩920,853 (3.647%)
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
- **HIGH_VOL** 국면: 68.3%
- **NOISE_CHOPPY** 국면: 31.7%

### 🌋 4. Self-Tuning Guard (리스크 미세조정) 성능 지표
- **평균 수량 조절 계수 (Avg Tuning Factor)**: **40.0%**
- **최저 수량 조절 계수 (Min Tuning Factor)**: **40.0%**
- **평균 매칭 딜레이 (Avg Slippage Latency)**: **50.0 ms**
- **최대 매칭 딜레이 (Max Slippage Latency)**: **50 ms**

### 🛡️ 5. 전략별 국면 및 PnL 성과분석 (Strategy Breakdown)
| 전략 (Strategy) | 총 누적 손익 (Total PnL) | 스트레스 국면 손익 (Stress PnL) | 평균 비중 | 방어 동작 방식 |
| :--- | :--- | :--- | :--- | :--- |
| **Track1 (Defense)** | ₩+4,594 | ₩+0 | 30.0% | 리스크 급증 시 100% 비중으로 증거금 제한 및 숏옵션 커버 |
| **Track2 (Trap)** | ₩+2,049 | ₩+0 | 10.0% | ⛔ **[V2 HOLD]** 박스권 내 역추세 포지션 진입 중단 |
| **Track3 (Arbitrage)** | ₩+0 | ₩+0 | 5.0% | ⛔ **[V2 HOLD]** 시뮬레이션 순도 유지를 위한 차익 진입 전면 차단 |
| **Track4 (Gamma)** | ₩-63 | ₩+0 | 5.0% | ⛔ **[V2 HOLD]** 현물 델타 헤징 및 스켈핑 중단 |
| **Track5 (Gap)** | ₩+0 | ₩+0 | 0.0% | 시가 갭 감지 시 역방향 진입 및 펜스 압축 회귀 저격 |
| **Track6 (Daily)** | ₩+0 | ₩+0 | 0.0% | 변동성 급증 시 당일 만기 극외가 양매수(0DTE) 가입 |
| **Track7 (Weekly)** | ₩-63 | ₩+0 | 0.3% | 매주 위클리 옵션 상장 첫날 주간 트렌드 저격 양매수 가입 |
| **Track8 (Monthly)** | ₩-63 | ₩+0 | 5.0% | 만기 초입 비대칭 외가격 양매수 및 D-3 감마이양 출구 |

### 🚨 6. 리스크 가드 발동 및 본전 청산 이력
- **비상 청산 가드 발동 횟수 (Emergency Guards Triggered)**: **5 회**

### 📅 7. 월물 전환(롤오버) 및 만기 정산 이력
- **세션 중 만기 도달 횟수 (Expiry Events)**: **0 회**
- **만기 정산 누적 손익 합계**: **₩+0**

> 이번 세션에서는 만기 도달 없이 종료되었습니다.

---

*본 보고서는 헌법 V25.2 가상 붕괴 시나리오에 따른 자율 대응 통합 결과를 반영하고 있습니다.*
