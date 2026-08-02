# 📊 KOSPI200 HFT 가상 테스트 세션 통합 분석 보고서
통합 보고서 최종 갱신 시각: 2026-08-02 23:39:19
총 구동 세션 수: 1개 세션

---


## 🔁 [SESSION #1] 상세 분석 보고서
- **적용된 실제 투자 일자 (Trading Date)**: **2025-01-10, 2025-01-13, 2025-01-14, 2025-01-15, 2025-01-16, 2025-01-17, 2025-01-20, 2025-01-21, 2025-01-22, 2025-01-23**
- **테스트 규모**: 총 7493 틱 스트리밍

### 🧪 [V2 STRESS TEST] 가상 테스트 환경 및 예산 강제 주입 현황
- **테스트 목적**: 월 단위 방어막(Insurance) 스트레스 테스트 및 비선형 맷집 검증
- **강제 할당된 보험 예산 (Track 5~8)**: **초기 자본 대비 고정 비율 주입 방식**
- **전략 3 (차익거래) 상태**: ⛔ **강제 Hold (테스트 순도 유지를 위한 캐시카우 차단)**
- **나머지 공격 트랙 (Track 2, 4) 상태**: ⛔ **비활성화 (0%)**
- **현재 유지 중인 수익 창출 트랙**: ✅ **Track 1 (Defense) 30%**
- **월단위 독립 테스트 (Monthly Capital Reset)**: ✅ **활성화됨 (매월 초 자본금/HWM 원금 ₩25,000,000 완벽 초기화)**
- **Track 2 & 3 포지션 진입**: ⛔ **비활성화 (가상 테스트 순도 유지를 위한 강제 HOLD)**

