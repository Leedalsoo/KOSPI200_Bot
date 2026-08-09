# 📊 KOSPI200 HFT 가상 테스트 세션 통합 분석 보고서
통합 보고서 최종 갱신 시각: 2026-08-09 14:15:56
총 구동 세션 수: 1개 세션

---


## 🔁 [SESSION #1] 상세 분석 보고서
- **적용된 실제 투자 일자 (Trading Date)**: **2025-01-10, 2025-01-13, 2025-01-14, 2025-01-15, 2025-01-16, 2025-01-17, 2025-01-20, 2025-01-21, 2025-01-22, 2025-01-23, 2025-01-24, 2025-01-27, 2025-01-31, 2025-02-03, 2025-02-04, 2025-02-05, 2025-02-06, 2025-02-07, 2025-02-10, 2025-02-11, 2025-02-12, 2025-02-13, 2025-02-14, 2025-02-17, 2025-02-18, 2025-02-19, 2025-02-20, 2025-02-21, 2025-02-24, 2025-02-25, 2025-02-26, 2025-02-27, 2025-02-28, 2025-03-04, 2025-03-05, 2025-03-06, 2025-03-07, 2025-03-10, 2025-03-11, 2025-03-12, 2025-03-13, 2025-03-14**
- **테스트 규모**: 총 31979 틱 스트리밍

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
- **[2025-01-10 09:50:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.45) <= threshold (-2.00) & Expected Net PnL (KRW 91,979) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0001 / 진입가: 367.33
- **[2025-01-10 10:23:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.47) <= threshold (-2.00) & Expected Net PnL (KRW 273,949) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0002 / 진입가: 367.37
- **[2025-01-10 10:44:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.71) <= threshold (-2.00) & Expected Net PnL (KRW 279,774) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0003 / 진입가: 366.96
- **[2025-01-10 11:37:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (2.09) with Economic Profitability (Net PnL: KRW -3,277). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0003 / 실현손익: -126,403원
- **[2025-01-10 12:10:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.00) <= threshold (-2.00) & Expected Net PnL (KRW 225,191) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0004 / 진입가: 366.20
- **[2025-01-10 13:00:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.23) >= threshold (2.00) & Expected Net PnL (KRW 119,872) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0005 / 진입가: 366.30
- **[2025-01-10 13:04:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.07) with Economic Profitability (Net PnL: KRW 2,664). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0005 / 실현손익: -581,336원
- **[2025-01-10 13:14:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.52) >= threshold (2.00) & Expected Net PnL (KRW 144,924) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0006 / 진입가: 366.17
- **[2025-01-10 14:02:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.03) >= threshold (2.00) & Expected Net PnL (KRW 294,335) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0007 / 진입가: 367.14
- **[2025-01-10 14:28:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-1.29) with Economic Profitability (Net PnL: KRW -4,510). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0007 / 실현손익: +118,157원
- **[2025-01-10 15:12:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.16) >= threshold (2.00) & Expected Net PnL (KRW 373,123) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0008 / 진입가: 366.87
- **[2025-01-10 15:15:00]** Track1 오버나잇 갭 방어 헷지 매입: Target: 1 (가두리 매도 2 기준) | Qty: +1, Cost: ₩75,000
- **[2025-01-13 09:00:00]** 영업일 2025-01-13 개장: 평가 자산: ₩24,403,680 / Track 7 할당 자본(0.5%): ₩122,018
- **[2025-01-13 09:00:00]** Track 7 Weekly Insurance Buy: New trading week started. Setting up weekly limit queue strangle protection via Mid-Price Adapter. / 지출예산: ₩350,000
- **[2025-01-13 10:41:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.08) <= threshold (-2.00) & Expected Net PnL (KRW 150,025) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0009 / 진입가: 362.74
- **[2025-01-13 12:11:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.69) >= threshold (2.00) & Expected Net PnL (KRW 261,496) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0010 / 진입가: 366.23
- **[2025-01-13 14:13:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-1.68) with Economic Profitability (Net PnL: KRW -1,328). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0010 / 실현손익: -2,102,434원
- **[2025-01-13 14:37:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.06) >= threshold (2.00) & Expected Net PnL (KRW 331,843) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0011 / 진입가: 366.12
- **[2025-01-13 14:57:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.33) with Economic Profitability (Net PnL: KRW -609). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0011 / 실현손익: +119,308원
- **[2025-01-14 09:00:00]** 영업일 2025-01-14 개장: 평가 자산: ₩22,355,285 / Track 7 할당 자본(0.5%): ₩111,776
- **[2025-01-14 09:00:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (4.83) >= threshold (2.00) & Expected Net PnL (KRW 1,000,472) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0012 / 진입가: 370.61
- **[2025-01-14 10:32:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.23) <= threshold (-2.00) & Expected Net PnL (KRW 254,560) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0013 / 진입가: 370.75
- **[2025-01-14 13:24:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.33) <= threshold (-2.00) & Expected Net PnL (KRW 228,046) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0014 / 진입가: 364.79
- **[2025-01-15 09:00:00]** 영업일 2025-01-15 개장: 평가 자산: ₩22,357,968 / Track 7 할당 자본(0.5%): ₩111,790
- **[2025-01-15 10:16:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.01) >= threshold (2.00) & Expected Net PnL (KRW 216,700) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0015 / 진입가: 355.61
- **[2025-01-15 10:21:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.09) with Economic Profitability (Net PnL: KRW 21,167). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0015 / 실현손익: +5,344,904원
- **[2025-01-15 10:51:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.11) >= threshold (2.00) & Expected Net PnL (KRW 276,305) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0016 / 진입가: 354.34
- **[2025-01-15 11:39:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-2.65) with Economic Profitability (Net PnL: KRW -2,536). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0016 / 실현손익: -319,079원
- **[2025-01-15 13:09:00]** 보험 이익 수취 청산 (PUT): Strike: 352.5, 실현이익: +267,389원
- **[2025-01-15 13:28:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.11) >= threshold (2.00) & Expected Net PnL (KRW 180,660) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0017 / 진입가: 351.80
- **[2025-01-15 14:13:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-1.15) with Economic Profitability (Net PnL: KRW -2,136). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0017 / 실현손익: -331,487원
- **[2025-01-15 14:55:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.00) <= threshold (-2.00) & Expected Net PnL (KRW 142,147) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0018 / 진입가: 350.77
- **[2025-01-15 15:15:00]** Track1 오버나잇 갭 방어 헷지 매입: Target: 1 (가두리 매도 1 기준) | Qty: +1, Cost: ₩75,000
- **[2025-01-15 15:23:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.18) >= threshold (2.00) & Expected Net PnL (KRW 130,578) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0019 / 진입가: 352.17
- **[2025-01-15 15:25:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.39) with Economic Profitability (Net PnL: KRW 7,689). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0019 / 실현손익: -576,311원
- **[2025-01-16 09:00:00]** 영업일 2025-01-16 개장: 평가 자산: ₩26,611,735 / Track 7 할당 자본(0.5%): ₩133,059
- **[2025-01-16 09:08:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.13) >= threshold (2.00) & Expected Net PnL (KRW 175,800) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0020 / 진입가: 353.08
- **[2025-01-16 09:14:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.10) with Economic Profitability (Net PnL: KRW -1,784). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0020 / 실현손익: -12,724원
- **[2025-01-16 09:35:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.06) <= threshold (-2.00) & Expected Net PnL (KRW 159,098) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0021 / 진입가: 352.02
- **[2025-01-16 09:47:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.03) with Economic Profitability (Net PnL: KRW -4,974). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0021 / 실현손익: -24,194원
- **[2025-01-16 10:01:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.13) >= threshold (2.00) & Expected Net PnL (KRW 201,366) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0022 / 진입가: 353.66
- **[2025-01-16 12:41:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.26) <= threshold (-2.00) & Expected Net PnL (KRW 395,641) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0023 / 진입가: 356.53
- **[2025-01-16 13:18:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (2.80) with Economic Profitability (Net PnL: KRW 2,147). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0023 / 실현손익: +1,293,147원
- **[2025-01-16 15:12:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.06) <= threshold (-2.00) & Expected Net PnL (KRW 200,742) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0024 / 진입가: 359.32
- **[2025-01-17 09:00:00]** 영업일 2025-01-17 개장: 평가 자산: ₩27,983,882 / Track 7 할당 자본(0.5%): ₩139,919
- **[2025-01-17 09:00:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (6.12) with Economic Profitability (Net PnL: KRW 196,463). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0024 / 실현손익: -780,541원
- **[2025-01-17 11:11:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.06) >= threshold (2.00) & Expected Net PnL (KRW 252,654) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0025 / 진입가: 366.06
- **[2025-01-17 11:39:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-2.03) with Economic Profitability (Net PnL: KRW 8,735). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0025 / 실현손익: +66,534원
- **[2025-01-17 12:22:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.04) >= threshold (2.00) & Expected Net PnL (KRW 383,337) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0026 / 진입가: 365.91
- **[2025-01-17 13:11:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-1.87) with Economic Profitability (Net PnL: KRW -4,425). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0026 / 실현손익: +80,175원
- **[2025-01-17 13:30:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.12) >= threshold (2.00) & Expected Net PnL (KRW 252,513) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0027 / 진입가: 368.07
- **[2025-01-17 13:56:00]** 보험 이익 수취 청산 (CALL): Strike: 367.5, 실현이익: +274,011원
- **[2025-01-17 14:07:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.31) >= threshold (2.00) & Expected Net PnL (KRW 284,214) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0028 / 진입가: 370.55
- **[2025-01-17 14:33:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.15) <= threshold (-2.00) & Expected Net PnL (KRW 259,047) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0029 / 진입가: 370.15
- **[2025-01-20 09:00:00]** 영업일 2025-01-20 개장: 평가 자산: ₩27,626,093 / Track 7 할당 자본(0.5%): ₩138,130
- **[2025-01-20 09:00:00]** Track 7 Weekly Insurance Buy: New trading week started. Setting up weekly limit queue strangle protection via Mid-Price Adapter. / 지출예산: ₩350,000
- **[2025-01-20 09:45:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.06) >= threshold (2.00) & Expected Net PnL (KRW 161,077) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0030 / 진입가: 369.54
- **[2025-01-20 09:53:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.10) with Economic Profitability (Net PnL: KRW 3,426). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0030 / 실현손익: -3,690원
- **[2025-01-20 10:55:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.13) <= threshold (-2.00) & Expected Net PnL (KRW 190,182) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0031 / 진입가: 368.08
- **[2025-01-20 11:00:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.08) with Economic Profitability (Net PnL: KRW 2,159). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0031 / 실현손익: -317,894원
- **[2025-01-20 11:31:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.06) <= threshold (-2.00) & Expected Net PnL (KRW 222,877) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0032 / 진입가: 367.89
- **[2025-01-20 12:28:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.15) <= threshold (-2.00) & Expected Net PnL (KRW 111,738) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0033 / 진입가: 365.46
- **[2025-01-20 12:32:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.73) with Economic Profitability (Net PnL: KRW 213). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0033 / 실현손익: +24,217원
- **[2025-01-20 12:53:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.18) >= threshold (2.00) & Expected Net PnL (KRW 119,003) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0034 / 진입가: 365.53
- **[2025-01-20 13:37:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-1.76) with Economic Profitability (Net PnL: KRW -839). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0034 / 실현손익: -27,398원
- **[2025-01-20 14:31:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.40) >= threshold (2.00) & Expected Net PnL (KRW 196,494) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0035 / 진입가: 363.97
- **[2025-01-20 14:45:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.15) with Economic Profitability (Net PnL: KRW 700). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0035 / 실현손익: -424,098원
- **[2025-01-20 15:11:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.23) >= threshold (2.00) & Expected Net PnL (KRW 162,050) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0036 / 진입가: 365.25
- **[2025-01-20 15:26:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-1.96) with Economic Profitability (Net PnL: KRW 5,824). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0036 / 실현손익: -124,878원
- **[2025-01-21 09:00:00]** 영업일 2025-01-21 개장: 평가 자산: ₩26,664,450 / Track 7 할당 자본(0.5%): ₩133,322
- **[2025-01-21 09:06:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.21) >= threshold (2.00) & Expected Net PnL (KRW 461,744) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0037 / 진입가: 369.23
- **[2025-01-21 09:38:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-2.07) with Economic Profitability (Net PnL: KRW -220). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0037 / 실현손익: -354,489원
- **[2025-01-21 10:53:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.20) >= threshold (2.00) & Expected Net PnL (KRW 113,926) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0038 / 진입가: 369.24
- **[2025-01-21 13:33:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.41) >= threshold (2.00) & Expected Net PnL (KRW 265,193) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0039 / 진입가: 372.01
- **[2025-01-21 14:22:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.00) <= threshold (-2.00) & Expected Net PnL (KRW 209,446) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0040 / 진입가: 373.54
- **[2025-01-21 14:59:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (1.47) with Economic Profitability (Net PnL: KRW 9,066). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0040 / 실현손익: +1,186,125원
- **[2025-01-22 09:00:00]** 영업일 2025-01-22 개장: 평가 자산: ₩27,544,885 / Track 7 할당 자본(0.5%): ₩137,724
- **[2025-01-22 09:00:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (5.89) >= threshold (2.00) & Expected Net PnL (KRW 1,310,662) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0041 / 진입가: 381.46
- **[2025-01-22 09:00:00]** 보험 이익 수취 청산 (CALL): Strike: 380.0, 실현이익: +364,043원
- **[2025-01-22 09:00:00]** 보험 이익 수취 청산 (CALL): Strike: 380.0, 실현이익: +364,043원
- **[2025-01-22 10:19:30]** 보험 이익 수취 청산 (CALL): Strike: 382.5, 실현이익: +281,095원
- **[2025-01-22 10:46:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.20) >= threshold (2.00) & Expected Net PnL (KRW 310,701) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0042 / 진입가: 385.73
- **[2025-01-22 10:49:30]** 보험 이익 수취 청산 (CALL): Strike: 385.0, 실현이익: +293,420원
- **[2025-01-22 10:53:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.02) with Economic Profitability (Net PnL: KRW 2,336). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0042 / 실현손익: +600,278원
- **[2025-01-22 11:08:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.05) <= threshold (-2.00) & Expected Net PnL (KRW 194,882) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0043 / 진입가: 384.57
- **[2025-01-22 11:45:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.01) <= threshold (-2.00) & Expected Net PnL (KRW 252,354) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0044 / 진입가: 383.67
- **[2025-01-22 12:08:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.34) <= threshold (-2.00) & Expected Net PnL (KRW 189,306) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0045 / 진입가: 382.33
- **[2025-01-22 12:10:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.20) with Economic Profitability (Net PnL: KRW 4,116). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0045 / 실현손익: +124,166원
- **[2025-01-22 12:36:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.36) >= threshold (2.00) & Expected Net PnL (KRW 165,570) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0046 / 진입가: 383.79
- **[2025-01-22 12:56:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.49) <= threshold (-2.00) & Expected Net PnL (KRW 182,632) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0047 / 진입가: 381.92
- **[2025-01-22 13:00:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.14) with Economic Profitability (Net PnL: KRW -2,413). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0047 / 실현손익: -586,413원
- **[2025-01-22 13:17:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.13) >= threshold (2.00) & Expected Net PnL (KRW 178,371) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0048 / 진입가: 383.26
- **[2025-01-22 13:37:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.05) >= threshold (2.00) & Expected Net PnL (KRW 182,778) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0049 / 진입가: 383.23
- **[2025-01-23 09:00:00]** 영업일 2025-01-23 개장: 평가 자산: ₩28,789,948 / Track 7 할당 자본(0.5%): ₩143,950
- **[2025-01-23 09:51:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.27) <= threshold (-2.00) & Expected Net PnL (KRW 261,606) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0050 / 진입가: 383.90
- **[2025-01-23 10:48:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.00) >= threshold (2.00) & Expected Net PnL (KRW 86,223) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0051 / 진입가: 382.54
- **[2025-01-23 11:01:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.88) >= threshold (2.00) & Expected Net PnL (KRW 314,418) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0052 / 진입가: 383.98
- **[2025-01-23 11:12:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.10) with Economic Profitability (Net PnL: KRW 3,475). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0052 / 실현손익: +489,734원
- **[2025-01-23 12:41:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.39) <= threshold (-2.00) & Expected Net PnL (KRW 213,304) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0053 / 진입가: 383.27
- **[2025-01-24 09:00:00]** 영업일 2025-01-24 개장: 평가 자산: ₩29,415,606 / Track 7 할당 자본(0.5%): ₩147,078
- **[2025-01-24 09:00:00]** 2주간격 7.0pt 약충격 주입: 평온 장세 테스트: 2주 간격 1회 하루 등락폭 7.0포인트 자율 가변 약충격
- **[2025-01-24 09:00:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-3.79) <= threshold (-2.00) & Expected Net PnL (KRW 525,810) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0054 / 진입가: 375.88
- **[2025-01-27 09:00:00]** 영업일 2025-01-27 개장: 평가 자산: ₩29,447,366 / Track 7 할당 자본(0.5%): ₩147,237
- **[2025-01-27 09:00:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (10.91) >= threshold (2.00) & Expected Net PnL (KRW 22,546) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0055 / 진입가: 376.21
- **[2025-01-27 09:00:00]** Track 7 Weekly Insurance Buy: New trading week started. Setting up weekly limit queue strangle protection via Mid-Price Adapter. / 지출예산: ₩350,000
- **[2025-01-27 09:23:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.69) >= threshold (2.00) & Expected Net PnL (KRW 74,505) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0056 / 진입가: 376.47
- **[2025-01-27 09:38:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-2.05) with Economic Profitability (Net PnL: KRW 5,918). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0056 / 실현손익: +1,296,918원
- **[2025-01-27 10:29:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.39) >= threshold (2.00) & Expected Net PnL (KRW 256,559) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0057 / 진입가: 376.08
- **[2025-01-27 11:36:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.55) >= threshold (2.00) & Expected Net PnL (KRW 302,876) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0058 / 진입가: 374.71
- **[2025-01-27 12:39:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.01) <= threshold (-2.00) & Expected Net PnL (KRW 205,638) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0059 / 진입가: 371.85
- **[2025-01-31 09:00:00]** 영업일 2025-01-31 개장: 평가 자산: ₩30,814,970 / Track 7 할당 자본(0.5%): ₩154,075
- **[2025-01-31 09:46:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.62) >= threshold (2.00) & Expected Net PnL (KRW 144,658) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0060 / 진입가: 362.83
- **[2025-01-31 11:33:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.67) >= threshold (2.00) & Expected Net PnL (KRW 192,828) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0061 / 진입가: 365.44
- **[2025-01-31 12:17:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-2.24) with Economic Profitability (Net PnL: KRW 7,796). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0061 / 실현손익: +165,369원
- **[2025-01-31 13:04:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.34) >= threshold (2.00) & Expected Net PnL (KRW 211,886) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0062 / 진입가: 365.30
- **[2025-01-31 13:26:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.91) with Economic Profitability (Net PnL: KRW -4,906). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0062 / 실현손익: -69,188원
- **[2025-01-31 13:36:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.84) <= threshold (-2.00) & Expected Net PnL (KRW 446,751) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0063 / 진입가: 362.74
- **[2025-01-31 14:20:00]** 보험 이익 수취 청산 (PUT): Strike: 360.0, 실현이익: +263,095원
- **[2025-02-03 09:00:00]** 영업일 2025-02-03 개장: 평가 자산: ₩31,043,532 / Track 7 할당 자본(0.5%): ₩155,218
- **[2025-02-03 09:00:00]** 월 변경 자본금 & 코스피 지수 100% 연속 이월: 전월 자산 ₩31,043,532 / 최종 지수 357.74pt 차월 승계 완료
- **[2025-02-03 09:00:00]** Track 7 Weekly Insurance Buy: New trading week started. Setting up weekly limit queue strangle protection via Mid-Price Adapter. / 지출예산: ₩350,000
- **[2025-02-03 10:11:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.02) >= threshold (2.00) & Expected Net PnL (KRW 118,386) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0064 / 진입가: 358.91
- **[2025-02-03 10:26:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.94) with Economic Profitability (Net PnL: KRW 654). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0064 / 실현손익: +666,654원
- **[2025-02-03 10:40:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.31) >= threshold (2.00) & Expected Net PnL (KRW 234,373) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0065 / 진입가: 360.09
- **[2025-02-03 13:57:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.05) <= threshold (-2.00) & Expected Net PnL (KRW 152,724) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0066 / 진입가: 366.04
- **[2025-02-03 15:15:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (1.25) with Economic Profitability (Net PnL: KRW 1,577). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0066 / 실현손익: +1,292,577원
- **[2025-02-03 15:28:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.45) >= threshold (2.00) & Expected Net PnL (KRW 207,853) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0067 / 진입가: 368.94
- **[2025-02-04 09:00:00]** 영업일 2025-02-04 개장: 평가 자산: ₩33,066,462 / Track 7 할당 자본(0.5%): ₩165,332
- **[2025-02-04 10:05:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.23) >= threshold (2.00) & Expected Net PnL (KRW 257,850) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0068 / 진입가: 371.20
- **[2025-02-04 10:32:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.28) <= threshold (-2.00) & Expected Net PnL (KRW 198,605) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0069 / 진입가: 369.91
- **[2025-02-04 11:14:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.26) >= threshold (2.00) & Expected Net PnL (KRW 213,546) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0070 / 진입가: 370.46
- **[2025-02-04 11:37:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-1.23) with Economic Profitability (Net PnL: KRW 9,667). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0070 / 실현손익: -227,707원
- **[2025-02-04 12:26:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.09) >= threshold (2.00) & Expected Net PnL (KRW 214,514) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0071 / 진입가: 369.37
- **[2025-02-04 14:27:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.09) >= threshold (2.00) & Expected Net PnL (KRW 123,447) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0072 / 진입가: 370.49
- **[2025-02-04 15:01:00]** 보험 이익 수취 청산 (CALL): Strike: 372.5, 실현이익: +257,977원
- **[2025-02-05 09:00:00]** 영업일 2025-02-05 개장: 평가 자산: ₩33,126,548 / Track 7 할당 자본(0.5%): ₩165,633
- **[2025-02-05 11:28:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.01) >= threshold (2.00) & Expected Net PnL (KRW 224,299) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0073 / 진입가: 385.55
- **[2025-02-05 12:09:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.12) <= threshold (-2.00) & Expected Net PnL (KRW 80,130) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0074 / 진입가: 387.65
- **[2025-02-05 13:17:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.08) <= threshold (-2.00) & Expected Net PnL (KRW 190,368) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0075 / 진입가: 385.41
- **[2025-02-05 13:26:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.37) with Economic Profitability (Net PnL: KRW -3,575). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0075 / 실현손익: +8,451,844원
- **[2025-02-05 13:36:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.59) >= threshold (2.00) & Expected Net PnL (KRW 254,094) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0076 / 진입가: 387.28
- **[2025-02-05 13:59:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.33) <= threshold (-2.00) & Expected Net PnL (KRW 271,754) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0077 / 진입가: 384.04
- **[2025-02-06 09:00:00]** 영업일 2025-02-06 개장: 평가 자산: ₩41,554,574 / Track 7 할당 자본(0.5%): ₩207,773
- **[2025-02-06 09:00:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (8.24) with Economic Profitability (Net PnL: KRW 189,602). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0077 / 실현손익: -1,519,398원
- **[2025-02-06 11:35:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.14) >= threshold (2.00) & Expected Net PnL (KRW 183,814) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0078 / 진입가: 386.04
- **[2025-02-06 12:02:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.15) <= threshold (-2.00) & Expected Net PnL (KRW 203,559) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0079 / 진입가: 384.53
- **[2025-02-06 14:16:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.12) >= threshold (2.00) & Expected Net PnL (KRW 152,085) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0080 / 진입가: 383.73
- **[2025-02-06 14:39:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.87) with Economic Profitability (Net PnL: KRW 313). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0080 / 실현손익: +142,213원
- **[2025-02-06 15:22:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.25) <= threshold (-2.00) & Expected Net PnL (KRW 202,538) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0081 / 진입가: 382.33
- **[2025-02-06 15:28:30]** Track 8 Monthly Strangle Cutoff: D-3 강제 청산 집행 / 정산회수: +0원
- **[2025-02-07 09:00:00]** 영업일 2025-02-07 개장: 평가 자산: ₩40,156,433 / Track 7 할당 자본(0.5%): ₩200,782
- **[2025-02-07 09:00:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (6.29) with Economic Profitability (Net PnL: KRW 240,601). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0081 / 실현손익: -841,335원
- **[2025-02-07 10:47:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.48) <= threshold (-2.00) & Expected Net PnL (KRW 175,353) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0082 / 진입가: 387.84
- **[2025-02-07 10:50:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.04) with Economic Profitability (Net PnL: KRW 10,626). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0082 / 실현손익: -290,284원
- **[2025-02-07 11:34:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.35) >= threshold (2.00) & Expected Net PnL (KRW 143,054) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0083 / 진입가: 389.42
- **[2025-02-07 11:56:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.04) <= threshold (-2.00) & Expected Net PnL (KRW 157,337) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0084 / 진입가: 388.16
- **[2025-02-07 11:59:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.06) with Economic Profitability (Net PnL: KRW 10,962). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0084 / 실현손익: -573,038원
- **[2025-02-07 12:12:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.49) <= threshold (-2.00) & Expected Net PnL (KRW 189,341) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0085 / 진입가: 387.96
- **[2025-02-07 15:14:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.01) >= threshold (2.00) & Expected Net PnL (KRW 225,321) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0086 / 진입가: 386.47
- **[2025-02-10 09:00:00]** 영업일 2025-02-10 개장: 평가 자산: ₩38,407,042 / Track 7 할당 자본(0.5%): ₩192,035
- **[2025-02-10 09:00:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (6.61) >= threshold (2.00) & Expected Net PnL (KRW 1,014,188) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0087 / 진입가: 390.99
- **[2025-02-10 09:00:00]** Track 7 Weekly Insurance Buy: New trading week started. Setting up weekly limit queue strangle protection via Mid-Price Adapter. / 지출예산: ₩350,000
- **[2025-02-10 09:16:30]** 보험 이익 수취 청산 (CALL): Strike: 390.0, 실현이익: +253,737원
- **[2025-02-10 10:30:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.08) <= threshold (-2.00) & Expected Net PnL (KRW 261,968) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0088 / 진입가: 393.31
- **[2025-02-10 11:17:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.17) >= threshold (2.00) & Expected Net PnL (KRW 204,448) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0089 / 진입가: 396.24
- **[2025-02-10 11:23:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.40) with Economic Profitability (Net PnL: KRW 10,584). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0089 / 실현손익: +1,530,350원
- **[2025-02-10 11:33:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.33) <= threshold (-2.00) & Expected Net PnL (KRW 221,327) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0090 / 진입가: 394.16
- **[2025-02-10 13:17:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.09) >= threshold (2.00) & Expected Net PnL (KRW 137,198) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0091 / 진입가: 396.28
- **[2025-02-11 09:00:00]** 영업일 2025-02-11 개장: 평가 자산: ₩40,215,588 / Track 7 할당 자본(0.5%): ₩201,078
- **[2025-02-11 09:41:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.08) <= threshold (-2.00) & Expected Net PnL (KRW 176,954) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0092 / 진입가: 395.18
- **[2025-02-11 09:45:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.13) with Economic Profitability (Net PnL: KRW -1,239). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0092 / 실현손익: -829,402원
- **[2025-02-11 10:00:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.12) >= threshold (2.00) & Expected Net PnL (KRW 175,577) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0093 / 진입가: 396.63
- **[2025-02-11 10:41:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.02) <= threshold (-2.00) & Expected Net PnL (KRW 165,225) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0094 / 진입가: 394.60
- **[2025-02-11 11:47:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.35) >= threshold (2.00) & Expected Net PnL (KRW 164,493) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0095 / 진입가: 394.97
- **[2025-02-11 11:52:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.29) with Economic Profitability (Net PnL: KRW 12,982). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0095 / 실현손익: -848,560원
- **[2025-02-11 12:30:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.09) <= threshold (-2.00) & Expected Net PnL (KRW 176,865) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0096 / 진입가: 393.77
- **[2025-02-11 12:33:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.08) with Economic Profitability (Net PnL: KRW 8,016). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0096 / 실현손익: +110,702원
- **[2025-02-11 12:53:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.16) <= threshold (-2.00) & Expected Net PnL (KRW 147,524) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0097 / 진입가: 393.77
- **[2025-02-11 13:22:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.01) >= threshold (2.00) & Expected Net PnL (KRW 191,124) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0098 / 진입가: 395.88
- **[2025-02-11 13:34:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.64) <= threshold (-2.00) & Expected Net PnL (KRW 307,167) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0099 / 진입가: 393.36
- **[2025-02-12 09:00:00]** 영업일 2025-02-12 개장: 평가 자산: ₩38,684,133 / Track 7 할당 자본(0.5%): ₩193,421
- **[2025-02-12 09:17:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.16) <= threshold (-2.00) & Expected Net PnL (KRW 129,895) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0100 / 진입가: 398.08
- **[2025-02-12 11:00:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.18) <= threshold (-2.00) & Expected Net PnL (KRW 199,254) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0101 / 진입가: 399.70
- **[2025-02-12 13:47:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.35) <= threshold (-2.00) & Expected Net PnL (KRW 125,158) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0102 / 진입가: 394.02
- **[2025-02-12 14:32:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.09) >= threshold (2.00) & Expected Net PnL (KRW 216,675) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0103 / 진입가: 392.75
- **[2025-02-12 14:42:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.19) with Economic Profitability (Net PnL: KRW 3,364). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0103 / 실현손익: +2,018,857원
- **[2025-02-12 14:55:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.16) >= threshold (2.00) & Expected Net PnL (KRW 301,140) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0104 / 진입가: 394.12
- **[2025-02-12 15:08:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.54) with Economic Profitability (Net PnL: KRW 6,073). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0104 / 실현손익: -407,972원
- **[2025-02-12 15:28:30]** 월 만기 옵션 정산 & 자본 이월: 정산손익: +11,250,188원 / 이월 자본금: ₩51,540,976
- **[2025-02-13 09:00:00]** 영업일 2025-02-13 개장: 평가 자산: ₩51,535,986 / Track 7 할당 자본(0.5%): ₩257,680
- **[2025-02-13 09:00:00]** 2주간격 5.9pt 약충격 주입: 평온 장세 테스트: 2주 간격 1회 하루 등락폭 5.9포인트 자율 가변 약충격
- **[2025-02-13 15:15:00]** Track1 오버나잇 갭 방어 헷지 매입: Target: 1 (가두리 매도 3 기준) | Qty: +1, Cost: ₩75,000
- **[2025-02-14 09:00:00]** 영업일 2025-02-14 개장: 평가 자산: ₩51,465,975 / Track 7 할당 자본(0.5%): ₩257,330
- **[2025-02-14 09:00:30]** Track 8 Monthly Strangle Buy: DTE 18.0 월물 초입 지정가 분할 큐 진입 via Mid-Price Adapter (비대칭 스큐 1.5x) / 지출예산: ₩1,725,000
- **[2025-02-14 09:03:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-8.04) <= threshold (-2.00) & Expected Net PnL (KRW 60,677) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0105 / 진입가: 393.35
- **[2025-02-14 09:30:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.56) <= threshold (-2.00) & Expected Net PnL (KRW 83,714) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0106 / 진입가: 393.21
- **[2025-02-14 10:57:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.06) >= threshold (2.00) & Expected Net PnL (KRW 87,207) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0107 / 진입가: 393.15
- **[2025-02-14 11:00:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.48) with Economic Profitability (Net PnL: KRW -1,263). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0107 / 실현손익: +74,860원
- **[2025-02-14 11:21:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.23) <= threshold (-2.00) & Expected Net PnL (KRW 81,160) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0108 / 진입가: 392.03
- **[2025-02-14 11:25:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.93) with Economic Profitability (Net PnL: KRW 1,595). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0108 / 실현손익: -54,019원
- **[2025-02-14 11:35:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.35) >= threshold (2.00) & Expected Net PnL (KRW 127,055) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0109 / 진입가: 393.75
- **[2025-02-14 12:36:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-1.78) with Economic Profitability (Net PnL: KRW 2,382). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0109 / 실현손익: -485,349원
- **[2025-02-14 12:56:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.09) >= threshold (2.00) & Expected Net PnL (KRW 179,075) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0110 / 진입가: 394.44
- **[2025-02-14 13:46:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.32) <= threshold (-2.00) & Expected Net PnL (KRW 227,043) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0111 / 진입가: 394.50
- **[2025-02-17 09:00:00]** 영업일 2025-02-17 개장: 평가 자산: ₩51,018,194 / Track 7 할당 자본(0.5%): ₩255,091
- **[2025-02-17 09:00:00]** Track 7 Weekly Insurance Buy: New trading week started. Setting up weekly limit queue strangle protection via Mid-Price Adapter. / 지출예산: ₩350,000
- **[2025-02-17 10:23:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.19) <= threshold (-2.00) & Expected Net PnL (KRW 108,536) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0112 / 진입가: 386.29
- **[2025-02-17 12:14:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (2.78) with Economic Profitability (Net PnL: KRW 6,813). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0112 / 실현손익: +925,533원
- **[2025-02-18 09:00:00]** 영업일 2025-02-18 개장: 평가 자산: ₩51,913,923 / Track 7 할당 자본(0.5%): ₩259,570
- **[2025-02-18 09:28:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.32) <= threshold (-2.00) & Expected Net PnL (KRW 145,850) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0113 / 진입가: 386.16
- **[2025-02-18 10:16:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.13) <= threshold (-2.00) & Expected Net PnL (KRW 255,951) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0114 / 진입가: 383.61
- **[2025-02-18 10:25:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.49) with Economic Profitability (Net PnL: KRW 98). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0114 / 실현손익: -300,102원
- **[2025-02-18 10:53:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.36) >= threshold (2.00) & Expected Net PnL (KRW 288,781) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0115 / 진입가: 383.85
- **[2025-02-18 13:36:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.28) >= threshold (2.00) & Expected Net PnL (KRW 147,487) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0116 / 진입가: 393.82
- **[2025-02-18 13:42:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.84) with Economic Profitability (Net PnL: KRW 3,187). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0116 / 실현손익: +1,510,145원
- **[2025-02-18 13:55:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.27) <= threshold (-2.00) & Expected Net PnL (KRW 211,216) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0117 / 진입가: 392.09
- **[2025-02-18 14:39:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.56) <= threshold (-2.00) & Expected Net PnL (KRW 194,365) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0118 / 진입가: 391.84
- **[2025-02-18 14:51:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.49) with Economic Profitability (Net PnL: KRW 4,838). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0118 / 실현손익: -83,349원
- **[2025-02-19 09:00:00]** 영업일 2025-02-19 개장: 평가 자산: ₩53,063,920 / Track 7 할당 자본(0.5%): ₩265,320
- **[2025-02-19 09:25:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.10) <= threshold (-2.00) & Expected Net PnL (KRW 186,833) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0119 / 진입가: 394.88
- **[2025-02-19 11:19:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.19) >= threshold (2.00) & Expected Net PnL (KRW 288,122) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0120 / 진입가: 391.99
- **[2025-02-19 14:14:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.60) <= threshold (-2.00) & Expected Net PnL (KRW 173,784) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0121 / 진입가: 396.27
- **[2025-02-19 14:17:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.38) with Economic Profitability (Net PnL: KRW 21,839). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0121 / 실현손익: +680,544원
- **[2025-02-19 14:33:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.12) <= threshold (-2.00) & Expected Net PnL (KRW 135,622) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0122 / 진입가: 396.88
- **[2025-02-20 09:00:00]** 영업일 2025-02-20 개장: 평가 자산: ₩53,782,509 / Track 7 할당 자본(0.5%): ₩268,913
- **[2025-02-20 10:37:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.03) <= threshold (-2.00) & Expected Net PnL (KRW 232,333) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0123 / 진입가: 391.04
- **[2025-02-20 12:13:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.22) >= threshold (2.00) & Expected Net PnL (KRW 170,490) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0124 / 진입가: 397.52
- **[2025-02-20 12:21:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-1.21) with Economic Profitability (Net PnL: KRW 4,680). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0124 / 실현손익: -1,079,320원
- **[2025-02-20 12:31:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.17) <= threshold (-2.00) & Expected Net PnL (KRW 283,928) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0125 / 진입가: 395.69
- **[2025-02-20 13:29:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.54) <= threshold (-2.00) & Expected Net PnL (KRW 172,449) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0126 / 진입가: 395.68
- **[2025-02-21 09:00:00]** 영업일 2025-02-21 개장: 평가 자산: ₩52,717,417 / Track 7 할당 자본(0.5%): ₩263,587
- **[2025-02-21 09:50:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.17) >= threshold (2.00) & Expected Net PnL (KRW 122,674) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0127 / 진입가: 393.59
- **[2025-02-21 10:44:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.12) <= threshold (-2.00) & Expected Net PnL (KRW 300,167) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0128 / 진입가: 392.43
- **[2025-02-21 13:38:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.05) >= threshold (2.00) & Expected Net PnL (KRW 130,002) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0129 / 진입가: 387.97
- **[2025-02-21 14:10:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-1.27) with Economic Profitability (Net PnL: KRW -1,382). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0129 / 실현손익: +4,074,848원
- **[2025-02-21 14:36:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.62) <= threshold (-2.00) & Expected Net PnL (KRW 159,559) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0130 / 진입가: 387.12
- **[2025-02-21 14:52:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (1.13) with Economic Profitability (Net PnL: KRW 872). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0130 / 실현손익: -73,581원
- **[2025-02-24 09:00:00]** 영업일 2025-02-24 개장: 평가 자산: ₩56,656,245 / Track 7 할당 자본(0.5%): ₩283,281
- **[2025-02-24 09:00:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-7.85) <= threshold (-2.00) & Expected Net PnL (KRW 1,359,173) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0131 / 진입가: 380.37
- **[2025-02-24 09:00:00]** Track 7 Weekly Insurance Buy: New trading week started. Setting up weekly limit queue strangle protection via Mid-Price Adapter. / 지출예산: ₩350,000
- **[2025-02-24 09:43:00]** 보험 이익 수취 청산 (PUT): Strike: 380.0, 실현이익: +277,983원
- **[2025-02-24 09:43:00]** 보험 이익 수취 청산 (PUT): Strike: 380.0, 실현이익: +833,948원
- **[2025-02-24 10:33:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.08) >= threshold (2.00) & Expected Net PnL (KRW 252,997) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0132 / 진입가: 376.63
- **[2025-02-24 11:14:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.06) <= threshold (-2.00) & Expected Net PnL (KRW 253,845) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0133 / 진입가: 372.68
- **[2025-02-24 11:32:30]** 보험 이익 수취 청산 (PUT): Strike: 372.5, 실현이익: +268,767원
- **[2025-02-24 13:19:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.15) <= threshold (-2.00) & Expected Net PnL (KRW 198,058) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0134 / 진입가: 372.36
- **[2025-02-24 15:15:00]** Track1 오버나잇 갭 방어 헷지 매입: Target: 1 (가두리 매도 2 기준) | Qty: +1, Cost: ₩75,000
- **[2025-02-25 09:00:00]** 영업일 2025-02-25 개장: 평가 자산: ₩58,176,720 / Track 7 할당 자본(0.5%): ₩290,884
- **[2025-02-25 09:00:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (3.28) with Economic Profitability (Net PnL: KRW 123,607). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0134 / 실현손익: -1,451,124원
- **[2025-02-25 10:49:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.01) >= threshold (2.00) & Expected Net PnL (KRW 229,002) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0135 / 진입가: 372.50
- **[2025-02-25 13:56:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.23) >= threshold (2.00) & Expected Net PnL (KRW 208,012) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0136 / 진입가: 374.08
- **[2025-02-26 09:00:00]** 영업일 2025-02-26 개장: 평가 자산: ₩56,581,933 / Track 7 할당 자본(0.5%): ₩282,910
- **[2025-02-26 09:00:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-5.91) with Economic Profitability (Net PnL: KRW 9,786). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0136 / 실현손익: -290,336원
- **[2025-02-26 09:10:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.07) <= threshold (-2.00) & Expected Net PnL (KRW 511,399) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0137 / 진입가: 372.04
- **[2025-02-26 10:37:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.46) <= threshold (-2.00) & Expected Net PnL (KRW 243,124) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0138 / 진입가: 375.98
- **[2025-02-26 11:15:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.11) <= threshold (-2.00) & Expected Net PnL (KRW 269,809) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0139 / 진입가: 375.17
- **[2025-02-26 11:27:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.25) with Economic Profitability (Net PnL: KRW -311). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0139 / 실현손익: -1,320,080원
- **[2025-02-26 12:23:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.07) <= threshold (-2.00) & Expected Net PnL (KRW 155,522) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0140 / 진입가: 374.94
- **[2025-02-26 12:28:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.10) with Economic Profitability (Net PnL: KRW -970). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0140 / 실현손익: -146,272원
- **[2025-02-26 12:46:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.08) >= threshold (2.00) & Expected Net PnL (KRW 194,093) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0141 / 진입가: 377.42
- **[2025-02-26 12:58:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.79) with Economic Profitability (Net PnL: KRW -3,893). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0141 / 실현손익: -169,240원
- **[2025-02-26 13:15:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.20) <= threshold (-2.00) & Expected Net PnL (KRW 289,284) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0142 / 진입가: 375.33
- **[2025-02-26 13:31:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.35) with Economic Profitability (Net PnL: KRW -4,513). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0142 / 실현손익: -228,864원
- **[2025-02-26 14:18:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.04) >= threshold (2.00) & Expected Net PnL (KRW 215,149) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0143 / 진입가: 374.61
- **[2025-02-26 14:38:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.14) >= threshold (2.00) & Expected Net PnL (KRW 220,600) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0144 / 진입가: 374.45
- **[2025-02-26 15:29:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.10) <= threshold (-2.00) & Expected Net PnL (KRW 171,615) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0145 / 진입가: 372.20
- **[2025-02-27 09:00:00]** 영업일 2025-02-27 개장: 평가 자산: ₩54,274,692 / Track 7 할당 자본(0.5%): ₩271,373
- **[2025-02-27 09:00:00]** 2주간격 7.1pt 약충격 주입: 평온 장세 테스트: 2주 간격 1회 하루 등락폭 7.1포인트 자율 가변 약충격
- **[2025-02-28 09:00:00]** 영업일 2025-02-28 개장: 평가 자산: ₩54,355,953 / Track 7 할당 자본(0.5%): ₩271,780
- **[2025-02-28 09:00:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (10.91) >= threshold (2.00) & Expected Net PnL (KRW 15,731) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0146 / 진입가: 368.83
- **[2025-02-28 09:23:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.46) >= threshold (2.00) & Expected Net PnL (KRW 131,056) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0147 / 진입가: 368.82
- **[2025-02-28 09:24:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.07) with Economic Profitability (Net PnL: KRW 3,921). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0147 / 실현손익: -2,099,674원
- **[2025-02-28 09:34:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.05) >= threshold (2.00) & Expected Net PnL (KRW 131,475) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0148 / 진입가: 368.87
- **[2025-02-28 12:35:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.23) <= threshold (-2.00) & Expected Net PnL (KRW 188,351) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0149 / 진입가: 372.62
- **[2025-02-28 15:25:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.44) <= threshold (-2.00) & Expected Net PnL (KRW 154,289) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0150 / 진입가: 370.84
- **[2025-03-04 09:00:00]** 영업일 2025-03-04 개장: 평가 자산: ₩52,204,570 / Track 7 할당 자본(0.5%): ₩261,023
- **[2025-03-04 09:00:00]** 월 변경 자본금 & 코스피 지수 100% 연속 이월: 전월 자산 ₩52,204,570 / 최종 지수 371.08pt 차월 승계 완료
- **[2025-03-04 11:21:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (1.50) with Economic Profitability (Net PnL: KRW -3,071). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0150 / 실현손익: +263,524원
- **[2025-03-04 12:45:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.32) <= threshold (-2.00) & Expected Net PnL (KRW 194,978) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0151 / 진입가: 372.14
- **[2025-03-04 13:19:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.16) >= threshold (2.00) & Expected Net PnL (KRW 183,224) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0152 / 진입가: 374.01
- **[2025-03-05 09:00:00]** 영업일 2025-03-05 개장: 평가 자산: ₩52,558,863 / Track 7 할당 자본(0.5%): ₩262,794
- **[2025-03-05 10:46:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.05) <= threshold (-2.00) & Expected Net PnL (KRW 230,327) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0153 / 진입가: 381.44
- **[2025-03-05 10:52:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.19) with Economic Profitability (Net PnL: KRW 2,695). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0153 / 실현손익: +793,695원
- **[2025-03-05 11:25:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.20) >= threshold (2.00) & Expected Net PnL (KRW 93,163) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0154 / 진입가: 381.42
- **[2025-03-05 11:28:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-0.42) with Economic Profitability (Net PnL: KRW 1,517). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0154 / 실현손익: -439,916원
- **[2025-03-05 11:41:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.54) >= threshold (2.00) & Expected Net PnL (KRW 134,275) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0155 / 진입가: 381.46
- **[2025-03-05 12:38:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.10) >= threshold (2.00) & Expected Net PnL (KRW 121,123) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0156 / 진입가: 384.64
- **[2025-03-05 12:51:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.65) <= threshold (-2.00) & Expected Net PnL (KRW 177,952) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0157 / 진입가: 383.14
- **[2025-03-05 12:54:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.06) with Economic Profitability (Net PnL: KRW 17,148). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0157 / 실현손익: -116,533원
- **[2025-03-05 13:04:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.25) <= threshold (-2.00) & Expected Net PnL (KRW 204,549) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0158 / 진입가: 383.04
- **[2025-03-06 09:00:00]** 영업일 2025-03-06 개장: 평가 자산: ₩52,743,920 / Track 7 할당 자본(0.5%): ₩263,720
- **[2025-03-06 09:49:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.17) >= threshold (2.00) & Expected Net PnL (KRW 154,822) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0159 / 진입가: 380.09
- **[2025-03-06 11:15:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.48) <= threshold (-2.00) & Expected Net PnL (KRW 161,545) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0160 / 진입가: 378.58
- **[2025-03-06 11:37:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (1.86) with Economic Profitability (Net PnL: KRW -3,195). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0160 / 실현손익: +203,745원
- **[2025-03-06 12:26:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.02) <= threshold (-2.00) & Expected Net PnL (KRW 253,746) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0161 / 진입가: 378.71
- **[2025-03-06 12:55:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.02) >= threshold (2.00) & Expected Net PnL (KRW 237,152) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0162 / 진입가: 381.00
- **[2025-03-06 13:02:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.11) with Economic Profitability (Net PnL: KRW 3,750). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0162 / 실현손익: -580,250원
- **[2025-03-06 13:31:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.20) <= threshold (-2.00) & Expected Net PnL (KRW 241,656) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0163 / 진입가: 378.14
- **[2025-03-06 14:06:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.22) >= threshold (2.00) & Expected Net PnL (KRW 194,038) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0164 / 진입가: 377.98
- **[2025-03-06 14:40:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-1.64) with Economic Profitability (Net PnL: KRW -3,143). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0164 / 실현손익: +37,857원
- **[2025-03-06 15:28:30]** Track 8 Monthly Strangle Cutoff: D-3 강제 청산 집행 / 정산회수: +0원
- **[2025-03-07 09:00:00]** 영업일 2025-03-07 개장: 평가 자산: ₩52,418,318 / Track 7 할당 자본(0.5%): ₩262,092
- **[2025-03-07 09:00:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (5.89) >= threshold (2.00) & Expected Net PnL (KRW 1,099,600) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0165 / 진입가: 380.13
- **[2025-03-07 10:57:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.09) <= threshold (-2.00) & Expected Net PnL (KRW 171,174) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0166 / 진입가: 379.05
- **[2025-03-07 14:17:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.38) <= threshold (-2.00) & Expected Net PnL (KRW 201,174) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0167 / 진입가: 382.30
- **[2025-03-10 09:00:00]** 영업일 2025-03-10 개장: 평가 자산: ₩52,412,649 / Track 7 할당 자본(0.5%): ₩262,063
- **[2025-03-10 09:00:00]** Track 7 Weekly Insurance Buy: New trading week started. Setting up weekly limit queue strangle protection via Mid-Price Adapter. / 지출예산: ₩350,000
- **[2025-03-10 11:28:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.07) <= threshold (-2.00) & Expected Net PnL (KRW 185,720) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0168 / 진입가: 382.02
- **[2025-03-10 14:32:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.04) <= threshold (-2.00) & Expected Net PnL (KRW 149,891) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0169 / 진입가: 379.57
- **[2025-03-10 14:34:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (0.05) with Economic Profitability (Net PnL: KRW 5,708). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0169 / 실현손익: -209,404원
- **[2025-03-10 14:49:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.20) >= threshold (2.00) & Expected Net PnL (KRW 197,017) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0170 / 진입가: 382.11
- **[2025-03-11 09:00:00]** 영업일 2025-03-11 개장: 평가 자산: ₩52,312,311 / Track 7 할당 자본(0.5%): ₩261,562
- **[2025-03-11 09:16:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.14) >= threshold (2.00) & Expected Net PnL (KRW 104,573) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0171 / 진입가: 384.64
- **[2025-03-11 09:28:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-2.15) with Economic Profitability (Net PnL: KRW -2,505). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0171 / 실현손익: +98,731원
- **[2025-03-11 10:24:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.01) >= threshold (2.00) & Expected Net PnL (KRW 210,944) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0172 / 진입가: 385.11
- **[2025-03-11 10:27:00]** 보험 이익 수취 청산 (CALL): Strike: 385.0, 실현이익: +304,755원
- **[2025-03-11 14:20:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.24) <= threshold (-2.00) & Expected Net PnL (KRW 89,862) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0173 / 진입가: 385.37
- **[2025-03-12 09:00:00]** 영업일 2025-03-12 개장: 평가 자산: ₩52,641,939 / Track 7 할당 자본(0.5%): ₩263,210
- **[2025-03-12 10:40:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.01) <= threshold (-2.00) & Expected Net PnL (KRW 129,765) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0174 / 진입가: 383.70
- **[2025-03-12 13:35:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.03) >= threshold (2.00) & Expected Net PnL (KRW 137,690) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0175 / 진입가: 379.72
- **[2025-03-12 13:51:00]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.07) >= threshold (2.00) & Expected Net PnL (KRW 167,966) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0176 / 진입가: 380.94
- **[2025-03-12 14:15:00]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (-2.88) with Economic Profitability (Net PnL: KRW -186). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0176 / 실현손익: +790,814원
- **[2025-03-12 15:28:30]** 월 만기 옵션 정산 & 자본 이월: 정산손익: +1,122,398원 / 이월 자본금: ₩54,525,708
- **[2025-03-13 09:00:00]** 영업일 2025-03-13 개장: 평가 자산: ₩54,550,248 / Track 7 할당 자본(0.5%): ₩272,751
- **[2025-03-13 09:05:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.62) >= threshold (2.00) & Expected Net PnL (KRW 199,493) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0177 / 진입가: 382.01
- **[2025-03-13 09:43:30]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.04) <= threshold (-2.00) & Expected Net PnL (KRW 301,548) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0178 / 진입가: 381.97
- **[2025-03-13 10:33:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.01) <= threshold (-2.00) & Expected Net PnL (KRW 135,053) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0179 / 진입가: 379.43
- **[2025-03-13 11:15:00]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (2.03) with Economic Profitability (Net PnL: KRW -339). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0179 / 실현손익: -582,563원
- **[2025-03-13 11:53:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.33) <= threshold (-2.00) & Expected Net PnL (KRW 228,074) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0180 / 진입가: 380.06
- **[2025-03-13 12:32:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.24) >= threshold (2.00) & Expected Net PnL (KRW 259,979) >= Min (15,000). Group ID: ARB-GROUP-UNKNOWN-TRACK3-0181 / 진입가: 381.92
- **[2025-03-13 15:15:00]** Track1 오버나잇 갭 방어 헷지 매입: Target: 1 (가두리 매도 3 기준) | Qty: +1, Cost: ₩75,000
- **[2025-03-14 09:00:00]** 영업일 2025-03-14 개장: 평가 자산: ₩53,903,141 / Track 7 할당 자본(0.5%): ₩269,516
- **[2025-03-14 09:00:00]** 2주간격 4.7pt 약충격 주입: 평온 장세 테스트: 2주 간격 1회 하루 등락폭 4.7포인트 자율 가변 약충격
- **[2025-03-14 09:00:30]** Track 8 Monthly Strangle Buy: DTE 19.0 월물 초입 지정가 분할 큐 진입 via Mid-Price Adapter (비대칭 스큐 1.5x) / 지출예산: ₩2,400,000


### 💰 1. 자산 및 자본 종합 요약
- **시작 총자산 (Starting Equity)**: ₩25,012,023
- **종료 총자산 (Ending Equity)**: ₩53,868,132
- **실현/평가 순손익 (Net Profit)**: **₩+28,856,109 (+115.369%)**
- **최대 낙폭 (Max Drawdown, MDD)**: ₩8,047,321 (13.410%)
- **안전 유보금 (Ending Reserve)**: ₩0 (전체 자산의 0.0%)

### 📦 2. 주문 집행 및 체결 성적
| 구분 | 건수 / 비율 | 비고 |
| :--- | :--- | :--- |
| **총 주문 요청 건수** | 2 건 | 틱당 평균 0.00회 |
| **완전 체결 (FILLED)** | 2 건 | 전체 주문의 100.0% |
| **부분 체결 (PARTIAL)** | 0 건 | 전체 주문의 0.0% (GC 회수 대상) |
| **주문 거부 (REJECTED)** | 0 건 | 전체 주문의 0.0% (백오프 유도) |
| **대기/미체결 (SENT)** | 0 건 | 전체 주문의 0.0% |
| **최종 체결 성공률** | **100.00%** | (FILLED + PARTIAL) / Total |
| **총 발생 거래수수료** | **₩0** | 선물 0.003% / 옵션 0.15% 기준 |

### 📈 3. 시장 국면(Regime)별 분포
- **HIGH_VOL** 국면: 61.6%
- **NEUTRAL** 국면: 0.0%
- **NOISE_CHOPPY** 국면: 38.3%
- **NORMAL** 국면: 0.1%

### 🌋 4. Self-Tuning Guard (리스크 미세조정) 성능 지표
- **평균 수량 조절 계수 (Avg Tuning Factor)**: **44.4%**
- **최저 수량 조절 계수 (Min Tuning Factor)**: **40.0%**
- **평균 매칭 딜레이 (Avg Slippage Latency)**: **50.0 ms**
- **최대 매칭 딜레이 (Max Slippage Latency)**: **50 ms**

### 🛡️ 5. 전략별 국면 및 PnL 성과분석 (Strategy Breakdown)
| 전략 (Strategy) | 총 누적 손익 (Total PnL) | 스트레스 국면 손익 (Stress PnL) | 평균 비중 | 방어 동작 방식 |
| :--- | :--- | :--- | :--- | :--- |
| **Track1 (Defense)** | ₩+1,405,226 | ₩+0 | 30.0% | 리스크 급증 시 100% 비중으로 증거금 제한 및 숏옵션 커버 |
| **Track2 (Trap)** | ₩+0 | ₩+0 | 10.0% | ⛔ **[V2 HOLD]** 박스권 내 역추세 포지션 진입 중단 |
| **Track3 (Arbitrage)** | ₩-5 | ₩+0 | 5.0% | ⛔ **[V2 HOLD]** 시뮬레이션 순도 유지를 위한 차익 진입 전면 차단 |
| **Track4 (Gamma)** | ₩+0 | ₩+0 | 5.0% | ⛔ **[V2 HOLD]** 현물 델타 헤징 및 스켈핑 중단 |
| **Track5 (Gap)** | ₩+0 | ₩+0 | 0.0% | 시가 갭 감지 시 역방향 진입 및 펜스 압축 회귀 저격 |
| **Track6 (Daily)** | ₩+0 | ₩+0 | 0.0% | 변동성 급증 시 당일 만기 극외가 양매수(0DTE) 가입 |
| **Track7 (Weekly)** | ₩+1,701,040 | ₩+0 | 0.4% | 매주 위클리 옵션 상장 첫날 주간 트렌드 저격 양매수 가입 |
| **Track8 (Monthly)** | ₩-1,202,010 | ₩+0 | 5.0% | 만기 초입 비대칭 외가격 양매수 및 D-3 감마이양 출구 |

### 🚨 6. 리스크 가드 발동 및 본전 청산 이력
- **비상 청산 가드 발동 횟수 (Emergency Guards Triggered)**: **0 회**

### 📅 7. 월물 전환(롤오버) 및 만기 정산 이력
- **세션 중 만기 도달 횟수 (Expiry Events)**: **2 회**
- **만기 정산 누적 손익 합계**: **₩+12,372,586**

| # | Seq(틱) | 만기 시점 기초자산가 | 당월물 정산 손익 | 차월물 D-Day 리셋 |
| :---: | :---: | :---: | :---: | :---: |
| 1 | Tick 16375 | 393.75pt | ₩+11,250,188 | D-1.0일 |
| 2 | Tick 31188 | 380.51pt | ₩+1,122,398 | D-1.0일 |

---

*본 보고서는 헌법 V25.2 가상 붕괴 시나리오에 따른 자율 대응 통합 결과를 반영하고 있습니다.*
