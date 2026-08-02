import logging
import math
from typing import Dict, Any

logger = logging.getLogger(__name__)

class GapProtocolStrategy:
    """
    [전략 5] Gap Protocol: 시가 괴리 회귀 저격 로직 (Track 5 Gap Protocol)
    - 자본 배분: 매일 시가 갭 조건 만족 시 +0.1% 동적 부여
    - 역할:
      1. 장 시작 직후(09:00:00) 시초가가 전일 종가 대비 과도하게 괴리(Gap)되어 시작할 때 발동.
      2. 통계적 괴리율(Z-Score)을 연산하여 임계점(1.5 시그마) 초과 시 진입.
      3. 역방향 선물 포지션(롱 또는 숏)을 진입하여 평균 회귀를 겨냥.
      4. 동시에 당일 ATM 기준 옵션 매도 가두리 펜스를 타이트하게(더 가깝게) 압축해 프리미엄 수취 폭 극대화.
      5. 장 개장 후 10~15분 내(09:15 이전) 지수가 전일 종가(괴리 0선)로 회귀 시 선물 청산(익절) 및 옵션 펜스 원복.
      6. 만약 갭이 메워지지 않고 추세적으로 뻗어나갈 때를 대비한 정교한 손절 가드 작동.
    """
    def __init__(self, config: Dict[str, Any]):
        self.params = config.get("strategies", {}).get("strategy_5", {}).get("params", {})
        # Z-Score 임계치 (기본 1.5 시그마)
        self.z_threshold = self.params.get("z_threshold", 1.5)
        # 옵션 펜스 압축률 (원래 너비에서 좁힐 거리 pt)
        self.fence_compress_pt = self.params.get("fence_compress_pt", 2.5)
        # 갭 회귀 손절선 (포인트 단위: 1.5pt 하드 손절 가드)
        self.stop_loss_pts = self.params.get("stop_loss_pts", 1.5)
        
        self.reset_state()
        logger.info("Gap Protocol Strategy (Strategy 5) Initialized.")

    def reset_state(self) -> None:
        self.gap_state: Dict[str, Any] = {
            "is_active": False,
            "direction": None,       # "SHORT" (갭상승 대응) 또는 "LONG" (갭하락 대응)
            "entry_price": 0.0,
            "target_price": 0.0,     # 평균 회귀 목표가 (괴리 0선 = 전일 종가)
            "stop_loss_price": 0.0,
            "open_time_tick": 0,     # 장 시작 후 경과 틱 카운트
            "peak_pnl": 0.0,         # 🚀 달성된 최고 PnL (pt)
            "trailing_active": False,# 🚀 동적 트레일링 스탑 활성화 여부
            "liquidity_provided": 0  # 💦 유동성 공급으로 분할 청산된 횟수/단계
        }

    def evaluate_gap_divergence(self, open_price: float, prev_close_price: float, active_vol: float, current_regime: str = "NORMAL") -> Dict[str, Any]:
        """
        [Z-Score 기반 시초가 괴리 감지 및 역방향 저격 진입 판단]
        - 장세 판단(Regime)에 따라 Z-Score 임계치를 자율 가변 조절:
          1) HIGH_VOL / NOISE_CHOPPY: 노이즈 방어를 위해 1.8 시그마로 신중하게 진입
          2) NORMAL / NEUTRAL: 변동성 침체기 갭 회귀 기회 포획을 위해 1.1 시그마로 완화
        """
        if self.gap_state["is_active"]:
            return {"status": "ALREADY_ACTIVE", "signals": []}

        gap_value = open_price - prev_close_price
        
        # 1. 일일 표준편차(Daily Volatility) 산출 (연율 15% 변동성을 252 영업일 기준으로 일일 환산)
        daily_vol_pct = (0.15 / math.sqrt(252)) * active_vol
        daily_std_pts = prev_close_price * daily_vol_pct
        
        # 2. 괴리 Z-Score 산출
        z_score = gap_value / max(0.1, daily_std_pts)

        # 3. 장세 판단(Regime)에 따른 동적 Z-Score 임계치 결정
        if current_regime in ["HIGH_VOL", "NOISE_CHOPPY", "CIRCUIT_BREAKER"]:
            effective_z = 1.8  # 고변동성 장세: 신중한 저격 (1.8 시그마)
        elif current_regime in ["NORMAL", "NEUTRAL"]:
            effective_z = 1.1  # 평온 장세: 매매 기회 포획 확대 (1.1 시그마)
        else:
            effective_z = self.z_threshold

        if abs(z_score) < effective_z:
            return {"status": "NO_TRIGGER", "signals": [], "z_score": z_score, "effective_z": effective_z}


        signals = []
        # 갭 상승 (Z-Score > +1.5) -> 숏 진입 및 콜 펜스 압축
        if z_score > 0:
            self.gap_state["is_active"] = True
            self.gap_state["direction"] = "SHORT"
            self.gap_state["entry_price"] = open_price
            self.gap_state["target_price"] = prev_close_price  # 괴리 0선으로 정확히 고정
            self.gap_state["stop_loss_price"] = open_price + self.stop_loss_pts
            self.gap_state["open_time_tick"] = 0
            self.gap_state["peak_pnl"] = 0.0
            self.gap_state["trailing_active"] = False
            self.gap_state["liquidity_provided"] = 0
            
            logger.info("⚡ [GAP PROTOCOL TRIGGER] 갭 상승 감지 (Z-Score: +%.2f). 숏 포지션 진입 및 동적 트레일링 익절 대기.", z_score)
            signals.append({
                "action": "ENTER_GAP_SHORT",
                "reason": f"Gap Up Z-Score (+{z_score:.2f}) exceeded threshold. Shorting index for mean reversion.",
                "entry_price": open_price,
                "target_price": self.gap_state["target_price"],
                "stop_loss": self.gap_state["stop_loss_price"]
            })
            
        # 갭 하락 (Z-Score < -1.5) -> 롱 진입 및 풋 펜스 압축 (보호 중심)
        else:
            self.gap_state["is_active"] = True
            self.gap_state["direction"] = "LONG"
            self.gap_state["entry_price"] = open_price
            self.gap_state["target_price"] = prev_close_price  # 괴리 0선으로 정확히 고정
            self.gap_state["stop_loss_price"] = open_price - self.stop_loss_pts
            self.gap_state["open_time_tick"] = 0
            self.gap_state["peak_pnl"] = 0.0
            self.gap_state["trailing_active"] = False
            self.gap_state["liquidity_provided"] = 0

            logger.info("⚡ [GAP PROTOCOL TRIGGER] 갭 하락 감지 (Z-Score: %.2f). 롱 포지션 진입 (양방향 익절 대기).", z_score)
            signals.append({
                "action": "ENTER_GAP_LONG",
                "reason": f"Gap Down Z-Score ({z_score:.2f}) breached threshold. Longing index for mean reversion.",
                "entry_price": open_price,
                "target_price": self.gap_state["target_price"],
                "stop_loss": self.gap_state["stop_loss_price"]
            })

        return {"status": "TRIGGERED", "signals": signals}

    def evaluate_mean_reversion(self, current_price: float) -> Dict[str, Any]:
        """
        [진입 후 모니터링: 갭하락 계좌 보호 vs 갭상승 최고점 익절 트레일링 락인]
        """
        if not self.gap_state["is_active"]:
            return {"status": "INACTIVE", "signals": []}

        self.gap_state["open_time_tick"] += 1
        direction = self.gap_state["direction"]
        entry = self.gap_state["entry_price"]
        target = self.gap_state["target_price"]
        stop_loss = self.gap_state["stop_loss_price"]

        signals = []

        # ── 🚀 [양방향: 최고점 동적 트레일링 익절 및 유동성 공급 (Liquidity Provision & Trailing Profit Lock)] ──
        current_pnl = (entry - current_price) if direction == "SHORT" else (current_price - entry)
        
        if current_pnl > self.gap_state["peak_pnl"]:
            self.gap_state["peak_pnl"] = current_pnl
        
        # 1. 💦 [유동성 공급 (Maker Order)] 일정 수익 구간마다 호가에 지정가를 깔아 분할 익절 시도 (가상 신호)
        if current_pnl >= 0.3 and self.gap_state["liquidity_provided"] == 0:
            self.gap_state["liquidity_provided"] = 1
            signals.append({
                "action": "PROVIDE_LIQUIDITY_LIMIT",
                "reason": f"💦 [LIQUIDITY PROVISION] 갭 회귀 1차 수익(+0.3pt 돌파). 지정가(Maker) 매수/매도 대기로 유동성 공급 및 분할 수익 수취 시작.",
                "pnl": current_pnl,
                "limit_price": current_price
            })
            return {"status": "LIQUIDITY_PROVISION_1", "signals": signals}

        if current_pnl >= 0.6 and self.gap_state["liquidity_provided"] == 1:
            self.gap_state["liquidity_provided"] = 2
            signals.append({
                "action": "PROVIDE_LIQUIDITY_LIMIT",
                "reason": f"💦 [LIQUIDITY PROVISION] 갭 회귀 2차 수익(+0.6pt 돌파). 지정가(Maker)로 추가 유동성 공급 및 분할 수익 수취.",
                "pnl": current_pnl,
                "limit_price": current_price
            })
            return {"status": "LIQUIDITY_PROVISION_2", "signals": signals}

        # +0.4pt 이상 이익 구간 진입 시 트레일링 스탑 락인 활성화
        if current_pnl >= 0.4:
            self.gap_state["trailing_active"] = True

        # 최고 달성 수익점 대비 0.15pt 눌림/반등 시 최고 수익 가격에서 남은 물량 즉시 익절 (Taker)
        if self.gap_state["trailing_active"] and (self.gap_state["peak_pnl"] - current_pnl >= 0.15):
            signals.append({
                "action": "CLOSE_GAP_FUTURES",
                "reason": f"🚀 [TRAILING LOCK] 최고 이익(+{self.gap_state['peak_pnl']:.2f}pt) 대비 0.15pt 반전 감지. 남은 물량 즉각 시장가 익절 락인!",
                "pnl": current_pnl
            })
            self.reset_state()
            return {"status": "TRAILING_PROFIT_LOCK", "signals": signals}

        # 2. 평균 회귀 타겟 도달 시 익절 청산 (괴리 0선)
        if (direction == "SHORT" and current_price <= target) or (direction == "LONG" and current_price >= target):
            signals.append({
                "action": "CLOSE_GAP_FUTURES",
                "reason": f"Mean reversion target ({target:.2f}) met. Taking final profit.",
                "pnl": current_pnl
            })
            self.reset_state()
            return {"status": "PROFIT_TAKEN", "signals": signals}

        # 3. 손절선 돌파 시 강제 청산
        if (direction == "SHORT" and current_price >= stop_loss) or (direction == "LONG" and current_price <= stop_loss):
            signals.append({
                "action": "CLOSE_GAP_FUTURES",
                "reason": f"Stop loss triggered at {stop_loss:.2f}. Cutting losses.",
                "pnl": current_pnl
            })
            self.reset_state()
            return {"status": "STOP_LOSS", "signals": signals}

        # 4. 시간 초과 청산 (예: 15분 경과 = 1틱 30초 시뮬레이터 상 30틱 경과)
        if self.gap_state["open_time_tick"] >= 30:
            signals.append({
                "action": "CLOSE_GAP_FUTURES",
                "reason": "Timeout (15 minutes elapsed since open). Liquidating remaining gap position.",
                "pnl": current_pnl
            })
            self.reset_state()
            return {"status": "TIMEOUT", "signals": signals}

        return {"status": "MONITORING", "signals": []}
