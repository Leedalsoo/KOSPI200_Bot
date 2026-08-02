# 📊 KOSPI200 HFT 가상 테스트 세션 통합 분석 보고서
통합 보고서 최종 갱신 시각: 2026-08-02 23:24:18
총 구동 세션 수: 1개 세션

---


## 🔁 [SESSION #1] 상세 분석 보고서
- **적용된 실제 투자 일자 (Trading Date)**: **2025-01-10, 2025-01-13, 2025-01-14, 2025-01-15, 2025-01-16**
- **테스트 규모**: 총 3581 틱 스트리밍

### 🧪 [V2 STRESS TEST] 가상 테스트 환경 및 예산 강제 주입 현황
- **테스트 목적**: 월 단위 방어막(Insurance) 스트레스 테스트 및 비선형 맷집 검증
- **강제 할당된 보험 예산 (Track 5~8)**: **초기 자본 대비 고정 비율 주입 방식**
- **전략 3 (차익거래) 상태**: ⛔ **강제 Hold (테스트 순도 유지를 위한 캐시카우 차단)**
- **나머지 공격 트랙 (Track 2, 4) 상태**: ⛔ **비활성화 (0%)**
- **현재 유지 중인 수익 창출 트랙**: ✅ **Track 1 (Defense) 30%**
- **월단위 독립 테스트 (Monthly Capital Reset)**: ✅ **활성화됨 (매월 초 자본금/HWM 원금 ₩25,000,000 완벽 초기화)**
- **Track 2 & 3 포지션 진입**: ⛔ **비활성화 (가상 테스트 순도 유지를 위한 강제 HOLD)**

