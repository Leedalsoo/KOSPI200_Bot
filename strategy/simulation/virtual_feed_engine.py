import logging
import random
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from virtual_market_simulator.runtime.simulator_runtime import VirtualMarketSimulatorRuntime
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime

logger = logging.getLogger(__name__)

@dataclass
class VirtualBrokerConfig:
    """
    [가상 증권 회사 상황 통제 파라미터 규격]
    - 사용자가 시뮬레이션 환경을 제어할 수 있는 최소한의 가상 파라미터 인터페이스
    """
    replay_speed: int = 1                  # 시뮬레이션 배속 (1x, 300x, 1000x)
    slippage_multiplier: float = 1.0        # 슬리피지 배수 (0.5x ~ 3.0x)
    fee_rate_multiplier: float = 1.0        # 수수료율 배수 (0.5x ~ 2.0x)
    volatility_scale: float = 1.0           # 시장 변동성 세기 (0.5x ~ 3.0x)
    scenario_name: str = "COVID_PANIC_2020" # 재생 시나리오 명칭
    gap_pct: float = 0.0                    # 시초가 갭 비율 (-0.02 ~ +0.02)
    base_spread: float = 0.05               # 기본 호가 스프레드 (pt)
    latency_ms: int = 50                    # 네트워크 체결 지연 (ms)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "replay_speed": self.replay_speed,
            "slippage_multiplier": self.slippage_multiplier,
            "fee_rate_multiplier": self.fee_rate_multiplier,
            "volatility_scale": self.volatility_scale,
            "scenario_name": self.scenario_name,
            "gap_pct": self.gap_pct,
            "base_spread": self.base_spread,
            "latency_ms": self.latency_ms
        }

    def update_from_dict(self, updates: Dict[str, Any]) -> None:
        if "replay_speed" in updates:
            spd = int(updates["replay_speed"])
            self.replay_speed = spd if spd in [1, 300, 1000] else spd
        if "slippage_multiplier" in updates:
            val = float(updates["slippage_multiplier"])
            self.slippage_multiplier = max(0.5, min(3.0, val))
        if "fee_rate_multiplier" in updates:
            val = float(updates["fee_rate_multiplier"])
            self.fee_rate_multiplier = max(0.5, min(2.0, val))
        if "volatility_scale" in updates:
            val = float(updates["volatility_scale"])
            self.volatility_scale = max(0.5, min(3.0, val))
        if "scenario_name" in updates:
            self.scenario_name = str(updates["scenario_name"])
        if "gap_pct" in updates:
            val = float(updates["gap_pct"])
            self.gap_pct = max(-0.02, min(0.02, val))
        if "base_spread" in updates:
            self.base_spread = float(updates["base_spread"])
        if "latency_ms" in updates:
            self.latency_ms = int(updates["latency_ms"])


class VirtualBrokerControlInterface:
    """
    [가상 증권 회사 사용자 파라미터 조율 및 상황 제어 인터페이스]
    """
    def __init__(self, config: Optional[VirtualBrokerConfig] = None) -> None:
        self.config = config if config is not None else VirtualBrokerConfig()
        logger.info("Virtual Broker Control Interface Initialized.")

    def get_config(self) -> Dict[str, Any]:
        return self.config.to_dict()

    def update_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        self.config.update_from_dict(updates)
        logger.info("🎛️ [VIRTUAL BROKER CONTROL] 가상 환경 파라미터 업데이트 완료: %s", self.config.to_dict())
        return self.config.to_dict()

    def reset_defaults(self) -> Dict[str, Any]:
        self.config = VirtualBrokerConfig()
        logger.info("🔄 [VIRTUAL BROKER CONTROL] 가상 환경 파라미터 기본값 초기화.")
        return self.config.to_dict()


