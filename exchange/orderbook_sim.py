# -*- coding: utf-8 -*-
"""
exchange/orderbook_sim.py

[Phase 2] KOSPI200 옵션/선물 가상 Bid/Ask 호가창 시뮬레이터

핵심 역할:
  1. mid_price + bid_ask_spread 기반으로 실시간 Bid/Ask 가격 생성
  2. KOSPI200 옵션 틱사이즈 테이블 적용 (3.00 미만: 0.01pt, 이상: 0.05pt)
  3. 지정가 체결을 위한 최적 Limit Price 결정 공식 제공
     - 매도 청산: min(target_price, bid + N*tick)
     - 매수 청산: max(target_price, ask - N*tick)
  4. random.uniform() 랜덤 가격 생성을 완전 대체
"""

import random
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Tuple, Optional
import logging
from virtual_securities_firm.exchange.order_book import (
    OPTION_TICK_TABLE,
    get_option_tick_size,
    snap_to_tick,
    OrderBook
)

logger = logging.getLogger(__name__)

# KOSPI200 선물 호가단위: 0.05pt
FUTURES_TICK = Decimal("0.05")

# 최소 옵션 가격 (0.01pt 미만 체결 불가)
MIN_OPTION_PRICE = Decimal("0.01")

# 최소 선물 스프레드 (최소 1틱)
MIN_FUTURES_SPREAD = Decimal("0.05")


