# 📊 KOSPI200 HFT 가상 테스트 세션 통합 분석 보고서
통합 보고서 최종 갱신 시각: 2026-08-07 13:40:11
총 구동 세션 수: 1개 세션

---


## 🔁 [SESSION #1] 상세 분석 보고서
- **적용된 실제 투자 일자 (Trading Date)**: **2025-01-10, 2025-01-13, 2025-01-14, 2025-01-15, 2025-01-16, 2025-01-17**
- **테스트 규모**: 총 4674 틱 스트리밍

### 🧪 [V2 STRESS TEST] 가상 테스트 환경 및 예산 강제 주입 현황
- **테스트 목적**: 월 단위 방어막(Insurance) 스트레스 테스트 및 비선형 맷집 검증
- **강제 할당된 보험 예산 (Track 5~8)**: **초기 자본 대비 고정 비율 주입 방식**
- **전략 3 (차익거래) 상태**: ⛔ **강제 Hold (테스트 순도 유지를 위한 캐시카우 차단)**
- **나머지 공격 트랙 (Track 2, 4) 상태**: ⛔ **비활성화 (0%)**
- **현재 유지 중인 수익 창출 트랙**: ✅ **Track1 30%**
- **월단위 독립 테스트 (Monthly Capital Reset)**: ✅ **활성화됨 (매월 초 자본금/HWM 원금 ₩25,000,000 완벽 초기화)**
- **Track 2 & 3 포지션 진입**: ⛔ **비활성화 (가상 테스트 순도 유지를 위한 강제 HOLD)**

