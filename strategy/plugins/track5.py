import logging
import math
from typing import Dict, Any
from strategy.common import TradingDateResetHelper

logger = logging.getLogger(__name__)

class Track5:
    """
    [Track5] Dynamic ATM Strangle & Gap Protocol
    - 자본 배분: 매일 시가 갭 조건 만족 시 +0.1% 동적 부여 및 만기일 세타 수취
    - 역할:
      1. 장 시작 직후(09:00:00) 시초가 괴리(Gap) 회귀 역방향 저격 로직.
      2. 만기일(DTE <= 1) 세타 decay 극대화 Dynamic ATM Strangle 포지션 수취.
      3. IV 급등 및 가두리 3.0pt 이탈 시 손절 및 헷지 전환 방어 가드 작동.
    """
    def __init__(self, config: Dict[str, Any]):
        self.params = config.get("strategies", {}).get("strategy_5", {}).get("params", {})
        # Z-Score 임계치 (기본 1.5 시그마)
        self.z_threshold = self.params.get("z_threshold", 1.5)
        # 옵션 펜스 압축률 (원래 너비에서 좁힐 거리 pt)
        self.fence_compress_pt = self.params.get("fence_compress_pt", 2.5)
        # 갭 회귀 손절선 (포인트 단위: 1.5pt 하드 손절 가드)
        self.stop_loss_pts = self.params.get("stop_loss_pts", 1.5)
        
        self.strangle_active: bool = False
        self.date_reset_helper = TradingDateResetHelper()
        self.reset_state()
        logger.info("Dynamic ATM Strangle & Gap Protocol Strategy (Track5) Initialized.")

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
            "liquidity_provided": 0  # 유동성 공급 분할 청산 단계
        }
        self.strangle_active = False

    def evaluate_gap_divergence(self, open_price: float, prev_close_price: float, active_vol: float, current_regime: str = "NORMAL", date_str: str = "UNKNOWN") -> Dict[str, Any]:
        """
        [Z-Score 기반 시초가 괴리 감지 및 역방향 저격 진입 판단]
        """
        if self.date_reset_helper.check_and_update(date_str):
            self.reset_state()

        if self.gap_state["is_active"]:
            return {"status": "ALREADY_ACTIVE", "signals": []}

        gap_value = open_price - prev_close_price
        
        # 1. 일일 표준편차(Daily Volatility) 산출
        daily_vol_pct = (0.15 / math.sqrt(252)) * active_vol
        daily_std_pts = prev_close_price * daily_vol_pct
        
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

        signals = []
        # 갭 상승 -> 숏 진입 및 콜 펜스 압축
        if z_score > 0:
            self.gap_state["is_active"] = True
            self.gap_state["direction"] = "SHORT"
            self.gap_state["entry_price"] = open_price
            self.gap_state["target_price"] = prev_close_price
            self.gap_state["stop_loss_price"] = open_price + self.stop_loss_pts
            self.gap_state["open_time_tick"] = 0
            self.gap_state["peak_pnl"] = 0.0
            self.gap_state["trailing_active"] = False
            self.gap_state["liquidity_provided"] = 0
            
            logger.info("⚡ [GAP PROTOCOL TRIGGER] 갭 상승 감지 (Z-Score: +%.2f). 숏 포지션 진입.", z_score)
            signals.append({
                "action": "ENTER_GAP_SHORT",
                "reason": f"Gap Up Z-Score (+{z_score:.2f}) exceeded threshold. Shorting index for mean reversion.",
                "entry_price": open_price,
                "target_price": self.gap_state["target_price"],
                "stop_loss": self.gap_state["stop_loss_price"],
                "qty": 1
            })
            
        # 갭 하락 -> 롱 진입 및 풋 펜스 압축
        else:
            self.gap_state["is_active"] = True
            self.gap_state["direction"] = "LONG"
            self.gap_state["entry_price"] = open_price
            self.gap_state["target_price"] = prev_close_price
            self.gap_state["stop_loss_price"] = open_price - self.stop_loss_pts
            self.gap_state["open_time_tick"] = 0
            self.gap_state["peak_pnl"] = 0.0
            self.gap_state["trailing_active"] = False
            self.gap_state["liquidity_provided"] = 0

            logger.info("⚡ [GAP PROTOCOL TRIGGER] 갭 하락 감지 (Z-Score: %.2f). 롱 포지션 진입.", z_score)
            signals.append({
                "action": "ENTER_GAP_LONG",
                "reason": f"Gap Down Z-Score ({z_score:.2f}) breached threshold. Longing index for mean reversion.",
                "entry_price": open_price,
                "target_price": self.gap_state["target_price"],
                "stop_loss": self.gap_state["stop_loss_price"],
                "qty": 1
            })

        return {"status": "TRIGGERED", "signals": signals}

    def evaluate_mean_reversion(self, current_price: float) -> Dict[str, Any]:
        """
        [진입 후 모니터링: 갭 회귀 및 손절/트레일링 익절]
        """
        if not self.gap_state["is_active"]:
            return {"status": "INACTIVE", "signals": []}

        self.gap_state["open_time_tick"] += 1
        direction = self.gap_state["direction"]
        entry = self.gap_state["entry_price"]
        target = self.gap_state["target_price"]
        stop_loss = self.gap_state["stop_loss_price"]

        signals = []
        current_pnl = (entry - current_price) if direction == "SHORT" else (current_price - entry)
        
        if current_pnl > self.gap_state["peak_pnl"]:
            self.gap_state["peak_pnl"] = current_pnl

        # 1. 평균 회귀 타겟 도달 시 익절 청산 (최우선)
        if (direction == "SHORT" and current_price <= target) or (direction == "LONG" and current_price >= target):
            signals.append({
                "action": "CLOSE_GAP_FUTURES",
                "reason": f"Mean reversion target ({target:.2f}) met. Taking final profit.",
                "pnl": current_pnl,
                "qty": 1
            })
            self.reset_state()
            return {"status": "PROFIT_TAKEN", "signals": signals}

        # 2. 손절선 돌파 시 강제 청산
        if (direction == "SHORT" and current_price >= stop_loss) or (direction == "LONG" and current_price <= stop_loss):
            signals.append({
                "action": "CLOSE_GAP_FUTURES",
                "reason": f"Stop loss triggered at {stop_loss:.2f}. Cutting losses.",
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

        # 4. 트레일링 스탑 락인 활성화 (+0.4pt 이상 이익 및 0.15pt 반전)
        if current_pnl >= 0.4:
            self.gap_state["trailing_active"] = True

        if self.gap_state["trailing_active"] and (self.gap_state["peak_pnl"] - current_pnl >= 0.15):
            signals.append({
                "action": "CLOSE_GAP_FUTURES",
                "reason": f"🚀 [TRAILING LOCK] 최고 이익(+{self.gap_state['peak_pnl']:.2f}pt) 대비 0.15pt 반전 감지. 시장가 익절!",
                "pnl": current_pnl,
                "qty": 1
            })
            self.reset_state()
            return {"status": "TRAILING_PROFIT_LOCK", "signals": signals}

        # 5. 중간 단계 유동성 공급 (Maker Order)
        if current_pnl >= 0.3 and self.gap_state["liquidity_provided"] == 0:
            self.gap_state["liquidity_provided"] = 1
            signals.append({
                "action": "PROVIDE_LIQUIDITY_LIMIT",
                "reason": "💦 갭 회귀 1차 수익(+0.3pt 돌파). 지정가 유동성 공급.",
                "pnl": current_pnl,
                "limit_price": current_price,
                "qty": 1
            })
            return {"status": "LIQUIDITY_PROVISION_1", "signals": signals}

        if current_pnl >= 0.6 and self.gap_state["liquidity_provided"] == 1:
            self.gap_state["liquidity_provided"] = 2
            signals.append({
                "action": "PROVIDE_LIQUIDITY_LIMIT",
                "reason": "💦 갭 회귀 2차 수익(+0.6pt 돌파). 추가 유동성 공급.",
                "pnl": current_pnl,
                "limit_price": current_price,
                "qty": 1
            })
            return {"status": "LIQUIDITY_PROVISION_2", "signals": signals}

        return {"status": "MONITORING", "signals": []}


    def evaluate_atm_strangle_decay(self, market_data: Dict[str, Any], days_to_expiry: float) -> Dict[str, Any]:
        """
        [Dynamic ATM Strangle 세타 Decay 수취 및 방어 로직]
        - 만기일(DTE <= 1) 세타 decay 극대화 스트랭글 포지션 구축.
        - Track 5 전용 손익/수수료 스코프 키 우선 참조.
        - IV 급등(iv_spike > 5.0) 또는 3.0pt 이탈 시 손절/헷지 전환.
        """
        date_str = market_data.get("date_str", "UNKNOWN")
        if self.date_reset_helper.check_and_update(date_str):
            self.reset_state()

        # 🛡️ [스코프 격리] Track 5 전용 키 우선 참조
        raw_pnl = market_data.get("track5_current_pnl") if market_data.get("track5_current_pnl") is not None else market_data.get("current_pnl", 0.0)
        raw_fees = market_data.get("track5_total_fees") if market_data.get("track5_total_fees") is not None else market_data.get("total_fees", 0.0)
        current_pnl: float = float(raw_pnl or 0.0)
        total_fees: float = float(raw_fees or 0.0)
        
        iv_spike = float(market_data.get("iv_spike", 0.0))
        price_displacement = float(market_data.get("price_displacement", 0.0))
        
        signals = []

        # 1. 만기일(DTE <= 1) 세타 수취 스트랭글 구축
        if days_to_expiry <= 1.0 and not self.strangle_active:
            if iv_spike <= 3.0:
                self.strangle_active = True
                signals.append({
                    "action": "BUILD_ATM_STRANGLE",
                    "reason": f"DTE ({days_to_expiry:.1f} <= 1.0) Theta decay harvest zone. Selling ATM Strangle.",
                    "qty": 1
                })
                return {"status": "STRANGLE_BUILT", "signals": signals}

        # 2. 보유 중일 때 방어 및 손절 조건 검증
        if self.strangle_active:
            # IV 급등(iv_spike > 5.0) 또는 가격 극단 이탈(|displacement| >= 3.0pt) 시 손절
            if iv_spike > 5.0 or abs(price_displacement) >= 3.0:
                self.strangle_active = False
                signals.append({
                    "action": "CLOSE_ATM_STRANGLE",
                    "reason": f"IV Spike ({iv_spike:.1f}) or Price Breach ({price_displacement:.2f}pt). Closing Strangle & Hedging.",
                    "qty": 1
                })
                return {"status": "STRANGLE_STOP_LOSS", "signals": signals}
                
            # 수수료 방어 조기 익절
            if total_fees > 0 and current_pnl >= total_fees * 1.2:
                self.strangle_active = False
                signals.append({
                    "action": "CLOSE_ATM_STRANGLE",
                    "reason": f"Fee cover profit lock triggered (PnL: ₩{current_pnl:,.0f} >= 1.2x Fees).",
                    "qty": 1
                })
                return {"status": "STRANGLE_CLOSED", "signals": signals}

        return {"status": "HOLD", "signals": []}

