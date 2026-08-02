# 📊 KOSPI200 HFT 가상 테스트 세션 통합 분석 보고서
통합 보고서 최종 갱신 시각: 2026-08-02 02:23:02
총 구동 세션 수: 1개 세션

---


## 🔁 [SESSION #1] 상세 분석 보고서
- **적용된 실제 투자 일자 (Trading Date)**: **2025-01-02, 2025-01-03, 2025-01-06, 2025-01-07, 2025-01-08, 2025-01-09**
- **테스트 규모**: 총 4085 틱 스트리밍

### 🧪 [V2 STRESS TEST] 가상 테스트 환경 및 예산 강제 주입 현황
- **테스트 목적**: 월 단위 방어막(Insurance) 스트레스 테스트 및 비선형 맷집 검증
- **강제 할당된 보험 예산 (Track 5~8)**: **초기 자본 대비 고정 비율 주입 방식**
- **전략 3 (차익거래) 상태**: ⛔ **강제 Hold (테스트 순도 유지를 위한 캐시카우 차단)**
- **나머지 공격 트랙 (Track 2, 4) 상태**: ⛔ **비활성화 (0%)**
- **현재 유지 중인 수익 창출 트랙**: ✅ **Track 1 (Defense) 30%**
- **월단위 독립 테스트 (Monthly Capital Reset)**: ✅ **활성화됨 (매월 초 자본금/HWM 원금 ₩25,000,000 완벽 초기화)**
- **Track 2 & 3 포지션 진입**: ⛔ **비활성화 (가상 테스트 순도 유지를 위한 강제 HOLD)**