### 📅 역사적 시장 국면 및 비상 감시(Watchdog/Risk Engine) 이벤트 로그
- **[2025-01-10 09:00:30]** Track 4 Basecamp: ATM: 350.0 양매수 진입
- **[2025-01-10 09:37:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.12) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 353.31
- **[2025-01-10 09:58:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.13). / 실현손익: -43,547원
- **[2025-01-10 10:14:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.06) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 351.40
- **[2025-01-10 10:31:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.87) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 353.17
- **[2025-01-10 10:44:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.99) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 351.13
- **[2025-01-10 10:46:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.02). / 실현손익: +208,787원
- **[2025-01-10 11:04:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.84) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 350.85
- **[2025-01-10 11:15:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.03). / 실현손익: +46,993원
- **[2025-01-10 11:34:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.85) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 350.77
- **[2025-01-10 11:48:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.91) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 351.44
- **[2025-01-10 11:51:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.18). / 실현손익: +258,904원
- **[2025-01-10 12:11:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.91) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 349.31
- **[2025-01-10 12:45:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.98) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 348.46
- **[2025-01-10 12:58:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.13). / 실현손익: +17,002원
- **[2025-01-10 13:08:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.54) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 349.89
- **[2025-01-10 13:29:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.99) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 350.79
- **[2025-01-10 13:59:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.18) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 352.18
- **[2025-01-10 14:02:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.05). / 실현손익: +210,779원
- **[2025-01-10 14:16:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.18) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 350.44
- **[2025-01-10 14:37:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.28) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 352.66
- **[2025-01-10 15:03:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.83) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 351.86
- **[2025-01-10 15:14:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.09) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 351.27
- **[2025-01-10 15:15:00]** Track1 오버나잇 갭 방어 헷지 매입: Target: 1 (가두리 매도 1 기준) | Qty: +1, Cost: ₩75,000
- **[2025-01-13 09:00:00]** 영업일 2025-01-13 개장: 평가 자산: ₩25,622,428 / Track 7 할당 자본(0.5%): ₩128,112
- **[2025-01-13 09:00:00]** Track 7 Weekly Insurance Buy: New trading week started. Setting up weekly limit queue strangle protection via Mid-Price Adapter. / 지출예산: ₩350,000
- **[2025-01-13 09:09:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.13). / 실현손익: -566,746원
- **[2025-01-13 09:20:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.88) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 349.84
- **[2025-01-13 09:58:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.81) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 351.27
- **[2025-01-13 10:41:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.19) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 351.02
- **[2025-01-13 11:11:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.82) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 351.97
- **[2025-01-13 12:02:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.10) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 353.71
- **[2025-01-13 12:32:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.97) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 352.50
- **[2025-01-13 12:59:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.01). / 실현손익: -371,381원
- **[2025-01-13 13:53:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.12) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 347.91
- **[2025-01-13 13:55:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.00). / 실현손익: +155,301원
- **[2025-01-13 14:07:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.83) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 349.13
- **[2025-01-13 14:54:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.87) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 346.63
- **[2025-01-13 15:06:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.50) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 344.85
- **[2025-01-13 15:10:30]** Track 1 Hedge (SELL): 선물 헷지 #1 발동 (MID_PRICE_OFFSET 슬리피지 0%)
- **[2025-01-13 15:23:30]** Track1 선물 헷지 언와인드 BUY: 청산가: 342.47
- **[2025-01-14 09:00:00]** 영업일 2025-01-14 개장: 평가 자산: ₩24,822,013 / Track 7 할당 자본(0.5%): ₩124,110
- **[2025-01-14 09:14:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.13). / 실현손익: -1,295,540원
- **[2025-01-14 09:24:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (3.15) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 340.99
- **[2025-01-14 11:10:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.96) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 336.99
- **[2025-01-14 12:53:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.25) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 336.00
- **[2025-01-14 13:06:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.05) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 335.89
- **[2025-01-14 13:51:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.92) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 336.58
- **[2025-01-14 14:27:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.16) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 335.39
- **[2025-01-14 14:38:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.84) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 334.98
- **[2025-01-14 14:49:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.81) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 333.98
- **[2025-01-14 14:49:30]** 보험 이익 수취 청산 (PUT): Strike: 335.0, 실현이익: +255,484원
- **[2025-01-14 14:49:30]** 보험 이익 수취 청산 (PUT): Strike: 335.0, 실현이익: +255,484원
- **[2025-01-14 14:49:30]** 보험 이익 수취 청산 (PUT): Strike: 335.0, 실현이익: +255,484원
- **[2025-01-14 14:53:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.23). / 실현손익: +220,248원
- **[2025-01-14 15:07:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.97) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 335.11
- **[2025-01-14 15:15:00]** Track1 오버나잇 갭 방어 헷지 매입: Target: 1 (가두리 매도 1 기준) | Qty: +1, Cost: ₩75,000
- **[2025-01-15 09:00:00]** 영업일 2025-01-15 개장: 평가 자산: ₩24,299,797 / Track 7 할당 자본(0.5%): ₩121,499
- **[2025-01-15 09:15:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.16). / 실현손익: -398,686원
- **[2025-01-15 09:50:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.92) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 338.65
- **[2025-01-15 10:31:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.84) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 339.82
- **[2025-01-15 11:13:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.84) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 338.94
- **[2025-01-15 11:39:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.86) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 340.24
- **[2025-01-15 12:17:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.94) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 338.76
- **[2025-01-15 12:26:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.30). / 실현손익: +216,612원
- **[2025-01-15 13:08:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.36) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 338.47
- **[2025-01-15 13:45:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.18). / 실현손익: -475,781원
- **[2025-01-15 14:10:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.30) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 340.66
- **[2025-01-15 14:21:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.43) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 340.26
- **[2025-01-16 09:00:00]** 영업일 2025-01-16 개장: 평가 자산: ₩23,791,402 / Track 7 할당 자본(0.5%): ₩118,957
- **[2025-01-16 09:02:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.24) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 341.03
- **[2025-01-16 09:13:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.83) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 340.55
- **[2025-01-16 09:29:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.06) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 342.60
- **[2025-01-16 09:44:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.03) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 344.03
- **[2025-01-16 10:02:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.08). / 실현손익: -193,395원
- **[2025-01-16 10:12:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.98) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 344.64
- **[2025-01-16 10:27:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.26) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 343.78
- **[2025-01-16 11:38:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.01) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 343.12
- **[2025-01-16 11:49:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.76) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 345.10
- **[2025-01-16 13:57:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.88) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 348.02
- **[2025-01-16 14:56:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.83) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 350.96
- **[2025-01-16 14:57:30]** 보험 이익 수취 청산 (CALL): Strike: 350.0, 실현이익: +260,684원
- **[2025-01-16 15:14:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.24) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 349.40
- **[2025-01-17 09:00:00]** 영업일 2025-01-17 개장: 평가 자산: ₩23,857,093 / Track 7 할당 자본(0.5%): ₩119,285
- **[2025-01-17 09:00:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (6.32) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 353.78
- **[2025-01-17 10:34:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.92) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 357.34
- **[2025-01-17 10:37:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.16). / 실현손익: +167,325원
- **[2025-01-17 11:09:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.83) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 358.93
- **[2025-01-17 11:10:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.48). / 실현손익: +205,450원
- **[2025-01-17 11:23:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.97) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 360.25
- **[2025-01-17 11:25:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.05). / 실현손익: +237,943원
- **[2025-01-17 11:43:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.92) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 359.70
- **[2025-01-17 11:55:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.94) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 359.79
- **[2025-01-17 12:05:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.04). / 실현손익: +177,471원
- **[2025-01-17 12:28:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.85) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 361.71
- **[2025-01-17 12:41:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.00) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 362.37
- **[2025-01-17 12:55:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.11). / 실현손익: -218,476원
- **[2025-01-17 13:17:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.02) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 363.65
- **[2025-01-17 13:42:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.15). / 실현손익: -248,782원
- **[2025-01-17 14:38:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.90) breached dynamic threshold (-1.80). Buying spread via Limit Queue. / 진입가: 362.73
- **[2025-01-17 15:06:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.07). / 실현손익: -470,114원
- **[2025-01-17 15:17:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.10) exceeded dynamic threshold (+1.80). Selling spread via Limit Queue. / 진입가: 362.27
- **[2025-01-17 15:24:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.03). / 실현손익: +340,019원


### 💰 1. 자산 및 자본 종합 요약
- **시작 총자산 (Starting Equity)**: ₩24,989,114
- **종료 총자산 (Ending Equity)**: ₩24,002,144
- **실현/평가 순손익 (Net Profit)**: **₩-986,970 (-3.950%)**
- **최대 낙폭 (Max Drawdown, MDD)**: ₩2,665,176 (10.286%)
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
- **HIGH_VOL** 국면: 75.1%
- **NOISE_CHOPPY** 국면: 24.9%

### 🌋 4. Self-Tuning Guard (리스크 미세조정) 성능 지표
- **평균 수량 조절 계수 (Avg Tuning Factor)**: **40.0%**
- **최저 수량 조절 계수 (Min Tuning Factor)**: **40.0%**
- **평균 매칭 딜레이 (Avg Slippage Latency)**: **50.0 ms**
- **최대 매칭 딜레이 (Max Slippage Latency)**: **50 ms**

### 🛡️ 5. 전략별 국면 및 PnL 성과분석 (Strategy Breakdown)
| 전략 (Strategy) | 총 누적 손익 (Total PnL) | 스트레스 국면 손익 (Stress PnL) | 평균 비중 | 방어 동작 방식 |
| :--- | :--- | :--- | :--- | :--- |
| **Track1 (Defense)** | ₩+492,613 | ₩+0 | 30.0% | 리스크 급증 시 100% 비중으로 증거금 제한 및 숏옵션 커버 |
| **Track2 (Trap)** | ₩+14,973 | ₩+0 | 10.0% | ⛔ **[V2 HOLD]** 박스권 내 역추세 포지션 진입 중단 |
| **Track3 (Arbitrage)** | ₩+0 | ₩+0 | 5.0% | ⛔ **[V2 HOLD]** 시뮬레이션 순도 유지를 위한 차익 진입 전면 차단 |
| **Track4 (Gamma)** | ₩-23,397 | ₩+0 | 5.0% | ⛔ **[V2 HOLD]** 현물 델타 헤징 및 스켈핑 중단 |
| **Track5 (Gap)** | ₩+0 | ₩+0 | 0.0% | 시가 갭 감지 시 역방향 진입 및 펜스 압축 회귀 저격 |
| **Track6 (Daily)** | ₩+0 | ₩+0 | 0.0% | 변동성 급증 시 당일 만기 극외가 양매수(0DTE) 가입 |
| **Track7 (Weekly)** | ₩+243,786 | ₩+0 | 0.4% | 매주 위클리 옵션 상장 첫날 주간 트렌드 저격 양매수 가입 |
| **Track8 (Monthly)** | ₩+243,786 | ₩+0 | 5.0% | 만기 초입 비대칭 외가격 양매수 및 D-3 감마이양 출구 |

### 🚨 6. 리스크 가드 발동 및 본전 청산 이력
- **비상 청산 가드 발동 횟수 (Emergency Guards Triggered)**: **5 회**

### 📅 7. 월물 전환(롤오버) 및 만기 정산 이력
- **세션 중 만기 도달 횟수 (Expiry Events)**: **0 회**
- **만기 정산 누적 손익 합계**: **₩+0**

> 이번 세션에서는 만기 도달 없이 종료되었습니다.

---

*본 보고서는 헌법 V25.2 가상 붕괴 시나리오에 따른 자율 대응 통합 결과를 반영하고 있습니다.*