class HistoricalReplayEngine:
    """
    [축 1] 가상 틱/호가 데이터 재생기 (Historical Replay Engine)
    - 역할: 과거 역사적 대폭락 장세 및 변동성 폭발 구간 틱을 재현하여 공급
    """
    def __init__(self, control_interface: Optional[VirtualBrokerControlInterface] = None) -> None:
        self.control = control_interface if control_interface is not None else VirtualBrokerControlInterface()
        self.vms_runtime = VirtualMarketSimulatorRuntime(time_scale=float(self.control.config.replay_speed))
        self.scenario_ticks: List[Dict[str, Any]] = []
        self.current_idx = 0
        self.is_active = False
        self.replay_stats: Dict[str, int] = {
            "total_ticks": 0,
            "processed_ticks": 0,
            "skipped_ticks": 0,
            "duplicate_ticks": 0,
            "sequence_errors": 0,
            "timestamp_errors": 0,
            "invalid_price_ticks": 0,
            "missing_field_ticks": 0
        }

    def load_scenario(self, scenario_name: str, start_price: Optional[float] = None) -> None:
        """
        특정 과거 폭락장 및 변동성 폭발 시나리오 틱 로딩 모사 (start_price 제공 시 연속 승계)
        """
        self.scenario_ticks.clear()
        self.current_idx = 0
        self.is_active = True
        random.seed(42)  # 🎲 시나리오 재생 재현성 보장용 시드 고정
        self.replay_stats = {
            "total_ticks": 0,
            "processed_ticks": 0,
            "skipped_ticks": 0,
            "duplicate_ticks": 0,
            "sequence_errors": 0,
            "timestamp_errors": 0,
            "invalid_price_ticks": 0,
            "missing_field_ticks": 0
        }
        
        cfg = self.control.config
        vol_scale = cfg.volatility_scale
        gap_pct = cfg.gap_pct

        # 1. 2020년 3월 코로나 팬데믹 서킷브레이커 폭락장 모사 시나리오 틱 생성
        if scenario_name in ["COVID_PANIC_2020", "BULL_TREND", "BEAR_TREND", "SIDEWAYS_BOX", "GAP_SPIKE"]:
            logger.info("🎬 [REPLAY ENGINE] %s 시나리오 로딩 (변동성 스케일: %.1fx, 갭: %.2f%%)...", scenario_name, vol_scale, gap_pct * 100)
            base_price = start_price if (start_price is not None and start_price > 0) else 280.0
            
            # 시초가 갭 반영
            if gap_pct != 0.0:
                base_price *= (1.0 + gap_pct)

            for i in range(1, 501):
                if scenario_name == "BULL_TREND":
                    vol_spike = 1.0 * vol_scale
                    price_change = random.uniform(0.1, 0.6)
                elif scenario_name == "BEAR_TREND":
                    vol_spike = 1.8 * vol_scale
                    price_change = random.uniform(-0.6, -0.1)
                elif scenario_name == "SIDEWAYS_BOX":
                    vol_spike = 0.8 * vol_scale
                    price_change = random.uniform(-0.15, 0.15)
                else: # COVID_PANIC_2020 or GAP_SPIKE
                    vol_spike = (1.0 if i < 100 else (3.0 if i < 300 else 5.0)) * vol_scale
                    price_change = 0.0 if i < 100 else (random.uniform(-1.5, -0.2) if i < 300 else random.uniform(-0.5, 0.5))

                base_price += price_change
                
                self.scenario_ticks.append({
                    "seq": i,
                    "price": round(base_price, 2),
                    "active_vol": vol_spike,
                    "regime": "HIGH_VOL" if vol_spike > 2.0 else "NORMAL"
                })
        else:
            logger.warning("⚠️ [REPLAY ENGINE] 알 수 없는 시나리오 명칭: %s. 기본 모의 틱 모사로 대체합니다.", scenario_name)
            self.is_active = False

    def next_tick(self) -> Optional[Dict[str, Any]]:
        if not self.is_active or not self.scenario_ticks:
            return None
        
        if self.current_idx >= len(self.scenario_ticks):
            logger.info("🏁 [REPLAY ENGINE] 시나리오 틱 재생 완료.")
            self.is_active = False
            return None
            
        tick_data = self.scenario_ticks[self.current_idx]
        self.current_idx += 1
        return tick_data