### 📅 역사적 시장 국면 및 비상 감시(Watchdog/Risk Engine) 이벤트 로그
- **[2025-01-02 09:00:00]** 영업일 2025-01-02 개장: 평가 자산: ₩25,000,000 / Track 7 할당 자본(0.5%): ₩125,000
- **[2025-01-02 09:00:00]** Track 5 Gap Trigger (ENTER_GAP_LONG): Gap Down Z-Score (-1.24) breached threshold. Longing index for mean reversion. / 수량: 1계약
- **[2025-01-02 09:00:00]** Track 2 함정(Trap) 구축 완료: ATM: 300.0, 설치 수량: 1계약
- **[2025-01-02 09:00:00]** Track 4 Basecamp: ATM: 300.0 양매수 진입
- **[2025-01-02 09:14:30]** Track 5 Gap Close: Timeout (15 minutes elapsed since open). Liquidating remaining gap position. / 실현손익: -60,483원
- **[2025-01-02 09:34:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.85) breached lower threshold (-1.8). Buying spread. / 진입가: 300.61
- **[2025-01-02 09:38:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.02). / 실현손익: +3,150원
- **[2025-01-02 09:48:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.94) exceeded upper threshold (+1.8). Selling spread. / 진입가: 300.78
- **[2025-01-02 09:59:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.01). / 실현손익: +15,151원
- **[2025-01-02 10:11:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.95) breached lower threshold (-1.8). Buying spread. / 진입가: 300.38
- **[2025-01-02 10:32:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.13). / 실현손익: -99,653원
- **[2025-01-02 11:05:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.89) exceeded upper threshold (+1.8). Selling spread. / 진입가: 299.63
- **[2025-01-02 11:34:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.10). / 실현손익: -93,464원
- **[2025-01-02 12:15:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.84) breached lower threshold (-1.8). Buying spread. / 진입가: 299.63
- **[2025-01-02 12:30:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.18). / 실현손익: +40,552원
- **[2025-01-02 12:48:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.85) breached lower threshold (-1.8). Buying spread. / 진입가: 299.36
- **[2025-01-02 13:20:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.14). / 실현손익: -213,080원
- **[2025-01-02 14:01:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.15) exceeded upper threshold (+1.8). Selling spread. / 진입가: 297.96
- **[2025-01-02 14:10:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.01). / 실현손익: +77,397원
- **[2025-01-02 14:20:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.26) breached lower threshold (-1.8). Buying spread. / 진입가: 297.30
- **[2025-01-02 14:46:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.03). / 실현손익: -206,913원
- **[2025-01-02 15:09:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.81) exceeded upper threshold (+1.8). Selling spread. / 진입가: 295.93
- **[2025-01-02 15:15:00]** OTM 옵션 보험 추가 매입: Strikes: P:280.0, C:310.0, Qty: +1, Cost: ₩75,000
- **[2025-01-03 09:00:00]** 영업일 2025-01-03 개장: 평가 자산: ₩24,925,112 / Track 7 할당 자본(0.5%): ₩124,626
- **[2025-01-03 09:00:00]** Track 5 Gap Trigger (ENTER_GAP_SHORT): Gap Up Z-Score (+2.51) exceeded threshold. Shorting index for mean reversion. / 수량: 1계약
- **[2025-01-03 09:14:30]** Track 5 Gap Close: Timeout (15 minutes elapsed since open). Liquidating remaining gap position. / 실현손익: +19,794원
- **[2025-01-03 09:21:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.20). / 실현손익: -664,168원
- **[2025-01-03 11:20:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.85) exceeded upper threshold (+1.8). Selling spread. / 진입가: 299.39
- **[2025-01-03 11:28:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.05). / 실현손익: +20,585원
- **[2025-01-03 11:48:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.86) breached lower threshold (-1.8). Buying spread. / 진입가: 299.56
- **[2025-01-03 11:52:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.16). / 실현손익: +44,766원
- **[2025-01-03 12:02:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.64) exceeded upper threshold (+1.8). Selling spread. / 진입가: 300.21
- **[2025-01-03 12:28:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.16). / 실현손익: -195,152원
- **[2025-01-03 12:49:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.02) breached lower threshold (-1.8). Buying spread. / 진입가: 301.07
- **[2025-01-03 13:03:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.12). / 실현손익: +106,431원
- **[2025-01-03 13:14:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.92) breached lower threshold (-1.8). Buying spread. / 진입가: 301.21
- **[2025-01-03 13:30:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.15). / 실현손익: +59,284원
- **[2025-01-03 13:41:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.02) breached lower threshold (-1.8). Buying spread. / 진입가: 301.02
- **[2025-01-03 13:44:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.08). / 실현손익: +54,298원
- **[2025-01-03 14:32:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.81) exceeded upper threshold (+1.8). Selling spread. / 진입가: 301.58
- **[2025-01-03 14:36:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.06). / 실현손익: +40,114원
- **[2025-01-03 14:48:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.41) breached lower threshold (-1.8). Buying spread. / 진입가: 301.19
- **[2025-01-03 15:20:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.02). / 실현손익: -179,947원
- **[2025-01-06 09:00:00]** 영업일 2025-01-06 개장: 평가 자산: ₩24,922,442 / Track 7 할당 자본(0.5%): ₩124,612
- **[2025-01-06 09:02:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.94) exceeded upper threshold (+1.8). Selling spread. / 진입가: 300.62
- **[2025-01-06 09:32:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.07). / 실현손익: +9,277원
- **[2025-01-06 09:55:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.84) exceeded upper threshold (+1.8). Selling spread. / 진입가: 300.96
- **[2025-01-06 09:58:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.08). / 실현손익: +42,582원
- **[2025-01-06 10:15:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.26) exceeded upper threshold (+1.8). Selling spread. / 진입가: 301.22
- **[2025-01-06 10:18:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.13). / 실현손익: +49,151원
- **[2025-01-06 10:44:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.22) exceeded upper threshold (+1.8). Selling spread. / 진입가: 301.48
- **[2025-01-06 10:59:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.11). / 실현손익: -46,494원
- **[2025-01-06 11:12:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.86) exceeded upper threshold (+1.8). Selling spread. / 진입가: 302.11
- **[2025-01-06 11:32:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.05). / 실현손익: -97,001원
- **[2025-01-06 11:42:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.13) breached lower threshold (-1.8). Buying spread. / 진입가: 302.39
- **[2025-01-06 12:22:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.06). / 실현손익: -87,823원
- **[2025-01-06 12:32:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.33) exceeded upper threshold (+1.8). Selling spread. / 진입가: 302.63
- **[2025-01-06 12:49:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.10). / 실현손익: +55,152원
- **[2025-01-06 13:32:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.84) exceeded upper threshold (+1.8). Selling spread. / 진입가: 302.98
- **[2025-01-06 13:39:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.39). / 실현손익: +49,137원
- **[2025-01-06 13:49:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-3.28) breached lower threshold (-1.8). Buying spread. / 진입가: 302.46
- **[2025-01-06 14:33:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.02). / 실현손익: -201,878원
- **[2025-01-06 14:43:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.16) exceeded upper threshold (+1.8). Selling spread. / 진입가: 301.81
- **[2025-01-06 15:05:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.09). / 실현손익: +19,493원
- **[2025-01-07 09:00:00]** 영업일 2025-01-07 개장: 평가 자산: ₩24,922,692 / Track 7 할당 자본(0.5%): ₩124,613
- **[2025-01-07 09:30:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.86) exceeded upper threshold (+1.8). Selling spread. / 진입가: 301.45
- **[2025-01-07 09:49:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.20). / 실현손익: -21,165원
- **[2025-01-07 10:05:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.91) breached lower threshold (-1.8). Buying spread. / 진입가: 301.29
- **[2025-01-07 10:14:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.16). / 실현손익: +42,200원
- **[2025-01-07 10:24:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.12) exceeded upper threshold (+1.8). Selling spread. / 진입가: 301.99
- **[2025-01-07 10:39:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.02). / 실현손익: -10,521원
- **[2025-01-07 11:47:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.25) breached lower threshold (-1.8). Buying spread. / 진입가: 302.80
- **[2025-01-07 12:40:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.19). / 실현손익: -145,798원
- **[2025-01-07 13:12:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.95) exceeded upper threshold (+1.8). Selling spread. / 진입가: 302.09
- **[2025-01-07 13:27:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.00). / 실현손익: +67,984원
- **[2025-01-07 13:39:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.82) breached lower threshold (-1.8). Buying spread. / 진입가: 301.62
- **[2025-01-07 13:48:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.13). / 실현손익: +3,627원
- **[2025-01-07 14:12:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.05) exceeded upper threshold (+1.8). Selling spread. / 진입가: 301.86
- **[2025-01-07 14:28:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.18). / 실현손익: +15,555원
- **[2025-01-07 14:50:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.90) breached lower threshold (-1.8). Buying spread. / 진입가: 301.78
- **[2025-01-07 14:53:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.02). / 실현손익: +43,579원
- **[2025-01-07 15:03:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.15) breached lower threshold (-1.8). Buying spread. / 진입가: 301.67
- **[2025-01-07 15:09:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.31). / 실현손익: +68,894원
- **[2025-01-07 15:21:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.98) exceeded upper threshold (+1.8). Selling spread. / 진입가: 302.15
- **[2025-01-08 09:00:00]** 영업일 2025-01-08 개장: 평가 자산: ₩24,918,710 / Track 7 할당 자본(0.5%): ₩124,594
- **[2025-01-08 09:02:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.15). / 실현손익: +16,135원
- **[2025-01-08 09:30:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.90) exceeded upper threshold (+1.8). Selling spread. / 진입가: 302.39
- **[2025-01-08 09:49:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.03). / 실현손익: -69,558원
- **[2025-01-08 11:01:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.92) breached lower threshold (-1.8). Buying spread. / 진입가: 303.22
- **[2025-01-08 11:46:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.20). / 실현손익: -155,028원
- **[2025-01-08 11:56:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.85) exceeded upper threshold (+1.8). Selling spread. / 진입가: 302.70
- **[2025-01-08 12:26:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.20). / 실현손익: +15,831원
- **[2025-01-08 12:37:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.99) exceeded upper threshold (+1.8). Selling spread. / 진입가: 303.09
- **[2025-01-08 12:48:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.06). / 실현손익: +27,365원
- **[2025-01-08 13:12:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.84) breached lower threshold (-1.8). Buying spread. / 진입가: 302.83
- **[2025-01-08 13:20:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.00). / 실현손익: +60,809원
- **[2025-01-08 13:42:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.38) exceeded upper threshold (+1.8). Selling spread. / 진입가: 303.20
- **[2025-01-08 14:33:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.06). / 실현손익: -370,438원
- **[2025-01-08 14:43:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.98) breached lower threshold (-1.8). Buying spread. / 진입가: 304.77
- **[2025-01-08 15:01:00]** 보험 이익 수취 청산 (CALL): Strike: 310.0, 실현이익: +0원
- **[2025-01-08 15:02:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.09). / 실현손익: +79,915원
- **[2025-01-08 15:21:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.89) exceeded upper threshold (+1.8). Selling spread. / 진입가: 305.73
- **[2025-01-09 09:00:00]** 영업일 2025-01-09 개장: 평가 자산: ₩24,915,286 / Track 7 할당 자본(0.5%): ₩124,576
- **[2025-01-09 09:02:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.06). / 실현손익: +3,873원
- **[2025-01-09 09:16:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.97) breached lower threshold (-1.8). Buying spread. / 진입가: 305.73
- **[2025-01-09 09:33:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.11). / 실현손익: +88,673원
- **[2025-01-09 10:18:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.54) breached lower threshold (-1.8). Buying spread. / 진입가: 306.28
- **[2025-01-09 10:26:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.16). / 실현손익: +52,751원


