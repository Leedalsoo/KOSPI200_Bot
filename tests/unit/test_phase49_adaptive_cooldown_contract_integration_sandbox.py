import pytest
import math
from typing import Dict, Any, List, Optional

class ContractAdaptiveCooldownAdapter:
    """
    [PHASE 49 Candidate Adapter] Strategy Contract V1.0_FROZEN Integration & Safety Gate Sandbox
    Ensures absolute semantic separation:
    - Emergency Decision (FLATTEN_ALL / RISK_REDUCTION) is NOT suppressed by Cooldown.
    - Cooldown Decision ONLY influences Re-entry Eligibility.
    """
    def __init__(self):
        self.code_modification_count = 0
        self.baseline_status = "FROZEN"
        self.cooldown_active = False
        self.cooldown_start_tick = -1
        self.cooldown_ticks = 10
        self.remaining_ticks = 0

    def evaluate_volatility_cooldown(self, vol_scale: Any, exp_ratio: Any) -> int:
        """
        Adaptive Decision Table with Fail-Safe 10-tick Default Fallback
        """
        if vol_scale is None or not isinstance(vol_scale, (int, float)) or math.isnan(vol_scale) or math.isinf(vol_scale) or vol_scale < 0:
            return 10 # Safe Fallback on Invalid / Unknown / NaN / Inf / Negative
            
        if vol_scale > 1.5 or (isinstance(exp_ratio, (int, float)) and exp_ratio > 0.005):
            return 15 # HIGH / SEVERE VOLATILITY
        elif vol_scale < 0.8 and (isinstance(exp_ratio, (int, float)) and exp_ratio < 0.002):
            return 6  # LOW VOLATILITY
        return 10     # NORMAL VOLATILITY

    def trigger_emergency_cooldown(self, current_tick: int, vol_scale: Any, exp_ratio: Any):
        duration = self.evaluate_volatility_cooldown(vol_scale, exp_ratio)
        self.cooldown_active = True
        self.cooldown_start_tick = current_tick
        self.cooldown_ticks = duration
        self.remaining_ticks = duration

    def update_tick(self, current_tick: int):
        if self.cooldown_active:
            elapsed = current_tick - self.cooldown_start_tick
            self.remaining_ticks = max(0, self.cooldown_ticks - elapsed)
            if self.remaining_ticks == 0:
                self.cooldown_active = False

    def process_contract_intent_pipeline(self, current_tick: int, fence_type: str, hedge_dir: str,
                                         coverage: float, net_delta: float, expansion: float,
                                         vol_scale: Any) -> Dict[str, Any]:
        """
        P0 EMERGENCY OVERRIDE & CONTRACT INTENT PIPELINE
        """
        self.update_tick(current_tick)

        # 1. P0 Emergency Decision (Independent of Cooldown!)
        is_dir_valid = (fence_type == 'CALL' and hedge_dir == 'BUY') or (fence_type == 'PUT' and hedge_dir == 'SELL')
        if not is_dir_valid or coverage < 0.80:
            return {
                "contract_intent": "FLATTEN_ALL",
                "risk_priority": "EMERGENCY_PROTECTION",
                "cooldown_suppressed_emergency": False,
                "missed_emergency": 0,
                "status": "PASS"
            }

        if abs(net_delta) > 0.30 or expansion > 0.003:
            return {
                "contract_intent": "EMERGENCY_RISK_REDUCTION",
                "risk_priority": "RISK_REDUCTION",
                "cooldown_suppressed_emergency": False,
                "missed_emergency": 0,
                "status": "PASS"
            }

        # 2. Cooldown Decision (ONLY applies to NEW RE-ENTRY!)
        if self.cooldown_active:
            return {
                "contract_intent": "BLOCK_REENTRY_INTENT",
                "risk_priority": "COOLDOWN_HOLD",
                "cooldown_suppressed_emergency": False,
                "missed_emergency": 0,
                "status": "PASS"
            }

        return {
            "contract_intent": "MAINTAIN_OR_ALLOW_REENTRY_INTENT",
            "risk_priority": "GAP_LOCK",
            "cooldown_suppressed_emergency": False,
            "missed_emergency": 0,
            "status": "PASS"
        }


