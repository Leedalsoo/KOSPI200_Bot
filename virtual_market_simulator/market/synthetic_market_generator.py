"""Virtual Market Simulator - Synthetic Market Generator & Historical Replay Engine."""
import logging
import random
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class VirtualBrokerConfig:
    """[가상 증권 회사 상황 통제 파라미터 규격]"""
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
    def __init__(self, config: Optional[VirtualBrokerConfig] = None) -> None:
        self.config = config if config is not None else VirtualBrokerConfig()
        logger.info("Virtual Broker Control Interface Initialized in VMS.")

    def get_config(self) -> Dict[str, Any]:
        return self.config.to_dict()

    def update_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        self.config.update_from_dict(updates)
        return self.config.to_dict()

    def reset_to_defaults(self) -> Dict[str, Any]:
        self.config = VirtualBrokerConfig()
        return self.config.to_dict()


class HistoricalReplayEngine:
    """[VMS 소유] 가상 틱/호가 데이터 재생기 (Historical Replay Engine)"""
    def __init__(self, control_interface: Optional[VirtualBrokerControlInterface] = None) -> None:
        self.control = control_interface if control_interface is not None else VirtualBrokerControlInterface()
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
        self.scenario_ticks.clear()
        self.current_idx = 0
        self.is_active = True
        random.seed(42)
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

        if scenario_name in ["COVID_PANIC_2020", "BULL_TREND", "BEAR_TREND", "SIDEWAYS_BOX", "GAP_SPIKE"]:
            base_price = start_price if (start_price is not None and start_price > 0) else 280.0
            if gap_pct != 0.0:
                base_price *= (1.0 + gap_pct)

            for i in range(1, 501):
                if scenario_name == "BULL_TREND":
                    vol_spike = 1.0 * vol_scale
                    price_change = random.uniform(0.1, 0.6)
                elif scenario_name == "BEAR_TREND":
                    vol_spike = 1.2 * vol_scale
                    price_change = random.uniform(-0.6, -0.1)
                elif scenario_name == "SIDEWAYS_BOX":
                    vol_spike = 0.8 * vol_scale
                    price_change = random.uniform(-0.25, 0.25)
                elif scenario_name == "GAP_SPIKE":
                    vol_spike = 2.0 * vol_scale
                    price_change = random.uniform(-1.2, 1.2)
                else: # COVID_PANIC_2020
                    vol_spike = (1.0 + (i / 100.0)) * vol_scale
                    price_change = random.uniform(-0.8, 0.2)

                base_price += price_change
                base_price = max(100.0, round(base_price, 2))

                spread = round(cfg.base_spread * (1.0 + (vol_spike - 1.0) * 0.5), 2)
                spread = max(0.05, min(1.0, spread))
                bid = round(base_price - (spread / 2.0), 2)
                ask = round(base_price + (spread / 2.0), 2)

                self.scenario_ticks.append({
                    "seq": i,
                    "price": base_price,
                    "bid": bid,
                    "ask": ask,
                    "spread": spread,
                    "volatility_index": vol_spike,
                    "active_vol": vol_spike,
                    "scenario": scenario_name,
                    "scenario_name": scenario_name
                })
            self.replay_stats["total_ticks"] = len(self.scenario_ticks)

    def get_next_tick(self) -> Optional[Dict[str, Any]]:
        if not self.is_active or self.current_idx >= len(self.scenario_ticks):
            self.is_active = False
            return None
        tick = self.scenario_ticks[self.current_idx]
        self.current_idx += 1
        self.replay_stats["processed_ticks"] += 1
        return tick

    def next_tick(self) -> Optional[Dict[str, Any]]:
        return self.get_next_tick()


class SyntheticMarketGenerator:
    """[VMS 소유] 가상 실시간 마켓 생성기"""
    def __init__(self, clock: Any, state: Any):
        self.clock = clock
        self.state = state

    def generate_next_tick(self) -> Dict[str, Any]:
        curr_time = self.clock.tick()
        price = self.state.underlying_price
        return {
            "timestamp": curr_time.isoformat(),
            "underlying_price": price,
            "volatility": self.state.volatility,
            "status": "ACTIVE"
        }
