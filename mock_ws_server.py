# -*- coding: utf-8 -*-
"""
HFT 대시보드 실시간 연동 테스트용 모의 웹소켓 스트리밍 서버 (mock_ws_server.py)
[극한 스트레스 테스트 V3] 8대 시장 붕괴 시나리오 복합 주입 엔진 탑재 버전

주입 시나리오:
  1. Flash Crash       — 순간 -5% 급락 후 부분 회복 (15~30틱 1회)
  2. Circuit Breaker   — 서킷브레이커 발동 시 5~10초 거래 완전 정지
  3. Order Rejection   — 연속 주문 거부율 80% 폭발 (10~20틱 지속)
  4. Liquidity Drought — 호가공백 10포인트 이상 극단적 확대
  5. IV Explosion      — 내재변동성 순간 3배 폭발 (블랙스완)
  6. Partial Fill 폭탄 — 주문의 30%가 PARTIAL 체결 → GC 타임아웃 테스트
  7. Price Gap         — 2.5p × 3~6 묶음 순간 점프 (밤 사이 갭)
  8. WebSocket 반복 단절 — 연결 강제 종료 후 재연결 → 고아 주문 발생
"""
import asyncio
import argparse
import os
import logging
import uuid
import random
import time
import sys
import math
from collections import deque
from typing import Any, List, Dict, Optional, Tuple
from datetime import datetime, timedelta, date

from strategy.plugins.track1 import Track1
from strategy.plugins.track2 import Track2
from strategy.plugins.track3 import Track3
from strategy.plugins.track4 import Track4
from strategy.plugins.track5 import Track5
from strategy.plugins.track6 import Track6
from strategy.plugins.track7 import Track7
from strategy.plugins.track8 import Track8
from strategy.plugins.track9 import Track9
from strategy.sensors.market_sensors import FuturesSensor, WeeklyOptionsSensor, DailyOptionsSensor
from strategy.simulation.virtual_feed_engine import HistoricalReplayEngine, SlippageEngine, PaperTradingAccount
import orjson
import numpy as np
from sensor.trade_replay_analyzer import TradeReplayAnalyzer

trade_replay_analyzer = TradeReplayAnalyzer(max_history=50, mode="VIRTUAL")

# 📝 [AUDIT TRAIL] 시계열 감사 로그 검증 모드 활성화
# 터미널(콘솔)은 INFO 레벨만 출력하여 깔끔하게 유지하고, 상세 판단 근거(DEBUG)는 audit_trail.log에 시계열로 영구 보존합니다.
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# 🔇 websockets 저수준 프로토콜 패킷 디버그 노이즈 로그 100% 필터링 차단 (매 0.1초 8KB 통신 패킷 중복 출력 방지)
logging.getLogger("websockets").setLevel(logging.INFO)
logging.getLogger("websockets.protocol").setLevel(logging.INFO)
logging.getLogger("websockets.server").setLevel(logging.INFO)

if logger.hasHandlers():
    logger.handlers.clear()

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(console_handler)