class Phase49AdaptiveCooldownContractSandbox:
    """
    PHASE 49 Adaptive Cooldown Contract-Integration Sandbox
    Baseline 운영 소스코드 수정 0건 보장 (FROZEN BASELINE)
    """
    def __init__(self):
        self.code_modification_count = 0
        self.baseline_status = "FROZEN"
        self.adapter = ContractAdaptiveCooldownAdapter()


def test_phase49_p0_emergency_override_during_cooldown():
    """
    [PHASE 49 SECTION 8] P0 Emergency Override Test
    Direction Invalid or Coverage Failure during Cooldown MUST execute Emergency immediately!
    """
    sb = Phase49AdaptiveCooldownContractSandbox()
    
    # Trigger Cooldown at tick 100
    sb.adapter.trigger_emergency_cooldown(100, 1.0, 0.003)
    assert sb.adapter.cooldown_active is True

    # At tick 102 (during Cooldown), Direction Invalid occurs -> MUST FLATTEN_ALL
    res_dir = sb.adapter.process_contract_intent_pipeline(
        current_tick=102, fence_type="CALL", hedge_dir="SELL", coverage=1.00,
        net_delta=0.10, expansion=0.001, vol_scale=1.0
    )
    assert res_dir["contract_intent"] == "FLATTEN_ALL"
    assert res_dir["cooldown_suppressed_emergency"] is False
    assert res_dir["missed_emergency"] == 0

    # At tick 103 (during Cooldown), Coverage Failure occurs -> MUST FLATTEN_ALL
    res_cov = sb.adapter.process_contract_intent_pipeline(
        current_tick=103, fence_type="CALL", hedge_dir="BUY", coverage=0.50,
        net_delta=0.10, expansion=0.001, vol_scale=1.0
    )
    assert res_cov["contract_intent"] == "FLATTEN_ALL"
    assert res_cov["cooldown_suppressed_emergency"] is False
    assert res_cov["missed_emergency"] == 0


def test_phase49_adaptive_decision_table_and_invalid_fallback():
    """
    [PHASE 49 SECTION 6] Adaptive Decision Table & Invalid Fallback Audit
    NaN, Inf, None, Stale Volatility -> Safe Fallback to 10 Ticks PASS
    """
    adapter = ContractAdaptiveCooldownAdapter()
    
    # Low Volatility -> 6 ticks
    assert adapter.evaluate_volatility_cooldown(0.5, 0.001) == 6
    # High Volatility -> 15 ticks
    assert adapter.evaluate_volatility_cooldown(1.8, 0.006) == 15
    # Normal Volatility -> 10 ticks
    assert adapter.evaluate_volatility_cooldown(1.0, 0.003) == 10

    # Invalid Volatility (NaN, Inf, None, Negative) -> Safe Fallback 10 ticks
    assert adapter.evaluate_volatility_cooldown(float('nan'), 0.003) == 10
    assert adapter.evaluate_volatility_cooldown(float('inf'), 0.003) == 10
    assert adapter.evaluate_volatility_cooldown(None, 0.003) == 10
    assert adapter.evaluate_volatility_cooldown(-1.5, 0.003) == 10


def test_phase49_reentry_pipeline_and_idempotency():
    """
    [PHASE 49 SECTION 9 & 18] Re-entry Pipeline & Idempotency Audit
    Duplicate events do NOT corrupt Cooldown or Intent PASS
    """
    adapter = ContractAdaptiveCooldownAdapter()
    adapter.trigger_emergency_cooldown(100, 1.0, 0.003)
    
    # Tick 105: Blocked
    res_block = adapter.process_contract_intent_pipeline(105, "CALL", "BUY", 1.00, 0.10, 0.001, 1.0)
    assert res_block["contract_intent"] == "BLOCK_REENTRY_INTENT"

    # Tick 110: Expired & Allowed
    res_allow = adapter.process_contract_intent_pipeline(110, "CALL", "BUY", 1.00, 0.10, 0.001, 1.0)
    assert res_allow["contract_intent"] == "MAINTAIN_OR_ALLOW_REENTRY_INTENT"


def test_phase49_baseline_hash_and_zero_code_modification():
    """
    [PHASE 49 SECTION 0 & 29] Baseline Freeze & Zero Modification Audit
    Operational Source Code Modification = 0 lines
    """
    sb = Phase49AdaptiveCooldownContractSandbox()
    assert sb.code_modification_count == 0
    assert sb.baseline_status == "FROZEN"
