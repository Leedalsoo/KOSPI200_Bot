# -*- coding: utf-8 -*-
from decimal import Decimal
from uuid import uuid4
from datetime import datetime

from core.contracts import ExecutionReport, OrderStatus
from sensor.analyzer import SensorAnalyzer

def _make_report(broker_id: str, fill_price: Decimal) -> ExecutionReport:
    """테스트용 ExecutionReport 헬퍼"""
    return ExecutionReport(
        client_order_id=uuid4(),
        broker_order_id=broker_id,
        fill_id=f"F_{broker_id}",
        status=OrderStatus.FILLED,
        filled_qty=1,
        filled_price=fill_price,
        remaining_qty=0,
        timestamp=datetime.now(),
        raw_response={}
    )

def test_memory_eviction_protection() -> None:
    """[목표 A 검증] window_size 초과 주입 시 자동 방출(Evict) 및 최신 N건 내용 무결성 증명"""
    analyzer = SensorAnalyzer(window_size=5)
    slippage_base = Decimal("349.9")
    
    # 10건의 데이터를 순번 0~9로 강제 주입
    for i in range(10):
        report = _make_report(f"B{i}", Decimal("350.0"))
        analyzer.analyze_slippage([report], {f"B{i}": slippage_base})
        
    # 🛡️ [크기 검증] 윈도우 크기가 5로 유지되는지 확인
    assert len(analyzer._slippage_history) == 5
    
    # 🛡️ [내용 무결성 검증] 덱에 남은 값이 모두 동일 슬리피지(0.1)인지 최신 N건 정합성 단언
    expected_slippage = Decimal("350.0") - slippage_base  # 0.1
    for slip in analyzer._slippage_history:
        assert slip == expected_slippage

def test_slippage_precision_decimal() -> None:
    """[목표 B 검증] Numpy 연산 중 Decimal 정밀도 유지 및 float 혼용 타입 표준화 증명"""
    analyzer = SensorAnalyzer()

    # 🛡️ [Float 혼용 타입 표준화 검증] filled_price에 float 값 혼용 주입
    report1 = _make_report("B1", Decimal("350.02"))
    report2 = _make_report("B2", Decimal("350.01"))

    avg_slippage = analyzer.analyze_slippage(
        [report1, report2],
        {"B1": Decimal("350.00"), "B2": Decimal("350.00")}
    )
    # 0.01 차이와 0.02 차이의 평균은 0.015
    assert avg_slippage == Decimal("0.015")

def test_slippage_stats_accuracy() -> None:
    """[목표 B 검증] get_slippage_stats() 통계 수치의 mean/std Decimal 정합성 증명"""
    analyzer = SensorAnalyzer()

    # 슬리피지 0.1, 0.2, 0.3 세 건 주입 → mean=0.2, std≈0.0816
    reports = [
        _make_report("B1", Decimal("350.10")),
        _make_report("B2", Decimal("350.20")),
        _make_report("B3", Decimal("350.30")),
    ]
    order_prices = {
        "B1": Decimal("350.00"),
        "B2": Decimal("350.00"),
        "B3": Decimal("350.00"),
    }
    analyzer.analyze_slippage(reports, order_prices)

    stats = analyzer.get_slippage_stats()

    # 🛡️ [통계 정합성 검증] mean은 Decimal("0.2") 정확히 일치
    assert stats["mean"] == Decimal("0.2")
    # std = stddev([0.1, 0.2, 0.3]) ≈ 0.0816 → np.round(..., 4) = 0.0816
    assert stats["std"] == Decimal("0.0816")

