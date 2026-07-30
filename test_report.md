# 📊 KOSPI200 HFT 가상 테스트 세션 통합 분석 보고서
통합 보고서 최종 갱신 시각: 2026-07-31 00:23:10
총 구동 세션 수: 1개 세션

---


## 🔁 [SESSION #1] 상세 분석 보고서
- **적용된 실제 투자 일자 (Trading Date)**: **2025-01-02, 2025-01-03, 2025-01-06, 2025-01-07, 2025-01-08, 2025-01-09**
- **테스트 규모**: 총 4304 틱 스트리밍

### 🧪 [V2 STRESS TEST] 가상 테스트 환경 및 예산 강제 주입 현황
- **테스트 목적**: 월 단위 방어막(Insurance) 스트레스 테스트 및 비선형 맷집 검증
- **강제 할당된 보험 예산 (Track 5~8)**: **초기 자본 대비 고정 비율 주입 방식**
- **전략 3 (차익거래) 상태**: ⛔ **강제 Hold (테스트 순도 유지를 위한 캐시카우 차단)**
- **나머지 공격 트랙 (Track 2, 4) 상태**: ⛔ **비활성화 (0%)**
- **현재 유지 중인 수익 창출 트랙**: ✅ **Track 1 (Defense) 30%**
- **월단위 독립 테스트 (Monthly Capital Reset)**: ✅ **활성화됨 (매월 초 자본금/HWM 원금 ₩25,000,000 완벽 초기화)**
- **Track 2 & 3 포지션 진입**: ⛔ **비활성화 (가상 테스트 순도 유지를 위한 강제 HOLD)**

### 📅 역사적 시장 국면 및 비상 감시(Watchdog/Risk Engine) 이벤트 로그
- **[2025-01-02 09:00:00]** 영업일 2025-01-02 개장: HWM: ₩25,000,000 / 가용예산(2%): ₩500,000
- **[2025-01-02 09:00:00]** Track 2 함정(Trap) 구축 완료: ATM: 390.0, 설치 수량: 1계약
- **[2025-01-02 09:00:00]** Track 4 Basecamp: ATM: 390.0 양매수 진입
- **[2025-01-02 09:37:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.12) breached lower threshold (-1.5). Buying spread. / 진입가: 390.16
- **[2025-01-02 09:38:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.25). / 실현손익: +33,628원
- **[2025-01-02 09:48:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.15) breached lower threshold (-1.5). Buying spread. / 진입가: 390.08
- **[2025-01-02 10:12:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.20). / 실현손익: -79,906원
- **[2025-01-02 10:42:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.80) exceeded upper threshold (+1.5). Selling spread. / 진입가: 389.31
- **[2025-01-02 15:15:00]** OTM 옵션 보험 추가 매입: Strikes: P:377.5, C:407.5, Qty: +1, Cost: ₩75,000
- **[2025-01-03 09:00:00]** 영업일 2025-01-03 개장: HWM: ₩25,043,788 / 가용예산(2%): ₩500,876
- **[2025-01-03 09:00:00]** Track 5 Gap Trigger (ENTER_GAP_SHORT): Gap Up Z-Score (+3.64) exceeded threshold. Shorting index for mean reversion. / 수량: 1계약
- **[2025-01-03 09:14:30]** Track 5 Gap Close: Timeout (15 minutes elapsed since open). Liquidating remaining gap position. / 실현손익: -11,704원
- **[2025-01-06 09:00:00]** 영업일 2025-01-06 개장: HWM: ₩26,797,142 / 가용예산(2%): ₩535,943
- **[2025-01-06 09:00:00]** Track 7 Weekly Insurance Buy: New trading week started. Setting up weekly long strangle protection. / 지출예산: ₩350,000
- **[2025-01-06 13:54:00]** 보험 이익 수취 청산 (CALL): Strike: 407.5, 실현이익: +125,000원
- **[2025-01-06 15:15:00]** OTM 옵션 보험 부분 축소: 보험 Qty -1 감소 (Target: 1)
- **[2025-01-07 09:00:00]** 영업일 2025-01-07 개장: HWM: ₩27,420,483 / 가용예산(2%): ₩548,410
- **[2025-01-08 09:00:00]** 영업일 2025-01-08 개장: HWM: ₩28,847,193 / 가용예산(2%): ₩576,944
- **[2025-01-09 09:00:00]** 영업일 2025-01-09 개장: HWM: ₩28,287,714 / 가용예산(2%): ₩565,754
- **[2025-01-09 09:00:00]** Track 5 Gap Trigger (ENTER_GAP_SHORT): Gap Up Z-Score (+3.78) exceeded threshold. Shorting index for mean reversion. / 수량: 1계약
- **[2025-01-09 09:00:00]** Track 1 Hedge (BUY): 선물 헷지 #1 발동
- **[2025-01-09 09:00:30]** Track 1 FLATTEN: 100% 방어선 격돌
- **[2025-01-09 09:14:30]** Track 5 Gap Close: Timeout (15 minutes elapsed since open). Liquidating remaining gap position. / 실현손익: -53,073원


