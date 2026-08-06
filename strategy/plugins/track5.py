# -*- coding: utf-8 -*-
import logging
import math
from typing import Dict, Any
from strategy.common import TradingDateResetHelper

logger = logging.getLogger(__name__)

class Track5:
    """
    [Track5] Pure Gap Divergence Protocol (시초가 갭 역방향 회귀 저격 전용 봇)
    - 자본 배분: 매일 시가 갭 조건 만족 시 +0.1% 동적 부여
    - 역할:
      1. 장 시작 직후(09:00:00) 시초가 괴리(Z-Score) 발생 시 역방향 저격 진입 (Mid-Price 지정가 큐).
      2. ATR 및 VKOSPI 일일 변동성 연동 동적 손절선 & 동적 트레일링 익절 락인.
      3. 15분 타임아웃 컷오프 및 선제 지정가 스탑 연계로 아침 슬리피지 완전 회피.
    """
    def __init__(self, config: Dict[str, Any]):
        self.params = config.get("strategies", {}).get("strategy_5", {}).get("params", {})
        # Z-Score 임계치 (기본 1.5 시그마)
        self.z_threshold = self.params.get("z_threshold", 1.5)
        # 옵션 펜스 압축률 (원래 너비에서 좁힐 거리 pt)
        self.fence_compress_pt = self.params.get("fence_compress_pt", 2.5)
        # 갭 회귀 손절선 기본값 (동적 ATR 연동 시 오버라이드)
        self.stop_loss_pts = self.params.get("stop_loss_pts", 1.5)
        
        self.date_reset_helper = TradingDateResetHelper()
        self.reset_state()
        logger.info("Pure Gap Divergence Protocol Strategy (Track5) Initialized.")

    def reset_state(self) -> None:
        self.gap_state: Dict[str, Any] = {
            "is_active": False,
            "direction": None,       # "SHORT" (갭상승 대응) 또는 "LONG" (갭하락 대응)
            "entry_price": 0.0,
            "target_price": 0.0,     # 평균 회귀 목표가 (괴리 0선 = 전일 종가)
            "stop_loss_price": 0.0,
            "open_time_tick": 0,     # 장 시작 후 경과 틱 카운트
            "peak_pnl": 0.0,         # 달성된 최고 PnL (pt)
            "trailing_active": False,# 동적 트레일링 스탑 활성화 여부
            "liquidity_provided": 0, # 유동성 공급 분할 청산 단계
            "daily_std_pts": 1.5,
        }

    def evaluate_gap_divergence(self, open_price: float, prev_close_price: float, active_vol: float, current_regime: str = "NORMAL", date_str: str = "UNKNOWN") -> Dict[str, Any]:
        """
        [Z-Score 기반 시초가 괴리 감지 및 지정가 큐 연계 역방향 저격 진입 판단]
        """
        if self.date_reset_helper.check_and_update(date_str):
            self.reset_state()

        if self.gap_state["is_active"]:
            return {"status": "ALREADY_ACTIVE", "signals": []}

        gap_value = open_price - prev_close_price
        
        # 1. 일일 표준편차(Daily Volatility) 및 ATR 동적 지표 산출
        daily_vol_pct = (0.15 / math.sqrt(252)) * active_vol
        daily_std_pts = prev_close_price * daily_vol_pct
        
        # 동적 ATR/변동성 연동 손절선 (기본 1.5pt 하드코딩 탈피 -> 동적 산정)
        dynamic_stop_loss_pts = max(1.0, daily_std_pts * 0.8)
        self.gap_state["daily_std_pts"] = daily_std_pts
        
        # 2. 괴리 Z-Score 산출
        z_score = gap_value / max(0.1, daily_std_pts)

        # 3. 장세 판단(Regime)에 따른 동적 Z-Score 임계치 결정
        if current_regime in ["HIGH_VOL", "NOISE_CHOPPY", "CIRCUIT_BREAKER"]:
            effective_z = 1.8
        elif current_regime in ["NORMAL", "NEUTRAL"]:
            effective_z = 1.1
        else:
            effective_z = self.z_threshold

        if abs(z_score) < effective_z:
            return {"status": "NO_TRIGGER", "signals": [], "z_score": z_score, "effective_z": effective_z}

        # 4. 블랙스완 파국 갭 방어 가드 (Z-Score >= 4.0 이상 극단 갭은 쏠림 폭주 위험으로 진입 차단)
        if abs(z_score) >= 4.0:
            logger.warning("🚨 [BLACK SWAN GAP BLOCK] 극단적 파국 갭 감지 (Z-Score: %.2f >= 4.0). 역방향 회귀 진입 차단.", z_score)
            return {"status": "BLACK_SWAN_GAP_BLOCKED", "signals": [], "z_score": z_score}

        signals = []
        # 갭 상승 -> 숏 진입 및 지정가 큐 방출
        if z_score > 0:
            self.gap_state["is_active"] = True
            self.gap_state["direction"] = "SHORT"
            self.gap_state["entry_price"] = open_price
            self.gap_state["target_price"] = prev_close_price
            self.gap_state["stop_loss_price"] = open_price + dynamic_stop_loss_pts
            self.gap_state["open_time_tick"] = 0
            self.gap_state["peak_pnl"] = 0.0
            self.gap_state["trailing_active"] = False
            self.gap_state["liquidity_provided"] = 0
            
            logger.info("⚡ [GAP PROTOCOL TRIGGER] 갭 상승 감지 (Z-Score: +%.2f). 지정가 큐 숏 진입.", z_score)
            signals.append({
                "action": "ENTER_GAP_SHORT",
                "reason": f"Gap Up Z-Score (+{z_score:.2f}) exceeded threshold. Shorting index via Limit Queue.",
                "entry_price": open_price,
                "target_price": self.gap_state["target_price"],
                "stop_loss": self.gap_state["stop_loss_price"],
                "pricing_mode": "MID_PRICE_OFFSET",
                "limit_offset_ticks": 1,
                "fallback_market_timeout_sec": 2.0,
                "qty": 1
            })
            
        # 갭 하락 -> 롱 진입 및 지정가 큐 방출
        else:
            self.gap_state["is_active"] = True
            self.gap_state["direction"] = "LONG"
            self.gap_state["entry_price"] = open_price
            self.gap_state["target_price"] = prev_close_price
            self.gap_state["stop_loss_price"] = open_price - dynamic_stop_loss_pts
            self.gap_state["open_time_tick"] = 0
            self.gap_state["peak_pnl"] = 0.0
            self.gap_state["trailing_active"] = False
            self.gap_state["liquidity_provided"] = 0

            logger.info("⚡ [GAP PROTOCOL TRIGGER] 갭 하락 감지 (Z-Score: %.2f). 지정가 큐 롱 진입.", z_score)
            signals.append({
                "action": "ENTER_GAP_LONG",
                "reason": f"Gap Down Z-Score ({z_score:.2f}) breached threshold. Longing index via Limit Queue.",
                "entry_price": open_price,
                "target_price": self.gap_state["target_price"],
                "stop_loss": self.gap_state["stop_loss_price"],
                "pricing_mode": "MID_PRICE_OFFSET",
                "limit_offset_ticks": 1,
                "fallback_market_timeout_sec": 2.0,
                "qty": 1
            })

        return {"status": "TRIGGERED", "signals": signals}

    def evaluate_mean_reversion(self, current_price: float) -> Dict[str, Any]:
        """
        [진입 후 모니터링: 동적 ATR/VKOSPI 기반 갭 회귀 및 트레일링 익절]
        """
        if not self.gap_state["is_active"]:
            return {"status": "INACTIVE", "signals": []}

        self.gap_state["open_time_tick"] += 1
        direction = self.gap_state["direction"]
        entry = self.gap_state["entry_price"]
        target = self.gap_state["target_price"]
        stop_loss = self.gap_state["stop_loss_price"]
        daily_std_pts = self.gap_state.get("daily_std_pts", 1.5)

        # 동적 변동성 기반 트레일링 가동선 및 반전선 산정
        dynamic_trail_threshold = max(0.3, daily_std_pts * 0.3)
        dynamic_trail_reversal = max(0.1, daily_std_pts * 0.1)

        signals = []
        current_pnl = (entry - current_price) if direction == "SHORT" else (current_price - entry)
        
        if current_pnl > self.gap_state["peak_pnl"]:
            self.gap_state["peak_pnl"] = current_pnl

        # 1. 평균 회귀 타겟 도달 시 지정가 선제 청산 (최우선)
        if (direction == "SHORT" and current_price <= target) or (direction == "LONG" and current_price >= target):
            signals.append({
                "action": "CLOSE_GAP_FUTURES",
                "pricing_mode": "MID_PRICE_OFFSET",
                "limit_offset_ticks": 1,
                "reason": f"Mean reversion target ({target:.2f}) met. Taking final profit via limit order.",
                "pnl": current_pnl,
                "qty": 1
            })
            self.reset_state()
            return {"status": "PROFIT_TAKEN", "signals": signals}

        # 2. 동적 손절선 돌파 시 강제 청산
        if (direction == "SHORT" and current_price >= stop_loss) or (direction == "LONG" and current_price <= stop_loss):
            signals.append({
                "action": "CLOSE_GAP_FUTURES",
                "reason": f"Dynamic stop loss triggered at {stop_loss:.2f}. Cutting losses.",
                "pnl": current_pnl,
                "qty": 1
            })
            self.reset_state()
            return {"status": "STOP_LOSS", "signals": signals}

        # 3. 시간 초과 청산 (15분 경과)
        if self.gap_state["open_time_tick"] >= 30:
            signals.append({
                "action": "CLOSE_GAP_FUTURES",
                "reason": "Timeout (15 minutes elapsed since open). Liquidating remaining gap position.",
                "pnl": current_pnl,
                "qty": 1
            })
            self.reset_state()
            return {"status": "TIMEOUT", "signals": signals}

        # 4. 동적 트레일링 스탑 락인 활성화 (동적 변동성 threshold 이상 이익 시)
        if current_pnl >= dynamic_trail_threshold:
            self.gap_state["trailing_active"] = True

        # 3단계 동적 스케일링 반락 비율 조정 (수익률 크기에 따라 락인 타이트화)
        pnl_ratio = current_pnl / max(0.1, daily_std_pts)
        if pnl_ratio >= 1.0:
            scale_mult = 0.67  # -10% 스케일 타이트
            step_name = "3단계(잭팟 -10% 타이트)"
        elif pnl_ratio >= 0.3:
            scale_mult = 0.80  # -12% 스케일 조임
            step_name = "2단계(-12% 조임)"
        else:
            scale_mult = 1.0   # -15% 기본 유지
            step_name = "1단계(-15% 유지)"

        effective_reversal = dynamic_trail_reversal * scale_mult

        if self.gap_state["trailing_active"] and (self.gap_state["peak_pnl"] - current_pnl >= effective_reversal):
            signals.append({
                "action": "CLOSE_GAP_FUTURES",
                "pricing_mode": "PREEMPTIVE_STOP_LIMIT_QUEUE",
                "limit_offset_ticks": 2,
                "reason": f"🚀 [TRAILING LOCK] 최고 이익(+{self.gap_state['peak_pnl']:.2f}pt) 대비 {step_name} {effective_reversal:.2f}pt 반전 감지. 선제 지정가 익절!",
                "pnl": current_pnl,
                "qty": 1
            })
            self.reset_state()
            return {"status": "TRAILING_PROFIT_LOCK", "signals": signals}

        # 5. 중간 단계 유동성 공급 (Maker Order)
        if current_pnl >= (dynamic_trail_threshold * 0.75) and self.gap_state["liquidity_provided"] == 0:
            self.gap_state["liquidity_provided"] = 1
            signals.append({
                "action": "PROVIDE_LIQUIDITY_LIMIT",
                "reason": "💦 갭 회귀 1차 동적 수익 돌파. 지정가 유동성 공급.",
                "pnl": current_pnl,
                "limit_price": current_price,
                "qty": 1
            })
            return {"status": "LIQUIDITY_PROVISION_1", "signals": signals}

        if current_pnl >= (dynamic_trail_threshold * 1.5) and self.gap_state["liquidity_provided"] == 1:
            self.gap_state["liquidity_provided"] = 2
            signals.append({
                "action": "PROVIDE_LIQUIDITY_LIMIT",
                "reason": "💦 갭 회귀 2차 동적 수익 돌파. 추가 유동성 공급.",
                "pnl": current_pnl,
                "limit_price": current_price,
                "qty": 1
            })
            return {"status": "LIQUIDITY_PROVISION_2", "signals": signals}

        return {"status": "MONITORING", "signals": []}

