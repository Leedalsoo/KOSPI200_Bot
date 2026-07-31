# 📊 KOSPI200 HFT 가상 테스트 세션 통합 분석 보고서
통합 보고서 최종 갱신 시각: 2026-07-31 11:30:20
총 구동 세션 수: 1개 세션

---


## 🔁 [SESSION #1] 상세 분석 보고서
- **적용된 실제 투자 일자 (Trading Date)**: **2025-01-02, 2025-01-03, 2025-01-06, 2025-01-07, 2025-01-08, 2025-01-09, 2025-01-10, 2025-01-13, 2025-01-14, 2025-01-15, 2025-01-16, 2025-01-17, 2025-01-20, 2025-01-21, 2025-01-22, 2025-01-23, 2025-01-24, 2025-01-27, 2025-01-31, 2025-02-03, 2025-02-04, 2025-02-05, 2025-02-06, 2025-02-07, 2025-02-10, 2025-02-11, 2025-02-12, 2025-02-13, 2025-02-14, 2025-02-17, 2025-02-18, 2025-02-19, 2025-02-20, 2025-02-21, 2025-02-24, 2025-02-25, 2025-02-26, 2025-02-27, 2025-02-28, 2025-03-04, 2025-03-05, 2025-03-06, 2025-03-07, 2025-03-10, 2025-03-11, 2025-03-12, 2025-03-13, 2025-03-14, 2025-03-17, 2025-03-18, 2025-03-19, 2025-03-20, 2025-03-21, 2025-03-24, 2025-03-25, 2025-03-26, 2025-03-27, 2025-03-28, 2025-03-31, 2025-04-01, 2025-04-02, 2025-04-03, 2025-04-04, 2025-04-07, 2025-04-08, 2025-04-09**
- **테스트 규모**: 총 51178 틱 스트리밍

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
- **[2025-01-02 09:00:00]** Track 2 함정(Trap) 구축 완료: ATM: 375.0, 설치 수량: 1계약
- **[2025-01-02 09:00:00]** Track 4 Basecamp: ATM: 375.0 양매수 진입
- **[2025-01-02 09:34:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-2.15) breached lower threshold (-1.5). Buying spread. / 진입가: 374.99
- **[2025-01-02 09:43:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.07). / 실현손익: -77,128원
- **[2025-01-02 09:53:30]** Track 3 Arb (SHORT_SPREAD): Z-Score (2.00) exceeded upper threshold (+1.5). Selling spread. / 진입가: 374.99
- **[2025-01-02 10:55:30]** Track 3 Arb Close (CLOSE_SHORT_SPREAD): Z-Score returned to mean (0.16). / 실현손익: -248,371원
- **[2025-01-02 11:12:00]** Track 3 Arb (LONG_SPREAD): Z-Score (-1.80) breached lower threshold (-1.5). Buying spread. / 진입가: 376.28
- **[2025-01-02 11:53:30]** Track 3 Arb Close (CLOSE_LONG_SPREAD): Z-Score returned to mean (-0.09). / 실현손익: -335,173원
- **[2025-01-02 15:15:00]** OTM 옵션 보험 추가 매입: Strikes: P:360.0, C:390.0, Qty: +1, Cost: ₩75,000
- **[2025-01-03 09:00:00]** 영업일 2025-01-03 개장: HWM: ₩25,073,309 / 가용예산(2%): ₩501,466
- **[2025-01-06 09:00:00]** 영업일 2025-01-06 개장: HWM: ₩25,184,065 / 가용예산(2%): ₩503,681
- **[2025-01-06 09:00:00]** Track 5 Gap Trigger (ENTER_GAP_SHORT): Gap Up Z-Score (+3.24) exceeded threshold. Shorting index for mean reversion. / 수량: 1계약
- **[2025-01-06 09:00:00]** Track 7 Weekly Insurance Buy: New trading week started. Setting up weekly long strangle protection. / 지출예산: ₩350,000
- **[2025-01-06 09:14:30]** Track 5 Gap Close: Timeout (15 minutes elapsed since open). Liquidating remaining gap position. / 실현손익: -102,736원
- **[2025-01-06 15:15:00]** OTM 옵션 보험 부분 축소: 보험 Qty -1 감소 (Target: 1)
- **[2025-01-07 09:00:00]** 영업일 2025-01-07 개장: HWM: ₩23,624,122 / 가용예산(2%): ₩472,482
- **[2025-01-08 09:00:00]** 영업일 2025-01-08 개장: HWM: ₩23,536,525 / 가용예산(2%): ₩470,730
- **[2025-01-09 09:00:00]** 영업일 2025-01-09 개장: HWM: ₩23,707,993 / 가용예산(2%): ₩474,160
- **[2025-01-09 12:53:30]** 보험 이익 수취 청산 (PUT): Strike: 362.5, 실현이익: +125,000원
- **[2025-01-09 15:15:00]** OTM 옵션 보험 추가 매입: Strikes: P:352.5, C:382.5, Qty: +1, Cost: ₩75,000
- **[2025-01-10 09:00:00]** 영업일 2025-01-10 개장: HWM: ₩24,809,635 / 가용예산(2%): ₩496,193
- **[2025-01-10 15:15:00]** Track 7 Weekly Insurance Close: 만기 강제청산 실행 / 정산이익: +0원
- **[2025-01-13 09:00:00]** 영업일 2025-01-13 개장: HWM: ₩24,585,739 / 가용예산(2%): ₩491,715
- **[2025-01-13 09:00:00]** Track 7 Weekly Insurance Buy: New trading week started. Setting up weekly long strangle protection. / 지출예산: ₩350,000
- **[2025-01-13 15:15:00]** OTM 옵션 보험 부분 축소: 보험 Qty -1 감소 (Target: 1)
- **[2025-01-14 09:00:00]** 영업일 2025-01-14 개장: HWM: ₩23,861,858 / 가용예산(2%): ₩477,237
- **[2025-01-15 09:00:00]** 영업일 2025-01-15 개장: HWM: ₩23,850,012 / 가용예산(2%): ₩477,000
- **[2025-01-15 10:54:00]** 보험 이익 수취 청산 (CALL): Strike: 380.0, 실현이익: +125,000원
- **[2025-01-16 09:00:00]** 영업일 2025-01-16 개장: HWM: ₩24,149,370 / 가용예산(2%): ₩482,987
- **[2025-01-17 09:00:00]** 영업일 2025-01-17 개장: HWM: ₩24,157,934 / 가용예산(2%): ₩483,159
- **[2025-01-17 09:00:00]** Track 5 Gap Trigger (ENTER_GAP_LONG): Gap Down Z-Score (-3.14) breached threshold. Longing index for mean reversion. / 수량: 1계약
- **[2025-01-17 09:00:00]** Track 1 Hedge (SELL): 선물 헷지 #1 발동
- **[2025-01-17 09:01:00]** Track 1 FLATTEN: 100% 방어선 격돌
- **[2025-01-17 09:14:30]** Track 5 Gap Close: Timeout (15 minutes elapsed since open). Liquidating remaining gap position. / 실현손익: -121,642원
- **[2025-01-17 15:15:00]** Track 7 Weekly Insurance Close: 만기 강제청산 실행 / 정산이익: +0원
- **[2025-01-20 09:00:00]** 영업일 2025-01-20 개장: HWM: ₩24,690,854 / 가용예산(2%): ₩493,817
- **[2025-01-20 09:00:00]** Track 5 Gap Trigger (ENTER_GAP_SHORT): Gap Up Z-Score (+3.33) exceeded threshold. Shorting index for mean reversion. / 수량: 1계약
- **[2025-01-20 09:00:00]** Track 7 Weekly Insurance Buy: New trading week started. Setting up weekly long strangle protection. / 지출예산: ₩350,000
- **[2025-01-20 09:14:30]** Track 5 Gap Close: Timeout (15 minutes elapsed since open). Liquidating remaining gap position. / 실현손익: -29,805원
- **[2025-01-21 09:00:00]** 영업일 2025-01-21 개장: HWM: ₩22,070,064 / 가용예산(2%): ₩441,401
- **[2025-01-21 09:00:00]** 2주간격 4.6pt 약충격 주입: 평온 장세 테스트: 2주 간격 1회 하루 등락폭 4.6포인트 자율 가변 약충격
- **[2025-01-21 09:00:00]** Track 5 Gap Trigger (ENTER_GAP_LONG): Gap Down Z-Score (-4.15) breached threshold. Longing index for mean reversion. / 수량: 1계약
- **[2025-01-21 09:14:30]** Track 5 Gap Close: Timeout (15 minutes elapsed since open). Liquidating remaining gap position. / 실현손익: -298,592원
- **[2025-01-21 11:28:30]** 보험 이익 수취 청산 (PUT): Strike: 355.0, 실현이익: +125,000원
- **[2025-01-21 14:32:00]** Track 7 Weekly Insurance Profit Realization: 동적 장중 익절 성공! 실현이익: +875,691원 (순손익: +875,691원)
- **[2025-01-22 09:00:00]** 영업일 2025-01-22 개장: HWM: ₩71,373,803 / 가용예산(2%): ₩1,427,476
- **[2025-01-23 09:00:00]** 영업일 2025-01-23 개장: HWM: ₩73,220,722 / 가용예산(2%): ₩1,464,414
- **[2025-01-24 09:00:00]** 영업일 2025-01-24 개장: HWM: ₩74,175,093 / 가용예산(2%): ₩1,483,502
- **[2025-01-27 09:00:00]** 영업일 2025-01-27 개장: HWM: ₩76,077,523 / 가용예산(2%): ₩1,521,550
- **[2025-01-27 09:00:00]** Track 7 Weekly Insurance Buy: New trading week started. Setting up weekly long strangle protection. / 지출예산: ₩350,000
- **[2025-01-27 15:15:00]** OTM 옵션 보험 부분 축소: 보험 Qty -1 감소 (Target: 0)
- **[2025-01-31 09:00:00]** 영업일 2025-01-31 개장: HWM: ₩73,890,825 / 가용예산(2%): ₩1,477,817
- **[2025-01-31 15:15:00]** Track 7 Weekly Insurance Close: 만기 강제청산 실행 / 정산이익: +0원
- **[2025-02-03 09:00:00]** 영업일 2025-02-03 개장: HWM: ₩70,944,835 / 가용예산(2%): ₩1,418,897
- **[2025-02-03 09:00:00]** 월단위 독립 테스트 자본 리셋: 자산 및 HWM ₩25,000,000 초기화 완료
- **[2025-02-03 09:00:00]** Track 5 Gap Trigger (ENTER_GAP_SHORT): Gap Up Z-Score (+2.80) exceeded threshold. Shorting index for mean reversion. / 수량: 1계약
- **[2025-02-03 09:00:00]** Track 7 Weekly Insurance Buy: New trading week started. Setting up weekly long strangle protection. / 지출예산: ₩350,000
- **[2025-02-03 09:14:30]** Track 5 Gap Close: Timeout (15 minutes elapsed since open). Liquidating remaining gap position. / 실현손익: -215,989원
- **[2025-02-03 15:15:00]** OTM 옵션 보험 부분 축소: 보험 Qty -1 감소 (Target: 0)
- **[2025-02-03 15:28:30]** 월 만기 옵션 정산 & 자본 이월: 정산손익: +0원 / 이월 자본금: ₩23,794,502
- **[2025-02-04 09:00:00]** 영업일 2025-02-04 개장: HWM: ₩23,794,505 / 가용예산(2%): ₩475,890
- **[2025-02-04 15:15:00]** OTM 옵션 보험 추가 매입: Strikes: P:337.5, C:367.5, Qty: +1, Cost: ₩75,000
- **[2025-02-05 09:00:00]** 영업일 2025-02-05 개장: HWM: ₩23,712,160 / 가용예산(2%): ₩474,243
- **[2025-02-05 09:00:00]** Track 5 Gap Trigger (ENTER_GAP_LONG): Gap Down Z-Score (-3.38) breached threshold. Longing index for mean reversion. / 수량: 1계약
- **[2025-02-05 09:14:30]** Track 5 Gap Close: Timeout (15 minutes elapsed since open). Liquidating remaining gap position. / 실현손익: +4,783원
- **[2025-02-06 09:00:00]** 영업일 2025-02-06 개장: HWM: ₩47,586,346 / 가용예산(2%): ₩951,727
- **[2025-02-06 09:00:00]** Track 5 Gap Trigger (ENTER_GAP_LONG): Gap Down Z-Score (-2.75) breached threshold. Longing index for mean reversion. / 수량: 1계약
- **[2025-02-06 09:00:00]** Track 8 Monthly Strangle Buy: DTE 19.0월물 초입 진입 (비대칭 스큐 1.5x) / 지출예산: ₩675,000
- **[2025-02-06 09:00:00]** 보험 이익 수취 청산 (PUT): Strike: 337.5, 실현이익: +125,000원
- **[2025-02-06 09:14:30]** Track 5 Gap Close: Timeout (15 minutes elapsed since open). Liquidating remaining gap position. / 실현손익: +56,962원
- **[2025-02-07 09:00:00]** 영업일 2025-02-07 개장: HWM: ₩46,762,965 / 가용예산(2%): ₩935,259
- **[2025-02-07 13:39:00]** Track 7 Weekly Insurance Profit Realization: 동적 장중 익절 성공! 실현이익: +875,409원 (순손익: +875,409원)
- **[2025-02-10 09:00:00]** 영업일 2025-02-10 개장: HWM: ₩47,708,287 / 가용예산(2%): ₩954,166
- **[2025-02-10 09:00:00]** 2주간격 5.0pt 약충격 주입: 평온 장세 테스트: 2주 간격 1회 하루 등락폭 5.0포인트 자율 가변 약충격
- **[2025-02-10 09:00:00]** Track 7 Weekly Insurance Buy: New trading week started. Setting up weekly long strangle protection. / 지출예산: ₩350,000
- **[2025-02-10 15:15:00]** OTM 옵션 보험 부분 축소: 보험 Qty -1 감소 (Target: 1)
- **[2025-02-11 09:00:00]** 영업일 2025-02-11 개장: HWM: ₩47,854,101 / 가용예산(2%): ₩957,082
- **[2025-02-12 09:00:00]** 영업일 2025-02-12 개장: HWM: ₩47,738,756 / 가용예산(2%): ₩954,775
- **[2025-02-12 09:00:00]** Track 5 Gap Trigger (ENTER_GAP_LONG): Gap Down Z-Score (-3.43) breached threshold. Longing index for mean reversion. / 수량: 1계약
- **[2025-02-12 09:14:30]** Track 5 Gap Close: Timeout (15 minutes elapsed since open). Liquidating remaining gap position. / 실현손익: +17,338원
- **[2025-02-13 09:00:00]** 영업일 2025-02-13 개장: HWM: ₩84,614,610 / 가용예산(2%): ₩1,692,292
- **[2025-02-14 09:00:00]** 영업일 2025-02-14 개장: HWM: ₩84,616,172 / 가용예산(2%): ₩1,692,323
- **[2025-02-14 15:15:00]** Track 7 Weekly Insurance Close: 만기 강제청산 실행 / 정산이익: +0원
- **[2025-02-17 09:00:00]** 영업일 2025-02-17 개장: HWM: ₩84,408,944 / 가용예산(2%): ₩1,688,179
- **[2025-02-17 09:00:00]** Track 5 Gap Trigger (ENTER_GAP_LONG): Gap Down Z-Score (-3.85) breached threshold. Longing index for mean reversion. / 수량: 1계약
- **[2025-02-17 09:00:00]** Track 7 Weekly Insurance Buy: New trading week started. Setting up weekly long strangle protection. / 지출예산: ₩350,000
- **[2025-02-17 09:14:30]** Track 5 Gap Close: Timeout (15 minutes elapsed since open). Liquidating remaining gap position. / 실현손익: -84,988원
- **[2025-02-18 09:00:00]** 영업일 2025-02-18 개장: HWM: ₩129,645,591 / 가용예산(2%): ₩2,592,912
- **[2025-02-19 09:00:00]** 영업일 2025-02-19 개장: HWM: ₩129,648,780 / 가용예산(2%): ₩2,592,976
- **[2025-02-20 09:00:00]** 영업일 2025-02-20 개장: HWM: ₩129,641,619 / 가용예산(2%): ₩2,592,832
- **[2025-02-21 09:00:00]** 영업일 2025-02-21 개장: HWM: ₩129,645,625 / 가용예산(2%): ₩2,592,913
- **[2025-02-21 09:00:00]** Track 5 Gap Trigger (ENTER_GAP_LONG): Gap Down Z-Score (-4.12) breached threshold. Longing index for mean reversion. / 수량: 1계약
- **[2025-02-21 09:14:30]** Track 5 Gap Close: Timeout (15 minutes elapsed since open). Liquidating remaining gap position. / 실현손익: +100,378원
- **[2025-02-21 15:15:00]** Track 7 Weekly Insurance Close: 만기 강제청산 실행 / 정산이익: +0원
- **[2025-02-24 09:00:00]** 영업일 2025-02-24 개장: HWM: ₩179,211,293 / 가용예산(2%): ₩3,584,226
- **[2025-02-24 09:00:00]** Track 5 Gap Trigger (ENTER_GAP_SHORT): Gap Up Z-Score (+2.13) exceeded threshold. Shorting index for mean reversion. / 수량: 1계약
- **[2025-02-24 09:00:00]** Track 7 Weekly Insurance Buy: New trading week started. Setting up weekly long strangle protection. / 지출예산: ₩350,000
- **[2025-02-24 09:14:30]** Track 5 Gap Close: Timeout (15 minutes elapsed since open). Liquidating remaining gap position. / 실현손익: +1,734원
- **[2025-02-25 09:00:00]** 영업일 2025-02-25 개장: HWM: ₩178,433,304 / 가용예산(2%): ₩3,568,666
- **[2025-02-26 09:00:00]** 영업일 2025-02-26 개장: HWM: ₩178,437,871 / 가용예산(2%): ₩3,568,757
- **[2025-02-26 09:00:00]** Track 5 Gap Trigger (ENTER_GAP_LONG): Gap Down Z-Score (-3.31) breached threshold. Longing index for mean reversion. / 수량: 1계약
- **[2025-02-26 09:14:30]** Track 5 Gap Close: Timeout (15 minutes elapsed since open). Liquidating remaining gap position. / 실현손익: +21,302원
- **[2025-02-27 09:00:00]** 영업일 2025-02-27 개장: HWM: ₩177,420,875 / 가용예산(2%): ₩3,548,417
- **[2025-02-27 13:58:00]** 보험 이익 수취 청산 (PUT): Strike: 317.5, 실현이익: +125,000원
- **[2025-02-27 15:15:00]** OTM 옵션 보험 추가 매입: Strikes: P:307.5, C:337.5, Qty: +1, Cost: ₩75,000
- **[2025-02-27 15:28:30]** Track 8 Monthly Strangle Cutoff: D-3 강제 청산 집행 / 정산회수: +0원
- **[2025-02-28 09:00:00]** 영업일 2025-02-28 개장: HWM: ₩177,385,262 / 가용예산(2%): ₩3,547,705
- **[2025-02-28 09:00:00]** 2주간격 5.7pt 약충격 주입: 평온 장세 테스트: 2주 간격 1회 하루 등락폭 5.7포인트 자율 가변 약충격
- **[2025-02-28 09:00:00]** Track 5 Gap Trigger (ENTER_GAP_LONG): Gap Down Z-Score (-3.97) breached threshold. Longing index for mean reversion. / 수량: 1계약
- **[2025-02-28 09:12:30]** Track 7 Weekly Insurance Profit Realization: 동적 장중 익절 성공! 실현이익: +880,818원 (순손익: +880,818원)
- **[2025-02-28 09:14:00]** Track 5 Gap Close: Stop loss triggered at 313.70. Cutting losses. / 실현손익: -752,384원
- **[2025-02-28 09:21:00]** 보험 이익 수취 청산 (PUT): Strike: 307.5, 실현이익: +125,000원
- **[2025-02-28 15:15:00]** OTM 옵션 보험 추가 매입: Strikes: P:305.0, C:335.0, Qty: +1, Cost: ₩75,000
- **[2025-03-04 09:00:00]** 영업일 2025-03-04 개장: HWM: ₩223,275,419 / 가용예산(2%): ₩4,465,508
- **[2025-03-04 09:00:00]** 월단위 독립 테스트 자본 리셋: 자산 및 HWM ₩23,793,829 초기화 완료
- **[2025-03-05 09:00:00]** 영업일 2025-03-05 개장: HWM: ₩23,793,829 / 가용예산(2%): ₩475,877
- **[2025-03-05 09:00:00]** Track 5 Gap Trigger (ENTER_GAP_LONG): Gap Down Z-Score (-3.24) breached threshold. Longing index for mean reversion. / 수량: 1계약
- **[2025-03-05 09:14:30]** Track 5 Gap Close: Timeout (15 minutes elapsed since open). Liquidating remaining gap position. / 실현손익: -70,080원
- **[2025-03-06 09:00:00]** 영업일 2025-03-06 개장: HWM: ₩22,704,488 / 가용예산(2%): ₩454,090
- **[2025-03-06 09:00:00]** Track 5 Gap Trigger (ENTER_GAP_SHORT): Gap Up Z-Score (+4.07) exceeded threshold. Shorting index for mean reversion. / 수량: 1계약
- **[2025-03-06 09:14:30]** Track 5 Gap Close: Timeout (15 minutes elapsed since open). Liquidating remaining gap position. / 실현손익: +34,749원
- **[2025-03-07 09:00:00]** 영업일 2025-03-07 개장: HWM: ₩21,464,688 / 가용예산(2%): ₩429,294
- **[2025-03-10 09:00:00]** 영업일 2025-03-10 개장: HWM: ₩21,464,688 / 가용예산(2%): ₩429,294
- **[2025-03-10 09:00:00]** Track 7 Weekly Insurance Buy: New trading week started. Setting up weekly long strangle protection. / 지출예산: ₩350,000
- **[2025-03-10 15:15:00]** OTM 옵션 보험 부분 축소: 보험 Qty -1 감소 (Target: 0)
- **[2025-03-11 09:00:00]** 영업일 2025-03-11 개장: HWM: ₩21,464,776 / 가용예산(2%): ₩429,296
- **[2025-03-12 09:00:00]** 영업일 2025-03-12 개장: HWM: ₩21,464,776 / 가용예산(2%): ₩429,296
- **[2025-03-12 09:00:00]** Track 5 Gap Trigger (ENTER_GAP_SHORT): Gap Up Z-Score (+3.71) exceeded threshold. Shorting index for mean reversion. / 수량: 1계약
- **[2025-03-12 09:14:30]** Track 5 Gap Close: Timeout (15 minutes elapsed since open). Liquidating remaining gap position. / 실현손익: +78,626원
- **[2025-03-13 09:00:00]** 영업일 2025-03-13 개장: HWM: ₩20,297,275 / 가용예산(2%): ₩405,945
- **[2025-03-14 09:00:00]** 영업일 2025-03-14 개장: HWM: ₩20,297,275 / 가용예산(2%): ₩405,945
- **[2025-03-14 15:15:00]** Track 7 Weekly Insurance Close: 만기 강제청산 실행 / 정산이익: +0원
- **[2025-03-17 09:00:00]** 영업일 2025-03-17 개장: HWM: ₩20,057,788 / 가용예산(2%): ₩401,156
- **[2025-03-17 09:00:00]** Track 5 Gap Trigger (ENTER_GAP_SHORT): Gap Up Z-Score (+2.86) exceeded threshold. Shorting index for mean reversion. / 수량: 1계약
- **[2025-03-17 09:00:00]** Track 7 Weekly Insurance Buy: New trading week started. Setting up weekly long strangle protection. / 지출예산: ₩350,000
- **[2025-03-17 09:14:30]** Track 5 Gap Close: Timeout (15 minutes elapsed since open). Liquidating remaining gap position. / 실현손익: +36,248원
- **[2025-03-17 15:15:00]** OTM 옵션 보험 부분 축소: 보험 Qty -1 감소 (Target: 0)
- **[2025-03-18 09:00:00]** 영업일 2025-03-18 개장: HWM: ₩19,172,688 / 가용예산(2%): ₩383,454
- **[2025-03-19 09:00:00]** 영업일 2025-03-19 개장: HWM: ₩19,172,688 / 가용예산(2%): ₩383,454
- **[2025-03-20 09:00:00]** 영업일 2025-03-20 개장: HWM: ₩19,172,688 / 가용예산(2%): ₩383,454
- **[2025-03-20 09:00:00]** 2주간격 7.8pt 약충격 주입: 평온 장세 테스트: 2주 간격 1회 하루 등락폭 7.8포인트 자율 가변 약충격
- **[2025-03-20 09:00:00]** Track 5 Gap Trigger (ENTER_GAP_LONG): Gap Down Z-Score (-3.84) breached threshold. Longing index for mean reversion. / 수량: 1계약
- **[2025-03-20 09:14:30]** Track 5 Gap Close: Timeout (15 minutes elapsed since open). Liquidating remaining gap position. / 실현손익: -78,444원
- **[2025-03-21 09:00:00]** 영업일 2025-03-21 개장: HWM: ₩18,195,245 / 가용예산(2%): ₩363,905
- **[2025-03-21 09:00:00]** Track 5 Gap Trigger (ENTER_GAP_SHORT): Gap Up Z-Score (+4.05) exceeded threshold. Shorting index for mean reversion. / 수량: 1계약
- **[2025-03-21 09:14:30]** Track 5 Gap Close: Timeout (15 minutes elapsed since open). Liquidating remaining gap position. / 실현손익: +86,255원
- **[2025-03-21 15:15:00]** Track 7 Weekly Insurance Close: 만기 강제청산 실행 / 정산이익: +0원
- **[2025-03-24 09:00:00]** 영업일 2025-03-24 개장: HWM: ₩16,653,257 / 가용예산(2%): ₩333,065
- **[2025-03-24 09:00:00]** Track 5 Gap Trigger (ENTER_GAP_SHORT): Gap Up Z-Score (+3.15) exceeded threshold. Shorting index for mean reversion. / 수량: 1계약
- **[2025-03-24 09:14:30]** Track 5 Gap Close: Timeout (15 minutes elapsed since open). Liquidating remaining gap position. / 실현손익: +67,977원
- **[2025-03-25 09:00:00]** 영업일 2025-03-25 개장: HWM: ₩15,602,224 / 가용예산(2%): ₩312,044
- **[2025-03-25 09:00:00]** Track 5 Gap Trigger (ENTER_GAP_LONG): Gap Down Z-Score (-2.51) breached threshold. Longing index for mean reversion. / 수량: 1계약
- **[2025-03-25 09:14:30]** Track 5 Gap Close: Timeout (15 minutes elapsed since open). Liquidating remaining gap position. / 실현손익: -115,857원
- **[2025-03-26 09:00:00]** 영업일 2025-03-26 개장: HWM: ₩14,611,467 / 가용예산(2%): ₩292,229
- **[2025-03-26 09:00:00]** Track 5 Gap Trigger (ENTER_GAP_LONG): Gap Down Z-Score (-3.04) breached threshold. Longing index for mean reversion. / 수량: 1계약
- **[2025-03-26 09:14:30]** Track 5 Gap Close: Timeout (15 minutes elapsed since open). Liquidating remaining gap position. / 실현손익: +15,274원
- **[2025-03-27 09:00:00]** 영업일 2025-03-27 개장: HWM: ₩13,558,410 / 가용예산(2%): ₩271,168
- **[2025-03-28 09:00:00]** 영업일 2025-03-28 개장: HWM: ₩13,558,410 / 가용예산(2%): ₩271,168
- **[2025-03-31 09:00:00]** 영업일 2025-03-31 개장: HWM: ₩13,558,410 / 가용예산(2%): ₩271,168
- **[2025-04-01 09:00:00]** 영업일 2025-04-01 개장: HWM: ₩13,558,410 / 가용예산(2%): ₩271,168
- **[2025-04-01 09:00:00]** 월단위 독립 테스트 자본 리셋: 자산 및 HWM ₩23,793,829 초기화 완료
- **[2025-04-02 09:00:00]** 영업일 2025-04-02 개장: HWM: ₩23,793,829 / 가용예산(2%): ₩475,877
- **[2025-04-02 09:00:00]** Track 5 Gap Trigger (ENTER_GAP_SHORT): Gap Up Z-Score (+2.81) exceeded threshold. Shorting index for mean reversion. / 수량: 1계약
- **[2025-04-02 09:14:30]** Track 5 Gap Close: Timeout (15 minutes elapsed since open). Liquidating remaining gap position. / 실현손익: +64,244원
- **[2025-04-03 09:00:00]** 영업일 2025-04-03 개장: HWM: ₩22,897,147 / 가용예산(2%): ₩457,943
- **[2025-04-04 09:00:00]** 영업일 2025-04-04 개장: HWM: ₩22,897,147 / 가용예산(2%): ₩457,943
- **[2025-04-04 09:00:00]** 2주간격 5.1pt 약충격 주입: 평온 장세 테스트: 2주 간격 1회 하루 등락폭 5.1포인트 자율 가변 약충격
- **[2025-04-07 09:00:00]** 영업일 2025-04-07 개장: HWM: ₩22,897,147 / 가용예산(2%): ₩457,943
- **[2025-04-07 09:00:00]** Track 5 Gap Trigger (ENTER_GAP_LONG): Gap Down Z-Score (-3.43) breached threshold. Longing index for mean reversion. / 수량: 1계약
- **[2025-04-07 09:00:00]** Track 7 Weekly Insurance Buy: New trading week started. Setting up weekly long strangle protection. / 지출예산: ₩350,000
- **[2025-04-07 09:14:30]** Track 5 Gap Close: Timeout (15 minutes elapsed since open). Liquidating remaining gap position. / 실현손익: +11,298원
- **[2025-04-07 15:15:00]** OTM 옵션 보험 부분 축소: 보험 Qty -1 감소 (Target: 0)
- **[2025-04-08 09:00:00]** 영업일 2025-04-08 개장: HWM: ₩21,886,928 / 가용예산(2%): ₩437,739
- **[2025-04-09 09:00:00]** 영업일 2025-04-09 개장: HWM: ₩21,886,928 / 가용예산(2%): ₩437,739
- **[2025-04-09 09:00:00]** Track 5 Gap Trigger (ENTER_GAP_LONG): Gap Down Z-Score (-3.03) breached threshold. Longing index for mean reversion. / 수량: 1계약
- **[2025-04-09 09:14:30]** Track 5 Gap Close: Timeout (15 minutes elapsed since open). Liquidating remaining gap position. / 실현손익: +67,425원