### 📅 역사적 시장 국면 및 비상 감시(Watchdog/Risk Engine) 이벤트 로그
- **[2025-01-10 09:00:30]** Track 2 함정(Trap) 구축 완료: ATM: 320.0, 설치 수량: 1계약
- **[2025-01-10 09:00:30]** Track 4 Basecamp: ATM: 320.0 양매수 진입
- **[2025-01-10 09:34:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.98) breached lower threshold (-1.8). Buying spread. / 진입가: 318.07
- **[2025-01-10 09:37:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.59). / 실현손익: +14,177원
- **[2025-01-10 09:47:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.65) exceeded upper threshold (+1.8). Selling spread. / 진입가: 318.01
- **[2025-01-10 10:12:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.12). / 실현손익: -220,957원
- **[2025-01-10 10:28:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.99) exceeded upper threshold (+1.8). Selling spread. / 진입가: 321.07
- **[2025-01-10 10:48:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.14). / 실현손익: -227,281원
- **[2025-01-10 11:41:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.96) breached lower threshold (-1.8). Buying spread. / 진입가: 324.76
- **[2025-01-10 12:09:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.12). / 실현손익: +160,145원
- **[2025-01-10 12:41:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.84) breached lower threshold (-1.8). Buying spread. / 진입가: 324.16
- **[2025-01-10 12:45:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.02). / 실현손익: +165,072원
- **[2025-01-10 13:15:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.22) exceeded upper threshold (+1.8). Selling spread. / 진입가: 323.83
- **[2025-01-10 13:42:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.05). / 실현손익: +66,515원
- **[2025-01-10 14:13:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.02) breached lower threshold (-1.8). Buying spread. / 진입가: 321.65
- **[2025-01-10 14:29:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.11). / 실현손익: -134,936원
- **[2025-01-10 14:41:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.94) exceeded upper threshold (+1.8). Selling spread. / 진입가: 321.34
- **[2025-01-10 15:00:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.04). / 실현손익: +88,656원
- **[2025-01-10 15:15:00]** Track 1 (Defense) 오버나잇 갭 방어 헷지 매입: Target: 1 (가두리 매도 2 기준) | Qty: +1, Cost: ₩75,000
- **[2025-01-13 09:00:00]** 영업일 2025-01-13 개장: 평가 자산: ₩24,964,522 / Track 7 할당 자본(0.5%): ₩124,823
- **[2025-01-13 09:00:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-5.97) breached lower threshold (-1.8). Buying spread. / 진입가: 316.30
- **[2025-01-13 09:22:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.17). / 실현손익: -509,816원
- **[2025-01-13 09:50:00]** Track 1 Hedge (SELL): 선물 헷지 #1 발동
- **[2025-01-13 09:52:00]** Track 1 FLATTEN: 100% 방어선 격돌
- **[2025-01-13 09:52:00]** 보험 이익 수취 청산 (PUT): Strike: 307.5, 실현이익: +0원
- **[2025-01-13 10:37:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.96) exceeded upper threshold (+1.8). Selling spread. / 진입가: 310.83
- **[2025-01-13 11:06:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.14). / 실현손익: +185,541원
- **[2025-01-13 11:38:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.00) exceeded upper threshold (+1.8). Selling spread. / 진입가: 310.27
- **[2025-01-13 11:49:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.13). / 실현손익: +194,738원
- **[2025-01-13 12:26:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.89) breached lower threshold (-1.8). Buying spread. / 진입가: 308.31
- **[2025-01-13 12:38:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.04). / 실현손익: -26,587원
- **[2025-01-13 12:50:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.07) exceeded upper threshold (+1.8). Selling spread. / 진입가: 309.62
- **[2025-01-13 13:14:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.03). / 실현손익: -258,585원
- **[2025-01-13 13:39:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.95) breached lower threshold (-1.8). Buying spread. / 진입가: 309.92
- **[2025-01-13 13:52:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.19). / 실현손익: +109,654원
- **[2025-01-13 14:16:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.88) exceeded upper threshold (+1.8). Selling spread. / 진입가: 312.63
- **[2025-01-13 14:24:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.07). / 실현손익: +159,291원
- **[2025-01-13 15:15:00]** Track 1 (Defense) 오버나잇 갭 방어 헷지 매입: Target: 1 (가두리 매도 1 기준) | Qty: +1, Cost: ₩75,000
- **[2025-01-13 15:29:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.87) exceeded upper threshold (+1.8). Selling spread. / 진입가: 310.12
- **[2025-01-14 09:00:00]** 영업일 2025-01-14 개장: 평가 자산: ₩24,493,319 / Track 7 할당 자본(0.5%): ₩122,467
- **[2025-01-14 09:34:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.10). / 실현손익: -769,377원
- **[2025-01-14 10:39:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.88) breached lower threshold (-1.8). Buying spread. / 진입가: 312.42
- **[2025-01-14 10:43:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.08). / 실현손익: +230,862원
- **[2025-01-14 10:56:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.03) exceeded upper threshold (+1.8). Selling spread. / 진입가: 314.48
- **[2025-01-14 11:09:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.01). / 실현손익: +111,274원
- **[2025-01-14 11:29:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.22) breached lower threshold (-1.8). Buying spread. / 진입가: 313.83
- **[2025-01-14 11:42:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.15). / 실현손익: +225,190원
- **[2025-01-14 12:02:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.85) exceeded upper threshold (+1.8). Selling spread. / 진입가: 316.73
- **[2025-01-14 12:06:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.02). / 실현손익: +210,859원
- **[2025-01-14 12:30:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.92) breached lower threshold (-1.8). Buying spread. / 진입가: 315.54
- **[2025-01-14 12:51:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.10). / 실현손익: +43,142원
- **[2025-01-14 13:15:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.93) exceeded upper threshold (+1.8). Selling spread. / 진입가: 316.18
- **[2025-01-14 13:20:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.24). / 실현손익: +303,120원
- **[2025-01-14 13:34:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.96) breached lower threshold (-1.8). Buying spread. / 진입가: 313.64
- **[2025-01-14 13:40:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.12). / 실현손익: +149,892원
- **[2025-01-14 13:50:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.56) exceeded upper threshold (+1.8). Selling spread. / 진입가: 315.67
- **[2025-01-14 14:08:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.12). / 실현손익: +58,541원
- **[2025-01-14 14:45:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.94) breached lower threshold (-1.8). Buying spread. / 진입가: 314.97
- **[2025-01-14 14:49:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.18). / 실현손익: +282,028원
- **[2025-01-14 14:59:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.82) exceeded upper threshold (+1.8). Selling spread. / 진입가: 317.09
- **[2025-01-14 15:11:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.21). / 실현손익: +93,731원
- **[2025-01-15 09:00:00]** 영업일 2025-01-15 개장: 평가 자산: ₩24,902,106 / Track 7 할당 자본(0.5%): ₩124,511
- **[2025-01-15 09:00:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-6.80) breached lower threshold (-1.8). Buying spread. / 진입가: 312.65
- **[2025-01-15 09:25:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.17). / 실현손익: -316,723원
- **[2025-01-15 10:32:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.12) breached lower threshold (-1.8). Buying spread. / 진입가: 309.28
- **[2025-01-15 10:44:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.14). / 실현손익: -45,032원
- **[2025-01-15 11:02:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.98) breached lower threshold (-1.8). Buying spread. / 진입가: 306.61
- **[2025-01-15 11:08:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.17). / 실현손익: +139,870원
- **[2025-01-15 11:21:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.87) exceeded upper threshold (+1.8). Selling spread. / 진입가: 307.36
- **[2025-01-15 11:32:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.17). / 실현손익: +246,839원
- **[2025-01-15 11:42:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.89) exceeded upper threshold (+1.8). Selling spread. / 진입가: 307.33
- **[2025-01-15 11:49:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.00). / 실현손익: +223,744원
- **[2025-01-15 11:59:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.34) breached lower threshold (-1.8). Buying spread. / 진입가: 304.27
- **[2025-01-15 12:19:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.08). / 실현손익: -452,830원
- **[2025-01-15 12:52:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.91) exceeded upper threshold (+1.8). Selling spread. / 진입가: 302.87
- **[2025-01-15 13:12:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.02). / 실현손익: +222,214원
- **[2025-01-15 13:41:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.27) exceeded upper threshold (+1.8). Selling spread. / 진입가: 303.40
- **[2025-01-15 14:00:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.06). / 실현손익: -102,326원
- **[2025-01-15 14:42:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.89) breached lower threshold (-1.8). Buying spread. / 진입가: 304.06
- **[2025-01-15 14:46:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.05). / 실현손익: +233,891원
- **[2025-01-15 15:14:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.26) breached lower threshold (-1.8). Buying spread. / 진입가: 304.48
- **[2025-01-15 15:18:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.39). / 실현손익: +225,405원
- **[2025-01-15 15:28:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.95) exceeded upper threshold (+1.8). Selling spread. / 진입가: 306.73
- **[2025-01-16 09:00:00]** 영업일 2025-01-16 개장: 평가 자산: ₩25,202,265 / Track 7 할당 자본(0.5%): ₩126,011
- **[2025-01-16 09:28:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.17). / 실현손익: -1,945,975원
- **[2025-01-16 09:53:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.84) breached lower threshold (-1.8). Buying spread. / 진입가: 314.31
- **[2025-01-16 10:11:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.18). / 실현손익: +500,430원
- **[2025-01-16 10:56:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.22) breached lower threshold (-1.8). Buying spread. / 진입가: 318.17
- **[2025-01-16 11:26:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.12). / 실현손익: -404,111원
- **[2025-01-16 12:12:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.91) breached lower threshold (-1.8). Buying spread. / 진입가: 315.84
- **[2025-01-16 12:39:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.03). / 실현손익: -117,172원
- **[2025-01-16 12:49:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.04) exceeded upper threshold (+1.8). Selling spread. / 진입가: 316.70
- **[2025-01-16 13:06:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.16). / 실현손익: +31,833원
- **[2025-01-16 13:19:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.85) breached lower threshold (-1.8). Buying spread. / 진입가: 314.98
- **[2025-01-16 13:29:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.10). / 실현손익: +186,948원
- **[2025-01-16 13:45:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.96) exceeded upper threshold (+1.8). Selling spread. / 진입가: 317.69
- **[2025-01-16 14:02:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.14). / 실현손익: +72,413원
- **[2025-01-16 15:03:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.88) exceeded upper threshold (+1.8). Selling spread. / 진입가: 319.06
- **[2025-01-16 15:08:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.04). / 실현손익: +304,471원
- **[2025-01-17 09:00:00]** 영업일 2025-01-17 개장: 평가 자산: ₩24,818,885 / Track 7 할당 자본(0.5%): ₩124,094
- **[2025-01-17 09:00:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.44) exceeded upper threshold (+1.8). Selling spread. / 진입가: 319.94
- **[2025-01-17 09:08:00]** 보험 이익 수취 청산 (CALL): Strike: 325.0, 실현이익: +0원
- **[2025-01-17 09:13:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.22). / 실현손익: +263,494원
- **[2025-01-17 09:28:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.10) breached lower threshold (-1.8). Buying spread. / 진입가: 317.89
- **[2025-01-17 09:36:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.11). / 실현손익: +247,404원
- **[2025-01-17 09:53:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.81) breached lower threshold (-1.8). Buying spread. / 진입가: 317.28
- **[2025-01-17 10:00:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.02). / 실현손익: +299,514원
- **[2025-01-17 10:34:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.24) exceeded upper threshold (+1.8). Selling spread. / 진입가: 319.14
- **[2025-01-17 10:39:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.19). / 실현손익: +187,689원
- **[2025-01-17 10:58:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.10) breached lower threshold (-1.8). Buying spread. / 진입가: 317.54
- **[2025-01-17 11:16:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.10). / 실현손익: -69,779원
- **[2025-01-17 12:08:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.98) breached lower threshold (-1.8). Buying spread. / 진입가: 315.71
- **[2025-01-17 12:17:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.09). / 실현손익: +102,054원
- **[2025-01-17 12:29:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.05) exceeded upper threshold (+1.8). Selling spread. / 진입가: 317.10
- **[2025-01-17 12:50:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.15). / 실현손익: -54,586원
- **[2025-01-17 13:03:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.91) exceeded upper threshold (+1.8). Selling spread. / 진입가: 318.77
- **[2025-01-17 13:20:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.01). / 실현손익: -198,278원
- **[2025-01-17 13:30:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.92) breached lower threshold (-1.8). Buying spread. / 진입가: 318.69
- **[2025-01-17 14:11:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.15). / 실현손익: -369,510원
- **[2025-01-17 14:21:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.69) exceeded upper threshold (+1.8). Selling spread. / 진입가: 317.97
- **[2025-01-17 14:35:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.10). / 실현손익: +171,027원
- **[2025-01-17 15:01:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.12) exceeded upper threshold (+1.8). Selling spread. / 진입가: 318.66
- **[2025-01-17 15:11:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.09). / 실현손익: +133,888원
- **[2025-01-17 15:29:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.10) breached lower threshold (-1.8). Buying spread. / 진입가: 317.62
- **[2025-01-20 09:00:00]** 영업일 2025-01-20 개장: 평가 자산: ₩24,902,994 / Track 7 할당 자본(0.5%): ₩124,515
- **[2025-01-20 09:22:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.17). / 실현손익: -8,443원
- **[2025-01-20 10:09:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.81) exceeded upper threshold (+1.8). Selling spread. / 진입가: 318.22
- **[2025-01-20 10:40:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.02). / 실현손익: -520,011원
- **[2025-01-20 11:03:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.87) breached lower threshold (-1.8). Buying spread. / 진입가: 319.13
- **[2025-01-20 11:28:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.09). / 실현손익: -117,220원
- **[2025-01-20 12:17:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.16) exceeded upper threshold (+1.8). Selling spread. / 진입가: 317.41
- **[2025-01-20 12:36:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.14). / 실현손익: +106,169원
- **[2025-01-20 12:52:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.90) breached lower threshold (-1.8). Buying spread. / 진입가: 315.51
- **[2025-01-20 13:26:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.19). / 실현손익: -895,066원
- **[2025-01-20 13:36:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.95) exceeded upper threshold (+1.8). Selling spread. / 진입가: 314.14
- **[2025-01-20 14:23:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.05). / 실현손익: -558,893원
- **[2025-01-20 14:35:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.21) breached lower threshold (-1.8). Buying spread. / 진입가: 316.11
- **[2025-01-20 14:54:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.22). / 실현손익: +148,581원
- **[2025-01-20 15:25:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.94) breached lower threshold (-1.8). Buying spread. / 진입가: 314.56
- **[2025-01-21 09:00:00]** 영업일 2025-01-21 개장: 평가 자산: ₩24,857,474 / Track 7 할당 자본(0.5%): ₩124,287
- **[2025-01-21 09:13:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.11). / 실현손익: -257,081원
- **[2025-01-21 09:32:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.83) exceeded upper threshold (+1.8). Selling spread. / 진입가: 313.88
- **[2025-01-21 09:53:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.16). / 실현손익: -220,132원
- **[2025-01-21 10:24:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.84) exceeded upper threshold (+1.8). Selling spread. / 진입가: 316.96
- **[2025-01-21 10:38:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.15). / 실현손익: +24,938원
- **[2025-01-21 11:15:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.92) breached lower threshold (-1.8). Buying spread. / 진입가: 319.38
- **[2025-01-21 11:44:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.00). / 실현손익: -36,432원
- **[2025-01-21 13:12:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.20) exceeded upper threshold (+1.8). Selling spread. / 진입가: 318.68
- **[2025-01-21 13:21:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.07). / 실현손익: +154,253원
- **[2025-01-21 13:31:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.04) breached lower threshold (-1.8). Buying spread. / 진입가: 317.06
- **[2025-01-21 13:53:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.08). / 실현손익: -251,846원
- **[2025-01-21 14:27:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.10) exceeded upper threshold (+1.8). Selling spread. / 진입가: 314.21
- **[2025-01-21 14:48:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.08). / 실현손익: +68,267원
- **[2025-01-21 14:58:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.43) breached lower threshold (-1.8). Buying spread. / 진입가: 310.93
- **[2025-01-21 15:16:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.08). / 실현손익: -209,866원
- **[2025-01-22 09:00:00]** 영업일 2025-01-22 개장: 평가 자산: ₩24,963,922 / Track 7 할당 자본(0.5%): ₩124,820
- **[2025-01-22 09:12:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.85) exceeded upper threshold (+1.8). Selling spread. / 진입가: 311.46
- **[2025-01-22 09:42:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.12). / 실현손익: -317,477원
- **[2025-01-22 09:52:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.80) breached lower threshold (-1.8). Buying spread. / 진입가: 311.82
- **[2025-01-22 10:10:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.18). / 실현손익: +112,952원
- **[2025-01-22 11:07:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.87) exceeded upper threshold (+1.8). Selling spread. / 진입가: 313.37
- **[2025-01-22 11:11:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.04). / 실현손익: +158,755원
- **[2025-01-22 11:21:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.14) breached lower threshold (-1.8). Buying spread. / 진입가: 311.99
- **[2025-01-22 11:41:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.17). / 실현손익: -249,445원
- **[2025-01-22 12:24:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.85) exceeded upper threshold (+1.8). Selling spread. / 진입가: 309.12
- **[2025-01-22 12:34:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.09). / 실현손익: +213,891원
- **[2025-01-22 12:53:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.90) breached lower threshold (-1.8). Buying spread. / 진입가: 305.86
- **[2025-01-22 12:58:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.32). / 실현손익: +186,934원
- **[2025-01-22 13:09:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.84) exceeded upper threshold (+1.8). Selling spread. / 진입가: 307.35
- **[2025-01-22 13:32:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.16). / 실현손익: +1,612원
- **[2025-01-22 14:05:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.83) breached lower threshold (-1.8). Buying spread. / 진입가: 308.66
- **[2025-01-22 14:27:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.12). / 실현손익: +152,302원
- **[2025-01-22 14:46:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.85) breached lower threshold (-1.8). Buying spread. / 진입가: 307.00
- **[2025-01-22 14:59:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.11). / 실현손익: +67,101원
- **[2025-01-22 15:12:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.01) breached lower threshold (-1.8). Buying spread. / 진입가: 305.72
- **[2025-01-22 15:15:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.19). / 실현손익: +85,950원
- **[2025-01-23 09:00:00]** 영업일 2025-01-23 개장: 평가 자산: ₩25,008,164 / Track 7 할당 자본(0.5%): ₩125,041
- **[2025-01-23 09:00:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (6.36) exceeded upper threshold (+1.8). Selling spread. / 진입가: 308.27
- **[2025-01-23 09:23:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.00). / 실현손익: -91,233원
- **[2025-01-23 10:31:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.97) breached lower threshold (-1.8). Buying spread. / 진입가: 305.11
- **[2025-01-23 10:43:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.17). / 실현손익: -93,799원
- **[2025-01-23 11:00:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.06) exceeded upper threshold (+1.8). Selling spread. / 진입가: 304.75
- **[2025-01-23 11:33:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.19). / 실현손익: +215,632원
- **[2025-01-23 11:46:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.96) exceeded upper threshold (+1.8). Selling spread. / 진입가: 305.60
- **[2025-01-23 11:53:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.12). / 실현손익: +127,113원
- **[2025-01-23 12:04:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (1.87) exceeded upper threshold (+1.8). Selling spread. / 진입가: 306.33
- **[2025-01-23 12:07:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.40). / 실현손익: +186,942원
- **[2025-01-23 12:42:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.98) breached lower threshold (-1.8). Buying spread. / 진입가: 305.93


### 💰 1. 자산 및 자본 종합 요약
- **시작 총자산 (Starting Equity)**: ₩25,021,260
- **종료 총자산 (Ending Equity)**: ₩24,866,025
- **실현/평가 순손익 (Net Profit)**: **₩-155,236 (-0.620%)**
- **최대 낙폭 (Max Drawdown, MDD)**: ₩6,754,499 (24.748%)
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
- **HIGH_VOL** 국면: 84.2%
- **NOISE_CHOPPY** 국면: 15.8%

### 🌋 4. Self-Tuning Guard (리스크 미세조정) 성능 지표
- **평균 수량 조절 계수 (Avg Tuning Factor)**: **40.0%**
- **최저 수량 조절 계수 (Min Tuning Factor)**: **40.0%**
- **평균 매칭 딜레이 (Avg Slippage Latency)**: **50.0 ms**
- **최대 매칭 딜레이 (Max Slippage Latency)**: **50 ms**

### 🛡️ 5. 전략별 국면 및 PnL 성과분석 (Strategy Breakdown)
| 전략 (Strategy) | 총 누적 손익 (Total PnL) | 스트레스 국면 손익 (Stress PnL) | 평균 비중 | 방어 동작 방식 |
| :--- | :--- | :--- | :--- | :--- |
| **Track1 (Defense)** | ₩+8,629 | ₩+0 | 30.0% | 리스크 급증 시 100% 비중으로 증거금 제한 및 숏옵션 커버 |
| **Track2 (Trap)** | ₩+3,698 | ₩+0 | 10.0% | ⛔ **[V2 HOLD]** 박스권 내 역추세 포지션 진입 중단 |
| **Track3 (Arbitrage)** | ₩+1,233 | ₩+0 | 5.0% | ⛔ **[V2 HOLD]** 시뮬레이션 순도 유지를 위한 차익 진입 전면 차단 |
| **Track4 (Gamma)** | ₩+2,465 | ₩+0 | 5.0% | ⛔ **[V2 HOLD]** 현물 델타 헤징 및 스켈핑 중단 |
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