class VirtualOrderBook:
    """
    [Phase 2] KOSPI200 가상 Bid/Ask 호가창

    랜덤 가격 생성을 완전 대체하여, 실제 시장 구조에 맞는
    Bid/Ask 기반 지정가 결정을 수행합니다.
    
    주요 메서드:
      get_bid_ask()       — Bid/Ask 가격 계산
      get_tick_size()     — 호가단위 조회
      round_to_tick()     — 틱사이즈 단위 절사
      calc_limit_price()  — 진입/청산 지정가 결정
      calc_option_mid()   — 옵션 중간가 산출 (Black-Scholes 간소화)
    """

    def __init__(self) -> None:
        logger.info("[VirtualOrderBook] KOSPI200 가상 호가창 초기화 완료")

    # ── 1. 틱사이즈 조회 ───────────────────────────────────────────────────

    def get_tick_size(self, price: Decimal, asset_type: str) -> Decimal:
        """
        가격과 자산 유형에 따른 KOSPI200 호가단위 반환
        
        Args:
            price:      현재 가격 (Decimal)
            asset_type: "OPTIONS" 또는 "FUTURES"
        Returns:
            호가단위 (Decimal)
        """
        if asset_type == "FUTURES":
            return FUTURES_TICK

        # 옵션 틱사이즈 테이블 적용
        for threshold, tick in OPTION_TICK_TABLE:
            if price < threshold:
                return tick
        return Decimal("0.05")  # 기본값

    # ── 2. 틱사이즈 라운딩 ─────────────────────────────────────────────────

    def round_to_tick(
        self,
        price: Decimal,
        asset_type: str,
        rounding: str = ROUND_DOWN,
    ) -> Decimal:
        """
        KOSPI200 호가단위 단위로 가격 절사
        
        매도 지정가는 ROUND_DOWN (불리한 쪽으로 보정하여 체결 확률 ↑)
        매수 지정가는 ROUND_HALF_UP (적당한 반올림)
        """
        tick = self.get_tick_size(price, asset_type)
        # 틱 단위로 나누어 정수화 후 다시 곱함
        ticked = (price / tick).to_integral_value(rounding=rounding) * tick
        # 옵션 최소가 보정
        if asset_type == "OPTIONS":
            ticked = max(ticked, MIN_OPTION_PRICE)
        return ticked

    # ── 3. Bid/Ask 생성 ────────────────────────────────────────────────────

    def get_bid_ask(
        self,
        mid_price: float,
        spread: float,
        asset_type: str,
        active_vol: float = 1.0,
    ) -> Tuple[Decimal, Decimal]:
        """
        mid_price와 bid_ask_spread로부터 Bid/Ask 계산
        
        옵션의 경우 spread가 클수록 (유동성 저하 시) 더 넓어집니다.
        
        Args:
            mid_price:  현재 기준 가격 (underlying price 또는 옵션 이론가)
            spread:     현재 bid-ask 스프레드 (pt 단위)
            asset_type: "OPTIONS" / "FUTURES"
            active_vol: 현재 변동성 배수 (고변동성 시 추가 스프레드 적용)
        Returns:
            (bid, ask) 튜플
        """
        mid = Decimal(str(mid_price))

        # 변동성 비례 스프레드 가산 (고변동성 시 Bid/Ask 확장)
        vol_spread_add = Decimal(str(spread)) * Decimal(str(max(0.0, active_vol - 1.0) * 0.1))
        effective_spread = Decimal(str(spread)) + vol_spread_add

        half_spread = effective_spread / Decimal("2")

        bid_raw = mid - half_spread
        ask_raw = mid + half_spread

        # 틱사이즈 라운딩
        bid = self.round_to_tick(bid_raw, asset_type, rounding=ROUND_DOWN)
        ask = self.round_to_tick(ask_raw, asset_type, rounding=ROUND_HALF_UP)

        # Bid가 Ask보다 크거나 같으면 최소 1틱 간격 보정
        tick = self.get_tick_size(mid, asset_type)
        if bid >= ask:
            bid = ask - tick

        # 음수 방지
        if asset_type == "OPTIONS":
            bid = max(bid, MIN_OPTION_PRICE)
        else:
            bid = max(bid, Decimal("0.05"))

        return bid, ask

    # ── 4. 지정가 결정 공식 ────────────────────────────────────────────────

    def calc_limit_price(
        self,
        side: str,
        target_price: Decimal,
        bid: Decimal,
        ask: Decimal,
        asset_type: str,
        tick_offset: int = 0,
    ) -> Decimal:
        """
        진입/청산 지정가 결정 (틱 오프셋 적용)
        
        매도(SELL) 지정가:
          min(target_price, bid + tick_offset * tick)
          → 시장 Bid 가격 이하로 지정가를 내리면 빠르게 체결
        
        매수(BUY) 지정가:
          max(target_price, ask - tick_offset * tick)
          → 시장 Ask 가격 이상으로 지정가를 올리면 빠르게 체결
        
        Args:
            side:         "BUY" 또는 "SELL"
            target_price: 전략이 원하는 목표 가격
            bid:          현재 Bid 가격
            ask:          현재 Ask 가격
            asset_type:   "OPTIONS" / "FUTURES"
            tick_offset:  공격적 체결 시 틱 오프셋 (양수=더 공격적)
        Returns:
            최종 지정가 (틱사이즈 라운딩 적용)
        """
        tick = self.get_tick_size(target_price, asset_type)
        offset_pts = tick * Decimal(str(tick_offset))

        if side == "SELL":
            # 매도: target과 (bid + offset) 중 낮은 쪽
            raw = min(target_price, bid + offset_pts)
            return self.round_to_tick(raw, asset_type, rounding=ROUND_DOWN)
        else:
            # 매수: target과 (ask - offset) 중 높은 쪽
            raw = max(target_price, ask - offset_pts)
            return self.round_to_tick(raw, asset_type, rounding=ROUND_HALF_UP)

    # ── 5. 옵션 이론가 간소 산출 ─────────────────────────────────────────

    def calc_option_mid_price(
        self,
        underlying: float,
        strike: float,
        dte: float,
        iv: float,
        option_type: str,
    ) -> Decimal:
        """
        옵션 이론가 간소 산출 (Intrinsic Value + Time Value 근사)
        
        실제 Black-Scholes 대신 간소화된 근사치를 사용합니다.
        (random.uniform(0.5, 8.0) 완전 대체)
        
        Args:
            underlying:  현물 가격 (KOSPI200 지수)
            strike:      행사가
            dte:         만기까지 잔여 영업일
            iv:          내재변동성 배수 (1.0 = 기본)
            option_type: "CALL" / "PUT"
        Returns:
            옵션 이론가 (Decimal, 호가단위 적용)
        """
        import math

        # 내재가치 (Intrinsic Value)
        if option_type == "CALL":
            intrinsic = max(0.0, underlying - strike)
        else:
            intrinsic = max(0.0, strike - underlying)

        # ── [BUG FIX] 시간가치 근사 수정 ──────────────────────────────────────
        # KOSPI200 옵션 ATM 프리미엄 현실 수준:
        #   DTE=21, IV=20% 기준 ATM 이론가 ≈ 3~8pt
        # 기존 공식: iv × 0.15 × underlying(≈392) × sqrt(dte/252) ≈ 17pt → 과대산출
        # 수정 공식: ATM 기준 포인트 스케일로 직접 산출 (underlying 제거, 0.4배 스케일)
        #   time_vol = iv × ATM_BASE_PT × sqrt(DTE/252)
        #   KOSPI200 ATM 기준가 ≈ 4.0pt (연간변동성 20% × ATM 스케일 상수)
        ATM_BASE_PT = 4.0   # KOSPI200 ATM 옵션 시간가치 기준 포인트 (실증값)
        if dte > 0:
            time_vol = iv * ATM_BASE_PT * math.sqrt(max(0.0, dte) / 21.0)
            # OTM 감소: 행사가와 현물가 차이가 클수록 시간가치 급감
            moneyness = abs(underlying - strike) / max(underlying * 0.01, 0.5)  # 1pt 단위 OTM
            atm_factor = math.exp(-moneyness * 0.4)   # OTM 감쇠 계수 (5.0→0.4로 완화)
            time_value = time_vol * atm_factor
        else:
            time_value = 0.0

        mid = intrinsic + time_value

        # 최솟값 보정 (0.01pt 미만 체결 불가)
        mid = max(0.01, round(mid, 2))

        # 약간의 마켓 노이즈 (+/- 2틱 이내)
        tick_val = 0.01 if mid < 3.0 else 0.05
        noise = random.uniform(-tick_val * 2, tick_val * 2)
        mid = max(0.01, round(mid + noise, 2))

        result = self.round_to_tick(Decimal(str(mid)), "OPTIONS")
        return result

    # ── 6. 선물 현재가 기반 진입가 산출 ─────────────────────────────────

    def calc_futures_entry_price(
        self,
        current_price: float,
        side: str,
        spread: float,
        active_vol: float = 1.0,
    ) -> Decimal:
        """
        선물 지정가 진입 가격 결정
        (random.uniform(-0.5, 0.5) 완전 대체)
        
        BUY:  ask 가격 (체결 용이)
        SELL: bid 가격 (체결 용이)
        """
        bid, ask = self.get_bid_ask(current_price, spread, "FUTURES", active_vol)
        if side == "BUY":
            return ask
        else:
            return bid


# ── 모듈 레벨 싱글턴 인스턴스 (mock_ws_server.py에서 import하여 사용) ────────
_orderbook_instance: Optional[VirtualOrderBook] = None


def get_orderbook() -> VirtualOrderBook:
    """싱글턴 VirtualOrderBook 반환"""
    global _orderbook_instance
    if _orderbook_instance is None:
        _orderbook_instance = VirtualOrderBook()
    return _orderbook_instance