### 💰 1. 자산 및 자본 종합 요약
- **시작 총자산 (Starting Equity)**: ₩25,050,025
- **종료 총자산 (Ending Equity)**: ₩21,006,614
- **실현/평가 순손익 (Net Profit)**: **₩-4,043,411 (-16.141%)**
- **최대 낙폭 (Max Drawdown, MDD)**: ₩209,940,622 (93.936%)
- **안전 유보금 (Ending Reserve)**: ₩39,654 (전체 자산의 0.2%)

### 📦 2. 주문 집행 및 체결 성적
| 구분 | 건수 / 비율 | 비고 |
| :--- | :--- | :--- |
| **총 주문 요청 건수** | 1 건 | 틱당 평균 0.00회 |
| **완전 체결 (FILLED)** | 1 건 | 전체 주문의 100.0% |
| **부분 체결 (PARTIAL)** | 0 건 | 전체 주문의 0.0% (GC 회수 대상) |
| **주문 거부 (REJECTED)** | 0 건 | 전체 주문의 0.0% (백오프 유도) |
| **대기/미체결 (SENT)** | 0 건 | 전체 주문의 0.0% |
| **최종 체결 성공률** | **100.00%** | (FILLED + PARTIAL) / Total |
| **총 발생 거래수수료** | **₩0** | 선물 0.003% / 옵션 0.15% 기준 |

