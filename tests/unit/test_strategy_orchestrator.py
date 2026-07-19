import numpy as np
from typing import Dict, Any
from strategy.orchestrator import StrategyOrchestrator

def test_active_weights_reference_preservation() -> None:
    """[목표 A 검증] 딕셔너리 업데이트 시 메모리 주소가 변경되지 않고 참조가 유지됨을 100% 증명"""
    ctx: Dict[str, Any] = {"active_weights": {"old_strat": 1.0}}
    orchestrator = StrategyOrchestrator(ctx)
    
    # 원본 메모리 주소 확보
    original_address = id(ctx["active_weights"])
    
    # 새로운 가중치 업데이트 수행
    orchestrator.update_weights({"new_strat": 0.8, "other": 0.2})
    
    # 1. 값이 올바르게 변경되었는지 확인
    assert "old_strat" not in ctx["active_weights"]
    assert ctx["active_weights"]["new_strat"] == 0.8
    # 2. 메모리 주소가 절대 변하지 않았음을 증명
    assert id(ctx["active_weights"]) == original_address

def test_hmm_regime_detection_logic() -> None:
    """[목표 B 검증] 변동성 배열에 따른 Numpy 국면 판별 로직(0,1,2) 증명"""
    ctx: Dict[str, Any] = {}
    orchestrator = StrategyOrchestrator(ctx)
    
    # 극단적으로 낮은 변동성 주입 -> 가두리(0) 기대
    low_vol = np.array([0.01, 0.012, 0.011, 0.009])
    assert orchestrator._run_hmm_regime_detection(low_vol) == 0
    
    # 극단적으로 높은 변동성 주입 -> 추세(2) 또는 돌파(1) 기대
    high_vol = np.array([1.5, 2.0, 3.1, 2.8])
    assert orchestrator._run_hmm_regime_detection(high_vol) in (1, 2)

def test_hmm_regime_detection_protection() -> None:
    """[방어 지령 검증] 비정상 데이터(빈 배열, NaN, Inf)가 입력되었을 때 예외 없이 가두리(0)를 반환하는지 검증"""
    ctx: Dict[str, Any] = {}
    orchestrator = StrategyOrchestrator(ctx)
    
    # 1. 빈 배열
    empty_vol = np.array([])
    assert orchestrator._run_hmm_regime_detection(empty_vol) == 0
    
    # 2. NaN 포함 배열
    nan_vol = np.array([0.1, np.nan, 0.2])
    assert orchestrator._run_hmm_regime_detection(nan_vol) == 0
    
    # 3. Inf 포함 배열
    inf_vol = np.array([0.1, np.inf, 0.2])
    assert orchestrator._run_hmm_regime_detection(inf_vol) == 0

def test_rebalance_integration() -> None:
    """[목표 C 검증] 국면 인식 후 가중치가 정상적으로 분배되는지 통합 증명"""
    ctx: Dict[str, Any] = {}
    orchestrator = StrategyOrchestrator(ctx)
    high_vol = np.array([2.0, 2.5, 3.0])
    
    orchestrator.rebalance_based_on_regime(high_vol)
    
    # 리밸런싱된 결과로 active_weights가 비어있지 않아야 함
    assert len(ctx["active_weights"]) > 0