class SlippageEngine:
    """
    [축 2] 가상 슬리피지와 체결 시뮬레이터 (Mock Broker & Slippage Engine)
    - 역할:
      1. 주문 수량, bidAskSpread, active_vol을 연동한 체결 오차 확률 모델링.
      2. 주문 방향에 따라 체결 가격 페널티 보정 (매수는 비싸게 가산, 매도는 싸게 감산).
      3. 가혹한 렉 상황을 모사하여 0.05pt ~ 0.50pt 범위 체결 오차 발생.
      4. VirtualBrokerControlInterface를 통한 슬리피지 배수 조절.
    """
    def __init__(self, control_interface: Optional[VirtualBrokerControlInterface] = None) -> None:
        self.control = control_interface if control_interface is not None else VirtualBrokerControlInterface()
        logger.info("Slippage Engine (체결 밀림 확률 모델) initialized.")

    def apply_slippage(self, 
                       side: str, 
                       requested_price: float, 
                       qty: int, 
                       active_vol: float, 
                       spread: float) -> Dict[str, Any]:
        """
        체결가 슬리피지 및 지연 딜레이 연산 (슬리피지 배수 반영)
        """
        cfg = self.control.config
        slip_mult = cfg.slippage_multiplier
        effective_spread = spread if spread > 0 else cfg.base_spread
        
        # 기본 슬리피지: 스프레드의 30% 수준 * 슬리피지 배수
        base_slippage = effective_spread * 0.3 * slip_mult
        
        # 변동성 및 수량 비례 체결가 패널티 가산
        vol_impact = (active_vol - 1.0) * 0.08 * slip_mult if active_vol > 1.0 else 0.0
        qty_impact = (qty * 0.01) * slip_mult  # 대량 주문일수록 밀림 가중
        
        total_slippage = round(base_slippage + vol_impact + qty_impact + random.uniform(0.01, 0.05), 2)
        total_slippage = min(1.0, max(0.01, total_slippage))  # 0.01pt ~ 1.0pt 범위 락다운
        
        # 체결 지연 딜레이 (ms)
        delay_ms = int(cfg.latency_ms + (active_vol * 80) + (qty * 5) + random.randint(10, 50))
        delay_ms = min(3000, delay_ms)  # 최대 3초 제한
        
        # 체결 가격 결정
        final_execution_price = requested_price
        if side == "BUY":
            final_execution_price += total_slippage
        elif side == "SELL":
            final_execution_price -= total_slippage
            
        final_execution_price = round(final_execution_price, 2)
        
        logger.info("📡 [SLIPPAGE ENGINE] 체결가 보정 집행 (%s) - 요청가: %.2f | 체결가: %.2f | 오차: -%.2fpt | 딜레이: %d ms (배수: %.1fx)",
                    side, requested_price, final_execution_price, total_slippage, delay_ms, slip_mult)
                    
        return {
            "execution_price": final_execution_price,
            "slippage_pts": total_slippage,
            "delay_ms": delay_ms
        }


class PaperTradingAccount:
    """
    [축 3] 페이퍼 트레이딩(Paper Trading) 모드 — 실시간 가상 구동 계정
    - 역할: 가상 계좌 장부 상태를 틱 단위로 관리하며 시스템 총 자산 평가
    """
    def __init__(self, initial_capital: float = 25000000.0):
        self.capital = initial_capital
        self.reserve = 0.0
        self.total_equity = initial_capital
        self.orders_history: List[Dict[str, Any]] = []
        self.firm_runtime = VirtualSecuritiesFirmRuntime(symbol="KOSPI200_OPT")
        self.firm_runtime.account.total_balance = initial_capital
        logger.info("Paper Trading Account initialized with Target VSSF Runtime. Initial capital: ₩%s", f"{initial_capital:,.0f}")

    def update_equity(self, 
                      current_price: float, 
                      position_qty: int, 
                      portfolio_options: List[Dict[str, Any]], 
                      multiplier_futures: float = 50000.0, 
                      multiplier_options: float = 250000.0) -> float:
        """
        선물 포지션 평가 금액 및 옵션 평가 금액을 종합해 총자산 산출
        """
        futures_valuation = position_qty * current_price * multiplier_futures
        options_valuation = sum(
            int(pos.get("qty", 0)) * float(pos.get("price", 0.0)) * multiplier_options
            for pos in portfolio_options
        )
        self.total_equity = self.capital + self.reserve + futures_valuation + options_valuation
        return self.total_equity