### 📈 3. 시장 국면(Regime)별 분포
- **NEUTRAL** 국면: 0.5%
- **NOISE_CHOPPY** 국면: 94.4%
- **NORMAL** 국면: 5.1%

### 🌋 4. Self-Tuning Guard (리스크 미세조정) 성능 지표
- **평균 수량 조절 계수 (Avg Tuning Factor)**: **100.0%**
- **최저 수량 조절 계수 (Min Tuning Factor)**: **100.0%**
- **평균 매칭 딜레이 (Avg Slippage Latency)**: **50.0 ms**
- **최대 매칭 딜레이 (Max Slippage Latency)**: **50 ms**

### 🛡️ 5. 전략별 국면 및 PnL 성과분석 (Strategy Breakdown)
| 전략 (Strategy) | 총 누적 손익 (Total PnL) | 스트레스 국면 손익 (Stress PnL) | 평균 비중 | 방어 동작 방식 |
| :--- | :--- | :--- | :--- | :--- |
| **Track1 (Defense)** | ₩+0 | ₩+0 | 30.0% | 리스크 급증 시 100% 비중으로 증거금 제한 및 숏옵션 커버 |
| **Track2 (Trap)** | ₩+0 | ₩+0 | 0.0% | ⛔ **[V2 HOLD]** 박스권 내 역추세 포지션 진입 중단 |
| **Track3 (Arbitrage)** | ₩+0 | ₩+0 | 0.0% | ⛔ **[V2 HOLD]** 시뮬레이션 순도 유지를 위한 차익 진입 전면 차단 |
| **Track4 (Gamma)** | ₩+0 | ₩+0 | 0.0% | ⛔ **[V2 HOLD]** 현물 델타 헤징 및 스켈핑 중단 |
| **Track5 (Gap)** | ₩+0 | ₩+0 | 2.0% | 시가 갭 감지 시 역방향 진입 및 펜스 압축 회귀 저격 |
| **Track6 (Daily)** | ₩+0 | ₩+0 | 0.0% | 변동성 급증 시 당일 만기 극외가 양매수(0DTE) 가입 |
| **Track7 (Weekly)** | ₩+0 | ₩+0 | 1.4% | 매주 위클리 옵션 상장 첫날 주간 트렌드 저격 양매수 가입 |
| **Track8 (Monthly)** | ₩+0 | ₩+0 | 0.5% | 만기 초입 비대칭 외가격 양매수 및 D-3 감마이양 출구 |

### 🚨 6. 리스크 가드 발동 및 본전 청산 이력
- **비상 청산 가드 발동 횟수 (Emergency Guards Triggered)**: **0 회**

### 📅 7. 월물 전환(롤오버) 및 만기 정산 이력
- **세션 중 만기 도달 횟수 (Expiry Events)**: **1 회**
- **만기 정산 누적 손익 합계**: **₩+0**

| # | Seq(틱) | 만기 시점 기초자산가 | 당월물 정산 손익 | 차월물 D-Day 리셋 |
| :---: | :---: | :---: | :---: | :---: |
| 1 | Tick 15595 | 357.40pt | ₩+0 | D-0.0일 |

---

*본 보고서는 헌법 V25.2 가상 붕괴 시나리오에 따른 자율 대응 통합 결과를 반영하고 있습니다.*