### 💰 1. 자산 및 자본 종합 요약
- **시작 총자산 (Starting Equity)**: ₩25,058,138
- **종료 총자산 (Ending Equity)**: ₩32,837,924
- **실현/평가 순손익 (Net Profit)**: **₩+7,779,786 (+31.047%)**
- **최대 낙폭 (Max Drawdown, MDD)**: ₩1,849,661 (6.304%)
- **안전 유보금 (Ending Reserve)**: ₩3,921,249 (전체 자산의 11.9%)

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
- **NORMAL** 국면: 0.6%

### 🌋 4. Self-Tuning Guard (리스크 미세조정) 성능 지표
- **평균 수량 조절 계수 (Avg Tuning Factor)**: **100.0%**
- **최저 수량 조절 계수 (Min Tuning Factor)**: **100.0%**
- **평균 매칭 딜레이 (Avg Slippage Latency)**: **50.0 ms**
- **최대 매칭 딜레이 (Max Slippage Latency)**: **50 ms**

### 🛡️ 5. 전략별 국면 및 PnL 성과분석 (Strategy Breakdown)
| 전략 (Strategy) | 총 누적 손익 (Total PnL) | 스트레스 국면 손익 (Stress PnL) | 평균 비중 | 방어 동작 방식 |
| :--- | :--- | :--- | :--- | :--- |
| **Track1 (Defense)** | ₩+468 | ₩+0 | 30.0% | 리스크 급증 시 100% 비중으로 증거금 제한 및 숏옵션 커버 |
| **Track2 (Trap)** | ₩+468 | ₩+0 | 0.0% | ⛔ **[V2 HOLD]** 박스권 내 역추세 포지션 진입 중단 |
| **Track3 (Arbitrage)** | ₩+156 | ₩+0 | 0.0% | ⛔ **[V2 HOLD]** 시뮬레이션 순도 유지를 위한 차익 진입 전면 차단 |
| **Track4 (Gamma)** | ₩+312 | ₩+0 | 0.0% | ⛔ **[V2 HOLD]** 현물 델타 헤징 및 스켈핑 중단 |
| **Track5 (Gap)** | ₩+0 | ₩+0 | 2.0% | 시가 갭 감지 시 역방향 진입 및 펜스 압축 회귀 저격 |
| **Track6 (Daily)** | ₩+0 | ₩+0 | 0.0% | 변동성 급증 시 당일 만기 극외가 양매수(0DTE) 가입 |
| **Track7 (Weekly)** | ₩+156 | ₩+0 | 1.3% | 매주 위클리 옵션 상장 첫날 주간 트렌드 저격 양매수 가입 |
| **Track8 (Monthly)** | ₩+0 | ₩+0 | 0.0% | 만기 초입 비대칭 외가격 양매수 및 D-3 감마이양 출구 |

### 🚨 6. 리스크 가드 발동 및 본전 청산 이력
- **비상 청산 가드 발동 횟수 (Emergency Guards Triggered)**: **0 회**

### 📅 7. 월물 전환(롤오버) 및 만기 정산 이력
- **세션 중 만기 도달 횟수 (Expiry Events)**: **0 회**
- **만기 정산 누적 손익 합계**: **₩+0**

> 이번 세션에서는 만기 도달 없이 종료되었습니다.

---

*본 보고서는 헌법 V25.2 가상 붕괴 시나리오에 따른 자율 대응 통합 결과를 반영하고 있습니다.*
