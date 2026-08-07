# 📊 KOSPI200 HFT 가상 테스트 세션 통합 분석 보고서
통합 보고서 최종 갱신 시각: 2026-08-07 17:42:50
총 구동 세션 수: 1개 세션

---


## 🔁 [SESSION #1] 상세 분석 보고서
- **적용된 실제 투자 일자 (Trading Date)**: **2025-01-10, 2025-01-13, 2025-01-14, 2025-01-15, 2025-01-16, 2025-01-17**
- **테스트 규모**: 총 4134 틱 스트리밍

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
- **[2025-01-10 10:36:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.00). / 실현손익: +137,622원
- **[2025-01-10 11:22:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.80) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 367.48
- **[2025-01-10 11:37:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.82) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 368.24
- **[2025-01-10 11:55:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.06). / 실현손익: -100,160원
- **[2025-01-10 12:11:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.11) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 367.44
- **[2025-01-10 13:01:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.11) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 367.54
- **[2025-01-10 13:05:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.08). / 실현손익: +218,318원
- **[2025-01-10 13:15:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.86) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 367.67
- **[2025-01-10 13:28:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.29). / 실현손익: +83,921원
- **[2025-01-10 13:54:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.86) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 368.86
- **[2025-01-10 14:29:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.91) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 369.11
- **[2025-01-10 14:48:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.81) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 368.00
- **[2025-01-10 15:15:00]** Track1 오버나잇 갭 방어 헷지 매입: Target: 1 (가두리 매도 1 기준) | Qty: +1, Cost: ₩75,000
- **[2025-01-13 09:00:00]** 영업일 2025-01-13 개장: 평가 자산: ₩25,263,068 / Track 7 할당 자본(0.5%): ₩126,315
- **[2025-01-13 09:00:00]** Track 7 Weekly Insurance Buy: New trading week started. Setting up weekly limit queue strangle protection via Mid-Price Adapter. / 지출예산: ₩350,000
- **[2025-01-13 09:02:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.95) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 368.80
- **[2025-01-13 09:24:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.14). / 실현손익: -110,739원
- **[2025-01-13 09:56:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.90) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 369.50
- **[2025-01-13 10:42:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.87) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 368.53
- **[2025-01-13 10:53:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.24). / 실현손익: -25,141원
- **[2025-01-13 11:26:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.97) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 369.44
- **[2025-01-13 12:11:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.22) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 371.33
- **[2025-01-13 12:45:30]** Track 1 Hedge (BUY): 선물 헷지 #1 발동 (MID_PRICE_OFFSET 슬리피지 0%)
- **[2025-01-13 12:48:00]** Track1 선물 헷지 언와인드 SELL: 청산가: 377.64
- **[2025-01-13 13:00:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.10). / 실현손익: -1,750,465원
- **[2025-01-13 13:10:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.70) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 377.39
- **[2025-01-13 13:24:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.91) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 376.99
- **[2025-01-13 13:56:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.92) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 375.92
- **[2025-01-13 14:10:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.29) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 374.03
- **[2025-01-13 14:42:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.81) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 375.06
- **[2025-01-13 14:58:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.05). / 실현손익: +158,110원
- **[2025-01-14 09:00:00]** 영업일 2025-01-14 개장: 평가 자산: ₩23,311,779 / Track 7 할당 자본(0.5%): ₩116,559
- **[2025-01-14 09:00:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (5.79) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 379.44
- **[2025-01-14 09:31:30]** 보험 이익 수취 청산 (CALL): Strike: 380.0, 실현이익: +271,609원
- **[2025-01-14 10:08:00]** 보험 이익 수취 청산 (CALL): Strike: 382.5, 실현이익: +281,732원
- **[2025-01-14 10:17:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.99) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 383.28
- **[2025-01-14 10:28:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.08) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 383.15
- **[2025-01-14 10:33:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.19). / 실현손익: +285,458원
- **[2025-01-14 10:54:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.94) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 383.84
- **[2025-01-14 11:20:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.18). / 실현손익: -271,364원
- **[2025-01-14 11:49:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.23) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 383.11
- **[2025-01-14 12:14:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.81) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 383.05
- **[2025-01-14 12:20:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.03). / 실현손익: +144,596원
- **[2025-01-14 12:35:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.18) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 383.71
- **[2025-01-14 12:46:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.97) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 382.42
- **[2025-01-14 13:25:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.89) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 380.44
- **[2025-01-14 13:42:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.36) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 381.44
- **[2025-01-14 14:51:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.92) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 383.55
- **[2025-01-14 15:03:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.08) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 381.65
- **[2025-01-15 09:00:00]** 영업일 2025-01-15 개장: 평가 자산: ₩24,371,794 / Track 7 할당 자본(0.5%): ₩121,859
- **[2025-01-15 09:00:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (4.01) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 385.60
- **[2025-01-15 09:12:00]** 보험 이익 수취 청산 (CALL): Strike: 385.0, 실현이익: +319,990원
- **[2025-01-15 09:48:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.89) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 383.21
- **[2025-01-15 10:09:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.03). / 실현손익: -213,653원
- **[2025-01-15 10:22:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.86) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 382.97
- **[2025-01-15 10:26:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.17). / 실현손익: +401,313원
- **[2025-01-15 11:04:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.89) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 381.82
- **[2025-01-15 11:43:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.16) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 380.75
- **[2025-01-15 11:52:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.12). / 실현손익: +200,839원
- **[2025-01-15 12:04:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.89) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 382.65
- **[2025-01-15 12:24:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.90) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 380.72
- **[2025-01-15 12:38:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.86) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 378.94
- **[2025-01-15 12:49:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.08). / 실현손익: +46,462원
- **[2025-01-15 13:31:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.95) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 376.82
- **[2025-01-15 14:19:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.84) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 375.63
- **[2025-01-15 15:28:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.08) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 377.59
- **[2025-01-16 09:00:00]** 영업일 2025-01-16 개장: 평가 자산: ₩25,043,436 / Track 7 할당 자본(0.5%): ₩125,217
- **[2025-01-16 10:29:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.00) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 385.09
- **[2025-01-16 11:00:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.98) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 385.54
- **[2025-01-16 11:11:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.01) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 384.99
- **[2025-01-16 11:23:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.82) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 383.85
- **[2025-01-16 11:53:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.95) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 385.24
- **[2025-01-16 12:21:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.20). / 실현손익: -400,340원
- **[2025-01-16 12:31:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.14) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 385.06
- **[2025-01-16 12:44:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.89) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 384.56
- **[2025-01-16 12:59:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.16). / 실현손익: -123,015원
- **[2025-01-16 13:18:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.82) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 384.05
- **[2025-01-16 13:45:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.19). / 실현손익: -294,922원
- **[2025-01-16 14:15:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.16) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 387.79
- **[2025-01-16 15:11:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.04) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 387.07
- **[2025-01-16 15:22:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.16) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 386.16
- **[2025-01-17 09:00:00]** 영업일 2025-01-17 개장: 평가 자산: ₩24,129,448 / Track 7 할당 자본(0.5%): ₩120,647
- **[2025-01-17 09:14:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.12). / 실현손익: -345,633원
- **[2025-01-17 09:46:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.97) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 383.30
- **[2025-01-17 10:06:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.18). / 실현손익: -73,423원
- **[2025-01-17 10:32:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.94) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 386.28
- **[2025-01-17 10:46:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.85) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 384.16


### 💰 1. 자산 및 자본 종합 요약
- **시작 총자산 (Starting Equity)**: ₩25,012,023
- **종료 총자산 (Ending Equity)**: ₩23,795,473
- **실현/평가 순손익 (Net Profit)**: **₩-1,216,550 (-4.864%)**
- **최대 낙폭 (Max Drawdown, MDD)**: ₩4,774,854 (17.057%)
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
- **HIGH_VOL** 국면: 66.7%
- **NOISE_CHOPPY** 국면: 33.3%

### 🌋 4. Self-Tuning Guard (리스크 미세조정) 성능 지표
- **평균 수량 조절 계수 (Avg Tuning Factor)**: **40.0%**
- **최저 수량 조절 계수 (Min Tuning Factor)**: **40.0%**
- **평균 매칭 딜레이 (Avg Slippage Latency)**: **50.0 ms**
- **최대 매칭 딜레이 (Max Slippage Latency)**: **50 ms**

### 🛡️ 5. 전략별 국면 및 PnL 성과분석 (Strategy Breakdown)
| 전략 (Strategy) | 총 누적 손익 (Total PnL) | 스트레스 국면 손익 (Stress PnL) | 평균 비중 | 방어 동작 방식 |
| :--- | :--- | :--- | :--- | :--- |
| **Track1 (Defense)** | ₩+340,059 | ₩+0 | 30.0% | 리스크 급증 시 100% 비중으로 증거금 제한 및 숏옵션 커버 |
| **Track2 (Trap)** | ₩+0 | ₩+0 | 10.0% | ⛔ **[V2 HOLD]** 박스권 내 역추세 포지션 진입 중단 |
| **Track3 (Arbitrage)** | ₩-6,767 | ₩+0 | 5.0% | ⛔ **[V2 HOLD]** 시뮬레이션 순도 유지를 위한 차익 진입 전면 차단 |
| **Track4 (Gamma)** | ₩+8,028 | ₩+0 | 5.0% | ⛔ **[V2 HOLD]** 현물 델타 헤징 및 스켈핑 중단 |
| **Track5 (Gap)** | ₩+0 | ₩+0 | 0.0% | 시가 갭 감지 시 역방향 진입 및 펜스 압축 회귀 저격 |
| **Track6 (Daily)** | ₩+0 | ₩+0 | 0.0% | 변동성 급증 시 당일 만기 극외가 양매수(0DTE) 가입 |
| **Track7 (Weekly)** | ₩+285,746 | ₩+0 | 0.2% | 매주 위클리 옵션 상장 첫날 주간 트렌드 저격 양매수 가입 |
| **Track8 (Monthly)** | ₩+275,623 | ₩+0 | 5.0% | 만기 초입 비대칭 외가격 양매수 및 D-3 감마이양 출구 |

### 🚨 6. 리스크 가드 발동 및 본전 청산 이력
- **비상 청산 가드 발동 횟수 (Emergency Guards Triggered)**: **9 회**

### 📅 7. 월물 전환(롤오버) 및 만기 정산 이력
- **세션 중 만기 도달 횟수 (Expiry Events)**: **0 회**
- **만기 정산 누적 손익 합계**: **₩+0**

> 이번 세션에서는 만기 도달 없이 종료되었습니다.

---

*본 보고서는 헌법 V25.2 가상 붕괴 시나리오에 따른 자율 대응 통합 결과를 반영하고 있습니다.*
