"""VMS State Manager and Scenario Engine."""
from typing import Dict, Any, List

class VMSStateManager:
    """[VMS 상태 관리자: 마켓 시율레이션 스냅샷 및 틱 시퀀스 소유]"""
    def __init__(self):
        self.sequence_id: int = 0
        self.active_regime: str = "NORMAL"

    def next_sequence(self) -> int:
        self.sequence_id += 1
        return self.sequence_id

    def set_regime(self, regime: str) -> None:
        self.active_regime = regime

class ScenarioEngine:
    """[VMS 시나리오 엔진: 갭/변동성 폭발 시나리오 주입]"""
    def __init__(self):
        self.active_scenario: str = "DEFAULT"

    def apply_scenario(self, scenario_name: str) -> Dict[str, Any]:
        self.active_scenario = scenario_name
        if scenario_name == "BLACK_SWAN_GAP_DOWN":
            return {"price_offset": -15.0, "vol_multiplier": 2.5}
        elif scenario_name == "VOLATILITY_SPIKE":
            return {"price_offset": 0.0, "vol_multiplier": 3.0}
        return {"price_offset": 0.0, "vol_multiplier": 1.0}