### 📅 역사적 시장 국면 및 비상 감시(Watchdog/Risk Engine) 이벤트 로그
- **[2025-01-10 09:00:30]** Track 2 함정(Trap) 구축 완료: ATM: 397.5, 설치 수량: 1계약
- **[2025-01-10 09:00:30]** Track 4 Basecamp: ATM: 397.5 양매수 진입
- **[2025-01-10 09:35:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.97) exceeded upper threshold (+1.8). Selling spread. / 진입가: 398.75
- **[2025-01-10 09:38:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.35). / 실현손익: +94,230원
- **[2025-01-10 10:02:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.95) exceeded upper threshold (+1.8). Selling spread. / 진입가: 397.59
- **[2025-01-10 10:08:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.06). / 실현손익: +260,831원
- **[2025-01-10 10:18:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.41) breached lower threshold (-1.8). Buying spread. / 진입가: 394.70
- **[2025-01-10 10:29:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.15). / 실현손익: +45,758원
- **[2025-01-10 10:41:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.80) exceeded upper threshold (+1.8). Selling spread. / 진입가: 394.95
- **[2025-01-10 11:26:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.02). / 실현손익: -428,998원
- **[2025-01-10 11:39:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.87) breached lower threshold (-1.8). Buying spread. / 진입가: 396.44
- **[2025-01-10 11:40:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.20). / 실현손익: +192,395원
- **[2025-01-10 11:51:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.81) breached lower threshold (-1.8). Buying spread. / 진입가: 396.82
- **[2025-01-10 11:55:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.09). / 실현손익: +209,198원
- **[2025-01-10 12:10:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.96) breached lower threshold (-1.8). Buying spread. / 진입가: 396.69
- **[2025-01-10 12:15:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.03). / 실현손익: +177,096원
- **[2025-01-10 12:25:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.87) breached lower threshold (-1.8). Buying spread. / 진입가: 396.66
- **[2025-01-10 12:29:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.08). / 실현손익: +124,983원
- **[2025-01-10 12:42:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.13) breached lower threshold (-1.8). Buying spread. / 진입가: 396.00
- **[2025-01-10 13:02:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.17). / 실현손익: -474,641원
- **[2025-01-10 13:12:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.13) exceeded upper threshold (+1.8). Selling spread. / 진입가: 395.50
- **[2025-01-10 13:34:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.13). / 실현손익: -30,329원
- **[2025-01-10 14:08:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.93) breached lower threshold (-1.8). Buying spread. / 진입가: 399.22
- **[2025-01-10 14:41:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.10). / 실현손익: +205,499원
- **[2025-01-10 15:03:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.80) exceeded upper threshold (+1.8). Selling spread. / 진입가: 402.47
- **[2025-01-10 15:08:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.06). / 실현손익: +247,414원
- **[2025-01-10 15:15:00]** Track 1 (Defense) 오버나잇 갭 방어 헷지 매입: Target: 1 (가두리 매도 2 기준) | Qty: +1, Cost: ₩75,000
- **[2025-01-13 09:00:00]** 영업일 2025-01-13 개장: 평가 자산: ₩24,892,500 / Track 7 할당 자본(0.5%): ₩124,462
- **[2025-01-13 09:04:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.92) breached lower threshold (-1.8). Buying spread. / 진입가: 400.83
- **[2025-01-13 09:59:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.05). / 실현손익: -1,585,906원
- **[2025-01-13 10:09:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (3.22) exceeded upper threshold (+1.8). Selling spread. / 진입가: 395.81
- **[2025-01-13 10:41:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.02). / 실현손익: -132,675원
- **[2025-01-13 10:59:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.93) breached lower threshold (-1.8). Buying spread. / 진입가: 395.69
- **[2025-01-13 11:16:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.08). / 실현손익: -34,622원
- **[2025-01-13 11:28:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.08) exceeded upper threshold (+1.8). Selling spread. / 진입가: 396.82
- **[2025-01-13 11:44:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.06). / 실현손익: +143,619원
- **[2025-01-13 12:13:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.85) breached lower threshold (-1.8). Buying spread. / 진입가: 396.90
- **[2025-01-13 12:31:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.04). / 실현손익: +197,565원
- **[2025-01-13 13:26:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.90) exceeded upper threshold (+1.8). Selling spread. / 진입가: 397.65
- **[2025-01-13 13:32:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.30). / 실현손익: +163,173원
- **[2025-01-13 13:42:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-3.32) breached lower threshold (-1.8). Buying spread. / 진입가: 395.41
- **[2025-01-13 13:45:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.07). / 실현손익: +320,017원
- **[2025-01-13 14:04:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.94) exceeded upper threshold (+1.8). Selling spread. / 진입가: 397.67
- **[2025-01-13 14:29:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.17). / 실현손익: -149,487원
- **[2025-01-13 14:57:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.93) exceeded upper threshold (+1.8). Selling spread. / 진입가: 400.55
- **[2025-01-13 15:05:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.48). / 실현손익: +99,841원
- **[2025-01-14 09:00:00]** 영업일 2025-01-14 개장: 평가 자산: ₩25,025,438 / Track 7 할당 자본(0.5%): ₩125,127
- **[2025-01-14 09:00:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (7.01) exceeded upper threshold (+1.8). Selling spread. / 진입가: 406.63
- **[2025-01-14 09:16:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.19). / 실현손익: +33,679원
- **[2025-01-14 10:08:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.96) breached lower threshold (-1.8). Buying spread. / 진입가: 406.94
- **[2025-01-14 10:31:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.07). / 실현손익: +50,793원
- **[2025-01-14 11:02:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.93) exceeded upper threshold (+1.8). Selling spread. / 진입가: 406.05
- **[2025-01-14 11:10:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.49). / 실현손익: +227,694원
- **[2025-01-14 11:45:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.19) breached lower threshold (-1.8). Buying spread. / 진입가: 404.62
- **[2025-01-14 12:00:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.10). / 실현손익: -108,700원
- **[2025-01-14 12:24:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.08) breached lower threshold (-1.8). Buying spread. / 진입가: 401.79
- **[2025-01-14 12:34:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.22). / 실현손익: +156,753원
- **[2025-01-14 13:03:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.20) exceeded upper threshold (+1.8). Selling spread. / 진입가: 400.80
- **[2025-01-14 13:31:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.14). / 실현손익: -195,106원
- **[2025-01-14 13:52:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.04) breached lower threshold (-1.8). Buying spread. / 진입가: 400.16
- **[2025-01-14 14:27:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.13). / 실현손익: -219,076원
- **[2025-01-14 14:41:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.88) exceeded upper threshold (+1.8). Selling spread. / 진입가: 399.66
- **[2025-01-14 15:05:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.12). / 실현손익: +26,207원
- **[2025-01-14 15:23:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.07) exceeded upper threshold (+1.8). Selling spread. / 진입가: 401.13
- **[2025-01-15 09:00:00]** 영업일 2025-01-15 개장: 평가 자산: ₩24,923,979 / Track 7 할당 자본(0.5%): ₩124,620
- **[2025-01-15 09:01:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.14). / 실현손익: +136,234원
- **[2025-01-15 09:13:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.81) breached lower threshold (-1.8). Buying spread. / 진입가: 399.71
- **[2025-01-15 09:25:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.05). / 실현손익: +191,203원
- **[2025-01-15 09:35:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.37) exceeded upper threshold (+1.8). Selling spread. / 진입가: 402.90
- **[2025-01-15 09:53:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.14). / 실현손익: -404,173원
- **[2025-01-15 10:07:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.87) breached lower threshold (-1.8). Buying spread. / 진입가: 402.24
- **[2025-01-15 10:54:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.05). / 실현손익: -1,317,382원
- **[2025-01-15 11:08:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.34) exceeded upper threshold (+1.8). Selling spread. / 진입가: 395.81
- **[2025-01-15 11:56:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.19). / 실현손익: +179,207원
- **[2025-01-15 12:12:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.83) exceeded upper threshold (+1.8). Selling spread. / 진입가: 396.71
- **[2025-01-15 12:31:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.18). / 실현손익: -114,853원
- **[2025-01-15 12:45:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.00) exceeded upper threshold (+1.8). Selling spread. / 진입가: 399.28
- **[2025-01-15 12:51:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.04). / 실현손익: +153,769원
- **[2025-01-15 13:10:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.89) breached lower threshold (-1.8). Buying spread. / 진입가: 399.30
- **[2025-01-15 13:17:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.11). / 실현손익: +127,028원
- **[2025-01-15 13:28:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.09) exceeded upper threshold (+1.8). Selling spread. / 진입가: 401.64
- **[2025-01-15 13:36:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.12). / 실현손익: +73,111원
- **[2025-01-15 13:52:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.98) breached lower threshold (-1.8). Buying spread. / 진입가: 401.48
- **[2025-01-15 13:58:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.32). / 실현손익: +344,973원
- **[2025-01-15 14:14:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.20) exceeded upper threshold (+1.8). Selling spread. / 진입가: 405.01
- **[2025-01-15 14:17:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.17). / 실현손익: +198,434원
- **[2025-01-15 14:27:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.78) breached lower threshold (-1.8). Buying spread. / 진입가: 402.96
- **[2025-01-15 14:47:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.05). / 실현손익: +71,625원
- **[2025-01-15 15:22:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.93) exceeded upper threshold (+1.8). Selling spread. / 진입가: 403.66
- **[2025-01-15 15:25:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.06). / 실현손익: +238,992원
- **[2025-01-16 09:00:00]** 영업일 2025-01-16 개장: 평가 자산: ₩24,898,808 / Track 7 할당 자본(0.5%): ₩124,494
- **[2025-01-16 09:19:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.13) exceeded upper threshold (+1.8). Selling spread. / 진입가: 403.47
- **[2025-01-16 09:25:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.38). / 실현손익: +296,880원
- **[2025-01-16 09:35:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.45) exceeded upper threshold (+1.8). Selling spread. / 진입가: 404.60
- **[2025-01-16 09:50:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.16). / 실현손익: -54,627원
- **[2025-01-16 11:33:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.97) breached lower threshold (-1.8). Buying spread. / 진입가: 403.73
- **[2025-01-16 11:35:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.09). / 실현손익: +257,764원
- **[2025-01-16 11:47:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.89) exceeded upper threshold (+1.8). Selling spread. / 진입가: 405.38
- **[2025-01-16 12:00:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.16). / 실현손익: -29,803원
- **[2025-01-16 12:26:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.00) breached lower threshold (-1.8). Buying spread. / 진입가: 404.60
- **[2025-01-16 12:30:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.08). / 실현손익: +273,433원


### 💰 1. 자산 및 자본 종합 요약
- **시작 총자산 (Starting Equity)**: ₩24,956,711
- **종료 총자산 (Ending Equity)**: ₩24,950,703
- **실현/평가 순손익 (Net Profit)**: **₩-6,008 (-0.024%)**
- **최대 낙폭 (Max Drawdown, MDD)**: ₩1,444,860 (5.530%)
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
- **HIGH_VOL** 국면: 63.0%
- **NOISE_CHOPPY** 국면: 37.0%

### 🌋 4. Self-Tuning Guard (리스크 미세조정) 성능 지표
- **평균 수량 조절 계수 (Avg Tuning Factor)**: **40.0%**
- **최저 수량 조절 계수 (Min Tuning Factor)**: **40.0%**
- **평균 매칭 딜레이 (Avg Slippage Latency)**: **50.0 ms**
- **최대 매칭 딜레이 (Max Slippage Latency)**: **50 ms**

### 🛡️ 5. 전략별 국면 및 PnL 성과분석 (Strategy Breakdown)
| 전략 (Strategy) | 총 누적 손익 (Total PnL) | 스트레스 국면 손익 (Stress PnL) | 평균 비중 | 방어 동작 방식 |
| :--- | :--- | :--- | :--- | :--- |
| **Track1 (Defense)** | ₩+13,840 | ₩+0 | 30.0% | 리스크 급증 시 100% 비중으로 증거금 제한 및 숏옵션 커버 |
| **Track2 (Trap)** | ₩+7,909 | ₩+0 | 10.0% | ⛔ **[V2 HOLD]** 박스권 내 역추세 포지션 진입 중단 |
| **Track3 (Arbitrage)** | ₩+0 | ₩+0 | 5.0% | ⛔ **[V2 HOLD]** 시뮬레이션 순도 유지를 위한 차익 진입 전면 차단 |
| **Track4 (Gamma)** | ₩+3,954 | ₩+0 | 5.0% | ⛔ **[V2 HOLD]** 현물 델타 헤징 및 스켈핑 중단 |
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