### 💰 1. 자산 및 자본 종합 요약
- **시작 총자산 (Starting Equity)**: ₩23,422,780
- **종료 총자산 (Ending Equity)**: ₩24,914,049
- **실현/평가 순손익 (Net Profit)**: **₩+1,491,269 (+6.367%)**
- **최대 낙폭 (Max Drawdown, MDD)**: ₩693,556 (2.771%)
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
- **NEUTRAL** 국면: 0.1%
- **NOISE_CHOPPY** 국면: 99.4%
- **NORMAL** 국면: 0.5%

### 🌋 4. Self-Tuning Guard (리스크 미세조정) 성능 지표
- **평균 수량 조절 계수 (Avg Tuning Factor)**: **100.0%**
- **최저 수량 조절 계수 (Min Tuning Factor)**: **100.0%**
- **평균 매칭 딜레이 (Avg Slippage Latency)**: **50.0 ms**
- **최대 매칭 딜레이 (Max Slippage Latency)**: **50 ms**

### 🛡️ 5. 전략별 국면 및 PnL 성과분석 (Strategy Breakdown)
| 전략 (Strategy) | 총 누적 손익 (Total PnL) | 스트레스 국면 손익 (Stress PnL) | 평균 비중 | 방어 동작 방식 |
| :--- | :--- | :--- | :--- | :--- |
| **Track1 (Defense)** | ₩-5,476 | ₩+0 | 30.0% | 리스크 급증 시 100% 비중으로 증거금 제한 및 숏옵션 커버 |
| **Track2 (Trap)** | ₩-3,650 | ₩+0 | 10.0% | ⛔ **[V2 HOLD]** 박스권 내 역추세 포지션 진입 중단 |
| **Track3 (Arbitrage)** | ₩+0 | ₩+0 | 5.0% | ⛔ **[V2 HOLD]** 시뮬레이션 순도 유지를 위한 차익 진입 전면 차단 |
| **Track4 (Gamma)** | ₩-1,825 | ₩+0 | 5.0% | ⛔ **[V2 HOLD]** 현물 델타 헤징 및 스켈핑 중단 |
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
