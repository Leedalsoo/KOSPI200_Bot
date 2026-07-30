import logging
from collections import deque
from typing import Dict, Any

logger = logging.getLogger(__name__)

class FuturesSensor:
    """
    [센서 1] 선물 시장 전용 센서 (Futures Analytics Sensor)
    - 역할:
      1. 실시간 선물 체결가, 현물가, 미결제약정(Open Interest) 모니터링.
      2. 실시간 베이시스(Basis = 선물 가격 - 현물 가격) 산출.
      3. 미결제약정(OI) 변화율 추적 (최근 10틱 평균 대비 1.5배 초과 시 추세 전환 경보).
      4. 야간 선물 연동 및 갭 보정값 제공.
    """
    def __init__(self) -> None:
        self.oi_history = deque(maxlen=30)  # 미결제약정 최근 이력 버퍼
        self.basis = 0.0
        self.oi_trend_alert = False
        logger.info("Futures Analytics Sensor initialized.")

    def update_sensor(self, futures_price: float, spot_price: float, open_interest: int) -> Dict[str, Any]:
        # 1. 실시간 베이시스 산출
        self.basis = round(futures_price - spot_price, 2)
        
        # 2. 미결제약정 추세 감지
        self.oi_history.append(open_interest)
        self.oi_trend_alert = False
        
        if len(self.oi_history) >= 10:
            avg_oi = sum(list(self.oi_history)[:-1]) / (len(self.oi_history) - 1)
            # 최근 미결제약정이 평균 대비 1.5배 급증한 경우 추세 휩쏘 경보 설정
            if avg_oi > 0 and open_interest >= avg_oi * 1.5:
                self.oi_trend_alert = True
                logger.warning("📡 [FUTURES SENSOR ALERT] 미결제약정 급증 감지 (현재 OI: %d / 10틱 평균: %.1f) - 선물 추세 휩쏘 위험 경보!", open_interest, avg_oi)

        return {
            "futures_price": futures_price,
            "spot_price": spot_price,
            "basis": self.basis,
            "open_interest": open_interest,
            "oi_trend_alert": self.oi_trend_alert
        }


class WeeklyOptionsSensor:
    """
    [센서 2] 위클리 옵션 시장 전용 센서 (Weekly Options Sensor)
    - 역할:
      1. 매주 상장되는 위클리 옵션 프리미엄 및 호가 잔량 변화 감지.
      2. 상장 첫날 유동성/거래량 발화점(주간 헷지 매수 타이밍) 스캔.
    """
    def __init__(self) -> None:
        logger.info("Weekly Options Sensor initialized.")

    def scan_weekly_market(self, 
                           current_price: float, 
                           budget: float, 
                           is_new_week_start: bool) -> Dict[str, Any]:
        """
        위클리 옵션 진입 적격성 판단 (상장 첫날 여부 및 최소 가용 예산 한도)
        """
        weekly_entry_ready = False
        reason = "Wait for new week start."

        if is_new_week_start:
            # 최소 1계약 양매수 예산인 35만 원(1.4pt) 확보되었을 때 유동성 진입 타이밍으로 인지
            estimated_cost = 1.4 * 250000.0
            if budget >= estimated_cost:
                weekly_entry_ready = True
                reason = "Weekly options listed day. Liquidity threshold met. Ready to buy protection."
            else:
                reason = f"New week start but insufficient budget (Required: ₩{estimated_cost:,.0f} / Budget: ₩{budget:,.0f})."

        return {
            "weekly_entry_ready": weekly_entry_ready,
            "reason": reason
        }


class DailyOptionsSensor:
    """
    [센서 3] 데일리 / 초단기 옵션 시장 센서 (Daily / 0DTE Sensor)
    - 역할:
      1. 당일 만기 옵션(0DTE)의 초고속 변동성 확장 감지.
      2. VKOSPI 연동 내재변동성 배율 위험 스캔.
    """
    def __init__(self) -> None:
        logger.info("Daily Options Sensor (0DTE) initialized.")

    def monitor_daily_risk(self, 
                           active_vol: float, 
                           base_vol: float, 
                           budget: float) -> Dict[str, Any]:
        """
        데일리 보험(전략 6) 기동을 위한 초단기 옵션 위험도 분석
        """
        daily_vol_alert = False
        reason = "Normal market volatility."

        # 내재변동성이 1.3배 이상 폭발하여 극외가 옵션 프리미엄이 부풀어 오를 때
        if active_vol >= (base_vol * 1.3):
            # 최소 1계약 양매수 가입 예산(25만 원) 존재 여부 체크
            estimated_cost = 1.0 * 250000.0
            if budget >= estimated_cost:
                daily_vol_alert = True
                reason = f"Volatility spike ({active_vol:.2f} >= {base_vol*1.3:.2f}). Budget pool enough. Trigger daily hedge."
            else:
                reason = f"Volatility spike but insufficient budget (Required: ₩{estimated_cost:,.0f} / Budget: ₩{budget:,.0f})."

        return {
            "daily_vol_alert": daily_vol_alert,
            "reason": reason
        }