audit_handler = logging.FileHandler("audit_trail.log", encoding="utf-8", mode="w")
audit_handler.setLevel(logging.DEBUG)
audit_handler.setFormatter(logging.Formatter("%(asctime)s.%(msecs)03d | %(levelname)-8s | [%(module)s] - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
logger.addHandler(audit_handler)

logger = logging.getLogger("MockWSServer")

# 🎲 Deterministic Simulation Seed (재현성 보장용 시드 42 고정)
SIMULATION_SEED: int = 42
random.seed(SIMULATION_SEED)

# 📅 KRX 실제 역사적 영업일 및 이벤트 맵 정의
TRADING_DAY_EVENTS = {
    "2020-03-19": "코로나19 폭락장 (서킷브레이커 발동 및 팬데믹 공포)",
    "2020-06-15": "글로벌 경기 둔화 우려에 따른 지수 급락",
    "2024-08-05": "엔 캐리 트레이드 청산발 글로벌 블랙 먼데이 (서킷브레이커 발동)",
    "2026-03-12": "선물/옵션 동시 만기일 (Quadruple Witching Day 및 롤오버)",
    "2026-07-21": "기준 시뮬레이션 영업일 (정상 개장)"
}

class CalendarSimulator:
    def __init__(self, start_date_str: str = "2025-01-10"):
        # 1월 만기일(1/9 목) 직후인 2025-01-10(금)부터 시작하여 꽉 찬 1개월 옵션 만기 주기 백테스트
        self.current_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        self.current_time = self.current_date.replace(hour=9, minute=0, second=0)
        self.seconds_per_tick = 30  # 1틱당 30초씩 시간 전진
        
        # 🛡️ 동적 KOSPI 200 옵션 만기일(둘째 주 목요일) 및 잔여 영업일 연산
        self.current_expiry = self.get_next_kospi200_expiry(self.current_date.date())
        self.remaining_days = self.calc_remaining_trading_days(self.current_date.date(), self.current_expiry)
        self.simulated_days_to_expiry = float(self.remaining_days)

        # 시작 가상 일시 기록
        self.start_datetime_str = self.current_time.strftime("%Y-%m-%d %H:%M:%S")
        self.expiry_datetime_str = datetime.combine(self.current_expiry, datetime.min.time()).strftime("%Y-%m-%d 15:30:00")
        self._market_scenario: Optional[str] = None
        self.extreme_vol_dir: int = 1


    def is_korean_holiday(self, d: date) -> bool:
        """토요일, 일요일 및 한국 대표 법정공휴일 판정"""
        if d.weekday() in (5, 6):  # 토(5), 일(6) 주말
            return True
        
        # 2025년 한국 공휴일 (대체공휴일 포함)
        holidays_2025 = {
            (1, 1),    # 신정
            (1, 28),   # 설날 연휴
            (1, 29),   # 설날
            (1, 30),   # 설날 연휴
            (3, 1),    # 삼일절
            (3, 3),    # 삼일절 대체공휴일 (3/1 토요일)
            (5, 5),    # 어린이날 / 석가탄신일
            (5, 6),    # 대체공휴일
            (6, 6),    # 현충일
            (8, 15),   # 광복절
            (10, 3),   # 개천절
            (10, 5),   # 추석 연휴 (일요일)
            (10, 6),   # 추석
            (10, 7),   # 추석 연휴
            (10, 8),   # 추석 대체공휴일 (10/5 일요일 대체)
            (10, 9),   # 한글날
            (12, 25),  # 성탄절
        }
        # 2026년 한국 공휴일
        holidays_2026 = {
            (1, 1), (2, 16), (2, 17), (2, 18), (3, 1), (3, 2), (5, 5), (5, 24), (5, 25), (6, 6), (8, 15), (8, 17), (9, 24), (9, 25), (9, 26), (10, 3), (10, 5), (10, 9), (12, 25)
        }
        
        m_d = (d.month, d.day)
        if d.year == 2025:
            return m_d in holidays_2025
        elif d.year == 2026:
            return m_d in holidays_2026
        
        # 기본 고정 법정공휴일
        fixed_holidays = {
            (1, 1), (3, 1), (5, 5), (6, 6), (8, 15), (10, 3), (10, 9), (12, 25)
        }
        return m_d in fixed_holidays

    def get_next_kospi200_expiry(self, from_date: date) -> date:
        """현재 날짜 기준 KOSPI 200 옵션 만기일 (매월 2번째 목요일, 공휴일 시 직전 영업일) 정밀 산출"""
        def calc_second_thursday(y: int, m: int) -> date:
            first_day = date(y, m, 1)
            days_to_thurs = (3 - first_day.weekday()) % 7
            first_thurs = first_day + timedelta(days=days_to_thurs)
            second_thurs = first_thurs + timedelta(days=7)
            
            target = second_thurs
            while self.is_korean_holiday(target):
                target -= timedelta(days=1)
            return target

        exp = calc_second_thursday(from_date.year, from_date.month)
        if from_date > exp:
            y = from_date.year + 1 if from_date.month == 12 else from_date.year
            m = 1 if from_date.month == 12 else from_date.month + 1
            exp = calc_second_thursday(y, m)
        return exp

    def calc_remaining_trading_days(self, from_date: date, expiry_date: date) -> int:
        """from_date부터 expiry_date까지의 실제 KRX 영업일수 (남은 DTE 정수) 계산"""
        if from_date >= expiry_date:
            return 0
        curr = from_date
        count = 0
        while curr < expiry_date:
            curr += timedelta(days=1)
            if not self.is_korean_holiday(curr):
                count += 1
        return count

    def tick(self, elapsed_real_seconds: float = 0.1) -> Tuple[str, str, bool, bool]:
        # 1초당 300초 전진 비율
        advance_seconds = max(1, int(elapsed_real_seconds * 300.0))
        self.current_time += timedelta(seconds=advance_seconds)

        # 주말 및 공휴일인 경우 즉시 다음 영업일 개장 시각(09:00)으로 워프 처리
        date_changed = False
        while self.is_korean_holiday(self.current_time.date()):
            self.current_date += timedelta(days=1)
            self.current_time = self.current_date.replace(hour=9, minute=0, second=0)
            date_changed = True

        # 초 단위를 00초 또는 30초 단위로 정밀 보정
        sec = self.current_time.second
        if sec < 15:
            self.current_time = self.current_time.replace(second=0)
        elif sec < 45:
            self.current_time = self.current_time.replace(second=30)
        else:
            try:
                self.current_time = self.current_time.replace(second=0) + timedelta(minutes=1)
            except ValueError:
                self.current_time = self.current_time.replace(second=0)

        # 09:00:00 기준 현재 하루 경과율 계산 (장 운영시간 23400초 대비)
        start_of_day = self.current_time.replace(hour=9, minute=0, second=0)
        elapsed_sec = (self.current_time - start_of_day).total_seconds()
        
        is_holiday = self.is_korean_holiday(self.current_time.date())
        is_market_open = (not is_holiday) and (0 <= elapsed_sec <= 23400)

        if is_market_open:
            day_progress = min(1.0, max(0.0, elapsed_sec / 23400.0))
            self.simulated_days_to_expiry = max(0.0, round(self.remaining_days - day_progress, 2))
        else:
            self.simulated_days_to_expiry = max(0.0, float(self.remaining_days))

        # 15:30:00 하루 마감 및 날짜 변경
        day_end = self.current_time.replace(hour=15, minute=30, second=0)

        if self.current_time >= day_end:
            date_changed = True
            
            # 다음 달력 날짜로 하루 전진
            self.current_date += timedelta(days=1)
            self.current_time = self.current_date.replace(hour=9, minute=0, second=0)

            # 주말/공휴일 워프
            while self.is_korean_holiday(self.current_time.date()):
                self.current_date += timedelta(days=1)
                self.current_time = self.current_date.replace(hour=9, minute=0, second=0)

            # 영업일 이동 후 만기일 및 남은 영업일수(DTE) 실시간 재계산
            self.current_expiry = self.get_next_kospi200_expiry(self.current_date.date())
            self.remaining_days = self.calc_remaining_trading_days(self.current_date.date(), self.current_expiry)

        # 만기일 동적 스트링 갱신
        self.expiry_datetime_str = datetime.combine(self.current_expiry, datetime.min.time()).strftime("%Y-%m-%d 15:30:00")

        date_str = self.current_time.strftime("%Y-%m-%d")
        time_str = self.current_time.strftime("%H:%M:%S")
        return date_str, time_str, date_changed, is_market_open

# 🛡️ [그레이스풀 셧다운 이벤트 정의]
shutdown_event: Optional[asyncio.Event] = None

try:
    import websockets  # type: ignore[import-not-found, unused-ignore]
except ImportError:
    logger.critical("websockets 라이브러리가 설치되어 있지 않습니다. 'pip install websockets'를 먼저 실행해 주세요.")
    sys.exit(1)

# 🛡️ [수수료 및 거래승수 정의]
FUTURES_FEE_RATE = 0.00003
OPTIONS_FEE_RATE = 0.0015
FUTURES_MULTIPLIER = 250000
OPTIONS_MULTIPLIER = 250000

# ── 🏗️ [아키텍처 기반 상수] ──────────────────────────────────────────────────
# 전략 이름 중앙 정의 — 모든 전략별 딕셔너리는 이 목록에서만 생성
TRACK_NAMES = [
    "Track1", "Track2", "Track3", "Track4",
    "Track5", "Track6", "Track7", "Track8"
]

def _make_strategy_dict(default: float = 0.0) -> Dict[str, float]:
    """전략별 8-key 딕셔너리를 팩토리로 생성 — Track 추가 시 TRACK_NAMES 1곳만 수정하면 됨."""
    return {t: default for t in TRACK_NAMES}

# ── 🔑 [세션 UUID] — 서버 기동/재기동마다 갱신, 모든 패킷에 포함 ──
SESSION_ID: str = str(uuid.uuid4())

# ── 🏗️ [런타임 모드] — 시뮬레이션 제어 채널 격리용 ──
# "SIMULATION" = 가상테스트 (기본), "PAPER" = 모의투자, "LIVE" = 실전
# 나중에 커맨드라인 --mode 인자 또는 .env 파일로 전환 가능
RUNTIME_MODE: str = "SIMULATION"

# 🛡️ [전략 기본 수량 제어 상수]
BASE_TRACK1_QTY = 1
BASE_TRACK2_QTY = 1

# 🛡️ [자본금 / 유보금 / 증거금 모의 상태 정의]
current_price: float = 350.0
prev_price: float = 350.0               # Flash Crash 감지용 직전 틱 가격
initial_capital: float = 25000000.0
current_capital: float = initial_capital
accumulated_reserve: float = 0.0
total_equity: float = initial_capital

# 🛡️ [캘린더 및 HWM / 보험 및 외부 감시 상태 정의]
daily_hwm: float = initial_capital
highest_equity_today: float = initial_capital
calendar_sim = CalendarSimulator("2025-01-10")
overnight_insurance_bought_today: bool = False
insurance_active_this_month: bool = False
insurance_reentry_needed_today: bool = False
is_market_opened_today: bool = False  # 🛡️ 당일 개장 초기화 1회 실행 보장 플래그
trading_date_logs: List[str] = []
event_logs: List[Dict[str, Any]] = []

# Watchdog 상태 및 장애 모사 플래그
main_engine_broken: bool = False
emergency_cooldown_ticks: int = 0
daily_friction_cost: float = 0.0
daily_friction_lockdown: bool = False
autobot_active: bool = True

# 🛡️ [동적 보험 갱신 상태 정의]
last_insurance_qty: int = 0
last_insurance_strike: float = 0.0
last_track1_sell_qty: int = 0

# 🛡️ [만기일 시뮬레이션 상태 정의]
simulated_days_to_expiry: float = float(calendar_sim.remaining_days)

# 🛡️ [만기일 롤오버 1회 실행 보장 플래그] — Phase 1.1 BUG FIX
already_rolled_this_month: bool = False
enabled_strategies: Dict[str, bool] = {f"track{i}": True for i in range(1, 10)}
hourly_start_equity: float = 25000000.0
month_start_capital: float = 25000000.0
last_tracked_hour: int = -1


# 🛡️ [월물 전환(롤오버) 이벤트 로그]
# 각 롤오버 발생 시 {'tick', 'seq', 'settlement_pnl', 'price', 'new_dte'} 딕셔너리를 누적한다.
rollover_event_log: List[Dict[str, Any]] = []

track1: Optional[Track1] = None
track2: Optional[Track2] = None
track3: Optional[Track3] = None
track4: Optional[Track4] = None
track5: Optional[Track5] = None
track6: Optional[Track6] = None
track7: Optional[Track7] = None
track8: Optional[Track8] = None
track9: Optional[Track9] = None
futures_sensor: Optional[FuturesSensor] = None
weekly_sensor: Optional[WeeklyOptionsSensor] = None
daily_sensor: Optional[DailyOptionsSensor] = None
replay_engine: Optional[HistoricalReplayEngine] = None
slippage_engine: Optional[SlippageEngine] = None
paper_account: Optional[PaperTradingAccount] = None
track5_active_qty: int = 0
insurance_budget_pool: float = 1000000.0
calculated_fee: float = 0.0
price_history_60: deque[float] = deque(maxlen=60)
spread_history_120: deque[float] = deque(maxlen=120)

# 🛡️ [자동 재가동 제어 이벤트]
# shutdown_event  : 사용자 Ctrl+C 또는 프로그램적 종료 요청
# risk_triggered_event : 15%붕괴 감지 시 구분자로 사용 (서버는 유지)
shutdown_event = asyncio.Event()   # 더미 초기화, main()에서 재생성
risk_triggered_event: asyncio.Event  = asyncio.Event()   # 더미 초기화

# 🛡️ [재시작 회차 카운터]
restart_count: int = 0

# 가상 테스트 쿨다운: 10초 = 실전 환경에서의 '다음날 재개' 시뮬레이션
RISK_COOLDOWN_SECS: int = 10

# 🛡️ [실시간 포지션 및 증거금 트래킹]
current_position_qty: int = 0
track3_entry_price: float = 0.0
track3_entry_qty: int = 0
track3_net_qty: int = 0
used_margin: float = 0.0

# 🛡️ [합성 옵션 포트폴리오 — 초기 숏 스트랭글 탑재]
portfolio_options: List[Dict[str, Any]] = [
    {"type": "PUT",  "side": "SELL", "strike": 345.0, "price": 2.20, "qty": BASE_TRACK1_QTY, "activeStrategy": "Track1", "tag_id": 1},
    {"type": "CALL", "side": "SELL", "strike": 355.0, "price": 2.50, "qty": BASE_TRACK1_QTY, "activeStrategy": "Track1", "tag_id": 2},
]

# 🛡️ [IV 이동평균 추적 — IVExplosionGuard 기반 블랙스완 감지]
iv_history: deque[float] = deque(maxlen=50)    # 최근 50틱 IV 이동평균 버퍼

# 🛡️ [세션 텔레메트리 백업 기록용 전역 리스트]
session_telemetry: List[Dict[str, Any]] = []

# 🛡️ [전체 세션 통합 저장용 전역 변수]
all_sessions_telemetry: Dict[str, List[Dict[str, Any]]] = {}
all_sessions_markdowns: List[str] = []

# 🛡️ [전략별 확정 실현 PnL 전역 변수] — _make_strategy_dict() 팩토리 사용
strategy_realized_pnl: Dict[str, float] = _make_strategy_dict()

# 🛡️ [전략별 누적 PnL 분석용 전역 변수 (실현+미실현 MTM 통합)]
strategy_pnl_tracker: Dict[str, float] = _make_strategy_dict()

# 🛡️ [스트레스 국면에서의 전략별 누적 PnL]
strategy_stress_pnl: Dict[str, float] = _make_strategy_dict()



# 🛡️ [리스크 가드 발동 횟수 기록용 전역 변수]
guard_trigger_count: int = 0

# 🛡️ [활성 대시보드 연결 관리 세트]
connected_clients: set[Any] = set()

# ── 🎛️ [대시보드 실시간 설정 제어 전역 변수] ──────────────────────────────────────
# HFT_Control_Panel.html 설정 블록에서 WebSocket으로 수신된 값이 즉시 반영됩니다.
SIM_VOL_LEVEL: str = "CALM"              # 변동성 레벨: "CALM" / "NORMAL" / "HIGH"
SIM_DAILY_SHOCK_PTS: float = 0.0         # 일단위 지수변동폭 강제주입 (0=비활성)
SIM_STRESS_CIRCUIT_BREAKER: bool = False  # 극한요소: 서킷브레이커
SIM_STRESS_FLASH_CRASH: bool = False      # 극한요소: 플래시 크래시
SIM_STRESS_IV_EXPLOSION: bool = False     # 극한요소: IV 3배 폭등
SIM_STRESS_SLIPPAGE_MS: int = 0          # 극한요소: 슬리피지 딜레이 ms (0=비활성)
# ────────────────────────────────────────────────────────────────────────────────

# [커맨드라인 인자 파싱]

parser = argparse.ArgumentParser(description="HFT Mock WebSocket Server (Extreme Stress V3)")
parser.add_argument("--vol",          type=float, default=1.0,   help="변동성 기준 배율 (기본값: 1.0)")
parser.add_argument("--stress",       type=bool,  default=False,  help="스트레스 모드 기본 ON")
parser.add_argument("--slippage-ms",  type=int,   default=50,    help="주문 레이턴시 기본 딜레이 ms")
parser.add_argument("--slippage-rate",type=float, default=0.001, help="체결 단가 슬리피지 페널티율 (기본값 0.001, 0.1%%)")
parser.add_argument("--capital",      type=float, default=None,  help="시작 자본금 (지정하지 않을 시 5천만~2억 사이 임의 설정)")
parser.add_argument("--hardened",     action="store_true", default=False, help="지옥 모드 (Hardened Stress Test) 활성화")

args, unknown = parser.parse_known_args()

BASE_VOLATILITY  = args.vol
STRESS_MODE: bool = args.stress
SLIPPAGE_MS: int  = args.slippage_ms
SLIPPAGE_RATE: float = args.slippage_rate
HARDENED_STRESS_MODE: bool = args.hardened

# ── 📊 Strangle 진입 폭(Width) 설정 상수 (5.0pt ~ 10.0pt 사이 동적 튜닝) ──
MIN_STRANGLE_WIDTH = 5.0
MAX_STRANGLE_WIDTH = 10.0

def calculate_dynamic_strangle_width(active_vol: float) -> float:
    """변동성(active_vol) 수준에 비례하여 MIN_STRANGLE_WIDTH ~ MAX_STRANGLE_WIDTH 사이의 Strangle 행사가 간격(width)을 도출합니다."""
    # active_vol이 BASE_VOLATILITY의 몇 배인지 비율 계산
    vol_ratio = active_vol / max(0.01, BASE_VOLATILITY)
    
    # 평상시(ratio=1.0)에는 MIN_STRANGLE_WIDTH, 
    # 변동성 폭발(ratio=4.8) 시에는 MAX_STRANGLE_WIDTH 근처로 선형 보간
    raw_width = MIN_STRANGLE_WIDTH + (vol_ratio - 1.0) * ((MAX_STRANGLE_WIDTH - MIN_STRANGLE_WIDTH) / 3.8)
    
    # KOSPI 200 옵션의 표준 행사가 단위인 2.5 단위로 반올림
    rounded_width = round(raw_width / 2.5) * 2.5
    
    # 최종 최소/최대 범위 클램핑
    return float(max(MIN_STRANGLE_WIDTH, min(MAX_STRANGLE_WIDTH, rounded_width)))

if args.capital is not None:
    initial_capital = args.capital
else:
    initial_capital = 25000000.0

current_capital  = initial_capital
total_equity     = initial_capital

logger.info("=" * 60)
logger.info(f"HFT Conductor: 자본 연동 수량 엔진 기동 (변동성: {BASE_VOLATILITY}x)")
if STRESS_MODE:
    logger.info("⚠️ [STRESS TEST MODE: ON (DEFAULT)] 8대 극한 시나리오 복합 주입 엔진 가동")
    if HARDENED_STRESS_MODE:
        logger.warning("🔥 [HARDENED STRESS TEST: ON (HELL)] 지옥 모드 활성화 - 슬리피지 쇼크, 증거금 할증, 강제 청산 페널티 주입")
else:
    logger.info("🍃 [STRESS TEST MODE: OFF] 인위적 제한 없음")
logger.info("=" * 60)


# 🛡️ [서버 시작 타임스탬프 정의]
server_start_time: float = time.time()

RUNTIME_MODE = os.environ.get("RUNTIME_MODE", "SIMULATION")
if len(sys.argv) > 1 and sys.argv[1].upper() in ["SIMULATION", "PAPER", "LIVE"]:
    RUNTIME_MODE = sys.argv[1].upper()

DASHBOARD_AUTH_TOKEN = os.environ.get("DASHBOARD_AUTH_TOKEN", "").strip()

# 🛡️ [ACCOUNT RISK THRESHOLD PARAMETERS]
MARGIN_LIQUIDATION_THRESHOLD = 92.0         # 마진 비율 92% 초과 시 MarginDietGuard
DAILY_DRAWDOWN_THRESHOLD = 0.70             # 당일 고점(HWM) 대비 30% 손실 시 ZeroLossGuard
ACCOUNT_KILL_SWITCH_THRESHOLD = 0.25       # 원금 대비 75% 손실 시 최후의 마진콜 락다운

def _recalc_margin(options_portfolio, futures_qty, price, capital, margin_haircut=1.0):
    sell_call_qty = sum(int(p.get("qty", 0)) for p in options_portfolio if p.get("side") == "SELL" and p.get("type") == "CALL")
    buy_call_qty = sum(int(p.get("qty", 0)) for p in options_portfolio if p.get("side") == "BUY" and p.get("type") == "CALL")
    net_short_call = max(0, sell_call_qty - buy_call_qty)
    
    sell_put_qty = sum(int(p.get("qty", 0)) for p in options_portfolio if p.get("side") == "SELL" and p.get("type") == "PUT")
    buy_put_qty = sum(int(p.get("qty", 0)) for p in options_portfolio if p.get("side") == "BUY" and p.get("type") == "PUT")
    net_short_put = max(0, sell_put_qty - buy_put_qty)
    
    net_naked_qty = net_short_call + net_short_put
    hedged_spread_qty = (sell_call_qty - net_short_call) + (sell_put_qty - net_short_put)
    
    naked_margin = net_naked_qty * price * OPTIONS_MULTIPLIER * 0.075 * margin_haircut
    spread_margin = hedged_spread_qty * 1250000 * margin_haircut
    options_margin = naked_margin + spread_margin
    
    used_m = (abs(futures_qty) * price * FUTURES_MULTIPLIER * 0.09 * margin_haircut) + options_margin
    ratio = (used_m / max(1000000.0, capital)) * 100.0
    return used_m, ratio


def _reset_session_state(preserve_capital: bool = False) -> None:
    """⚠️ 세션 전역 상태 완전 리셋 — 자동 재기동 시 호출.

    preserve_capital=True 이면 직전 세션 종료 시의 변경된 자본금을 그대로 이월하여 연결한다.
    False일 경우(최초 기동) 자산이 2500만원으로 새로 리셋된다.
    """
    global current_capital, accumulated_reserve, total_equity, initial_capital, server_start_time, emergency_cooldown_ticks, daily_friction_cost, daily_friction_lockdown, autobot_active
    global current_price, prev_price, current_position_qty, used_margin
    global portfolio_options, iv_history, session_telemetry, rollover_event_log
    global strategy_pnl_tracker, strategy_stress_pnl, guard_trigger_count
    global simulated_days_to_expiry, risk_triggered_event, restart_count
    global daily_hwm, highest_equity_today, calendar_sim, overnight_insurance_bought_today, insurance_active_this_month, insurance_reentry_needed_today, is_market_opened_today
    global trading_date_logs, event_logs, main_engine_broken
    global all_sessions_telemetry, all_sessions_markdowns
    global track1, track2, track3, track4, track5, track6, track7, track8, track9, futures_sensor, weekly_sensor, daily_sensor, replay_engine, slippage_engine, paper_account
    global track3_entry_price, track3_entry_qty, track3_net_qty, track5_active_qty, insurance_budget_pool
    global price_history_60, spread_history_120
    global strategy_realized_pnl  # Phase 2.4: 팩토리 재생성을 위해 global 선언 필수
    global SESSION_ID, already_rolled_this_month  # Phase 1.1 + 2.1: 세션 UUID 갱신 및 롤오버 플래그
    global enabled_strategies  # 전략 1~8 개별 온오프 강제 토글 플래그
    global hourly_start_equity, month_start_capital, last_tracked_hour  # 매시간 및 월마감 손익률 추적용 변수

    # 🔑 [Phase 2.1] 세션 UUID 재생성 — 프론트엔드가 세션 경계를 감지할 수 있도록
    SESSION_ID = str(uuid.uuid4())
    logger.info("🔑 [NEW SESSION] 세션 UUID 발급: %s", SESSION_ID)

    # 🛡️ [Phase 1.1] 만기 롤오버 1회 실행 플래그 리셋 (단, 당월 정산 기록 존재 시 무차용 유지)
    already_rolled_this_month = False
    enabled_strategies = {f"track{i}": True for i in range(1, 9)}

    track3_entry_price = 0.0
    track3_entry_qty = 0
    track3_net_qty = 0

    restart_count = 0

    # 이전 테스트 기록 삭제
    all_sessions_telemetry.clear()
    all_sessions_markdowns.clear()

    if not preserve_capital:
        is_market_opened_today = False
        initial_capital  = 25000000.0
        logger.info("💰 [CAPITAL INITIALIZED] 매 테스트마다 2500만원으로 완전 초기화: ₩%s", f"{initial_capital:,.0f}")
        current_capital  = initial_capital
        accumulated_reserve = 0.0
        total_equity     = initial_capital
        hourly_start_equity = initial_capital
        month_start_capital = initial_capital
        last_tracked_hour = -1
        
        # 최초 기동이거나 롤오버(월 단위 리셋) 시에만 달력과 지수 위치 초기화
        calendar_sim = CalendarSimulator("2025-01-10")
        current_price    = round(random.uniform(300.0, 400.0), 2)
        prev_price       = current_price
    else:
        logger.info("💰 [CAPITAL & STATE PRESERVED] 🚨 15%% 셧다운으로 인한 재기동 - 직전 자본, 지수 위치, 달력을 100%% 그대로 이월하여 연속 방어 테스트 진입!")
        
        # 1. 가상 시간 50분 전진 (현실 10초 쿨다운 보상)
        if calendar_sim is not None:
            calendar_sim.tick(10.0) 
            logger.info("⏳ [TIME WARP] 쿨다운 10초 동안 가상 시간 50분 경과 및 달력 반영 완료: %s", calendar_sim.current_time.strftime("%Y-%m-%d %H:%M:%S"))
            
        # 2. 50분(가상) 공백 동안의 지수 난수화(격변 모사)
        price_jump = round(random.uniform(-5.0, 5.0), 2)
        current_price = max(100.0, current_price + price_jump)
        prev_price = current_price
        logger.info("📉 [MARKET SHIFT] 쿨다운 중 코스피 지수 격변 반영: %spt 변동 (현재가: %.2fpt)", f"{price_jump:+.2f}", current_price)
        
        # 3. 새로운 방어선(HWM) 기준점 재설정
        # 직전 붕괴로 인해 깎인 자본금을 새로운 최고점(HWM)으로 설정하여 무한 셧다운 루프 방지
        daily_hwm = total_equity
        highest_equity_today = total_equity

    overnight_insurance_bought_today = False
    insurance_active_this_month = False
    insurance_reentry_needed_today = False
    emergency_cooldown_ticks = 0
    daily_friction_cost = 0.0
    daily_friction_lockdown = False
    trading_date_logs = []
    event_logs = []
    main_engine_broken = False
    autobot_active = True
    
    # ── ⏳ 가상 테스트 경과 시간(server_start_time) 세션 단위 초기화 ──
    import time as real_time
    server_start_time = real_time.time()
    current_position_qty = 0
    used_margin      = 0.0

    # ── [NEW] Track 1: Track1 ──
    track1 = Track1(config={})
    
    # 💥 [CRITICAL FIX] 장 시작 직후 Track 1 넓은 양매수(Long Strangle) 구축 및 풋매도 가두리 주입 (당일 1회만 수행)
    if not is_market_opened_today:
        t1_open_signals = track1.on_market_open(current_price)
        portfolio_options = []
        for sig in t1_open_signals:
            act = sig.get("action")
            if act == "TAIL_DEFENSE_BUILD":
                call_k = sig.get("call_strike")
                put_k = sig.get("put_strike")
                portfolio_options.append({"type": "CALL", "side": "BUY", "strike": call_k, "price": 1.50, "qty": BASE_TRACK1_QTY, "activeStrategy": "Track1", "tag_id": "TAIL"})
                portfolio_options.append({"type": "PUT", "side": "BUY", "strike": put_k, "price": 1.50, "qty": BASE_TRACK1_QTY, "activeStrategy": "Track1", "tag_id": "TAIL"})
            elif act == "FENCE_BUILD":
                opt_type = sig.get("type")
                opt_strike = sig.get("strike")
                tag_id = sig.get("tag_id")
                portfolio_options.append({"type": opt_type, "side": "SELL", "strike": opt_strike, "price": 2.00, "qty": BASE_TRACK1_QTY, "activeStrategy": "Track1", "tag_id": tag_id})
        is_market_opened_today = True
    
    # ── [NEW] Track 2: Asymmetric Trap Strategy ──
    track2 = Track2(config={})
    
    # ── [NEW] Track 3: Statistical Arbitrage Strategy ──
    track3 = Track3(config={})
    price_history_60 = deque(maxlen=60)
    spread_history_120 = deque(maxlen=120)
    
    # ── [NEW] Track 4: Smart Gamma Scalping Strategy ──
    track4 = Track4(config={})
    
    # ── [NEW] Track 5: Gap Protocol Strategy ──
    track5 = Track5(config={})
    track5_active_qty = 0
    
    # ── [NEW] Track 6: Daily Tail Insurance Bot ──
    track6 = Track6(config={})
    
    # ── [NEW] Track 7: Weekly Tail Insurance Bot ──
    track7 = Track7(config={})
    
    # ── [NEW] Track 8: Monthly Wide Strangle Strategy ──
    track8 = Track8(config={})
    t8_init = track8.evaluate_entry(
        dte=simulated_days_to_expiry,
        budget=initial_capital * 0.050,
        current_price=current_price,
        current_regime="NORMAL",
        date_str=calendar_sim.current_date.strftime("%Y-%m-%d")
    )
    if t8_init.get("status") == "TRIGGERED":
        for signal in t8_init.get("signals", []):
            portfolio_options.append({
                "type": "PUT", "side": "BUY", "strike": float(signal.get("put_strike")), "price": 1.50, "qty": int(signal.get("qty_put")),
                "activeStrategy": "Track8", "is_insurance": True
            })
            portfolio_options.append({
                "type": "CALL", "side": "BUY", "strike": float(signal.get("call_strike")), "price": 1.20, "qty": int(signal.get("qty_call")),
                "activeStrategy": "Track8", "is_insurance": True
            })
            logger.warning("⚠️ [MONTHLY STRANGLE BUY] 월간 지정가 분할 큐 양매수 진입! (예산지출: KRW %s / 콜: %d계약 / 풋: %d계약)", 
                           f"{signal.get('cost', 0.0):,.0f}", signal.get("qty_call", 1), signal.get("qty_put", 2))

    # ── [NEW] Track 9: Overnight Insurance Strategy ──
    track9 = Track9(config={})
    
    futures_sensor = FuturesSensor()
    weekly_sensor = WeeklyOptionsSensor()
    daily_sensor = DailyOptionsSensor()
    
    replay_engine = HistoricalReplayEngine()
    slippage_engine = SlippageEngine()
    paper_account = PaperTradingAccount(initial_capital=25000000.0)
    
    insurance_budget_pool = 1000000.0
    
    session_telemetry   = []
    rollover_event_log  = []

    strategy_realized_pnl = _make_strategy_dict()
    strategy_pnl_tracker = _make_strategy_dict()
    strategy_stress_pnl = _make_strategy_dict()
    guard_trigger_count       = 0
    simulated_days_to_expiry  = float(calendar_sim.remaining_days)

    # 이벤트 리셋
    risk_triggered_event.clear()

    logger.info(
        "🆕 [SESSION #%d] 새 세션 리셋 완료! \n"
        "   시작 자본: ₩%s  |　시작가: %.2f  |　D-Day: %.1f일",
        restart_count,
        f"{initial_capital:,.0f}",
        current_price,
        simulated_days_to_expiry,
    )
async def handler(websocket: Any) -> None:
    global autobot_active
    global SIM_VOL_LEVEL, SIM_DAILY_SHOCK_PTS
    global SIM_STRESS_CIRCUIT_BREAKER, SIM_STRESS_FLASH_CRASH, SIM_STRESS_IV_EXPLOSION, SIM_STRESS_SLIPPAGE_MS
    logger.info("대시보드 클라이언트 연결됨!")
    connected_clients.add(websocket)
    try:
        async for message in websocket:
            try:
                data = orjson.loads(message)

                # ── 🔑 [PAPER / LIVE 모드 토큰 인증 검증] ──────────────────────────
                if RUNTIME_MODE in ("PAPER", "LIVE") and DASHBOARD_AUTH_TOKEN:
                    provided_token = data.get("auth_token", "")
                    if provided_token != DASHBOARD_AUTH_TOKEN:
                        logger.warning("⛔ [AUTH FAILED] RUNTIME_MODE=%s 에서 인증 토큰 검증 실패!", RUNTIME_MODE)
                        await websocket.send(orjson.dumps({
                            "type": "auth_rejected",
                            "reason": "invalid_auth_token"
                        }).decode('utf-8'))
                        continue

                # ── 🔐 [RUNTIME_MODE 액션 권한 매트릭스] ─────────────────────────
                # SIMULATION : 모든 액션 허용 (로컬 테스트 편의)
                # PAPER/LIVE : 봇 시작·전략 토글만 허용, 시뮬레이션 설정 변경·시나리오 주입 차단
                _ACTION_PERMISSIONS: Dict[str, set] = {
                    "SIMULATION": {"start_bot", "update_settings", "update_strategy_flags", "inject_scenario", "change_scenario"},
                    "PAPER":      {"start_bot", "update_strategy_flags"},
                    "LIVE":       {"start_bot", "update_strategy_flags"},
                }
                _req_action = data.get("action")
                if _req_action:
                    _allowed = _ACTION_PERMISSIONS.get(RUNTIME_MODE, set())
                    if _req_action not in _allowed:
                        logger.warning(
                            "⛔ [ACL BLOCKED] action='%s' RUNTIME_MODE=%s 에서 차단됨 (허용: %s)",
                            _req_action, RUNTIME_MODE, sorted(_allowed)
                        )
                        await websocket.send(orjson.dumps({
                            "type": "action_rejected",
                            "action": _req_action,
                            "reason": f"not_allowed_in_{RUNTIME_MODE.lower()}_mode"
                        }).decode('utf-8'))
                        continue

                if data.get("action") == "start_bot":

                    if not autobot_active:
                        autobot_active = True
                        logger.info("🚀 [AUTO BOT START] 대시보드 커맨드 수신: 오토봇 알고리즘 매매가 활성화되었습니다!")

                elif data.get("action") == "update_strategy_flags":
                    flags = data.get("enabled_strategies", {})
                    for k, v in flags.items():
                        if k in enabled_strategies:
                            enabled_strategies[k] = bool(v)
                    logger.info("🎯 [STRATEGY CONTROL] 대시보드 커맨드 수신: 전략 활성화 상태 변경 %s", enabled_strategies)

                # ── 🌤️ [대시보드 장세 시나리오 실시간 핫 리로드 수신] ──
                elif data.get("action") == "change_scenario":
                    new_sc = data.get("scenario", "MODERATE_TREND")
                    if calendar_sim:
                        calendar_sim._market_scenario = new_sc
                    logger.info("🌤️ [HOT RELOAD] 대시보드 시나리오 스위치 커맨드 수신: '%s' 주입 완료!", new_sc)
                    
                    sc_file = os.path.join("config", "market_scenarios.yaml")
                    if os.path.exists(sc_file):
                        try:
                            import yaml
                            with open(sc_file, "r", encoding="utf-8") as f:
                                sc_conf = yaml.safe_load(f) or {}
                            sc_conf["active_scenario"] = new_sc
                            with open(sc_file, "w", encoding="utf-8") as f:
                                yaml.dump(sc_conf, f, allow_unicode=True)
                        except Exception as e_sc:
                            logger.warning("시나리오 YAML 파일 업데이트 에러: %s", e_sc)

                # ── 🎛️ [대시보드 실시간 설정 수신] ──
                elif data.get("action") == "update_settings":
                    # 🏗️ [Phase 2.2] 실전/모의 모드에서는 시뮬레이션 설정 변경 차단
                    if RUNTIME_MODE != "SIMULATION":
                        logger.warning("⛔ [BLOCKED] RUNTIME_MODE=%s 에서 시뮬레이션 설정 변경 차단됨", RUNTIME_MODE)
                        await websocket.send(orjson.dumps({"type": "settings_rejected", "reason": "not_simulation_mode"}).decode('utf-8'))
                        continue

                    cfg = data.get("settings", {})

                    # 🛡️ [Phase 2.3] 원자적 적용: 임시 변수에 파싱 후 전부 성공 시에만 전역 적용
                    try:
                        _vol = str(cfg["volLevel"]) if "volLevel" in cfg else SIM_VOL_LEVEL
                        _shock = float(cfg["dailyShockPts"]) if "dailyShockPts" in cfg else SIM_DAILY_SHOCK_PTS
                        _cb = bool(cfg["stressCircuitBreaker"]) if "stressCircuitBreaker" in cfg else SIM_STRESS_CIRCUIT_BREAKER
                        _fc = bool(cfg["stressFlashCrash"]) if "stressFlashCrash" in cfg else SIM_STRESS_FLASH_CRASH
                        _iv = bool(cfg["stressIVExplosion"]) if "stressIVExplosion" in cfg else SIM_STRESS_IV_EXPLOSION
                        _slip = int(cfg["stressSlippageMs"]) if "stressSlippageMs" in cfg else SIM_STRESS_SLIPPAGE_MS
                    except (ValueError, TypeError, KeyError) as parse_err:
                        logger.error("🎛️ [SETTINGS PARSE ERROR] 설정 파싱 실패 (부분 적용 방지): %s", parse_err)
                        await websocket.send(orjson.dumps({"type": "settings_rejected", "reason": str(parse_err)}).decode('utf-8'))
                        continue

                    # 모든 파싱 성공 → 전역 변수에 원자적 일괄 적용
                    SIM_VOL_LEVEL = _vol
                    SIM_DAILY_SHOCK_PTS = _shock
                    SIM_STRESS_CIRCUIT_BREAKER = _cb
                    SIM_STRESS_FLASH_CRASH = _fc
                    SIM_STRESS_IV_EXPLOSION = _iv
                    SIM_STRESS_SLIPPAGE_MS = _slip

                    logger.info("🎛️ [SETTINGS APPLIED] 변동성=%s, 충격=%spt, CB=%s, FC=%s, IV=%s, Slip=%dms",
                                _vol, _shock, _cb, _fc, _iv, _slip)

                    # 설정 반영 확인 응답 전송
                    ack = orjson.dumps({"type": "settings_ack", "applied": cfg})
                    await websocket.send(ack)
            except Exception as e_msg:
                logger.error("클라이언트 메시지 디코딩 에러: %s", e_msg)
    except Exception:
        pass
    finally:
        if websocket in connected_clients:
            connected_clients.remove(websocket)
        logger.info("대시보드 클라이언트 연결 종료")



async def simulation_loop() -> None:  # noqa: C901
    global current_capital, accumulated_reserve, total_equity, initial_capital
    global current_price, prev_price, current_position_qty, used_margin
    global portfolio_options, iv_history, session_telemetry
    global strategy_pnl_tracker, strategy_stress_pnl, guard_trigger_count
    global shutdown_event, simulated_days_to_expiry, rollover_event_log
    global risk_triggered_event
    global daily_hwm, highest_equity_today, calendar_sim, overnight_insurance_bought_today, insurance_active_this_month, insurance_reentry_needed_today, emergency_cooldown_ticks, daily_friction_cost, daily_friction_lockdown, autobot_active
    global trading_date_logs, event_logs, main_engine_broken
    global last_insurance_qty, last_insurance_strike, last_track1_sell_qty
    global track3_entry_price, track3_entry_qty, track3_net_qty
    global track1, track2, track3, track4, track5, track6, track7, track8, track9, futures_sensor, weekly_sensor, daily_sensor, replay_engine, slippage_engine, paper_account
    global price_history_60, spread_history_120, track5_active_qty, insurance_budget_pool, calculated_fee
    global SIM_CAPITAL_RATIO, SIM_VOL_LEVEL, SIM_DAILY_SHOCK_PTS
    global SIM_STRESS_CIRCUIT_BREAKER, SIM_STRESS_FLASH_CRASH, SIM_STRESS_IV_EXPLOSION, SIM_STRESS_SLIPPAGE_MS
    global already_rolled_this_month, strategy_realized_pnl, is_market_opened_today  # Phase 1.1 + 2.4


    global last_tracked_hour, hourly_start_equity, month_start_capital

    assert track1 is not None and track2 is not None
    assert track3 is not None and track4 is not None
    assert track5 is not None and track6 is not None
    assert track7 is not None and track8 is not None and track9 is not None
    assert futures_sensor is not None and weekly_sensor is not None
    assert daily_sensor is not None and replay_engine is not None
    assert slippage_engine is not None and paper_account is not None

    seq = 0
    current_regime = "NORMAL"
    active_vol = 1.0
    calculated_fee = 0.0
    price_history: deque[float] = deque(maxlen=10)

    # ── 🔄 강제 시뮬레이션 환경 (Monthly Loop & Injection) 상태 변수 ──
    current_month_str = ""
    sim_month_count = 0
    track5_investment_ratio = 0.02  # 고정 2.0% 자본금 할당 비율


    sim_day_in_month = 0
    target_extreme_shock_pts = 8.0

    extreme_vol_day_countdown = random.randint(10, 14)  # 2주 간격 (10~14 영업일)
    extreme_vol_active_today = False


    track2_unwind_cooldown_ticks = 0

    # ── 📊 현실적 매크로 시나리오 상태 변수 ──
    macro_regime = "MACRO_NORMAL"
    crisis_stage = 0
    crisis_ticks_left = 0

    # ── 극한 시나리오 상태 변수 ─────────────────────────────────────────
    flash_crash_active   = False   # Flash Crash 진행 중 여부
    flash_crash_ticks    = 0       # Flash Crash 남은 틱
    flash_crash_cooldown = 0       # Flash Crash 재발동 쿨다운

    circuit_breaker_active  = False  # 서킷브레이커 정지 중
    circuit_breaker_ticks   = 0      # 정지 남은 틱
    circuit_breaker_cooldown = 0     # 재발동 쿨다운

    rejection_storm_active   = False # 주문 거부 폭풍 중
    rejection_storm_ticks    = 0

    liquidity_drought_active = False  # 유동성 고갈 중
    liquidity_drought_ticks  = 0

    iv_explosion_active = False       # IV 폭발 중
    iv_explosion_ticks  = 0

    # 다음 WebSocket 강제 단절까지 남은 틱 (월 1회 수준인 12000~20000틱 랜덤)
    ws_disconnect_countdown = random.randint(12000, 20000)

    import time as real_time
    last_tick_real_time = real_time.time()

    try:
        # 최초 1회 가상서버 기동 시 현실 대기 시간 5초 적용
        if restart_count == 1:
            logger.info("⏳ [INITIAL SERVER WAIT] 인터페이스 화면 접속 대기를 위해 5초간 대기합니다...")
            await asyncio.sleep(5.0)
            last_tick_real_time = real_time.time()
            # 🎬 [축 1] 과거 코로나 팬데믹 대폭락 시나리오 데이터 재생 강제 로드 (현재가 연속 승계)
            if replay_engine is None:
                replay_engine = HistoricalReplayEngine()
            replay_engine.load_scenario("COVID_PANIC_2020", start_price=current_price)

        while True:
            await asyncio.sleep(0.1)
            seq += 1
            order = None

            # 실제 경과 시간 측정 (슬리피지 딜레이 반영)
            now_real_time = real_time.time()
            elapsed_real_seconds = now_real_time - last_tick_real_time
            last_tick_real_time = now_real_time

            # ── 🛡️ 증거금 및 마진 비율 실시간 선제 연산 ──
            margin_haircut = 2.0 if (HARDENED_STRESS_MODE and iv_explosion_active) else 1.0
            used_margin, margin_ratio = _recalc_margin(portfolio_options, current_position_qty, current_price, current_capital, margin_haircut)

            # ── 캘린더 날짜/시간 전진 ──
            date_str, time_str, date_changed, is_market_open = calendar_sim.tick(elapsed_real_seconds)
            if date_changed:
                is_market_opened_today = False  # 🛡️ 거래일 변경 시 개장 초기화 플래그 안전 리셋
            if date_str not in trading_date_logs:
                trading_date_logs.append(date_str)

            # 주말/공휴일 및 장외 시간대에는 시장 거래 잠금 (No Trade / Standby)
            if not is_market_open:
                no_trade_packet: Dict[str, Any] = {
                    "date":                  date_str,
                    "time":                  time_str,
                    "underlyingPrice":       round(current_price, 2),
                    "regime":                "STANDBY",
                    "bidAskSpread":          0.0,
                    "coord":                 {"x": seq, "y": round(total_equity, 2), "date": date_str},
                    "payoffCoords":          [],
                    "strategyWeights":       {"Track1": 30.0, "Track2": 10.0, "Track3": 5.0, "Track4": 5.0, "Track5": 0.0, "Track6": 0.0, "Track7": 0.0, "Track8": 5.0},
                    "capital":               round(current_capital, 2),
                    "reserve":               round(accumulated_reserve, 2),
                    "budgetPool":            round(insurance_budget_pool, 2),
                    "stressMode":            False,
                    "slippageMs":            0,
                    "slippageRate":          0.0,
                    "usedMargin":            round(used_margin, 2),
                    "marginRatio":           round((used_margin / max(1.0, current_capital)) * 100, 1),
                    "riskLevel":             "NORMAL",
                    "activeStrategy":        "STANDBY (HOLIDAY)",
                    "tuningFactor":          0.0,
                    "tunedSlippage":         0,
                    "circuitBreaker":        False,
                    "is_market_open":        False,
                    "simStartDateTime":      calendar_sim.start_datetime_str,
                    "simEndDateTime":        calendar_sim.expiry_datetime_str,
                    "realElapsedSecs":       int(time.time() - server_start_time),
                    "daysToExpiry":          simulated_days_to_expiry,
                }
                session_telemetry.append(no_trade_packet)
                if connected_clients:
                    msg = orjson.dumps(no_trade_packet).decode('utf-8')
                    asyncio.gather(*[client.send(msg) for client in connected_clients], return_exceptions=True)
                continue

            is_first_tick_of_day = False
            if date_changed:
                # 매 영업일 개장 시점 Daily High-Water Mark 및 마찰 비용 리셋
                daily_hwm = total_equity
                highest_equity_today = total_equity
                overnight_insurance_bought_today = False
                daily_friction_cost = 0.0
                daily_friction_lockdown = False
                is_first_tick_of_day = True
                
                # ── ⚡ [NEW] 매일 시초가 오버나이트 갭(0.8%~1.8%) 주입 모사 (Track 5 시가 갭 회귀 테스트용) ──
                if random.random() < 0.35:
                    gap_dir = random.choice([-1, 1])
                    gap_pct = random.uniform(0.008, 0.018)
                    current_price = round(current_price * (1.0 + gap_dir * gap_pct), 2)
                    logger.info("⚡ [OVERNIGHT GAP] %s 개장 시초가 갭(%.2f%%) 발생! 시가: %.2fp", date_str, gap_dir * gap_pct * 100, current_price)

                # ── 💰 [STRATEGY CAPITAL ISOLATION] 전략별 독립 할당 자본금 표기 (Track 7: 0.5%) ──
                track7_capital = total_equity * 0.005
                
                logger.info("🌅 [NEW TRADING DATE] %s 영업일 시작. Total Equity: ₩%s | Track7 독립 자본: ₩%s", 
                            date_str, f"{total_equity:,.0f}", f"{track7_capital:,.0f}")
                event_logs.append({
                    "seq": seq,
                    "date": date_str,
                    "time": time_str,
                    "event": f"영업일 {date_str} 개장",
                    "details": f"평가 자산: ₩{total_equity:,.0f} / Track 7 할당 자본(0.5%): ₩{track7_capital:,.0f}"
                })
                
                sim_day_in_month += 1
                if simulated_days_to_expiry > 0.5:
                    already_rolled_this_month = False

                # ── 🌤️ [CALM MODE] 2주 간격 (4~8pt 자율선택) 약충격 주입 (평온 약추세 장세 테스트) ──
                extreme_vol_day_countdown -= 1
                if extreme_vol_day_countdown <= 0:
                    extreme_vol_active_today = True
                    extreme_vol_day_countdown = random.randint(10, 14)  # 2주 간격 (10~14 영업일)
                    target_extreme_shock_pts = round(random.uniform(4.0, 8.0), 1)  # 4.0 ~ 8.0pt 자율 가변 선택
                    logger.info(f"🌤️ [BIWEEKLY SHOCK] 오늘({date_str})은 2주 간격 자율 가변 충격({target_extreme_shock_pts}pt) 약충격 장세입니다.")
                    event_logs.append({
                        "seq": seq, "date": date_str, "time": time_str,
                        "event": f"2주간격 {target_extreme_shock_pts}pt 약충격 주입",
                        "details": f"평온 장세 테스트: 2주 간격 1회 하루 등락폭 {target_extreme_shock_pts}포인트 자율 가변 약충격"
                    })
                else:
                    extreme_vol_active_today = False

                # ── 🔕 [CALM MODE] 4대 극한 스트레스 스케줄러 OFF — 평온 장세 순수 전략 손익 관찰 모드 ──
                # 4대 스트레스 환경(IV Explosion / Flash Crash / Circuit Breaker / Rejection Storm) 주입 비활성화됨
                # 재활성화 시 아래 블록 주석 해제

                
                # ── 🧪 1. 월 변경 루프 감지 (자본금 리셋 및 월단위 독립 테스트 환경 구축) ──
                month_str = date_str[:7] # YYYY-MM
                if month_str != current_month_str:
                    sim_day_in_month = 1  # 신규 월 시작 시 일자 카운트 초기화
                    if current_month_str != "":
                        # 💰 [CARRY-OVER CAPITAL & INDEX] 월 변경 시 자본금 및 코스피 지수를 100% 연속 이월 승계 (끊김 없는 세션 전환)
                        logger.info("📅 [MONTHLY CARRY-OVER] 월 변경 감지! (%s -> %s) 전월 최종 자본금(₩%s) 및 종가 지수(%.2fpt)를 차월로 100%% 연속 이월 승계합니다.", 
                                    current_month_str, month_str, f"{total_equity:,.0f}", current_price)
                        
                        event_logs.append({
                            "seq": seq, "date": date_str, "time": time_str,
                            "event": "월 변경 자본금 & 코스피 지수 100% 연속 이월",
                            "details": f"전월 자산 ₩{total_equity:,.0f} / 최종 지수 {current_price:.2f}pt 차월 승계 완료"
                        })
                        
                    current_month_str = month_str
                    sim_month_count += 1
                    
                    logger.info("📅 [MONTHLY TRANSITION] 새로운 달력 월(%s) 진입! 루프 %d. (현재 진행중 옵션 만기일: %s | 자본금: ₩%s)", 
                                month_str, sim_month_count, calendar_sim.current_expiry.strftime("%Y-%m-%d"), f"{total_equity:,.0f}")

                
                # [Track5] 시초가 갭 괴리 감지 및 역방향 저격 진입 판단 (장세 지표 연동 동적 Z-Score 적용)
                if autobot_active and track5:
                    gap_res = track5.evaluate_gap_divergence(current_price, prev_price, active_vol, current_regime=current_regime)

                    if gap_res.get("status") == "TRIGGERED":
                        # 갭 수량 결정 (자본금의 투자비율 기반, 1500만원당 1계약)
                        track5_active_qty = max(1, int(total_equity * track5_investment_ratio / 15_000_000.0))
                        for signal in gap_res.get("signals", []):
                            action = signal.get("action")
                            reason = signal.get("reason")
                            
                            # 수수료 가산
                            calculated_fee += track5_active_qty * current_price * FUTURES_MULTIPLIER * FUTURES_FEE_RATE
                            
                            if action == "ENTER_GAP_SHORT":
                                current_position_qty -= track5_active_qty
                                logger.info("⚡ [TRACK 5 GAP] %s - 선물 숏 %d계약 진입! (진입가: %.2f)", reason, track5_active_qty, current_price)
                                
                                # 콜 펜스 압축
                                for pos in portfolio_options:
                                    if pos.get("type") == "CALL" and pos.get("side") == "SELL":
                                        pos["strike"] -= track5.fence_compress_pt
                                        logger.info("🕸️ [TRACK 5 FENCE] 콜 가두리 펜스 압축 구축! 행사 변경: %.2f", pos["strike"])
                                        
                            elif action == "ENTER_GAP_LONG":
                                current_position_qty += track5_active_qty
                                logger.info("⚡ [TRACK 5 GAP] %s - 선물 롱 %d계약 진입! (진입가: %.2f)", reason, track5_active_qty, current_price)
                                
                                # 풋 펜스 압축
                                for pos in portfolio_options:
                                    if pos.get("type") == "PUT" and pos.get("side") == "SELL":
                                        pos["strike"] += track5.fence_compress_pt
                                        logger.info("🕸️ [TRACK 5 FENCE] 풋 가두리 펜스 압축 구축! 행사 변경: %.2f", pos["strike"])
                                        
                            event_logs.append({
                                "seq": seq, "date": date_str, "time": time_str,
                                "event": f"Track 5 Gap Trigger ({action})",
                                "details": f"{reason} / 수량: {track5_active_qty}계약"
                            })

            # ── 🔌 장애 자동 복구 모사 ──
            if main_engine_broken:
                if random.random() < 0.05:  # 5% 확률 복구
                    main_engine_broken = False
                    logger.info("🔌 [WS RECONNECT] 연결 유실 장애 정상 복구 완료.")

            # ── 쿨다운 감소 ──────────────────────────────────────────────
            flash_crash_cooldown    = max(0, flash_crash_cooldown - 1)
            circuit_breaker_cooldown = max(0, circuit_breaker_cooldown - 1)
            emergency_cooldown_ticks = max(0, emergency_cooldown_ticks - 1)
            ws_disconnect_countdown -= 1

            # ── 🛡️ 만기일 잔여 일수(D-Days) 캘린더 연동 동기화 ───────
            simulated_days_to_expiry = calendar_sim.simulated_days_to_expiry
            
            rollover_event_happened = False
            curr_expiry_str = calendar_sim.current_expiry.strftime("%Y-%m-%d")
            is_already_settled = any(r.get("expiry_date") == curr_expiry_str for r in rollover_event_log)
            if simulated_days_to_expiry <= 0.0 and not already_rolled_this_month and not is_already_settled:
                # 🛡️ [Phase 1.1 BUG FIX] 당월 1회만 실행 보장 및 Replay/재시작 멱등성(Idempotency) Guard
                already_rolled_this_month = True
                rollover_event_happened = True
                settlement_total_pnl = 0.0
                
                for pos in list(portfolio_options):
                    k = float(pos["strike"])
                    side = pos["side"]
                    p_type = pos["type"]
                    qty = int(pos["qty"])
                    
                    # 내재가치 정산: Call = max(0, S - K), Put = max(0, K - S)
                    intrinsic_val = max(0.0, current_price - k) if p_type == "CALL" else max(0.0, k - current_price)
                    
                    if side == "BUY":
                        settlement_pnl = intrinsic_val * qty * OPTIONS_MULTIPLIER
                    else:
                        settlement_pnl = - intrinsic_val * qty * OPTIONS_MULTIPLIER
                        
                    settlement_total_pnl += settlement_pnl
                
                portfolio_options.clear()
                
                # 롤오버 실행: 새로운 ATM 기준 숏 스트랭글 재구축 (동적 간격 적용)
                atm_strike = round(current_price / 2.5) * 2.5
                if macro_regime == "MACRO_NORMAL":
                    curr_vol = BASE_VOLATILITY * 0.95
                elif macro_regime == "MACRO_BEAR_VOL":
                    curr_vol = BASE_VOLATILITY * 2.2
                else:
                    curr_vol = BASE_VOLATILITY * 4.8
                
                rollover_width = calculate_dynamic_strangle_width(curr_vol)
                portfolio_options.append({"type": "PUT",  "side": "SELL", "strike": atm_strike - rollover_width, "price": 2.20, "qty": BASE_TRACK1_QTY})
                portfolio_options.append({"type": "CALL", "side": "SELL", "strike": atm_strike + rollover_width, "price": 2.50, "qty": BASE_TRACK1_QTY})
                
                # 💰 [CARRY-OVER CAPITAL] 만기 정산 손익을 자본금에 최종 가산하여 차월로 100% 연속 이월
                current_capital += settlement_total_pnl
                total_equity = current_capital + accumulated_reserve
                highest_equity_today = total_equity
                daily_hwm = total_equity
                initial_capital = current_capital  # 차월 기준 자본금으로 업데이트
                month_start_capital = total_equity  # 차월 월마감 손익률 기준점 업데이트

                pnl_fmt = f"+{settlement_total_pnl:,.0f}원" if settlement_total_pnl >= 0 else f"-{abs(settlement_total_pnl):,.0f}원"
                logger.info("📅 [EXPIRY & CARRY-OVER ROLLOVER] 당월물 옵션 만기 정산 완료! 정산손익: %s | 이월 자본금: ₩%s. 차월물 롤오버 완료.", pnl_fmt, f"{total_equity:,.0f}")
                
                event_logs.append({
                    "seq": seq, "date": date_str, "time": time_str,
                    "event": "월 만기 옵션 정산 & 자본 이월",
                    "details": f"정산손익: {pnl_fmt} / 이월 자본금: ₩{total_equity:,.0f}"
                })

                insurance_active_this_month = False
                insurance_reentry_needed_today = False
                
                # 새로운 차월물 D-Day 동적 정밀 리셋 (실제 차월 KRX 영업일수 계산)
                calendar_sim.current_expiry = calendar_sim.get_next_kospi200_expiry(calendar_sim.current_date.date())
                calendar_sim.remaining_days = calendar_sim.calc_remaining_trading_days(calendar_sim.current_date.date(), calendar_sim.current_expiry)
                calendar_sim.simulated_days_to_expiry = float(calendar_sim.remaining_days)
                simulated_days_to_expiry = float(calendar_sim.remaining_days)
                
                # 롤오버 이벤트 기록
                rollover_event_log.append({
                    "seq":             seq,
                    "expiry_date":     curr_expiry_str,
                    "settlement_pnl":  round(settlement_total_pnl, 2),
                    "price_at_expiry": round(current_price, 2),
                    "new_dte":         round(simulated_days_to_expiry, 2),
                })

            # ── 1. 매크로 국면 및 시나리오 체인 제어 ──────────────────────────────────
            # ── 🌤️ [CALM MODE] 매크로 국면 NORMAL 고정 — 평온 약추세 장세 테스트 모드 ──
            # BEAR_VOL / CRISIS 국면 전이 비활성화. 모든 극한 악재 OFF 상태 유지.
            macro_regime = "MACRO_NORMAL"
            crisis_stage = 0
            crisis_ticks_left = 0
            iv_explosion_active = False
            flash_crash_active = False
            circuit_breaker_active = False
            liquidity_drought_active = False
            rejection_storm_active = False

            # ── 🎛️ [대시보드 설정 반영] 매크로 국면 & 변동성 — SIM_VOL_LEVEL 실시간 제어 ──
            if SIM_VOL_LEVEL == "CALM":
                macro_regime = "MACRO_NORMAL"
                current_regime = "NORMAL" if random.random() < 0.90 else "NEUTRAL"
                active_vol = BASE_VOLATILITY * 0.45    # 평온: 변동성 극소
                bid_ask_spread = round(random.uniform(0.05, 0.10), 2)
            elif SIM_VOL_LEVEL == "NORMAL":
                macro_regime = "MACRO_NORMAL"
                current_regime = "NORMAL" if random.random() < 0.80 else "NEUTRAL"
                active_vol = BASE_VOLATILITY * 0.95    # 보통: 표준 변동성
                bid_ask_spread = round(random.uniform(0.05, 0.20), 2)
            else:  # HIGH
                macro_regime = "MACRO_BEAR_VOL"
                current_regime = "HIGH_VOL" if random.random() < 0.65 else "NORMAL"
                active_vol = BASE_VOLATILITY * 2.2     # 강함: 고변동성
                bid_ask_spread = round(random.uniform(0.20, 0.60), 2)

            # ── 🎛️ [대시보드 설정 반영] 극한요소 스트레스 주입 — SIM_STRESS_* 실시간 제어 ──
            # 각 토글 ON 시 즉시 해당 극한 시나리오 활성화, OFF 시 비활성화
            if SIM_STRESS_IV_EXPLOSION:
                iv_explosion_active = True
                macro_regime = "MACRO_CRISIS"
                active_vol = BASE_VOLATILITY * 4.8
            else:
                iv_explosion_active = False

            if SIM_STRESS_FLASH_CRASH:
                flash_crash_active = True
                flash_crash_ticks = max(flash_crash_ticks, 5)
                macro_regime = "MACRO_CRISIS"
            else:
                if not SIM_STRESS_IV_EXPLOSION:
                    flash_crash_active = False

            if SIM_STRESS_CIRCUIT_BREAKER:
                circuit_breaker_active = True
                circuit_breaker_ticks = max(circuit_breaker_ticks, 10)
                macro_regime = "MACRO_CRISIS"
            else:
                if not (SIM_STRESS_FLASH_CRASH or SIM_STRESS_IV_EXPLOSION):
                    circuit_breaker_active = False

            if not (SIM_STRESS_IV_EXPLOSION or SIM_STRESS_FLASH_CRASH or SIM_STRESS_CIRCUIT_BREAKER):
                rejection_storm_active = False
                liquidity_drought_active = False
                crisis_stage = 0
                crisis_ticks_left = 0

            # 슬리피지 딜레이 설정 반영
            _effective_slippage_ms = SIM_STRESS_SLIPPAGE_MS if SIM_STRESS_SLIPPAGE_MS > 0 else SLIPPAGE_MS


            # ── 1.3 위기 국면(MACRO_CRISIS) 하의 재난 연쇄 시나리오 (Crisis Chain) ──
            if STRESS_MODE and macro_regime == "MACRO_CRISIS":
                crisis_ticks_left -= 1
                if crisis_ticks_left <= 0:
                    # 다음 단계로의 전이
                    if crisis_stage == 1:
                        # 1단계(IV 폭발) 종료 ➡️ 2단계(플래시 크래시 폭락) 전이
                        crisis_stage = 2
                        crisis_ticks_left = random.randint(8, 15)
                        flash_crash_active = True
                        flash_crash_ticks = crisis_ticks_left
                        logger.warning("💥 [CRISIS CHAIN #2] 패닉 투매 물량 급증! 플래시 크래시(Flash Crash) 급락 개시!")
                    elif crisis_stage == 2:
                        # 2단계(플래시 크래시) 종료 ➡️ 3단계(서킷브레이커 거래 정지) 전이
                        crisis_stage = 3
                        crisis_ticks_left = random.randint(40, 80)
                        circuit_breaker_active = True
                        circuit_breaker_ticks = crisis_ticks_left
                        logger.warning("🚨 [CRISIS CHAIN #3] 가격 제한폭 도달! 거래 완전 정지(MARKET HALT / Circuit Breaker) 집행!")
                    elif crisis_stage == 3:
                        # 3단계(서킷브레이커) 종료 ➡️ 4단계(거래 재개 및 극심한 호가공백) 전이
                        crisis_stage = 4
                        crisis_ticks_left = random.randint(25, 45)
                        liquidity_drought_active = True
                        liquidity_drought_ticks = crisis_ticks_left
                        logger.warning("🏜️ [CRISIS CHAIN #4] 거래 재개. 그러나 참여자 실종으로 극단적인 호가공백(Liquidity Drought) 발생!")
                    elif crisis_stage == 4:
                        # 4단계(호가공백) 종료 ➡️ 5단계(증권사 체결 렉 및 통신장애 거부 폭풍) 전이
                        crisis_stage = 5
                        crisis_ticks_left = random.randint(30, 50)
                        rejection_storm_active = True
                        rejection_storm_ticks = crisis_ticks_left
                        logger.warning("🔌 [CRISIS CHAIN #5] 서버 트래픽 폭주! 통신장애 및 주문 거부 폭풍(Rejection Storm) 및 렉 슬리피지 감지!")
                    else:
                        # 5단계 종료 후 ➡️ 다시 1단계로 순환하여 추가 재난이 일어나거나, 매크로 국면 변경을 대기
                        crisis_stage = 1
                        crisis_ticks_left = random.randint(20, 35)
                        iv_explosion_active = True
                        iv_explosion_ticks = crisis_ticks_left
                        logger.warning("🌋 [CRISIS CHAIN #1] 금융 리스크 재확산. 내재변동성 3배 폭발(IV Explosion) 가드 작동!")
                
                # 각 단계별 액티브 상태 동기화
                iv_explosion_active = (crisis_stage == 1)
                flash_crash_active = (crisis_stage == 2)
                circuit_breaker_active = (crisis_stage == 3)
                liquidity_drought_active = (crisis_stage == 4)
                rejection_storm_active = (crisis_stage == 5)

            # ── 1.4 개장 시점(장초기) 야간 외부 변수 모사 (Price Gap) ──
            if STRESS_MODE and date_changed:
                gap_prob = 0.80 if macro_regime == "MACRO_CRISIS" else (0.40 if macro_regime == "MACRO_BEAR_VOL" else 0.05)
                if random.random() < gap_prob:
                    gap_direction = -1 if (macro_regime in ("MACRO_CRISIS", "MACRO_BEAR_VOL")) else random.choice([-1, 1])
                    gap_value = gap_direction * random.uniform(3.5, 9.5)
                    current_price += gap_value
                    # 호가공백 순간 동반 상승
                    bid_ask_spread = max(bid_ask_spread, round(abs(gap_value) * 0.4, 2))
                    logger.warning("⚡ [OVERNIGHT INCIDENT] 야간 외부 변수 반영: %s%s pt 갭 출발!", "+" if gap_value > 0 else "", f"{gap_value:.2f}")

            # ── 2. 주가 변동성 연산 ──────────────────────────────────────
            if flash_crash_active:
                flash_crash_ticks -= 1
                current_price *= (1.0 - random.uniform(0.003, 0.008))
                if flash_crash_ticks <= 0:
                    flash_crash_active = False
                    current_price *= (1.0 + random.uniform(0.010, 0.020))
                    logger.info("📈 [FLASH CRASH] 부분 회복 진행 중")
            else:
                # 평시 무작위 주가 변동
                if extreme_vol_active_today:
                    # 10포인트 급등락 주입: 강한 추세성 변동 및 휩소 (1주 간격)
                    if not hasattr(calendar_sim, "extreme_vol_dir"):
                        calendar_sim.extreme_vol_dir = random.choice([-1, 1])
                    # 3% 확률로 추세 반전 (하루 동안 여러 번 상하로 크게 출렁임)
                    if random.random() < 0.03:
                        calendar_sim.extreme_vol_dir *= -1
                    
                    # 5~10포인트 자율 선택 스케일링 (방어막 및 헷지 반응성 테스트용)
                    shock_scale = target_extreme_shock_pts / 10.0
                    base_change = (calendar_sim.extreme_vol_dir * random.uniform(0.10, 0.48) * shock_scale) + random.uniform(-0.3 * shock_scale, 0.3 * shock_scale)




                else:
                    # 🌤️ [CONFIGURABLE MARKET SCENARIO] config/market_scenarios.yaml 실시간 핫 리로드 주입
                    scenario_file = os.path.join("config", "market_scenarios.yaml")
                    active_sc = getattr(calendar_sim, '_market_scenario', None)
                    
                    if not active_sc and os.path.exists(scenario_file):
                        try:
                            import yaml
                            with open(scenario_file, "r", encoding="utf-8") as f:
                                sc_conf = yaml.safe_load(f)
                                active_sc = sc_conf.get("active_scenario", "MODERATE_TREND")
                                calendar_sim._market_scenario = active_sc
                        except Exception:
                            active_sc = "MODERATE_TREND"

                    # 🎛️ 시나리오별 주가 변동성 & HMM 국면 배지 실시간 동기화
                    if active_sc == "CALM":
                        current_regime = "NEUTRAL"
                        base_volatility = 1.0
                        drift_val = random.uniform(-0.03, 0.03)
                    elif active_sc == "HIGH_VOLATILITY":
                        current_regime = "HIGH_VOL"
                        base_volatility = 2.85
                        drift_val = random.uniform(-0.35, 0.35)
                    elif active_sc == "CRASH_FLASH":
                        current_regime = "HIGH_VOL"
                        base_volatility = 4.5
                        drift_val = random.uniform(-0.80, -0.30)
                    else:  # MODERATE_TREND (기본: 중간 추세 장세)
                        current_regime = "NORMAL"
                        base_volatility = 1.75
                        drift_val = random.uniform(0.08, 0.22)
                    
                    active_vol = base_volatility
                    current_price += drift_val
                    current_price = max(100.0, current_price)

            # ── 📡 3대 실시간 센서 레이어 데이터 갱신 및 상태 측정 ──
            if futures_sensor is None:
                futures_sensor = FuturesSensor()
            if weekly_sensor is None:
                weekly_sensor = WeeklyOptionsSensor()
            if daily_sensor is None:
                daily_sensor = DailyOptionsSensor()
            if replay_engine is None:
                replay_engine = HistoricalReplayEngine()
            if slippage_engine is None:
                slippage_engine = SlippageEngine()
            if paper_account is None:
                paper_account = PaperTradingAccount(initial_capital=25000000.0)
            if track8 is None:
                track8 = Track8()
            if track9 is None:
                track9 = Track9()

            # [축 1] 가상 틱/호가 데이터 재생기 (Historical Replay Engine) 데이터 덮어쓰기
            if replay_engine.is_active:
                replay_tick = replay_engine.next_tick()
                if replay_tick:
                    current_price = replay_tick["price"]
                    active_vol = replay_tick["active_vol"]
                    current_regime = replay_tick["regime"]
                    logger.info("🎬 [HISTORICAL REPLAY] 틱 재생 중 - 가격: %.2f | 변동성: %.1f | 국면: %s",
                                current_price, active_vol, current_regime)

            # [축 3] 페이퍼 트레이딩(Paper Trading) 총자산 실시간 가치 평가 동기화
            # [제 3부] 모의 서버의 누적 실시간 자본금을 총자산으로 동기화 (버그 수정: 이중 계산 및 오류 방지)
            total_equity = current_capital + accumulated_reserve

            mock_open_interest = int(100000 + (active_vol * 50000) + random.randint(-5000, 5000))
            spot_price_sim = current_price * 0.998  # 지수 대비 현물 미세 괴리 모사
            
            # 1. 선물 센서
            _ = futures_sensor.update_sensor(current_price, spot_price_sim, mock_open_interest)
            
            # 2. 위클리 옵션 센서
            time_str_val = calendar_sim.current_time.strftime("%H:%M:%S")
            is_new_week_start = (date_changed and calendar_sim.current_time.weekday() == 0)
            track7_allocated_capital = total_equity * 0.02  # Track 7 할당 자본 2.0%
            weekly_state = weekly_sensor.scan_weekly_market(current_price, track7_allocated_capital, is_new_week_start)
            
            # 3. 데일리 / 0DTE 옵션 센서 (Track 6 할당 자본 2.0%)
            track6_allocated_capital = total_equity * 0.02  # Track 6 할당 자본 2.0%
            daily_state = daily_sensor.monitor_daily_risk(active_vol, BASE_VOLATILITY, track6_allocated_capital)

            # 횡보장 노이즈 필터 동작을 위해 최근 10틱 가격 보관 및 표준편차 산출
            price_history.append(float(current_price))
            is_noise_filter_standby = False
            if len(price_history) >= 10:
                price_std = float(np.std(list(price_history)))
                price_mean = float(np.mean(list(price_history)))
                price_bbw = (4.0 * price_std) / max(1e-5, abs(price_mean))
                if price_bbw < 0.002 or price_std < 0.15:
                    is_noise_filter_standby = True
                    current_regime = "NOISE_CHOPPY"

            # ── 3. 서킷브레이커 처리 ─────────────────────────────────────
            if circuit_breaker_active:
                circuit_breaker_ticks -= 1
                if circuit_breaker_ticks <= 0:
                    circuit_breaker_active = False
                    logger.info("✅ [CIRCUIT BREAKER] 거래 재개")
                cb_packet: Dict[str, Any] = {
                    "date":                  date_str,
                    "time":                  time_str,
                    "underlyingPrice":       round(current_price, 2),
                    "regime":                "CIRCUIT_BREAKER",
                    "bidAskSpread":          99.0,
                    "coord":                 {"x": seq, "y": round(total_equity, 2), "date": date_str},
                    "payoffCoords":          [],
                    "strategyWeights":       {"Track1": 100.0, "Track2": 0.0, "Track3": 0.0, "Track4": 0.0},
                    "capital":               round(current_capital, 2),
                    "reserve":               round(accumulated_reserve, 2),
                    "stressMode":            True,
                    "slippageMs":            0,
                    "slippageRate":          0.0,
                    "usedMargin":            round(used_margin, 2),
                    "marginRatio":           round((used_margin / max(1.0, current_capital)) * 100, 1),
                    "riskLevel":             "DANGER",
                    "activeStrategy":        "Track1",
                    "tuningFactor":          0.1,
                    "tunedSlippage":         1000,
                    "circuitBreaker":        True,
                    "flashCrash":            False,
                    "ivExplosion":           False,
                    "simStartDateTime":      calendar_sim.start_datetime_str,
                    "simEndDateTime":        calendar_sim.expiry_datetime_str,
                    "realElapsedSecs":       int(time.time() - server_start_time),
                }
                session_telemetry.append(cb_packet)
                if connected_clients:
                    msg = orjson.dumps(cb_packet).decode('utf-8')
                    asyncio.gather(*[client.send(msg) for client in connected_clients], return_exceptions=True)
                continue

            # ── 4. 호가 공백 처리 ─────────────────────────────────────────
            if liquidity_drought_active:
                liquidity_drought_ticks -= 1
                bid_ask_spread = round(random.uniform(8.0, 15.0), 2)
                if liquidity_drought_ticks <= 0:
                    liquidity_drought_active = False

            # ── 5. IV 폭발 처리 ───────────────────────────────────────────
            current_iv = active_vol * random.uniform(0.8, 1.2)
            
            if iv_explosion_active:
                iv_explosion_ticks -= 1
                active_vol = BASE_VOLATILITY * 3.0
                current_iv = active_vol * random.uniform(0.8, 1.2)
                if iv_explosion_ticks <= 0:
                    iv_explosion_active = False
                    active_vol = BASE_VOLATILITY  # 폭발 종료 후 원상복구
            else:
                # 폭발이 아닐 때는 서서히 BASE_VOLATILITY 로 회귀하거나 유지
                pass

            iv_history.append(current_iv)

            iv_sell_blocked = iv_explosion_active

            # 고정 배분: Track1(30%), Track2(10%), Track3(5%), Track4(5%), Track8(5%)
            # 조건부 배분: Track5(조건시 +0.1%), Track6(조건시 +0.1%), Track7(조건시 +0.5%)
            t1 = 30.0
            t2 = 10.0
            t3 = 5.0
            t4 = 5.0
            t5_pct = 0.1 if (track5 and track5.gap_state["is_active"]) else 0.0
            t6_pct = 0.1 if (track6 and track6.insurance_state["is_active"]) else 0.0
            t7_pct = 0.5 if (track7 and track7.insurance_state["is_active"]) else 0.0
            t8_pct = 5.0

            strategy_weights = {
                "Track1":    t1,
                "Track2":       t2,
                "Track3":  t3,
                "Track4":      t4,
                "Track5":        t5_pct,
                "Track6":      t6_pct,
                "Track7":     t7_pct,
                "Track8":    t8_pct,
            }
            active_strategy = max(strategy_weights, key=lambda k: strategy_weights[k])
            if current_regime == "NOISE_CHOPPY" or (is_noise_filter_standby and current_regime == "NORMAL"):
                active_strategy = "STANDBY (NOISE)"

            # ── 5. 동적 슬리피지 연산 ────────────────────────────────────
            dynamic_slippage_ms   = SLIPPAGE_MS
            dynamic_slippage_rate = SLIPPAGE_RATE

            if STRESS_MODE:
                if iv_explosion_active:
                    dynamic_slippage_ms   = random.randint(200, 500)
                    dynamic_slippage_rate = random.uniform(0.005, 0.012)
                elif flash_crash_active:
                    dynamic_slippage_ms   = random.randint(150, 480)
                    dynamic_slippage_rate = random.uniform(0.003, 0.008)
                elif current_regime == "HIGH_VOL":
                    dynamic_slippage_ms   = random.randint(80, 250)
                    dynamic_slippage_rate = random.uniform(0.0015, 0.0040)
                    if random.random() < 0.04:
                        dynamic_slippage_ms = random.randint(350, 480)
                        logger.warning(f"⚠️ [MOCK INCIDENT] 증권사 체결 매칭 엔진 순간 병목 정체 감지: {dynamic_slippage_ms}ms")
                elif current_regime == "NEUTRAL":
                    dynamic_slippage_ms   = random.randint(5, 15)
                    dynamic_slippage_rate = random.uniform(0.0, 0.0002)
                else:
                    dynamic_slippage_ms   = random.randint(15, 45)
                    dynamic_slippage_rate = random.uniform(0.0002, 0.0008)

                # 🌪️ [Dynamic_Slippage_Multiplier] 지옥 모드: 서킷브레이커 시 3~5틱 강제 밀림, 평상시 1틱 추가
                if HARDENED_STRESS_MODE:
                    if circuit_breaker_active:
                        dynamic_slippage_rate += random.uniform(0.015, 0.025)
                        dynamic_slippage_ms = max(dynamic_slippage_ms, random.randint(800, 1500))
                    else:
                        dynamic_slippage_rate += 0.0005

            # ── 6. PnL 원 신호 생성 ──────────────────────────────────────
            raw_pnl = 0.0

            # ── 7. 증거금 비율 산출 (지연 제거: 최신 포지션/가격 기반 실시간 재계산) ──
            margin_haircut = 2.0 if (HARDENED_STRESS_MODE and iv_explosion_active) else 1.0
            used_margin, margin_ratio = _recalc_margin(portfolio_options, current_position_qty, current_price, current_capital, margin_haircut)

            if margin_ratio > 90.0:
                risk_level = "DANGER"
            elif margin_ratio > 70.0:
                risk_level = "WARNING"
            else:
                risk_level = "NORMAL"

            # ── 7-1. [NEW] 시가 갭 점프 프로토콜 (Gap Protocol) ──
            if autobot_active and is_first_tick_of_day and margin_ratio > 90.0:
                logger.critical("🚨 [GAP PROTOCOL TRIGGERED] 시가 갭 점프로 마지노선 90%% 즉시 붕괴! 구조적 테일 리스크 방어 헷지 가동!")
                if current_position_qty >= 0:
                    current_position_qty -= 1
                    gap_action = "SELL"
                else:
                    current_position_qty += 1
                    gap_action = "BUY"
                
                event_logs.append({
                    "seq": seq, "date": date_str, "time": time_str,
                    "event": "Gap Protocol", "details": f"시가 점프 방어 선물 {gap_action} 진입"
                })

            # ── 8. 동적 주문 수량 조절 ────────────────────────────────────
            # 🛡️ [Self-Tuning Dynamic Sizing] 실시간 자산 체급(total_equity)과 시장 국면(current_regime)에 연동되는 자율 동적 연동 산식
            regime_multiplier = 0.5 if current_regime in ("HIGH_VOL", "CIRCUIT_BREAKER") else 1.0
            base_sizing_qty = max(1, int((total_equity / 15000000.0) * regime_multiplier))

            # 🛡️ [Position Sizing 절대 상한 캡] 현실의 KOSPI200 선물/옵션 유동성 상한을
            # 고려하여 단일 주문 최대 계약 수를 50계약으로 제한한다.
            MAX_ORDER_QTY_CAP = 50

            if flash_crash_active or iv_explosion_active:
                order_qty = 1   # 극한 이벤트 시 무조건 최소 수량 락다운
            elif margin_ratio > 90.0:
                order_qty = 1
            elif margin_ratio > 70.0:
                order_qty = max(1, min(MAX_ORDER_QTY_CAP, int(base_sizing_qty * random.uniform(0.6, 1.2) * 0.5)))
            else:
                order_qty = max(1, min(MAX_ORDER_QTY_CAP, int(base_sizing_qty * random.uniform(0.6, 1.2))))

            # ── 8-0. [TRACK 1] 실시간 꼬리표 순환, 테일 방어, 선물 헷지 평가 및 포지션 장부 연동 ──
            if autobot_active and enabled_strategies.get("Track1", True) and track1 is not None:
                t1_eval = track1.evaluate_strategy(current_price, round(current_price / 2.5) * 2.5, {"date_str": date_str, "days_to_expiry": simulated_days_to_expiry})
                for sig in t1_eval.get("signals", []):
                    act = sig.get("action")
                    if act == "FENCE_BUILD":
                        portfolio_options.append({
                            "type": sig.get("type"), "side": "SELL", "strike": sig.get("strike"),
                            "price": 2.00, "qty": BASE_TRACK1_QTY, "activeStrategy": "Track1", "tag_id": sig.get("tag_id")
                        })
                    elif act == "FENCE_CLEAR":
                        tag_to_clear = sig.get("tag_id")
                        portfolio_options = [p for p in portfolio_options if not (p.get("activeStrategy") == "Track1" and p.get("tag_id") == tag_to_clear)]
                    elif act == "FUTURES_ORDER":
                        hedge_side = sig.get("type")
                        current_position_qty += (1 if hedge_side == "BUY" else -1)
                        event_logs.append({
                            "seq": seq, "date": date_str, "time": time_str,
                            "event": f"Track1 선물 헷지 {hedge_side} 진입",
                            "details": f"진입가: {current_price:.2f}"
                        })
                    elif act == "FUTURES_UNWIND":
                        unwind_side = sig.get("type")
                        current_position_qty += (1 if unwind_side == "BUY" else -1)
                        event_logs.append({
                            "seq": seq, "date": date_str, "time": time_str,
                            "event": f"Track1 선물 헷지 언와인드 {unwind_side}",
                            "details": f"청산가: {current_price:.2f}"
                        })

            # ── 8-4. [TRACK 4] 감마 스캘핑 델타 리밸런싱 평가 및 연동 ──
            if autobot_active and enabled_strategies.get("Track4", True) and track4 is not None:
                t4_eval = track4.evaluate_scalping_rebalance({
                    "current_delta": round((current_price - round(current_price / 2.5) * 2.5) * 0.1, 2),
                    "deadband": 0.3
                }, simulated_days_to_expiry)
                for sig in t4_eval.get("signals", []):
                    if sig.get("action") == "GAMMA_REBALANCE":
                        rebal_qty = sig.get("qty", 0)
                        current_position_qty += rebal_qty
                        event_logs.append({
                            "seq": seq, "date": date_str, "time": time_str,
                            "event": "Track4 감마 스캘핑 델타 리밸런싱",
                            "details": f"수량: {rebal_qty:+d}계약 (Delta 편차 회수)"
                        })

            # ── 8-5. [TRACK 5] Pure Gap Divergence Protocol 시초가 갭 역방향 평가 ──
            if autobot_active and enabled_strategies.get("Track5", True) and track5 is not None:
                t5_eval = track5.evaluate_gap_divergence(
                    open_price=current_price,
                    prev_close_price=prev_price,
                    active_vol=active_vol,
                    current_regime="NORMAL",
                    date_str=date_str
                )
                pass

            # ── 8-1. 오버나잇 보험용 극외가(OTM) 옵션 매입 파이프라인 (Track 9 연동) ──
            # 매 영업일 15:15:00 ~ 15:20:00 사이 작동
            h_time, m_time = calendar_sim.current_time.hour, calendar_sim.current_time.minute
            if autobot_active and enabled_strategies.get("Track9", True) and (h_time == 15 and 15 <= m_time < 20) and not overnight_insurance_bought_today:
                # 1. 살아있는(is_locked가 False인) 가두리 매도 수량 합산 (Track 1)
                active_sell_qty = sum(
                    int(pos.get("qty", 0)) for pos in portfolio_options 
                    if pos.get("side") == "SELL" and pos.get("activeStrategy", "Track1") == "Track1" and not pos.get("is_locked", False)
                )
                # 2. 현재 보유 중인 오버나잇 보험 수량 파악 (PUT 기준)
                active_insurances = [
                    pos for pos in portfolio_options 
                    if pos.get("is_overnight_insurance", False) and pos.get("side") == "BUY"
                ]
                current_ins_qty = sum(int(p.get("qty", 0)) for p in active_insurances if p.get("type") == "PUT")
                
                # 3. Track 9 플러그인에 평가 위임 (프론트엔드상으로는 Track 1 그룹으로 묶임)
                t9_res = track9.evaluate_insurance(current_price, active_sell_qty, current_ins_qty)
                
                target_insurance_qty = 0
                if t9_res.get("status") == "ADD":
                    for sig in t9_res.get("signals", []):
                        diff_qty = sig["diff_qty"]
                        target_insurance_qty = sig["target_qty"]
                        put_k = sig["put_strike"]
                        call_k = sig["call_strike"]
                        premium = sig["premium"]
                        
                        portfolio_options.append({
                            "type": "PUT", "side": "BUY", "strike": put_k,
                            "price": premium, "qty": diff_qty,
                            "is_insurance": True, "is_overnight_insurance": True, "activeStrategy": "Track1", "tag_id": "O/N"
                        })
                        portfolio_options.append({
                            "type": "CALL", "side": "BUY", "strike": call_k,
                            "price": premium, "qty": diff_qty,
                            "is_insurance": True, "is_overnight_insurance": True, "activeStrategy": "Track1", "tag_id": "O/N"
                        })
                        
                        insurance_cost = premium * diff_qty * OPTIONS_MULTIPLIER * 2
                        current_capital -= insurance_cost
                        
                        event_logs.append({
                            "seq": seq, "date": date_str, "time": time_str,
                            "event": "Track1 오버나잇 갭 방어 헷지 매입",
                            "details": f"Target: {target_insurance_qty} (가두리 매도 {active_sell_qty} 기준) | Qty: +{diff_qty}, Cost: ₩{insurance_cost:,.0f}"
                        })
                elif t9_res.get("status") == "REDUCE":
                    for sig in t9_res.get("signals", []):
                        diff_qty = sig["diff_qty"]
                        target_insurance_qty = sig["target_qty"]
                        
                        qty_to_reduce_put = diff_qty
                        qty_to_reduce_call = diff_qty
                        for p in active_insurances:
                            cur_qty = int(p.get("qty", 0))
                            if p.get("type") == "PUT" and qty_to_reduce_put > 0:
                                reduce = min(cur_qty, qty_to_reduce_put)
                                p["qty"] = cur_qty - reduce
                                qty_to_reduce_put -= reduce
                            elif p.get("type") == "CALL" and qty_to_reduce_call > 0:
                                reduce = min(cur_qty, qty_to_reduce_call)
                                p["qty"] = cur_qty - reduce
                                qty_to_reduce_call -= reduce
                                
                        # 빈 포지션 제거
                        portfolio_options = [p for p in portfolio_options if int(p.get("qty", 1)) > 0]
                        
                        event_logs.append({
                            "seq": seq, "date": date_str, "time": time_str,
                            "event": "Track1 오버나잇 갭 방어 헷지 잉여분 축소",
                            "details": f"Target: {target_insurance_qty} (가두리 매도 {active_sell_qty} 기준) | Qty: -{diff_qty}"
                        })
                elif t9_res.get("status") == "HOLD":
                    for sig in t9_res.get("signals", []):
                        target_insurance_qty = sig["target_qty"]
                
                last_track1_sell_qty = active_sell_qty
                overnight_insurance_bought_today = True
                insurance_active_this_month = (target_insurance_qty > 0)
                insurance_reentry_needed_today = False

            # 🛡️ [시장충격(Market Impact) 동적 슬리피지 가산]
            # 주문 수량이 클수록 호가창 잠식 비율이 높아져 실제 체결 가격이 불리해진다.
            # 수량 1계약 기준 선형 가산 → 10계약이면 슬리피지 +0.05%p 추가 부과.
            market_impact_rate_add = order_qty * 0.00005
            dynamic_slippage_rate  = dynamic_slippage_rate + market_impact_rate_add

            # ── 9. 체결 확률 연산 ─────────────────────────────────────────
            volatility_impact  = abs(active_vol * random.uniform(-0.5, 0.5))
            base_fill_prob     = 0.85
            fill_penalty       = (volatility_impact * 0.15) + (bid_ask_spread * 0.18)
            realtime_fill_prob = max(0.04, base_fill_prob - fill_penalty)

            # ────────────────────────────────────────────────────────────
            # 🔥 [극한 시나리오 3] Order Rejection Storm — 연속 거부율 80%
            # 방어: ExecutionAgent.execute_order() 지수 백오프 재시도
            # ────────────────────────────────────────────────────────────
            if STRESS_MODE and not rejection_storm_active:
                if random.random() < 0.004:
                    rejection_storm_active = True
                    rejection_storm_ticks  = random.randint(10, 20)
                    logger.warning("🚫 [REJECTION STORM] 연속 주문 거부율 80% 폭발!")

            if rejection_storm_active:
                rejection_storm_ticks -= 1
                realtime_fill_prob = min(realtime_fill_prob, 0.20)  # 최대 20% 체결
                if rejection_storm_ticks <= 0:
                    rejection_storm_active = False

            # ── 9-1. Self-Tuning Guard (리스크 자율 미세 조정) ───────────
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 🎯 [MDD 보완 조율 — 3대 감도 레버 상향]
            # 문제: IV Explosion + Flash Crash + Rejection Storm 복합 구간에서
            #       tuning_factor가 충분히 빠르게 수량을 압축하지 못해 MDD 심화.
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            #
            # [레버 1] risk_score 민감도 상향
            #   변동성 가중치: 0.5 → 0.8 (변동성 폭발에 더 빠르게 반응)
            #   거부율 가중치: 0.8 → 1.2 (체결 거부 폭증 시 더 강하게 억제)
            rejection_rate = 1.0 - realtime_fill_prob
            risk_score = max(0.0, (active_vol - 1.0) * 0.8 + rejection_rate * 1.2)

            # [레버 2 수정] tuning_factor 최솟값 하한 상향 (0.05 → 0.40)
            #   선물 델타 헤징 및 극외가(OTM) 보험 옵션 방어막이 완벽하게 가동되므로,
            #   과도한 물량 축소를 차단하고 최소 40% 이상의 진입 체급을 유지하여 회수력을 확보한다.
            tuning_factor = round(max(0.40, min(1.0, 1.0 / (1.0 + risk_score))), 3)

            # [레버 3] 복합 스트레스 2중 억제 (Compound Stress Multiplier)
            #   극한 이벤트가 2개 이상 동시 발화 시 추가 압축을 하되, 최솟값 40% 하한 캡은 엄격히 준수한다.
            compound_stress_count = sum([
                flash_crash_active, iv_explosion_active,
                circuit_breaker_active, rejection_storm_active,
                liquidity_drought_active,
            ])
            if compound_stress_count >= 2:
                tuning_factor = round(max(0.40, tuning_factor * 0.5), 3)  # 50% 추가 압축하되 40% 하한 캡 적용
                logger.warning(
                    "🧨 [COMPOUND STRESS x%d] 극한 이벤트 %d개 동시 발화! "
                    "tuning_factor → %.3f (복합 억제 적용 및 40%% 하한 보장)",
                    compound_stress_count, compound_stress_count, tuning_factor,
                )

            # 슬리피지 가산 (1.5 → 2.5 — 복합 스트레스 구간 체결 비용 현실화)
            tuned_slippage = int(dynamic_slippage_ms * (1.0 + risk_score * 2.5))

            # 주문 수량 보정
            order_qty = max(1, int(order_qty * tuning_factor))
            
            # NOISE_CHOPPY 국면 시 수량 40% 강제 축소 적용
            if current_regime == "NOISE_CHOPPY":
                order_qty = max(1, int(order_qty * 0.40))


            # ── 10. 주문 생성 ─────────────────────────────────────────────
            order = None
            calculated_fee = 0.0

            if rollover_event_happened:
                order = {
                    "id":            f"ROLLOVER-{seq}",
                    "tick":          seq,
                    "time":          time.strftime("%H:%M:%S") + f".{random.randint(100, 999)}",
                    "type":          "ROLLOVER",
                    "assetType":     "SYSTEM",
                    "price":         round(current_price, 2),
                    "qty":           0,
                    "status":        "FILLED",
                    "fee":           0,
                    "debugFillProb": 100.0,
                    "activeStrategy": "SYSTEM",
                }
            elif False: # [V2 STRESS TEST] 가짜 더미 오더(Dummy Logs) 시각적 효과 비활성화 (순수 알고리즘 체결만 기록)
                order_types  = ["BUY", "SELL"]
                # [Central Risk Engine] Track 2, 3, 4는 개별 선물 델타 헤지를 수행하지 않고 알파(옵션) 창출에만 집중.
                # 선물(FUTURES) 델타 헤지는 오직 Track1의 채널을 통해서만 독점적으로 집행.
                if active_strategy != "Track1":
                    asset_type = "OPTIONS"
                else:
                    asset_type = "FUTURES" if random.random() < 0.7 else "OPTIONS"
                order_side   = random.choice(order_types)

                # IV Explosion 시 옵션 매도 차단
                if iv_sell_blocked and asset_type == "OPTIONS" and order_side == "SELL":
                    order_side = "BUY"  # 매수 헤지로 강제 전환

                # 만기 D-3 ~ D-5 전략 1 신규 매도 진입 금지(Blackout)
                is_blackout_rejection = False
                if active_strategy == "Track1" and simulated_days_to_expiry <= 4.0:
                    if asset_type == "OPTIONS" and order_side == "SELL":
                        is_blackout_rejection = True

                # 횡보 노이즈 필터 대기: NORMAL 국면이지만 변동성이 매우 낮을 때 신규 매매 억제
                is_noise_rejection = False
                if is_noise_filter_standby and current_regime == "NORMAL":
                    if asset_type == "OPTIONS" and order_side == "SELL":
                        is_noise_rejection = True

                if asset_type == "OPTIONS":
                    order_price = round(random.uniform(0.5, 8.0), 2)
                else:
                    order_price = round(current_price + random.uniform(-0.5, 0.5), 2)

                if STRESS_MODE:
                    if HARDENED_STRESS_MODE:
                        # ⏳ [Stochastic_Network_Latency] 지옥 모드: 30% 확률로 500ms~2000ms의 거래폭증 지연 주입
                        if random.random() < 0.30:
                            hardened_delay = random.uniform(0.5, 2.0)
                            await asyncio.sleep(hardened_delay)
                        else:
                            await asyncio.sleep(random.uniform(0.03, 0.05))
                    else:
                        await asyncio.sleep(tuned_slippage / 1000.0)

                rand_val = random.random()

                # ────────────────────────────────────────────────────────
                # 🔥 [극한 시나리오 6] Partial Fill 폭탄 / 🌪️ [Orderbook_Liquidity_Cap]
                # 방어: ExecutionAgent._garbage_collect_orphans() 3초 GC
                # ────────────────────────────────────────────────────────
                if HARDENED_STRESS_MODE and order_qty > 50:
                    liquidity_cap_rand = random.random()
                    if liquidity_cap_rand < 0.10:
                        status = "REJECTED"
                    elif liquidity_cap_rand < 0.70:
                        status = "PARTIAL"
                        # 30~50% 강제 미체결 (50%~70%만 체결)
                        order_qty = max(1, int(order_qty * random.uniform(0.5, 0.7)))
                    else:
                        if rand_val < realtime_fill_prob:
                            status = "FILLED"
                        else:
                            status = "REJECTED" if bid_ask_spread > 0.4 or random.random() < 0.5 else "SENT"
                else:
                    if STRESS_MODE and rand_val < 0.30 and not rejection_storm_active:
                        status = "PARTIAL"  # 30% 확률 부분 체결
                    elif rand_val < realtime_fill_prob:
                        status = "FILLED"
                    else:
                        status = "REJECTED" if bid_ask_spread > 0.4 or random.random() < 0.5 else "SENT"

                if is_blackout_rejection or is_noise_rejection:
                    status = "REJECTED"
                    if is_blackout_rejection:
                        logger.warning("🚫 [BLACKOUT LIMIT] 만기 D-3 이하 진입으로 전략 1 (Track 1) 신규 매도 진입 주문 강제 거부 처리!")
                    else:
                        logger.info("🚫 [NOISE FILTER] 극심한 횡보장 가격 노이즈로 신규 진입 매매 억제 (Standby)")

                raw_price = order_price
                # 슬리피지 페널티 적용 (가상 슬리피지 확률 모델 엔진 연동)
                if status in ("FILLED", "PARTIAL") and STRESS_MODE:
                    if slippage_engine is None:
                        slippage_engine = SlippageEngine()
                    slip_res = slippage_engine.apply_slippage(
                        side=order_side,
                        requested_price=order_price,
                        qty=order_qty,
                        active_vol=active_vol,
                        spread=bid_ask_spread
                    )
                    order_price = slip_res["execution_price"]
                    tuned_slippage = slip_res["delay_ms"]

                # 수수료 및 포지션 업데이트 (PARTIAL은 절반 체결로 처리)
                fill_qty = order_qty if status == "FILLED" else (order_qty // 2 if status == "PARTIAL" else 0)

                if fill_qty > 0:
                    if asset_type == "FUTURES":
                        trade_value = order_price * fill_qty * FUTURES_MULTIPLIER
                        calculated_fee = trade_value * FUTURES_FEE_RATE

                        if order_side == "BUY":
                            current_position_qty += fill_qty
                        else:
                            current_position_qty -= fill_qty
                        current_position_qty = max(-25, min(25, current_position_qty))
                        
                        # 슬리피지 비용 누적
                        slippage_cost = abs(order_price - raw_price) * fill_qty * FUTURES_MULTIPLIER
                    else:
                        trade_value = order_price * fill_qty * OPTIONS_MULTIPLIER
                        calculated_fee = trade_value * OPTIONS_FEE_RATE

                        # 옵션 체결 시 합성 포트폴리오 누적 및 평단가 보존
                        offset = random.choice([-5.0, -2.5, 0.0, 2.5, 5.0])
                        opt_strike = round((current_price + offset) / 2.5) * 2.5
                        opt_type = random.choice(["CALL", "PUT"])
                        existing_pos = next((p for p in portfolio_options if p.get("type") == opt_type and p.get("side") == order_side and abs(float(p.get("strike", 0)) - float(opt_strike)) < 1e-4), None)
                        if existing_pos:
                            from decimal import Decimal
                            from core.contracts import calculate_weighted_average_price
                            old_qty = int(existing_pos.get("qty", 0))
                            old_avg = Decimal(str(existing_pos.get("avg_price", existing_pos.get("price", 0.0))))
                            new_avg = calculate_weighted_average_price(old_qty, old_avg, int(fill_qty), Decimal(str(order_price)))
                            existing_pos["qty"] = old_qty + int(fill_qty)
                            existing_pos["avg_price"] = float(new_avg)
                        else:
                            portfolio_options.append({
                                "type": opt_type,
                                "side": order_side,
                                "strike": float(opt_strike),
                                "price": float(order_price),
                                "avg_price": float(order_price),
                                "qty": int(fill_qty),
                                "activeStrategy": active_strategy
                            })
                        # 슬리피지 비용 누적
                        slippage_cost = abs(order_price - raw_price) * fill_qty * OPTIONS_MULTIPLIER

                    # 🔑 [Execution Traceability Pass] 캡처 레코드에 정밀 파이프라인 데이터 기록
                    trade_replay_analyzer.capture_trade_event(
                        trade_type="ENTRY" if current_position_qty == 0 else ("EXIT" if (current_position_qty > 0 and order_side == "SELL") or (current_position_qty < 0 and order_side == "BUY") else "ENTRY"),
                        track_name=active_strategy,
                        side=order_side,
                        asset_type=asset_type,
                        price=order_price,
                        qty=fill_qty,
                        reason=f"전략 체결 시그널 수신 ({status})",
                        realized_pnl=0.0,
                        sensor_snapshot={"zScore": round(random.uniform(1.0, 2.8), 2), "activeVol": round(active_vol, 2), "vpin": round(random.uniform(0.1, 0.4), 2)},
                        state_snapshot={"capital": round(current_capital, 2), "equity": round(total_equity, 2), "marginRatio": round(margin_ratio, 1), "slippageMs": dynamic_slippage_ms},
                        entry_reason=f"{active_strategy} 알파 지표 포획 조건충족 진입",
                        date_str=date_str,
                        requested_price=raw_price,
                        market_price=current_price,
                        execution_price=order_price,
                        slippage_cost=slippage_cost,
                        fee=calculated_fee
                    )
                    
                    # 일일 마찰 비용 가산 및 1.0% 한도 락다운 검사
                    daily_friction_cost += (calculated_fee + slippage_cost)
                    if daily_friction_cost > (total_equity * 0.01):
                        daily_friction_lockdown = True
                        logger.warning(
                            "🚨 [DAILY FRICTION LIMIT] 일일 누적 마찰 비용(₩%s)이 총자산의 1.0%%를 초과했습니다. "
                            "당일 알고리즘 매매를 전면 동결(Lockdown)합니다.",
                            f"{daily_friction_cost:,.0f}"
                        )

                order = {
                    "id":            f"order-{seq}-{random.randint(1000, 9999)}",
                    "tick":          seq,
                    "time":          time.strftime("%H:%M:%S") + f".{random.randint(100, 999)}",
                    "type":          order_side,
                    "assetType":     asset_type,
                    "price":         order_price,
                    "qty":           order_qty,
                    "status":        status,
                    "fee":           round(calculated_fee, 0),
                    "debugFillProb": round(realtime_fill_prob * 100, 1),
                    "activeStrategy": active_strategy,
                }

            # ── 10.1 숏 옵션 ITM 자동 청산 (숏커버) ───────────────────────────
            # 🛡️ [이중 계상(Double-Counting) 방지 설계 원칙]
            # 이 시스템은 '델타 기반 누적 PnL' 아키텍처입니다.
            # options_pnl이 매 틱 dp × delta × qty × 승수로 손실을 이미 누적 차감합니다.
            # 따라서 ITM 강제 청산 시 buyback_cost(내재가치 전액)를 재차 차감하면
            # 동일한 손실이 두 번 계상되어 즉시 15% 보호선을 붕괴시키는 오류가 발생합니다.
            # 올바른 처리: 강제 청산 시 수수료만 차감하고, 포지션을 제거하여
            # 이후 델타 PnL에서 해당 포지션이 더 이상 손실을 누적하지 않도록 합니다.
            covered_fee = 0.0
            if autobot_active:
                for pos in list(portfolio_options):
                    strike_val = float(pos["strike"])
                    side_val = pos["side"]
                    p_type_val = pos["type"]
                    qty_val = int(pos["qty"])
                    
                    is_itm = False
                    if side_val == "SELL":
                        # ITM 임계값 5.0pt: 너무 민감한 조기 발동을 방지
                        if p_type_val == "PUT" and (strike_val - current_price) > 5.0:
                            is_itm = True
                        elif p_type_val == "CALL" and (current_price - strike_val) > 5.0:
                            is_itm = True
                            
                    if is_itm:
                        logger.warning("🛡️ [RISK COVER] 숏 옵션 ITM 위험 감지! 강제 숏커버 청산. Strike: %s, Type: %s, Qty: %d", strike_val, p_type_val, qty_val)
                        try:
                            portfolio_options.remove(pos)
                        except ValueError:
                            pass
                        # 수수료만 차감 (내재가치 손실은 options_pnl의 델타 누적이 처리)
                        cover_price = max(0.2, abs(current_price - strike_val))
                        covered_fee += cover_price * qty_val * OPTIONS_MULTIPLIER * OPTIONS_FEE_RATE

            calculated_fee += covered_fee

            # ── 10.2 MarginDietGuard / ZeroLossGuard 비상 청산 감지 ───────────
            # (지연 제거: 비상 청산 감지 직전 실시간 마진/손익 재계산)
            margin_haircut = 2.0 if (HARDENED_STRESS_MODE and iv_explosion_active) else 1.0
            used_margin, margin_ratio = _recalc_margin(portfolio_options, current_position_qty, current_price, current_capital, margin_haircut)
            
            if autobot_active and emergency_cooldown_ticks == 0 and (margin_ratio > MARGIN_LIQUIDATION_THRESHOLD or total_equity < (daily_hwm * DAILY_DRAWDOWN_THRESHOLD)):
                if len(portfolio_options) > 0 or current_position_qty != 0:
                    logger.warning("🚨 [EMERGENCY PROTECTION] MarginDietGuard/ZeroLossGuard 트리거! 위험 매도/선물 포지션 비상 청산 집행 (Track 1 테일 보험 제외).")
                    guard_trigger_count += 1
                    emergency_cooldown_ticks = 15
                    
                    liq_fee = 0.0
                    for pos in portfolio_options:
                        strike_val = float(pos["strike"])
                        qty_val = int(pos["qty"])
                        liq_fee += strike_val * qty_val * OPTIONS_MULTIPLIER * OPTIONS_FEE_RATE
                    
                    futures_liq_value = abs(current_position_qty) * current_price * FUTURES_MULTIPLIER
                    liq_fee += futures_liq_value * FUTURES_FEE_RATE
                    
                    calculated_fee += liq_fee
                    
                    # 🛡️ 양매수를 기본으로 하는 모든 롱 옵션(BUY) 포지션은 증거금을 발생시키지 않으므로 절대로 지우지 않고 100% 보존!
                    t1_long_buys = [p for p in portfolio_options if p.get("activeStrategy") == "Track1" and p.get("side") == "BUY"]
                    protected_long_buys = [p for p in portfolio_options if p.get("side") == "BUY"]
                    portfolio_options = protected_long_buys
                    current_position_qty = 0
                    
                    # 만약 t1_long_buys가 전혀 없으면 즉시 넓은 양매수 재건!
                    if not t1_long_buys and track1:
                        rebuild_sigs = track1.on_market_open(current_price)
                        for sig in rebuild_sigs:
                            if sig.get("action") == "TAIL_DEFENSE_BUILD":
                                portfolio_options.append({"type": "CALL", "side": "BUY", "strike": sig.get("call_strike"), "price": 1.50, "qty": BASE_TRACK1_QTY, "activeStrategy": "Track1", "tag_id": "TAIL"})
                                portfolio_options.append({"type": "PUT", "side": "BUY", "strike": sig.get("put_strike"), "price": 1.50, "qty": BASE_TRACK1_QTY, "activeStrategy": "Track1", "tag_id": "TAIL"})
                    
                    # 🛡️ 청산 후 재진입 가능하도록 전략 상태 초기화
                    if track2:
                        track2.trap_state["is_active"] = False
                    if track4:
                        track4.scalp_state["is_active"] = False


            # ── 10.2.2 [NEW] 포트폴리오 넷 델타(Net Delta) 산출 ──
            current_portfolio_delta = 0.0
            if autobot_active:
                for pos in portfolio_options:
                    p_qty = max(0, int(pos.get("qty", 0)))
                    p_type = pos.get("type", "CALL")
                    p_side = pos.get("side", "BUY")
                    if p_type == "CALL":
                        delta_contrib = 0.5 if p_side == "BUY" else -0.5
                    else: # PUT
                        delta_contrib = -0.5 if p_side == "BUY" else 0.5
                    current_portfolio_delta += delta_contrib * p_qty
                
                # 선물 델타 (계약당 +1.0)
                safe_futures_pos = int(current_position_qty or 0)
                current_portfolio_delta += safe_futures_pos * 1.0
                current_portfolio_delta = round(float(current_portfolio_delta), 4)

            track3_override = False
            # ── 10.2.5 [NEW] Track 3: Statistical Arbitrage (1순위 제어권) - 활성화 ──
            if autobot_active and enabled_strategies.get("Track3", True):
                price_history_60.append(current_price)
                if len(price_history_60) == 60:
                    ma_60 = np.mean(price_history_60)
                    spread = current_price - ma_60
                    spread_history_120.append(float(spread))

                    
                    # 현재 전략 3 미실현 평가손익 연산
                    current_track3_pnl = 0.0
                    if track3.active_position == "SHORT_SPREAD":
                        current_track3_pnl = (track3_entry_price - current_price) * track3_entry_qty * FUTURES_MULTIPLIER
                    elif track3.active_position == "LONG_SPREAD":
                        current_track3_pnl = (current_price - track3_entry_price) * track3_entry_qty * FUTURES_MULTIPLIER

                    track3_status = track3.evaluate_arbitrage({
                        "spread_history": list(spread_history_120),
                        "total_fees": calculated_fee,
                        "current_pnl": current_track3_pnl
                    })
                    if track3_status.get("status") in ["ENTER_SHORT_SPREAD", "ENTER_LONG_SPREAD", "CLOSED"]:
                        track3_override = True
                        for signal in track3_status.get("signals", []):
                            action = signal.get("action")
                            t_type = signal.get("type")
                            
                            # 차익거래 비중 (자본의 30% 기반, 최소 자본금 가드 적용)
                            if total_equity < 15_000_000.0:
                                arb_qty = 0
                            else:
                                arb_qty = max(1, int(total_equity * 0.3 / 15_000_000.0))
                            
                            if arb_qty > 0:
                                if action == "EXECUTE_STAT_ARB":
                                    track3_entry_price = current_price
                                    track3_entry_qty = arb_qty
                                    
                                    # 진입 수수료 부과
                                    calculated_fee += arb_qty * current_price * FUTURES_MULTIPLIER * FUTURES_FEE_RATE
                                    
                                    track3_atm = round(current_price / 2.5) * 2.5
                                    if t_type == "SHORT_SPREAD":
                                        current_position_qty -= arb_qty
                                        track3_net_qty = -arb_qty
                                        # 선물 숏 + 합성 컨버전 옵션 레그 (Call BUY + Put SELL) 주입
                                        portfolio_options.append({"type": "FUTURES", "side": "SELL", "strike": 0, "price": round(current_price, 2), "qty": arb_qty, "activeStrategy": "Track3", "tag_id": "ARB"})
                                        portfolio_options.append({"type": "CALL", "side": "BUY", "strike": track3_atm, "price": 4.50, "qty": arb_qty, "activeStrategy": "Track3", "tag_id": "ARB"})
                                        portfolio_options.append({"type": "PUT", "side": "SELL", "strike": track3_atm, "price": 4.50, "qty": arb_qty, "activeStrategy": "Track3", "tag_id": "ARB"})
                                        logger.info("⚡ [TRACK 3 ARB] %s - 스프레드 매도(선물 숏 + 컨버전 옵션 1쌍) %d계약 진입! (진입가: %.2f)", signal.get('reason'), arb_qty, current_price)
                                    elif t_type == "LONG_SPREAD":
                                        current_position_qty += arb_qty
                                        track3_net_qty = arb_qty
                                        # 선물 롱 + 합성 리버설 옵션 레그 (Call SELL + Put BUY) 주입
                                        portfolio_options.append({"type": "FUTURES", "side": "BUY", "strike": 0, "price": round(current_price, 2), "qty": arb_qty, "activeStrategy": "Track3", "tag_id": "ARB"})
                                        portfolio_options.append({"type": "CALL", "side": "SELL", "strike": track3_atm, "price": 4.50, "qty": arb_qty, "activeStrategy": "Track3", "tag_id": "ARB"})
                                        portfolio_options.append({"type": "PUT", "side": "BUY", "strike": track3_atm, "price": 4.50, "qty": arb_qty, "activeStrategy": "Track3", "tag_id": "ARB"})
                                        logger.info("⚡ [TRACK 3 ARB] %s - 스프레드 매수(선물 롱 + 리버설 옵션 1쌍) %d계약 진입! (진입가: %.2f)", signal.get('reason'), arb_qty, current_price)
                                        
                                    trade_replay_analyzer.capture_trade_event(
                                        trade_type="ENTRY",
                                        track_name="Track3",
                                        side="SELL" if t_type == "SHORT_SPREAD" else "BUY",
                                        asset_type="FUTURES",
                                        price=current_price,
                                        qty=arb_qty,
                                        reason=signal.get('reason', 'Track 3 Arb Trigger'),
                                        realized_pnl=0.0,
                                        sensor_snapshot={"zScore": 1.8, "activeVol": round(active_vol, 2), "vpin": 0.15},
                                        state_snapshot={"capital": round(current_capital, 2), "equity": round(total_equity, 2), "marginRatio": round(margin_ratio, 1), "slippageMs": dynamic_slippage_ms},
                                        entry_reason="Track 3 Z-Score 1.8 합성 차익거래 시그널 발생",
                                        date_str=date_str
                                    )

                                    event_logs.append({
                                        "seq": seq, "date": date_str, "time": time_str,
                                        "event": f"Track 3 Arb ({t_type})",
                                        "details": f"{signal.get('reason')} / 진입가: {current_price:.2f}"
                                    })
                                elif action == "CLOSE_STAT_ARB":
                                    realized_pnl = 0.0
                                    # 청산 수수료 부과
                                    calculated_fee += track3_entry_qty * current_price * FUTURES_MULTIPLIER * FUTURES_FEE_RATE
                                    
                                    if t_type == "CLOSE_SHORT_SPREAD":
                                        current_position_qty += arb_qty # 숏 청산
                                        realized_pnl = (track3_entry_price - current_price) * track3_entry_qty * FUTURES_MULTIPLIER
                                        portfolio_options = [p for p in portfolio_options if not p.get("activeStrategy") == "Track3"]
                                        logger.info("💰 [TRACK 3 ARB CLOSE] %s - 숏 스프레드 및 옵션 차익 레그 전량 청산! (틱 마진 MTM에 기반영)", signal.get('reason'))
                                    elif t_type == "CLOSE_LONG_SPREAD":
                                        current_position_qty -= arb_qty # 롱 청산
                                        realized_pnl = (current_price - track3_entry_price) * track3_entry_qty * FUTURES_MULTIPLIER
                                        portfolio_options = [p for p in portfolio_options if not p.get("activeStrategy") == "Track3"]
                                        logger.info("💰 [TRACK 3 ARB CLOSE] %s - 롱 스프레드 및 옵션 차익 레그 전량 청산! (틱 마진 MTM에 기반영)", signal.get('reason'))
                                    
                                    trade_replay_analyzer.capture_trade_event(
                                        trade_type="EXIT",
                                        track_name="Track3",
                                        side="BUY" if t_type == "CLOSE_SHORT_SPREAD" else "SELL",
                                        asset_type="FUTURES",
                                        price=current_price,
                                        qty=arb_qty,
                                        reason=signal.get('reason', 'Track 3 Arb Close'),
                                        realized_pnl=realized_pnl,
                                        sensor_snapshot={"zScore": 0.2, "activeVol": round(active_vol, 2), "vpin": 0.15},
                                        state_snapshot={"capital": round(current_capital, 2), "equity": round(total_equity, 2), "marginRatio": round(margin_ratio, 1), "slippageMs": dynamic_slippage_ms},
                                        entry_reason="Track 3 Z-Score 1.8 차익거래 진입",
                                        date_str=date_str
                                    )
                                    
                                    pass
                                        
                                    # [CRITICAL FIX REVERT] MTM 미실현 손익이 0이 되므로 실현 손익을 자본에 가산해야 함!
                                    current_capital += realized_pnl
                                    track3_entry_qty = 0
                                    track3_net_qty = 0
                                    pnl_str = f"+{realized_pnl:,.0f}원" if realized_pnl >= 0 else f"-{abs(realized_pnl):,.0f}원"
                                    event_logs.append({
                                        "seq": seq, "date": date_str, "time": time_str,
                                        "event": f"Track 3 Arb Close ({t_type})",
                                        "details": f"{signal.get('reason')} / 실현손익: {pnl_str}"
                                    })

            # ── 10.2.1 [NEW] Track 5: Gap Protocol Mean Reversion Monitoring ──
            if autobot_active and enabled_strategies.get("Track5", True) and track5 and track5.gap_state["is_active"]:
                gap_eval = track5.evaluate_mean_reversion(current_price)
                if gap_eval.get("status") in ["PROFIT_TAKEN", "STOP_LOSS", "TIMEOUT", "TRAILING_PROFIT_LOCK", "LIQUIDITY_PROVISION_1", "LIQUIDITY_PROVISION_2"]:
                    for signal in gap_eval.get("signals", []):
                        action = signal.get("action")
                        reason = signal.get("reason")
                        pnl = signal.get("pnl", 0.0)
                        
                        is_partial = (action == "PROVIDE_LIQUIDITY_LIMIT")
                        close_qty = max(1, int(track5_active_qty * 0.4)) if is_partial and track5_active_qty > 1 else track5_active_qty
                        if close_qty <= 0:
                            continue
                            
                        # 청산 수수료 가산
                        calculated_fee += close_qty * current_price * FUTURES_MULTIPLIER * FUTURES_FEE_RATE
                        
                        # 선물 포지션 청산 (언와인드)
                        if track5.gap_state["direction"] == "SHORT":
                            current_position_qty += close_qty  # 숏 청산 -> 매수
                            
                            # 콜 펜스 원복 (최종 청산 시에만)
                            if not is_partial or close_qty == track5_active_qty:
                                for pos in portfolio_options:
                                    if pos.get("type") == "CALL" and pos.get("side") == "SELL":
                                        pos["strike"] += track5.fence_compress_pt
                                        logger.info("🕸️ [TRACK 5 FENCE] 숏 청산에 따른 콜 가두리 펜스 원복! 행사 변경: %.2f", pos["strike"])
                        else:
                            current_position_qty -= close_qty  # 롱 청산 -> 매도
                            
                            # 풋 펜스 원복 (최종 청산 시에만)
                            if not is_partial or close_qty == track5_active_qty:
                                for pos in portfolio_options:
                                    if pos.get("type") == "PUT" and pos.get("side") == "SELL":
                                        pos["strike"] -= track5.fence_compress_pt
                                        logger.info("🕸️ [TRACK 5 FENCE] 롱 청산에 따른 풋 가두리 펜스 원복! 행사 변경: %.2f", pos["strike"])
                            
                        realized_pnl = pnl * close_qty * FUTURES_MULTIPLIER
                        strategy_pnl_tracker["Track5"] += realized_pnl
                        
                        # [SELF-FUNDING] 실현손익을 일일 마찰비용에서 탕감(비용 차감)
                        if realized_pnl > 0:
                            daily_friction_cost = max(0.0, daily_friction_cost - realized_pnl)
                            logger.info("💰 [SELF-FUNDING] Gap Protocol 수익 ₩%s으로 일일 헤지 마찰비용 탕감 완료 (남은 마찰비용: ₩%s)", f"{realized_pnl:,.0f}", f"{daily_friction_cost:,.0f}")
                            
                            pass
                        
                        pnl_fmt = f"+{realized_pnl:,.0f}원" if realized_pnl >= 0 else f"-{abs(realized_pnl):,.0f}원"
                        logger.info("💰 [TRACK 5 GAP CLOSE] %s | 실현손익: %s", reason, pnl_fmt)
                        trade_replay_analyzer.capture_trade_event(
                            trade_type="EXIT",
                            track_name="Track5",
                            side="SELL" if track5.gap_state["direction"] == "LONG" else "BUY",
                            asset_type="FUTURES",
                            price=current_price,
                            qty=close_qty,
                            reason=reason,
                            realized_pnl=realized_pnl,
                            sensor_snapshot={"zScore": 1.5, "activeVol": active_vol, "vpin": 0.12},
                            state_snapshot={"capital": round(current_capital, 2), "equity": round(total_equity, 2), "marginRatio": round(margin_ratio, 1), "slippageMs": dynamic_slippage_ms},
                            entry_reason="시가 괴리(Z-Score) 회귀 저격 롱/숏 진입"
                        )
                        event_logs.append({
                            "seq": seq, "date": date_str, "time": time_str,
                            "event": "Track 5 Gap Close",
                            "details": f"{reason} / 실현손익: {pnl_fmt}"
                        })
                    track5_active_qty -= close_qty
                    if track5_active_qty <= 0:
                        track5_active_qty = 0
                        track5.reset_state()

            # ── 10.2.6 [NEW] Track 6 & 7: Daily & Weekly Tail Insurance Evaluation ──
            if autobot_active:
                time_str_val = calendar_sim.current_time.strftime("%H:%M:%S")
                # 월요일 개장 시점 판정
                is_new_week_start = (date_changed and calendar_sim.current_time.weekday() == 0)
                # 금요일 장마감 판정
                is_week_end = (calendar_sim.current_time.weekday() == 4)

                # 1) 전략 6 (데일리 보험 봇) 진입 평가 (데일리 센서 시그널 감시)
                if enabled_strategies.get("Track6", True) and track6 and not track6.insurance_state["is_active"]:
                    if daily_state.get("daily_vol_alert"):
                        t6_res = track6.evaluate_insurance_buy(
                            current_price=current_price,
                            active_vol=active_vol,
                            base_vol=BASE_VOLATILITY,
                            budget=total_equity * 0.001,
                            date_str=date_str
                        )
                    else:
                        t6_res = {"status": "STANDBY"}
                    if t6_res.get("status") == "TRIGGERED":
                        for signal in t6_res.get("signals", []):
                            cost = signal.get("cost", 0.0)
                            
                            # 포트폴리오에 데일리 보험 롱 스트랭글 추가
                            portfolio_options.append({
                                "type": "PUT", "side": "BUY", "strike": float(signal.get("put_strike")), "price": 0.50, "qty": int(signal.get("qty")),
                                "activeStrategy": "Track6", "is_insurance": True
                            })
                            portfolio_options.append({
                                "type": "CALL", "side": "BUY", "strike": float(signal.get("call_strike")), "price": 0.50, "qty": int(signal.get("qty")),
                                "activeStrategy": "Track6", "is_insurance": True
                            })
                            logger.warning("🚨 [DAILY INSURANCE BUY] 데일리 극외가 양매수(0DTE) 가입 완료! 지출예산: ₩%s", f"{cost:,.0f}")
                            trade_replay_analyzer.capture_trade_event(
                                trade_type="ENTRY",
                                track_name="Track6",
                                side="BUY",
                                asset_type="OPTIONS",
                                price=0.50,
                                qty=int(signal.get("qty")),
                                reason=signal.get('reason', '0DTE Insurance Buy'),
                                realized_pnl=0.0,
                                sensor_snapshot={"zScore": 0.0, "activeVol": round(active_vol, 2), "vpin": 0.12},
                                state_snapshot={"capital": round(current_capital, 2), "equity": round(total_equity, 2), "marginRatio": round(margin_ratio, 1), "slippageMs": dynamic_slippage_ms},
                                entry_reason="0DTE 데일리 양매수 헤지 가입",
                                date_str=date_str
                            )
                            event_logs.append({
                                "seq": seq, "date": date_str, "time": time_str,
                                "event": "Track 6 Daily Insurance Buy",
                                "details": f"{signal.get('reason')} / 지출예산: ₩{cost:,.0f}"
                            })

                # 2) 전략 6 (데일리 보험 봇) 강제 청산(15:15) 평가
                if track6 and track6.insurance_state["is_active"]:
                    t6_flat = track6.evaluate_expiry_cutoff(time_str_val)
                    if t6_flat.get("status") == "CUTOFF_TRIGGERED":
                        for signal in t6_flat.get("signals", []):
                            total_realized = 0.0
                            for pos in list(portfolio_options):
                                if pos.get("activeStrategy") == "Track6":
                                    k = float(pos["strike"])
                                    p_type = pos["type"]
                                    qty = int(pos["qty"])
                                    
                                    # 만기 내재가치 연산
                                    intrinsic = max(0.0, current_price - k) if p_type == "CALL" else max(0.0, k - current_price)
                                    realized = intrinsic * qty * OPTIONS_MULTIPLIER
                                    total_realized += realized
                                    
                                    try:
                                        portfolio_options.remove(pos)
                                    except ValueError:
                                        pass
                            
                            # 수수료 정산
                            calculated_fee += signal.get("qty") * 2 * current_price * OPTIONS_MULTIPLIER * OPTIONS_FEE_RATE
                            
                            # 자본 정산 (이중계상 방지 롤백: 실현이익 가산)
                            current_capital += total_realized
                            net_profit = total_realized - track6.insurance_state["premium_spent"]
                            strategy_realized_pnl["Track6"] += net_profit  # ← strategy_pnl_tracker는 line 2711에서 자동 계산
                            
                            logger.warning("💰 [DAILY INSURANCE CUTOFF] 15:15 데일리 보험 정산 청산 완료! (정산금액: ₩%s, 순손익: ₩%s)", f"{total_realized:,.0f}", f"{net_profit:,.0f}")
                            trade_replay_analyzer.capture_trade_event(
                                trade_type="EXIT",
                                track_name="Track6",
                                side="SELL",
                                asset_type="OPTIONS",
                                price=current_price,
                                qty=signal.get("qty", 1),
                                reason="15:15 데일리 만기 강제 정산",
                                realized_pnl=net_profit,
                                sensor_snapshot={"zScore": 0.0, "activeVol": round(active_vol, 2), "vpin": 0.12},
                                state_snapshot={"capital": round(current_capital, 2), "equity": round(total_equity, 2), "marginRatio": round(margin_ratio, 1), "slippageMs": dynamic_slippage_ms},
                                entry_reason="0DTE 데일리 극외가 양매수 가입",
                                date_str=date_str
                            )
                            pnl_fmt = f"+{total_realized:,.0f}원" if total_realized >= 0 else f"-{abs(total_realized):,.0f}원"
                            event_logs.append({
                                "seq": seq, "date": date_str, "time": time_str,
                                "event": "Track 6 Daily Insurance Close",
                                "details": f"만기 강제청산 실행 / 정산이익: {pnl_fmt}"
                            })

                # 3) 전략 7 (위클리 보험 봇) 진입 평가 (위클리 센서 시그널 감시)
                if enabled_strategies.get("Track7", True) and track7 and not track7.insurance_state["is_active"]:
                    if weekly_state.get("weekly_entry_ready"):
                        t7_res = track7.evaluate_insurance_buy(
                            current_price=current_price,
                            budget=total_equity * 0.02,
                            date_str=date_str,
                            is_new_week_start=is_new_week_start,
                            active_vol=active_vol
                        )
                    else:
                        t7_res = {"status": "STANDBY"}
                    if t7_res.get("status") == "TRIGGERED":
                        for signal in t7_res.get("signals", []):
                            cost = signal.get("cost", 0.0)
                            
                            # 포트폴리오에 위클리 보험 롱 스트랭글 추가
                            portfolio_options.append({
                                "type": "PUT", "side": "BUY", "strike": float(signal.get("put_strike")), "price": 0.70, "qty": int(signal.get("qty")),
                                "activeStrategy": "Track7", "is_insurance": True
                            })
                            portfolio_options.append({
                                "type": "CALL", "side": "BUY", "strike": float(signal.get("call_strike")), "price": 0.70, "qty": int(signal.get("qty")),
                                "activeStrategy": "Track7", "is_insurance": True
                            })
                            logger.warning("🚨 [WEEKLY INSURANCE BUY] 위클리 극외가 양매수 가입 완료! 지출예산: ₩%s", f"{cost:,.0f}")
                            trade_replay_analyzer.capture_trade_event(
                                trade_type="ENTRY",
                                track_name="Track7",
                                side="BUY",
                                asset_type="OPTIONS",
                                price=0.70,
                                qty=int(signal.get("qty")),
                                reason=signal.get('reason', 'Weekly Insurance Buy'),
                                realized_pnl=0.0,
                                sensor_snapshot={"zScore": 0.0, "activeVol": round(active_vol, 2), "vpin": 0.12},
                                state_snapshot={"capital": round(current_capital, 2), "equity": round(total_equity, 2), "marginRatio": round(margin_ratio, 1), "slippageMs": dynamic_slippage_ms},
                                entry_reason="주간 테일 헤지 극외가 양매수 가입",
                                date_str=date_str
                            )
                            event_logs.append({
                                "seq": seq, "date": date_str, "time": time_str,
                                "event": "Track 7 Weekly Insurance Buy",
                                "details": f"{signal.get('reason')} / 지출예산: ₩{cost:,.0f}"
                            })

                # 4) 전략 7 (위클리 보험 봇) 동적 장중 익절 및 만기 강제 청산(금요일 15:15) 평가
                if track7 and track7.insurance_state["is_active"]:
                    t7_tp = track7.evaluate_take_profit(current_price)
                    if t7_tp.get("status") == "PROFIT_TAKEN":
                        for signal in t7_tp.get("signals", []):
                            realized_amount = signal.get("realized_amount", 0.0)
                            for pos in list(portfolio_options):
                                if pos.get("activeStrategy") == "Track7":
                                    try:
                                        portfolio_options.remove(pos)
                                    except ValueError:
                                        pass
                            # 이중계상 방지 롤백: 실현이익 가산
                            current_capital += realized_amount
                            net_profit = realized_amount - track7.insurance_state.get("premium_spent", 350000.0)
                            strategy_realized_pnl["Track7"] += net_profit  # ← 이중계상 방지: tracker는 line 2711에서 자동 계산
                            logger.warning("🎉 [WEEKLY INSURANCE PROFIT REALIZATION] 위클리 옵션 동적 익절 청산 완료! (실현이익: ₩%s, 순손익: ₩%s)", f"{realized_amount:,.0f}", f"{net_profit:,.0f}")
                            trade_replay_analyzer.capture_trade_event(
                                trade_type="EXIT",
                                track_name="Track7",
                                side="SELL",
                                asset_type="OPTIONS",
                                price=current_price,
                                qty=1,
                                reason="위클리 옵션 평가이익 150% 동적 익절 청산",
                                realized_pnl=net_profit,
                                sensor_snapshot={"zScore": 0.0, "activeVol": round(active_vol, 2), "vpin": 0.12},
                                state_snapshot={"capital": round(current_capital, 2), "equity": round(total_equity, 2), "marginRatio": round(margin_ratio, 1), "slippageMs": dynamic_slippage_ms},
                                entry_reason="주간 테일 헤지 극외가 양매수 가입",
                                date_str=date_str
                            )
                            realized_fmt = f"+{realized_amount:,.0f}원" if realized_amount >= 0 else f"-{abs(realized_amount):,.0f}원"
                            net_fmt = f"+{net_profit:,.0f}원" if net_profit >= 0 else f"-{abs(net_profit):,.0f}원"
                            event_logs.append({
                                "seq": seq, "date": date_str, "time": time_str,
                                "event": "Track 7 Weekly Insurance Profit Realization",
                                "details": f"동적 장중 익절 성공! 실현이익: {realized_fmt} (순손익: {net_fmt})"
                            })
                    else:
                        t7_flat = track7.evaluate_expiry_cutoff(time_str_val, is_week_end)
                        if t7_flat.get("status") == "CUTOFF_TRIGGERED":
                            for signal in t7_flat.get("signals", []):
                                total_realized = 0.0
                                for pos in list(portfolio_options):
                                    if pos.get("activeStrategy") == "Track7":
                                        k = float(pos["strike"])
                                        p_type = pos["type"]
                                        qty = int(pos["qty"])
                                        
                                        # 만기 내재가치 연산
                                        intrinsic = max(0.0, current_price - k) if p_type == "CALL" else max(0.0, k - current_price)
                                        realized = intrinsic * qty * OPTIONS_MULTIPLIER
                                        total_realized += realized
                                        
                                        try:
                                            portfolio_options.remove(pos)
                                        except ValueError:
                                            pass

                            
                            # 수수료 정산
                            calculated_fee += signal.get("qty") * 2 * current_price * OPTIONS_MULTIPLIER * OPTIONS_FEE_RATE
                            
                            # 자본 정산 (이중계상 방지 롤백: 실현이익 가산)
                            current_capital += total_realized
                            net_profit = total_realized - track7.insurance_state["premium_spent"]
                            strategy_realized_pnl["Track7"] += net_profit  # ← tracker는 line 2711에서 자동 계산
                            
                            logger.warning("💰 [WEEKLY INSURANCE CUTOFF] 15:15 위클리 보험 정산 청산 완료! (정산금액: ₩%s, 순손익: ₩%s)", f"{total_realized:,.0f}", f"{net_profit:,.0f}")
                            pnl_fmt = f"+{total_realized:,.0f}원" if total_realized >= 0 else f"-{abs(total_realized):,.0f}원"
                            event_logs.append({
                                "seq": seq, "date": date_str, "time": time_str,
                                "event": "Track 7 Weekly Insurance Close",
                                "details": f"만기 강제청산 실행 / 정산이익: {pnl_fmt}"
                            })

                # 5) [NEW] 전략 8 (월간 넓은 양매수 봇) 진입 평가
                if enabled_strategies.get("Track8", True) and track8 and not track8.strangle_state["is_active"]:
                    t8_res = track8.evaluate_entry(
                        dte=simulated_days_to_expiry,
                        budget=total_equity * 0.050,
                        current_price=current_price,
                        current_regime=current_regime,
                        date_str=date_str
                    )
                    if t8_res.get("status") == "TRIGGERED":
                        for signal in t8_res.get("signals", []):
                            cost = signal.get("cost", 0.0)
                            
                            # 포트폴리오에 월간 보험 풋 편향 외가격 롱 스트랭글 구축
                            portfolio_options.append({
                                "type": "PUT", "side": "BUY", "strike": float(signal.get("put_strike")), "price": 1.50, "qty": int(signal.get("qty_put")),
                                "activeStrategy": "Track8", "is_insurance": True
                            })
                            portfolio_options.append({
                                "type": "CALL", "side": "BUY", "strike": float(signal.get("call_strike")), "price": 1.20, "qty": int(signal.get("qty_call")),
                                "activeStrategy": "Track8", "is_insurance": True
                            })
                            event_logs.append({
                                "seq": seq, "date": date_str, "time": time_str,
                                "event": "Track 8 Monthly Strangle Buy",
                                "details": f"{signal.get('reason')} / 지출예산: ₩{cost:,.0f}"
                            })

                # 6) [NEW] 전략 8 (월간 넓은 양매수 봇) 만기 D-3 출구 전략 평가
                if track8 and track8.strangle_state["is_active"]:
                    t8_flat = track8.evaluate_expiry_cutoff(simulated_days_to_expiry)
                    if t8_flat.get("status") == "CUTOFF_TRIGGERED":
                        for signal in t8_flat.get("signals", []):
                            total_realized = 0.0
                            for pos in list(portfolio_options):
                                if pos.get("activeStrategy") == "Track8":
                                    k = float(pos["strike"])
                                    p_type = pos["type"]
                                    qty = int(pos["qty"])
                                    
                                    # 만기 가상 내재가치 정산
                                    intrinsic = max(0.0, current_price - k) if p_type == "CALL" else max(0.0, k - current_price)
                                    realized = intrinsic * qty * OPTIONS_MULTIPLIER
                                    total_realized += realized
                                    
                                    try:
                                        portfolio_options.remove(pos)
                                    except ValueError:
                                        pass
                            # 수수료 차감
                            calculated_fee += (signal.get("qty_call") + signal.get("qty_put")) * current_price * OPTIONS_MULTIPLIER * OPTIONS_FEE_RATE
                            # 자본에 정산금 회수 적용 (이중계상 방지 롤백: 실현이익 가산)
                            current_capital += total_realized
                            net_profit = total_realized - signal.get("premium_spent")
                            strategy_realized_pnl["Track8"] += net_profit  # ← 기존 미갱신 버그 수정: tracker는 line 2711에서 자동 계산
                            pnl_str = f"+{total_realized:,.0f}원" if total_realized >= 0 else f"-{abs(total_realized):,.0f}원"
                            event_logs.append({
                                 "seq": seq, "date": date_str, "time": time_str,
                                 "event": "Track 8 Monthly Strangle Cutoff",
                                 "details": f"D-3 강제 청산 집행 / 정산회수: {pnl_str}"
                            })

            # ── 10.3 [NEW] Track 1: Advanced Dual-Side Dynamic Strangle & Trend Alpha ──
            t1_has_pos = any(p.get("activeStrategy") == "Track1" for p in portfolio_options)
            t1_enabled = enabled_strategies.get("Track1", True)
            if autobot_active and not track3_override and (t1_enabled or t1_has_pos):
                # 1) 가상의 market_data (지표 필터 및 Whipsaw 방어막 시간 정보) 조립
                mock_market_data = {
                    "vkospi_expanding": active_vol > BASE_VOLATILITY * 1.1,
                    "is_candle_closed": True,  # 모의 환경이므로 항상 봉마감으로 간주
                    "delta_threshold_met": True,
                    "momentum_confirmed": current_regime in ["NORMAL", "HIGH_VOL", "CIRCUIT_BREAKER"],
                    "current_portfolio_delta": current_portfolio_delta,
                    "date_str": date_str,
                    "timestamp": calendar_sim.current_time.timestamp()
                }
                
                # 2) 전략 평가 (evaluate_strategy)
                current_atm = round(current_price / 2.5) * 2.5
                
                # 🛡️ [TRACK 1] 신규 상시 억제막 구축은 t1_enabled 일 때만 실행 (토글 OFF 시 신규 진입만 차단)
                if t1_enabled:
                    t1_buys = [p for p in portfolio_options if p.get("activeStrategy") == "Track1" and p.get("side") == "BUY"]
                    if not t1_buys and track1:
                        call_k = round((current_price + 7.5) / 2.5) * 2.5
                        put_k = round((current_price - 7.5) / 2.5) * 2.5
                        portfolio_options.append({"type": "CALL", "side": "BUY", "strike": call_k, "price": 1.50, "qty": BASE_TRACK1_QTY, "activeStrategy": "Track1", "tag_id": "TAIL"})
                        portfolio_options.append({"type": "PUT", "side": "BUY", "strike": put_k, "price": 1.50, "qty": BASE_TRACK1_QTY, "activeStrategy": "Track1", "tag_id": "TAIL"})
                        logger.info("🛡️ [TRACK 1] 넓은 양매수(CALL %s / PUT %s) 상시 보유 상태 재구축 완료!", call_k, put_k)

                    t1_sells = [p for p in portfolio_options if p.get("activeStrategy") == "Track1" and p.get("side") == "SELL"]
                    if not t1_sells and track1:
                        put_fence_k = round((current_price - 7.5) / 2.5) * 2.5
                        portfolio_options.append({"type": "PUT", "side": "SELL", "strike": put_fence_k, "price": 2.00, "qty": BASE_TRACK1_QTY, "activeStrategy": "Track1", "tag_id": 1})
                        logger.info("🚧 [TRACK 1] 풋 가두리 매도 (행사가: %s) 상시 보유 상태 재구축 완료!", put_fence_k)

                eval_result = track1.evaluate_strategy(
                    current_underlying=current_price,
                    current_atm=current_atm,
                    market_data=mock_market_data
                )
                
                # 3) 반환된 Signal 처리 (기존 포지션의 헷지, 언와인드, FLATTEN 등 리스크 방어로직은 항상 작동)
                for signal in eval_result.get("signals", []):
                    action = signal.get("action")
                    
                    if action == "TAIL_DEFENSE_BUILD" and t1_enabled:
                        call_k = signal.get("call_strike")
                        put_k = signal.get("put_strike")
                        qty_val = signal.get("qty", BASE_TRACK1_QTY)
                        portfolio_options.append({"type": "CALL", "side": "BUY", "strike": call_k, "price": 1.50, "qty": qty_val, "activeStrategy": "Track1", "tag_id": "TAIL"})
                        portfolio_options.append({"type": "PUT", "side": "BUY", "strike": put_k, "price": 1.50, "qty": qty_val, "activeStrategy": "Track1", "tag_id": "TAIL"})
                        logger.info("🛡️ [TRACK 1] 테일 방어 양매수 구축 완료")
                        
                    elif action == "FENCE_BUILD" and t1_enabled:
                        opt_type = signal.get("type")
                        opt_strike = signal.get("strike")
                        tag_id = signal.get("tag_id")
                        qty_val = signal.get("qty", BASE_TRACK1_QTY)
                        portfolio_options.append({"type": opt_type, "side": "SELL", "strike": opt_strike, "price": 2.00, "qty": qty_val, "activeStrategy": "Track1", "tag_id": tag_id})
                        logger.info("🚧 [TRACK 1] 신규 %s 가두리(매도) 형성 (꼬리표 #%s)", opt_type, tag_id)
                        
                    elif action == "FENCE_CLEAR":
                        tag_id = signal.get("tag_id")
                        portfolio_options = [p for p in portfolio_options if not (p.get("activeStrategy") == "Track1" and p.get("tag_id") == tag_id)]
                        logger.info("🔄 [TRACK 1] 꼬리표 #%s 순환 청산 완료 (이익 확정)", tag_id)
                        
                    elif action == "FUTURES_ORDER":
                        order_side = signal.get("type")
                        qty_val = signal.get("qty", BASE_TRACK1_QTY)
                        if order_side == "BUY":
                            current_position_qty += qty_val
                        else:
                            current_position_qty -= qty_val
                            
                        portfolio_options.append({"type": "FUTURES", "side": order_side, "strike": 0, "price": current_price, "qty": qty_val, "activeStrategy": "Track1", "tag_id": "HEDGE"})
                            
                        logger.warning("🚨 [TRACK 1] %s - 휩소 방어용 선물 %s %d계약 투입!", signal.get('reason'), order_side, qty_val)
                        event_logs.append({
                            "seq": seq, "date": date_str, "time": time_str,
                            "event": f"Track 1 Hedge ({order_side})",
                            "details": signal.get("reason")
                        })
                            
                    elif action == "FUTURES_UNWIND":
                        order_side = signal.get("type")
                        qty_val = 1
                        if order_side == "BUY":
                            current_position_qty += qty_val
                        else:
                            current_position_qty -= qty_val
                            
                        portfolio_options = [p for p in portfolio_options if not (p.get("activeStrategy") == "Track1" and p.get("type") == "FUTURES")]
                            
                        logger.info("✅ [TRACK 1] %s - 1.5pt 반전 감지로 선물 헷지 언와인드", signal.get('reason'))
                        event_logs.append({
                            "seq": seq, "date": date_str, "time": time_str,
                            "event": "Track 1 Unwind",
                            "details": signal.get("reason")
                        })
                        
                    elif action == "FLATTEN_ALL":
                        hedge_side = track1.active_hedge
                        if hedge_side == "BUY":
                            current_position_qty -= 1
                        elif hedge_side == "SELL":
                            current_position_qty += 1
                            
                        portfolio_options = [p for p in portfolio_options if not (p.get("activeStrategy") == "Track1" and (p.get("side") == "SELL" or p.get("type") == "FUTURES"))]
                        
                        logger.critical("💥 [TRACK 1 FLATTEN] 100%% 격돌! 선물 헷지 및 가두리 포지션 전량 피난 청산 완료.")
                        event_logs.append({
                            "seq": seq, "date": date_str, "time": time_str,
                            "event": "Track 1 FLATTEN",
                            "details": signal.get("reason")
                        })

            # ── 10.4 [NEW] Track 2: Asymmetric Trap & Volatility Funding ──
            t2_has_pos = any(p.get("activeStrategy") == "Track2" for p in portfolio_options)
            t2_enabled = enabled_strategies.get("Track2", True)
            if autobot_active and not track3_override and (t2_enabled or t2_has_pos):
                current_atm = round(current_price / 2.5) * 2.5
                
                # 신규 트랩 설치는 t2_enabled 및 D-4(4.0) 이상 일 때만 실행
                if t2_enabled and simulated_days_to_expiry >= 4.0 and not track2.trap_state["is_active"]:
                    trap_eval = track2.build_asymmetric_trap(current_atm)
                    if trap_eval.get("status") == "SUCCESS":
                        trap_qty = 0 if total_equity < 15_000_000.0 else max(1, int(total_equity / 30_000_000.0))
                        if trap_qty > 0:
                            for signal in trap_eval.get("signals", []):
                                action = signal.get("action")
                                if action == "EXECUTE_SHORT_LEG":
                                    strikes = signal.get("strikes", {})
                                    for opt_type, strike_val in strikes.items():
                                        portfolio_options.append({
                                            "type": opt_type.upper(), "side": "SELL",
                                            "strike": strike_val, "price": 0.50, "qty": trap_qty,
                                            "activeStrategy": "Track2"
                                        })
                                    logger.info("🕸️ [TRACK 2 FUNDING] 외가격 매도(보험료 수취) 세팅 완료 - %s", strikes)
                                elif action == "EXECUTE_LONG_TRAP_LEG":
                                    strikes = signal.get("strikes", {})
                                    for opt_type, strike_val in strikes.items():
                                        portfolio_options.append({
                                            "type": opt_type.upper(), "side": "BUY",
                                            "strike": strike_val, "price": 1.20, "qty": trap_qty,
                                            "activeStrategy": "Track2"
                                        })
                                    logger.info("🕸️ [TRACK 2 TRAP] 비대칭 양매수 함정 세팅 완료 - %s", strikes)
                                    
                            event_logs.append({
                                "seq": seq, "date": date_str, "time": time_str,
                                "event": "Track 2 함정(Trap) 구축 완료",
                                "details": f"ATM: {current_atm}, 설치 수량: {trap_qty}계약"
                            })
                
                if track2_unwind_cooldown_ticks > 0:
                    track2_unwind_cooldown_ticks -= 1

                # 기존 트랩 포지션의 선물 헷지 및 방어로직은 t2_enabled와 무관하게 항상 동작
                track2_status = track2.evaluate_trap_status(current_price)
                if track2_status.get("status") == "HEDGE_TRIGGERED":
                    for signal in track2_status.get("signals", []):
                        action = signal.get("action")
                        if action == "FUTURES_ORDER":
                            if track2_unwind_cooldown_ticks > 0:
                                pass
                            else:
                                order_side = signal.get("type")
                                qty_val = 1
                                if order_side == "BUY":
                                    current_position_qty += qty_val
                                else:
                                    current_position_qty -= qty_val
                                
                                logger.info("🛡️ [TRACK 2 HEDGE] %s - 방어 선물 %s %d계약 진입!", signal.get('reason'), order_side, qty_val)
                                event_logs.append({
                                    "seq": seq, "date": date_str, "time": time_str,
                                    "event": f"Track 2 Hedge ({order_side})",
                                    "details": signal.get("reason")
                                })
                        elif action == "FUTURES_UNWIND":
                            track2_unwind_cooldown_ticks = 5
                            target = signal.get("target")
                            qty_val = 1
                            if target == "PUT_SIDE":
                                current_position_qty += qty_val
                                logger.info("🛡️ [TRACK 2 UNWIND] %s - 풋 방어 헷지 매수(청산)!", signal.get('reason'))
                            else:
                                current_position_qty -= qty_val
                                logger.info("🛡️ [TRACK 2 UNWIND] %s - 콜 방어 헷지 매도(청산)!", signal.get('reason'))
                            
                            event_logs.append({
                                "seq": seq, "date": date_str, "time": time_str,
                                "event": "Track 2 Unwind",
                                "details": signal.get("reason")
                            })

                elif track2_status.get("status") == "MONITORING_TRAP":
                    pass

            # ── 10.5 [NEW] Track 4: Smart Gamma Scalping & D-3 Attack Mode ──
            t4_has_pos = any(p.get("activeStrategy") == "Track4" for p in portfolio_options)
            t4_enabled = enabled_strategies.get("Track4", True)
            
            # 🛡️ [TRACK 4 STATE SYNC] 계좌 내 Track4 롱 양매수 포지션 존재 시 scalp_state 자동 동기화 (중복 진입 방지)
            if t4_has_pos and track4:
                track4.scalp_state["is_active"] = True

            if autobot_active and not track3_override and (t4_enabled or t4_has_pos):
                current_atm = round(current_price / 2.5) * 2.5
                
                # 신규 베이스캠프 양매수 구축은 계좌 내 미보유(not t4_has_pos) 및 상태 미작동 시에만 1회 실행
                if t4_enabled and simulated_days_to_expiry >= 4.0 and (not t4_has_pos) and (not track4.scalp_state.get("is_active")):
                    gamma_qty = 0 if total_equity < 15_000_000.0 else max(1, int(total_equity / 30_000_000.0))
                    if gamma_qty > 0:
                        track4.scalp_state["is_active"] = True
                        portfolio_options.append({
                            "type": "CALL", "side": "BUY", "strike": current_atm, "price": 4.50, "qty": gamma_qty, "activeStrategy": "Track4"
                        })
                        portfolio_options.append({
                            "type": "PUT", "side": "BUY", "strike": current_atm, "price": 4.50, "qty": gamma_qty, "activeStrategy": "Track4"
                        })
                        logger.info("🎯 [TRACK 4 BASECAMP] ATM 스트래들 양매수(콜/풋) 베이스캠프 구축 완료! (수량: %d)", gamma_qty)
                        event_logs.append({
                            "seq": seq, "date": date_str, "time": time_str,
                            "event": "Track 4 Basecamp", "details": f"ATM: {current_atm} 양매수 진입"
                        })
                
                # 기존 포지션의 감마 스캘핑 리밸런싱은 t4_enabled와 무관하게 계속 실행
                if track4.scalp_state.get("is_active"):
                    track4_status = track4.evaluate_scalping_rebalance(mock_market_data, simulated_days_to_expiry)
                    for signal in track4_status.get("signals", []):
                        action = signal.get("action")
                        
                        if action == "EXECUTE_SCALP_HEDGE":
                            order_side = signal.get("type")
                            if order_side == "BUY":
                                current_position_qty += 1
                            else:
                                current_position_qty -= 1
                            logger.info("⚔️ [TRACK 4 SCALP] %s - 델타 헷지 선물 %s 1계약 진입!", signal.get('reason'), order_side)
                            
                        elif action == "UNWIND_SCALP_FUTURES":
                            # 스캘핑용으로 쌓았던 선물 수량 청산 (델타 리셋)
                            target_qty = signal.get("target_qty", 0)
                            current_position_qty -= target_qty 
                            logger.critical("🔥 [TRACK 4 ATTACK MODE] %s - 감마 폭발 조준! 잔여 선물 헷지(%d계약) 전량 언와인딩!", signal.get('reason'), target_qty)
                            
                            # [NEW] 마스터 룰 4: 만기 감마 공격 모드 - 외가격 매도 전량 강제 청산
                            sell_positions = [p for p in portfolio_options if p.get("side") == "SELL"]
                            if sell_positions:
                                logger.critical("🔥 [MASTER RULE] 감마 공격 모드 스위칭! 시스템 내 모든 SELL(매도) 포지션 강제 청산(폭파) 진행!")
                                for p in sell_positions:
                                    try:
                                        portfolio_options.remove(p)
                                    except ValueError:
                                        pass
                                    # 수수료 정산
                                    close_fee = float(p.get("strike", 0)) * int(p.get("qty", 0)) * OPTIONS_MULTIPLIER * OPTIONS_FEE_RATE
                                    calculated_fee += close_fee
                                    
                            event_logs.append({
                                "seq": seq, "date": date_str, "time": time_str,
                                "event": "Track 4 Gamma Attack", "details": "스캘핑 종료 및 SELL 포지션 전량 폭파"
                            })


            # ── 11.0 OTM 보험 옵션 평가이익 수취(청산) 및 재진입 예약 ──
            # 🛡️ [Phase 1.3 BUG FIX] PUT/CALL 타입별 내재가치 공식 분기 추가
            for pos in list(portfolio_options):
                if not autobot_active:
                    continue
                if pos.get("is_insurance", False) and pos.get("side") == "BUY":
                    strike_val = float(pos["strike"])
                    qty_val = int(pos["qty"])
                    pos_type = pos.get("type", "PUT")

                    # PUT: 지수 하락 시 이익, CALL: 지수 상승 시 이익
                    if pos_type == "PUT":
                        intrinsic = max(0.0, strike_val - current_price)
                    elif pos_type == "CALL":
                        intrinsic = max(0.0, current_price - strike_val)
                    else:
                        continue  # 알 수 없는 타입 건너뜀

                    # 🛡️ [CRITICAL FIX] 조기 +0원 청산 차단: 내재가치가 최소 1.0pt (25만원) 이상 실제 유의미하게 발생 시에만 익절 청산!
                    trigger = intrinsic >= 1.0

                    if trigger:
                        # 1. 평가이익 계산 및 실현 (지수 기반 내재가치 정직 수취 — 이중계상 방지 롤백: 실현이익 가산)
                        realized_pnl = intrinsic * qty_val * OPTIONS_MULTIPLIER
                        current_capital += realized_pnl
                        # strategy_realized_pnl 누적 (activeStrategy로 Track 판별)
                        _ins_strat = pos.get("activeStrategy", "Track1")
                        _ins_key = next((k for k in strategy_realized_pnl if k.split(' ')[0] in _ins_strat), "Track1")
                        strategy_realized_pnl[_ins_key] += realized_pnl
                        
                        # 2. 보험 포지션 청산 (이익 수취 완료)
                        try:
                            portfolio_options.remove(pos)
                        except ValueError:
                            pass
                        
                        # 3. 당일 장마감 시 재가입하도록 플래그 세팅
                        insurance_active_this_month = False
                        insurance_reentry_needed_today = True
                        
                        logger.warning(
                            "🎉 [INSURANCE PROFIT REALIZATION] %s 보험 평가이익 수취 청산 완료! "
                            "이익 실현액: +₩%s. 오늘 장마감 전(15:15~15:20)에 신규 보험에 재가입합니다.",
                            pos_type, f"{realized_pnl:,.0f}"
                        )
                        pnl_fmt = f"+{realized_pnl:,.0f}원" if realized_pnl >= 0 else f"-{abs(realized_pnl):,.0f}원"
                        event_logs.append({
                            "seq": seq, "date": date_str, "time": time_str,
                            "event": f"보험 이익 수취 청산 ({pos_type})",
                            "details": f"Strike: {strike_val}, 실현이익: {pnl_fmt}"
                        })

            # ── 11. 이익 50% 적립 / 손실 완충 대칭 알고리즘 ─────────────
            dp = current_price - prev_price
            futures_pnl = dp * current_position_qty * FUTURES_MULTIPLIER

            options_pnl = 0.0
            for pos in portfolio_options:
                k = float(pos["strike"])
                side = pos["side"]
                p_type = pos["type"]
                qty = int(pos["qty"])
                
                try:
                    diff = current_price - k
                    diff_clamped = max(-50.0, min(50.0, diff))
                    delta_call = 1.0 / (1.0 + math.exp(-0.2 * diff_clamped))
                except Exception:
                    delta_call = 0.5
                
                delta = delta_call if p_type == "CALL" else (delta_call - 1.0)
                delta_sign = 1.0 if side == "BUY" else -1.0
                opt_delta_eff = delta_sign * delta
                
                tick_pnl = dp * opt_delta_eff * qty * OPTIONS_MULTIPLIER
                
                # [CRITICAL FIX] 횡보장 옵션 양매도의 핵심인 '시간 가치(Theta) 수취' 로직 도입
                # 매 틱(초)마다 옵션 매도자는 세타 이익을 수취하고 매수자는 프리미엄을 잃음.
                # (현실적 수치 조정: 틱당 너무 높으면 분당 수백만 원 돈복사 발생. 틱당 1.5원으로 안정화)
                theta_decay_per_tick = 1.5
                theta_pnl = theta_decay_per_tick * float(qty) * (1.0 if side == "SELL" else -1.0)
                tick_pnl += theta_pnl
                
                # 옵션 프리미엄 세타 차감 및 정직한 평가 손익 반영
                pass
                
                options_pnl += tick_pnl

            raw_pnl = futures_pnl + options_pnl
            net_pnl = raw_pnl - calculated_fee

            # ── 11.1 전략별 손익 및 스트레스 국면 손익 집계 ──────────────────
            # [CRITICAL FIX] 각 전략의 실시간 PnL = 확정 실현 손익(strategy_realized_pnl) + 보유 중인 포지션의 미실현 MTM 손익
            # 보유 물량이 없는 전략(Track 3 HOLD, Track 7 COMPLETED 등)은 MTM=0이 되어 손익 수치가 고정(정지)됩니다.
            strategy_mtm_tick: Dict[str, float] = {
                "Track1": 0.0, "Track2": 0.0,
                "Track3": 0.0, "Track4": 0.0,
                "Track5": 0.0,
                "Track6": 0.0,
                "Track7": 0.0,
                "Track8": 0.0
            }

            # (1) 보유 옵션 포지션의 실시간 MTM 손익을 소속 전략별로만 귀속
            if portfolio_options:
                per_option_pnl = options_pnl / len(portfolio_options)
                for pos in portfolio_options:
                    pos_strat = pos.get("activeStrategy", "Track1")
                    matched_key = "Track1"
                    for strat_k in strategy_mtm_tick.keys():
                        if strat_k.split(' ')[0] in pos_strat:
                            matched_key = strat_k
                            break

                    strategy_mtm_tick[matched_key] += per_option_pnl

            # (2) 선물 헷지 및 스캘핑 MTM 손익을 해당 주체 전략별로만 귀속
            if futures_pnl != 0:
                if track5_active_qty != 0:
                    strategy_mtm_tick["Track5"] += futures_pnl
                elif track3_net_qty != 0:
                    strategy_mtm_tick["Track3"] += futures_pnl
                else:
                    strategy_mtm_tick["Track1"] += futures_pnl * 0.70
                    strategy_mtm_tick["Track2"] += futures_pnl * 0.30

            # (3) 전략별 최종 PnL 갱신 (확정 실현 손익 + 보유 포지션 MTM)
            for strat_name in strategy_pnl_tracker.keys():
                strategy_pnl_tracker[strat_name] = strategy_realized_pnl[strat_name] + strategy_mtm_tick[strat_name]

            is_stress_active = (
                flash_crash_active or iv_explosion_active or circuit_breaker_active or 
                rejection_storm_active or liquidity_drought_active
            )
            if is_stress_active:
                for strat_name in strategy_stress_pnl.keys():
                    strategy_stress_pnl[strat_name] = strategy_pnl_tracker[strat_name]


            # ── [CRITICAL FIX] 이중 계상(Double Counting) 제거 및 지수 연동 정직 자산 계산 ──
            # current_capital은 청산 시점의 확정 실현 손익만 반영하며, 매 틱 MTM 손익은 total_equity에만 단 1회 가산됩니다.
            unrealized_mtm_pnl = futures_pnl + options_pnl
            total_equity = current_capital + accumulated_reserve + unrealized_mtm_pnl

            # ── 11.2 Daily HWM (High-Water Mark) 실시간 갱신 ──
            highest_equity_today = max(highest_equity_today, total_equity)
            daily_hwm = highest_equity_today

            # ── [CRITICAL FIX] 11.2.5 리스크 가드용 증거금/마진 재계산 (최신 틱 변동 반영) ──
            margin_haircut = 2.0 if (HARDENED_STRESS_MODE and iv_explosion_active) else 1.0
            used_margin, margin_ratio = _recalc_margin(portfolio_options, current_position_qty, current_price, current_capital, margin_haircut)

            # ── 11.3 3중 방어막 독트린 감시 및 락다운 집행 ──
            
            # [제3방어막] 최후의 절대 고정값: -75% 마진콜 방어선 절대 숏커버 락다운
            if total_equity < (initial_capital * ACCOUNT_KILL_SWITCH_THRESHOLD):
                logger.critical(
                    "🚨 [MARGNCALL KILL-SWITCH] 최후의 제3방어막 -75%% 마진콜 락다운 발동! "
                    "총자산(₩%s)이 원금 대비 25%% 미만으로 붕괴되었습니다. "
                    "보유 포지션 즉시 시장가 청산 및 프로그램 영구 셧다운.",
                    f"{total_equity:,.0f}"
                )
                portfolio_options.clear()
                current_position_qty = 0
                total_equity = current_capital + accumulated_reserve
                
                event_logs.append({
                    "seq": seq,
                    "date": date_str,
                    "time": time_str,
                    "event": "제3방어막 발동 (락다운)",
                    "details": f"자산: ₩{total_equity:,.0f} (원금대비 -75% 돌파)"
                })
                
                # 영구 종료 처리 (자동 재기동 루프 진입 차단)
                if shutdown_event is not None:
                    shutdown_event.set()
                return

            # 제1방어막 (15% Normal Limit) & 제2방어막 (40% Hard Limit) 감시
            # 평온한 장세(NORMAL/NEUTRAL) vs 스트레스 상황(HIGH_VOL/CIRCUIT_BREAKER 등)
            is_stress_active = (
                flash_crash_active or iv_explosion_active or circuit_breaker_active or 
                rejection_storm_active or liquidity_drought_active
            )
            limit_pct = 0.60 if is_stress_active else 0.70
            limit_name = "제2방어막 (40% Hard Limit)" if is_stress_active else "제1방어막 (30% Normal Limit)"
            limit_val = daily_hwm * limit_pct

            if total_equity < limit_val:
                logger.critical(
                    "🛑 [RISK ENGINE SHUTDOWN] %s 붕괴 감지 (총자산: ₩%s / 기준 HWM: ₩%s)! "
                    "즉시 전체 포지션 청산 후 세션 재기동을 집행합니다.",
                    limit_name, f"{total_equity:,.0f}", f"{daily_hwm:,.0f}"
                )
                
                event_logs.append({
                    "seq": seq,
                    "date": date_str,
                    "time": time_str,
                    "event": f"{limit_name} 발동 (리셋)",
                    "details": f"자산: ₩{total_equity:,.0f} / HWM: ₩{daily_hwm:,.0f}"
                })

                # 강제 일괄 청산
                portfolio_options.clear()
                current_position_qty = 0
                total_equity = current_capital + accumulated_reserve
                
                final_packet: Dict[str, Any] = {
                    "date":                  date_str,
                    "time":                  time_str,
                    "underlyingPrice":       round(current_price, 2),
                    "regime":                "CIRCUIT_BREAKER",
                    "bidAskSpread":          99.0,
                    "coord":                 {"x": seq, "y": round(total_equity, 2), "date": date_str},
                    "payoffCoords":          [],
                    "strategyWeights":       strategy_weights,
                    "capital":               round(current_capital, 2),
                    "reserve":               round(accumulated_reserve, 2),
                    "stressMode":            STRESS_MODE,
                    "hardenedMode":          HARDENED_STRESS_MODE,
                    "slippageMs":            0,
                    "slippageRate":          0.0,
                    "usedMargin":            0.0,
                    "marginRatio":           0.0,
                    "riskLevel":             "DANGER",
                    "activeStrategy":        active_strategy,
                    "tuningFactor":          0.1,
                    "tunedSlippage":         1000,
                    "daysToExpiry":          round(simulated_days_to_expiry, 2),
                    "circuitBreaker":        True,
                    "flashCrash":            False,
                    "ivExplosion":           False,
                    "rejectionStorm":        False,
                    "liquidityDrought":      False,
                    "ivSellBlocked":         False,
                    "simStartDateTime":      calendar_sim.start_datetime_str,
                    "simEndDateTime":        calendar_sim.expiry_datetime_str,
                    "realElapsedSecs":       int(time.time() - server_start_time),
                    "portfolioOptions":      [],
                    "futuresQty":            0,
                }
                session_telemetry.append(final_packet)
                
                # 자동 재기동 트리거
                risk_triggered_event.set()
                return

            # ── 12. 포지션 자연 반대매매 시뮬레이션 ─────────────────────
            # ── 13. 합성 옵션 페이오프 연산 (세션 기준 앵커 고정형 X축) ────────
            payoff_coords = []
            base_anchor = round(current_price / 5.0) * 5.0
            strike_range_start = base_anchor - 50.0
            strike_range_end   = base_anchor + 50.0
            strike = round(strike_range_start / 2.5) * 2.5

            while strike <= strike_range_end:
                total_pnl = 0.0
                for pos in portfolio_options:
                    p_type = pos.get("type")
                    if p_type not in ("CALL", "PUT"):
                        continue
                    k       = float(pos.get("strike", base_anchor))
                    premium = float(pos.get("entryPrice", pos.get("price", 0.0)))
                    qty     = int(pos.get("qty", 1))
                    side    = pos.get("side", "BUY")
                    
                    expiry_val = max(0.0, strike - k) if p_type == "CALL" else max(0.0, k - strike)
                    pnl = ((expiry_val - premium) if side == "BUY" else (premium - expiry_val)) * OPTIONS_MULTIPLIER * qty
                    total_pnl += pnl
                payoff_coords.append({"x": float(round(strike, 2)), "y": round(total_pnl, 2)})
                strike += 2.5

            # ── 14. 패킷 송신 ────────────────────────────────────────────
            # (루프 시작 시 계산된 used_margin 및 margin_ratio 값 재사용)

            coord_data: Dict[str, Any] = {
                "x": seq, 
                "y": round(total_equity, 2),
                "date": date_str,
                "dte": f"D-{int(simulated_days_to_expiry)}",
                "dayLabel": f"D-{int(simulated_days_to_expiry)} ({date_str[5:]})"
            }

            if order:
                coord_data["status"] = order["status"]
                coord_data["activeStrategy"] = order.get("activeStrategy", "")
                coord_data["type"] = order.get("type", "")
                coord_data["assetType"] = order.get("assetType", "")
                coord_data["price"] = order.get("price", 0.0)
                coord_data["qty"] = order.get("qty", 0)
                coord_data["fee"] = order.get("fee", 0.0)
                coord_data["time"] = order.get("time", "")

            # ── ⏱️ 매시간 손익률 & 월마감 손익률 연산 ─────────────────────
            curr_hour = calendar_sim.current_time.hour
            if last_tracked_hour == -1 or curr_hour != last_tracked_hour:
                last_tracked_hour = curr_hour
                hourly_start_equity = total_equity

            hourly_return = ((total_equity - hourly_start_equity) / hourly_start_equity * 100.0) if hourly_start_equity > 0 else 0.0
            monthly_return = ((total_equity - month_start_capital) / month_start_capital * 100.0) if month_start_capital > 0 else 0.0

            packet: Dict[str, Any] = {
                "sessionId":             SESSION_ID,
                "date":                  date_str,
                "time":                  time_str,
                "underlyingPrice":       round(current_price, 2),
                "regime":                current_regime,
                "bidAskSpread":          bid_ask_spread,
                "coord":                 coord_data,
                "payoffCoords":          payoff_coords,
                "strategyWeights":       strategy_weights,
                "strategyPnL":           strategy_pnl_tracker,
                "realizedPnl":           round(sum(strategy_realized_pnl.values()), 2),
                "unrealizedPnl":         round(total_equity - current_capital, 2),
                "hedgePnl":              round(strategy_pnl_tracker.get("Hedge", 0.0), 2),
                "netPnl":                 round(total_equity - initial_capital, 2),
                "capital":               round(current_capital, 2),

                "reserve":               round(accumulated_reserve, 2),
                "stressMode":            STRESS_MODE,
                "hardenedMode":          HARDENED_STRESS_MODE,
                "slippageMs":            dynamic_slippage_ms,
                "slippageRate":          dynamic_slippage_rate,
                "usedMargin":            round(used_margin, 2),
                "marginRatio":           round(margin_ratio, 1),
                "riskLevel":             risk_level,
                "activeStrategy":        active_strategy,
                "tuningFactor":          tuning_factor,
                "tunedSlippage":         tuned_slippage,
                "daysToExpiry":          round(simulated_days_to_expiry, 2),
                "autobotActive":         autobot_active,
                "restartCount":          restart_count,
                "isMarketOpenedToday":   is_market_opened_today,
                "replaySpeed":           "300x",
                # ── 🎬 Trade Replay & Decision Analyzer 월/일 계층 아카이빙 ──
                "tradeReplayList":       trade_replay_analyzer.get_recent_records(200),
                "tradeTreeArchive":      trade_replay_analyzer.get_tree_archive(),
                # ── 📈 매시간 & 월마감 손익률 ──
                "hourlyReturn":          round(hourly_return, 2),
                "monthlyReturn":         round(monthly_return, 2),
                "hourlyStartEquity":     round(hourly_start_equity, 2),
                "monthStartCapital":     round(month_start_capital, 2),
                # ── 극한 시나리오 상태 플래그 (프론트엔드 경보용) ──
                "circuitBreaker":        circuit_breaker_active,
                "flashCrash":            flash_crash_active,
                "ivExplosion":           iv_explosion_active,
                "rejectionStorm":        rejection_storm_active,
                "liquidityDrought":      liquidity_drought_active,
                "ivSellBlocked":         iv_sell_blocked,
                "simStartDateTime":      calendar_sim.start_datetime_str,
                "simEndDateTime":        calendar_sim.expiry_datetime_str,
                "realElapsedSecs":       int(time.time() - server_start_time),
                "is_market_open":        True,
                "noiseFilter":           is_noise_filter_standby,
                "portfolioOptions":      portfolio_options,
                "futuresQty":            int(current_position_qty - track3_net_qty),
                "frictionCost":          round(daily_friction_cost, 2),
                "budgetPool":            round(insurance_budget_pool, 2),
                "enabledStrategies":     enabled_strategies,
                "eventLogs":             event_logs[-30:],
            }

            if order:
                packet["order"] = order

            prev_price = current_price
            session_telemetry.append(packet)
            
            if connected_clients:
                msg = orjson.dumps(packet).decode('utf-8')
                asyncio.gather(*[client.send(msg) for client in connected_clients], return_exceptions=True)

            # ────────────────────────────────────────────────────────────
            # 🔥 [극한 시나리오 8] WebSocket 반복 단절 (비활성화됨)
            # 방어: ExecutionAgent.execute_order() 지수 백오프 + 고아 GC
            # ────────────────────────────────────────────────────────────
            # if STRESS_MODE and ws_disconnect_countdown <= 0:
            #     logger.warning("🔌 [WS DISCONNECT] 강제 연결 단절 주입! (고아 주문 발생 시나리오)")
            #     main_engine_broken = True
            #     ws_disconnect_countdown = random.randint(12000, 20000)
            #     if connected_clients:
            #         for client in list(connected_clients):
            #             try:
            #                 await client.close(3001, "Mock network partition")
            #             except Exception:
            #                 pass

    except asyncio.CancelledError:
        logger.info("시뮬레이션 루프 태스크가 안전하게 취소되었습니다.")
    except Exception as e:
        logger.error("시뮬레이션 루프 중 에러 발생: %s", e)


async def watchdog_daemon() -> None:
    """🛡️ HFT 헌법 5부: 외부 관측 데몬 (Watchdog Daemon)

    메인 HFT 연결이 예기치 않게 끊겨 'main_engine_broken' 상태가 되었을 때도,
    백그라운드에서 독립 생존하여 외부 가상 네이버금융 실시간 코스피200 인덱스 피드를 추적하고
    포지션 손실이 제2방어막(40% Hard Limit) 또는 제3방어막(-75%)을 넘을 때 즉각 직권 청산을 집행합니다.
    """
    global main_engine_broken, current_price, prev_price, portfolio_options, current_position_qty
    global total_equity, daily_hwm, initial_capital, current_capital, accumulated_reserve
    global risk_triggered_event, event_logs

    logger.info("🛡️ [WATCHDOG DAEMON] 외부 관측 및 페일오버 감시 데몬 가동 시작.")

    try:
        while True:
            await asyncio.sleep(0.5)

            if main_engine_broken:
                # 메인 엔진 중단 중에도 시장 가격 변동에 따른 임시 평가자산 모사
                temp_total_equity = current_capital + accumulated_reserve
                
                limit_40 = daily_hwm * 0.60
                limit_75 = initial_capital * 0.25

                # 외부 지수 변동성(안정성) 감시 모사
                external_price_change = abs(current_price - prev_price) / max(1.0, prev_price)
                is_market_stable = external_price_change < 0.015  # 1.5% 미만 변동 시 안정

                if temp_total_equity < limit_75 or temp_total_equity < limit_40:
                    if HARDENED_STRESS_MODE:
                        # ⏳ [Forced_Liquidation_Penalty] 지옥 모드: 500ms~1000ms 청산 지연 주입 및 자산 15% 훼손 페널티
                        logger.critical("🔥 [LIQUIDATION PENALTY] 증권사 강제 청산 지연 및 Worst Price 슬리피지 왜곡 페널티 발동 (자산 -15% 추가 차감)")
                        await asyncio.sleep(random.uniform(0.5, 1.0))
                        penalty_loss = temp_total_equity * 0.15
                        current_capital -= penalty_loss
                        temp_total_equity -= penalty_loss
                        
                    logger.critical(
                        "🚨 [WATCHDOG FORCE CLOSE] HFT 중단 중 외부 지수 급변으로 방어선 붕괴 감지! "
                        "백그라운드 즉각 직권 청산 집행. 평가자산: ₩%s / 제2방어막: ₩%s",
                        f"{temp_total_equity:,.0f}", f"{limit_40:,.0f}"
                    )
                    portfolio_options.clear()
                    current_position_qty = 0
                    main_engine_broken = False
                    
                    event_logs.append({
                        "seq": 0,
                        "date": calendar_sim.current_time.strftime("%Y-%m-%d") if calendar_sim else "N/A",
                        "time": calendar_sim.current_time.strftime("%H:%M:%S") if calendar_sim else "N/A",
                        "event": "Watchdog 직권 강제청산",
                        "details": f"자산 붕괴로 강제 숏커버 실행: ₩{temp_total_equity:,.0f}"
                    })
                    risk_triggered_event.set()
                else:
                    # 방어선 이내 상태
                    if is_market_stable:
                        # 변동성이 작고 안정적인 상태 -> 기존 포지션 및 주문을 그대로 유지 (Hold)
                        logger.info(
                            "🛡️ [WATCHDOG HOLD] 외부 지수 변동성 안정적(%.2f%%). 기존 포지션 및 전략 흐름 유지 (Hold). 평가자산: ₩%s",
                            external_price_change * 100.0, f"{temp_total_equity:,.0f}"
                        )
                    else:
                        logger.warning(
                            "🛡️ [WATCHDOG WARNING] 외부 변동성 급증 감지(%.2f%%)! 예비 숏커버 준비 대기 중.",
                            external_price_change * 100.0
                        )
    except asyncio.CancelledError:
        logger.info("🛡️ [WATCHDOG DAEMON] 감시 데몬 태스크가 취소되었습니다.")
    except Exception as e:
        logger.error("🛡️ [WATCHDOG DAEMON] 에러 발생: %s", e)


async def main() -> None:
    """감독자 루프(Supervisor Loop)

    WebSocket 서버는 주프로세스 수명 동안 단 한 번 기동된다.
    자본 15% 붕괴 감지 시:
      1. 세션 데이터를 저장하고 리포트를 생성한다.
      2. 쿨다운 대기 (RISK_COOLDOWN_SECS에 진카운트 디스플레이)
      3. 전역 상태를 리셋하고 시뮬레이션 루프를 재개한다.
      4. 사용자 Ctrl+C 실행 시에만 실제 종료된다.
    """
    global shutdown_event, risk_triggered_event

    session_number = 0
    
    # ── [BUG FIX] 서버 최초 기동 시 전역 변수(전략 객체 등) 1회 초기화 ──
    _reset_session_state()

    async with websockets.serve(handler, "localhost", 8080):
        logger.info("모의 웹소켓 가동 시작 (ws://localhost:8080)")

        while True:
            session_number += 1
            shutdown_event       = asyncio.Event()
            risk_triggered_event = asyncio.Event()

            if session_number > 1:
                # ─── 리셋 후 시작 자본 재공지 ───────────────────────────
                logger.info(
                    "=" * 60 + "\n"
                    "🔁 [AUTO RESTART] SESSION #%d\n"
                    "   시작 자본금: ₩%s  |  시작가: %.2fpt\n" +
                    "=" * 60,
                    session_number,
                    f"{initial_capital:,.0f}",
                    current_price,
                )

            sim_task = asyncio.create_task(simulation_loop())
            watchdog_task = asyncio.create_task(watchdog_daemon())

            # shutdown_event(Ctrl+C) 또는 risk_triggered_event(붕괴) 둘 중 하나 대기
            done, _ = await asyncio.wait(
                [asyncio.ensure_future(shutdown_event.wait()),
                 asyncio.ensure_future(risk_triggered_event.wait())],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # ── 태스크 중단 ──────────────────────────────────────────────
            sim_task.cancel()
            watchdog_task.cancel()
            try:
                await asyncio.gather(sim_task, watchdog_task, return_exceptions=True)
            except Exception:
                pass

            # ── 세션 데이터 저장 및 리포트 생성 ──────────────────────────
            if session_telemetry:
                session_name = f"session_{session_number}"
                all_sessions_telemetry[session_name] = list(session_telemetry)

                logger.info("💾 %d 건의 세션 텔레메트리 데이터 취합 중 (Session #%d)...",
                            len(session_telemetry), session_number)
                try:
                    with open("test_session_data.json", "wb") as f_json:
                        f_json.write(orjson.dumps(all_sessions_telemetry))
                    logger.info("✅ test_session_data.json 통합 저장 완료.")
                    
                    session_md = generate_markdown_report(session_telemetry, session_number=session_number)
                    all_sessions_markdowns.append(session_md)
                    
                    from datetime import datetime
                    combined_md = "# 📊 KOSPI200 HFT 가상 테스트 세션 통합 분석 보고서\n"
                    combined_md += f"통합 보고서 최종 갱신 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    combined_md += f"총 구동 세션 수: {session_number}개 세션\n\n"
                    combined_md += "---\n\n"
                    combined_md += "\n".join(all_sessions_markdowns)
                    combined_md += "\n*본 보고서는 헌법 V25.2 가상 붕괴 시나리오에 따른 자율 대응 통합 결과를 반영하고 있습니다.*\n"
                    
                    with open("test_report.md", "w", encoding="utf-8") as f_report:
                        f_report.write(combined_md)
                    logger.info("✅ test_report.md 통합 보고서 갱신 완료.")
                except Exception as e_save:
                    logger.error("세션 데이터 저장 중 에러: %s", e_save)

            # ── 사용자 종료(Ctrl+C) 시 루프 탈출 ─────────────────────────
            if shutdown_event.is_set():
                logger.info("서버가 사용자 요청에 의해 안전하게 종료되었습니다.")
                break

            # ── 자본금 붕괴 → 쿨다운 후 자동 재기동 ──────────────────────
            logger.critical(
                "🚨 [SYSTEM HALT] 리스크 관리 엔진에 의해 거래가 강제 중단되었습니다. "
                "(자본금 보호선 붕괴) — %d초 후 자동 재기동...",
                RISK_COOLDOWN_SECS,
            )

            # 쿨다운 카운트다운 브로드캐스트 (대시보드에 표시)
            for remaining in range(RISK_COOLDOWN_SECS, 0, -1):
                cooldown_msg = orjson.dumps({
                    "type":      "COOLDOWN",
                    "remaining": remaining,
                    "message":   f"⏳ 시스템 쿨다운 중... {remaining}초 후 SESSION #{session_number + 1} 자동 재기동",
                }).decode()
                if connected_clients:
                    await asyncio.gather(
                        *[c.send(cooldown_msg) for c in list(connected_clients)],
                        return_exceptions=True,
                    )
                await asyncio.sleep(1)

            # 전역 상태 리셋 후 다음 세션 진입 (자본금 보존)
            _reset_session_state(preserve_capital=True)


def generate_markdown_report(telemetry: List[Dict[str, Any]], session_number: int = 1) -> str:
    """테스트 세션 데이터를 분석하여 통합 요약 보고서(Markdown) 본문을 리턴"""
    import numpy as np

    total_ticks = len(telemetry)
    if total_ticks == 0:
        return ""

    # 1. 자산 데이터 분석
    equities = np.array([p["coord"]["y"] for p in telemetry if "coord" in p], dtype=np.float64)
    reserve_vals = np.array([p["reserve"] for p in telemetry if "reserve" in p], dtype=np.float64)

    start_equity = equities[0] if len(equities) > 0 else 100000000.0
    end_equity = equities[-1] if len(equities) > 0 else 100000000.0
    net_profit = end_equity - start_equity
    profit_pct = (net_profit / start_equity) * 100.0

    # MDD 계산
    running_max = np.maximum.accumulate(equities)
    drawdowns = running_max - equities
    max_dd = np.max(drawdowns) if len(drawdowns) > 0 else 0.0
    mdd_pct = (max_dd / running_max[np.argmax(drawdowns)]) * 100.0 if len(drawdowns) > 0 and running_max[np.argmax(drawdowns)] > 0 else 0.0

    # 2. 주문 정보 수집
    orders = [p["order"] for p in telemetry if "order" in p]
    total_orders = len(orders)
    filled_orders = len([o for o in orders if o["status"] == "FILLED"])
    partial_orders = len([o for o in orders if o["status"] == "PARTIAL"])
    rejected_orders = len([o for o in orders if o["status"] == "REJECTED"])
    sent_orders = len([o for o in orders if o["status"] == "SENT"])

    fill_rate = ((filled_orders + partial_orders) / total_orders * 100.0) if total_orders > 0 else 0.0
    total_fees = sum([o.get("fee", 0.0) for o in orders])

    # 3. 국면 분석
    regimes = [p["regime"] for p in telemetry if "regime" in p]
    unique_regimes, counts = np.unique(regimes, return_counts=True)
    regime_dist = {r: (c / total_ticks * 100.0) for r, c in zip(unique_regimes, counts)}

    # 4. 슬리피지 & 튜닝 팩터 분석
    slippage_ms = np.array([p["slippageMs"] for p in telemetry if "slippageMs" in p], dtype=np.float64)
    tuning_factors = np.array([p["tuningFactor"] for p in telemetry if "tuningFactor" in p], dtype=np.float64)

    avg_slippage = np.mean(slippage_ms) if len(slippage_ms) > 0 else 0.0
    max_slippage = np.max(slippage_ms) if len(slippage_ms) > 0 else 0.0
    avg_tuning = np.mean(tuning_factors) if len(tuning_factors) > 0 else 1.0
    min_tuning = np.min(tuning_factors) if len(tuning_factors) > 0 else 1.0

    # 5. 전략별 가중치 평균
    t1_w = np.mean([p["strategyWeights"]["Track1"] for p in telemetry if "strategyWeights" in p]) if total_ticks > 0 else 0.0
    t2_w = np.mean([p["strategyWeights"]["Track2"] for p in telemetry if "strategyWeights" in p]) if total_ticks > 0 else 0.0
    t3_w = np.mean([p["strategyWeights"]["Track3"] for p in telemetry if "strategyWeights" in p]) if total_ticks > 0 else 0.0
    t4_w = np.mean([p["strategyWeights"]["Track4"] for p in telemetry if "strategyWeights" in p]) if total_ticks > 0 else 0.0
    t5_w = np.mean([p["strategyWeights"].get("Track5", 0.0) for p in telemetry if "strategyWeights" in p]) if total_ticks > 0 else 0.0
    t6_w = np.mean([p["strategyWeights"].get("Track6", 0.0) for p in telemetry if "strategyWeights" in p]) if total_ticks > 0 else 0.0
    t7_w = np.mean([p["strategyWeights"].get("Track7", 0.0) for p in telemetry if "strategyWeights" in p]) if total_ticks > 0 else 0.0
    t8_w = np.mean([p["strategyWeights"].get("Track8", 0.0) for p in telemetry if "strategyWeights" in p]) if total_ticks > 0 else 0.0

    # 전략별 누적 PnL 및 스트레스 PnL 추출
    global strategy_pnl_tracker, strategy_stress_pnl, guard_trigger_count
    t1_pnl = strategy_pnl_tracker["Track1"]
    t2_pnl = strategy_pnl_tracker["Track2"]
    t3_pnl = strategy_pnl_tracker["Track3"]
    t4_pnl = strategy_pnl_tracker["Track4"]
    t5_pnl = strategy_pnl_tracker["Track5"]
    t6_pnl = strategy_pnl_tracker["Track6"]
    t7_pnl = strategy_pnl_tracker["Track7"]
    t8_pnl = strategy_pnl_tracker["Track8"]

    t1_stress = strategy_stress_pnl["Track1"]
    t2_stress = strategy_stress_pnl["Track2"]
    t3_stress = strategy_stress_pnl["Track3"]
    t4_stress = strategy_stress_pnl["Track4"]
    t5_stress = strategy_stress_pnl["Track5"]
    t6_stress = strategy_stress_pnl["Track6"]
    t7_stress = strategy_stress_pnl["Track7"]
    t8_stress = strategy_stress_pnl["Track8"]

    # 0. 실제 투자 영업일 및 역사적 시장 이벤트 감시 이력 분석
    global trading_date_logs, event_logs
    trading_dates_str = ", ".join(trading_date_logs) if trading_date_logs else "N/A"

    event_details_str = ""
    if event_logs:
        for ev in event_logs:
            date_event_desc = TRADING_DAY_EVENTS.get(ev.get("date", ""), "")
            desc_prefix = f" ({date_event_desc})" if date_event_desc else ""
            event_details_str += f"- **[{ev.get('date', 'N/A')} {ev.get('time', 'N/A')}]** {ev.get('event', 'N/A')}{desc_prefix}: {ev.get('details', 'N/A')}\n"
    else:
        event_details_str += "- *세션 중 발생한 특이 역사적 지수 급변 또는 비상 락다운 이벤트가 없습니다.*\n"

    # 6. 마크다운 빌드
    md = f"""
## 🔁 [SESSION #{session_number}] 상세 분석 보고서
- **적용된 실제 투자 일자 (Trading Date)**: **{trading_dates_str}**
- **테스트 규모**: 총 {total_ticks} 틱 스트리밍

### 🧪 [V2 STRESS TEST] 가상 테스트 환경 및 예산 강제 주입 현황
- **테스트 목적**: 월 단위 방어막(Insurance) 스트레스 테스트 및 비선형 맷집 검증
- **강제 할당된 보험 예산 (Track 5~8)**: **초기 자본 대비 고정 비율 주입 방식**
- **전략 3 (차익거래) 상태**: ⛔ **강제 Hold (테스트 순도 유지를 위한 캐시카우 차단)**
- **나머지 공격 트랙 (Track 2, 4) 상태**: ⛔ **비활성화 (0%)**
- **현재 유지 중인 수익 창출 트랙**: ✅ **Track1 30%**
- **월단위 독립 테스트 (Monthly Capital Reset)**: ✅ **활성화됨 (매월 초 자본금/HWM 원금 ₩25,000,000 완벽 초기화)**
- **Track 2 & 3 포지션 진입**: ⛔ **비활성화 (가상 테스트 순도 유지를 위한 강제 HOLD)**

### 📅 역사적 시장 국면 및 비상 감시(Watchdog/Risk Engine) 이벤트 로그
{event_details_str}

### 💰 1. 자산 및 자본 종합 요약
- **시작 총자산 (Starting Equity)**: ₩{start_equity:,.0f}
- **종료 총자산 (Ending Equity)**: ₩{end_equity:,.0f}
- **실현/평가 순손익 (Net Profit)**: **₩{net_profit:+,.0f} ({profit_pct:+.3f}%)**
- **최대 낙폭 (Max Drawdown, MDD)**: ₩{max_dd:,.0f} ({mdd_pct:.3f}%)
- **안전 유보금 (Ending Reserve)**: ₩{reserve_vals[-1] if len(reserve_vals) > 0 else 0.0:,.0f} (전체 자산의 {(reserve_vals[-1]/end_equity*100.0) if len(reserve_vals) > 0 and end_equity > 0 else 0.0:.1f}%)

### 📦 2. 주문 집행 및 체결 성적
| 구분 | 건수 / 비율 | 비고 |
| :--- | :--- | :--- |
| **총 주문 요청 건수** | {total_orders} 건 | 틱당 평균 {total_orders/total_ticks:.2f}회 |
| **완전 체결 (FILLED)** | {filled_orders} 건 | 전체 주문의 {(filled_orders/max(1, total_orders)*100.0):.1f}% |
| **부분 체결 (PARTIAL)** | {partial_orders} 건 | 전체 주문의 {(partial_orders/max(1, total_orders)*100.0):.1f}% (GC 회수 대상) |
| **주문 거부 (REJECTED)** | {rejected_orders} 건 | 전체 주문의 {(rejected_orders/max(1, total_orders)*100.0):.1f}% (백오프 유도) |
| **대기/미체결 (SENT)** | {sent_orders} 건 | 전체 주문의 {(sent_orders/max(1, total_orders)*100.0):.1f}% |
| **최종 체결 성공률** | **{fill_rate:.2f}%** | (FILLED + PARTIAL) / Total |
| **총 발생 거래수수료** | **₩{total_fees:,.0f}** | 선물 0.003% / 옵션 0.15% 기준 |

### 📈 3. 시장 국면(Regime)별 분포
"""
    for reg, pct in regime_dist.items():
        md += f"- **{reg}** 국면: {pct:.1f}%\n"

    md += f"""
### 🌋 4. Self-Tuning Guard (리스크 미세조정) 성능 지표
- **평균 수량 조절 계수 (Avg Tuning Factor)**: **{avg_tuning*100.0:.1f}%**
- **최저 수량 조절 계수 (Min Tuning Factor)**: **{min_tuning*100.0:.1f}%**
- **평균 매칭 딜레이 (Avg Slippage Latency)**: **{avg_slippage:.1f} ms**
- **최대 매칭 딜레이 (Max Slippage Latency)**: **{max_slippage:.0f} ms**

### 🛡️ 5. 전략별 국면 및 PnL 성과분석 (Strategy Breakdown)
| 전략 (Strategy) | 총 누적 손익 (Total PnL) | 스트레스 국면 손익 (Stress PnL) | 평균 비중 | 방어 동작 방식 |
| :--- | :--- | :--- | :--- | :--- |
| **Track1 (Defense)** | ₩{t1_pnl:+,.0f} | ₩{t1_stress:+,.0f} | {t1_w:.1f}% | 리스크 급증 시 100% 비중으로 증거금 제한 및 숏옵션 커버 |
| **Track2 (Trap)** | ₩{t2_pnl:+,.0f} | ₩{t2_stress:+,.0f} | {t2_w:.1f}% | ⛔ **[V2 HOLD]** 박스권 내 역추세 포지션 진입 중단 |
| **Track3 (Arbitrage)** | ₩{t3_pnl:+,.0f} | ₩{t3_stress:+,.0f} | {t3_w:.1f}% | ⛔ **[V2 HOLD]** 시뮬레이션 순도 유지를 위한 차익 진입 전면 차단 |
| **Track4 (Gamma)** | ₩{t4_pnl:+,.0f} | ₩{t4_stress:+,.0f} | {t4_w:.1f}% | ⛔ **[V2 HOLD]** 현물 델타 헤징 및 스켈핑 중단 |
| **Track5 (Gap)** | ₩{t5_pnl:+,.0f} | ₩{t5_stress:+,.0f} | {t5_w:.1f}% | 시가 갭 감지 시 역방향 진입 및 펜스 압축 회귀 저격 |
| **Track6 (Daily)** | ₩{t6_pnl:+,.0f} | ₩{t6_stress:+,.0f} | {t6_w:.1f}% | 변동성 급증 시 당일 만기 극외가 양매수(0DTE) 가입 |
| **Track7 (Weekly)** | ₩{t7_pnl:+,.0f} | ₩{t7_stress:+,.0f} | {t7_w:.1f}% | 매주 위클리 옵션 상장 첫날 주간 트렌드 저격 양매수 가입 |
| **Track8 (Monthly)** | ₩{t8_pnl:+,.0f} | ₩{t8_stress:+,.0f} | {t8_w:.1f}% | 만기 초입 비대칭 외가격 양매수 및 D-3 감마이양 출구 |

### 🚨 6. 리스크 가드 발동 및 본전 청산 이력
- **비상 청산 가드 발동 횟수 (Emergency Guards Triggered)**: **{guard_trigger_count} 회**

### 📅 7. 월물 전환(롤오버) 및 만기 정산 이력
"""
    global rollover_event_log
    rollover_count = len(rollover_event_log)
    total_settlement_pnl = sum(e["settlement_pnl"] for e in rollover_event_log)

    md += f"""- **세션 중 만기 도달 횟수 (Expiry Events)**: **{rollover_count} 회**
- **만기 정산 누적 손익 합계**: **₩{total_settlement_pnl:+,.0f}**
"""

    if rollover_count > 0:
        md += """
| # | Seq(틱) | 만기 시점 기초자산가 | 당월물 정산 손익 | 차월물 D-Day 리셋 |
| :---: | :---: | :---: | :---: | :---: |
"""
        for i, ev in enumerate(rollover_event_log, start=1):
            pnl_str = f"₩{ev['settlement_pnl']:+,.0f}"
            md += f"| {i} | Tick {ev['seq']} | {ev['price_at_expiry']:.2f}pt | {pnl_str} | D-{ev['new_dte']:.1f}일 |\n"
    else:
        md += "\n> 이번 세션에서는 만기 도달 없이 종료되었습니다.\n"

    md += "\n---\n"
    return md


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("서버가 사용자 요청(Ctrl+C)에 의해 안전하게 종료되었습니다.")
    # 세션별 저장/리포트는 main()의 감독자 루프가 수행하며,
    # 마지막 세션 데이터가 단 1건 남았을 경우를 대비해 다시 저장한다.
    if session_telemetry:
        logger.info("💾 [종료 안전망] 마지막 세션 텔레메트리 %d 건 저장 중...", len(session_telemetry))
        try:
            session_name = f"session_{restart_count + 1}"
            if session_name not in all_sessions_telemetry:
                all_sessions_telemetry[session_name] = list(session_telemetry)
                session_md = generate_markdown_report(session_telemetry, session_number=restart_count + 1)
                all_sessions_markdowns.append(session_md)
            
            with open("test_session_data.json", "wb") as f_json:
                f_json.write(orjson.dumps(all_sessions_telemetry))
            
            from datetime import datetime
            combined_md = "# 📊 KOSPI200 HFT 가상 테스트 세션 통합 분석 보고서\n"
            combined_md += f"통합 보고서 최종 갱신 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            combined_md += f"총 구동 세션 수: {len(all_sessions_markdowns)}개 세션\n\n"
            combined_md += "---\n\n"
            combined_md += "\n".join(all_sessions_markdowns)
            combined_md += "\n*본 보고서는 헌법 V25.2 가상 붕괴 시나리오에 따른 자율 대응 통합 결과를 반영하고 있습니다.*\n"
            
            with open("test_report.md", "w", encoding="utf-8") as f_report:
                f_report.write(combined_md)
            logger.info("✅ test_session_data.json / test_report.md 최종 통합 저장 완료.")
        except Exception as e_save:
            logger.error("완료 데이터 저장 에러: %s", e_save)
