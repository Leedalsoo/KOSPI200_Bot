# -*- coding: utf-8 -*-
import pytest
from decimal import Decimal
from datetime import datetime, timedelta

from sensor.report_agent import ReportAgent
from core.bus import EventBus

def test_daily_summary_calculation() -> None:
    """[목표 C 검증] 누적 손익 및 MDD 집계 정합성 증명"""
    agent = ReportAgent(EventBus())
    history = [
        {"pnl": Decimal("100"), "slippage": Decimal("0.01")},
        {"pnl": Decimal("-50"), "slippage": Decimal("0.02")}
    ]
    summary = agent.generate_summary(history)
    assert summary["total_pnl"] == Decimal("50")
    assert summary["avg_slippage"] == Decimal("0.015")

def test_embargo_window_lookahead_defense() -> None:
    """[목표 B 검증] 미래 데이터(현재 시각 이후 타임스탬프)는 집계에서 제외됨을 증명"""
    agent = ReportAgent(EventBus())
    now = datetime.now()
    future_ts = now + timedelta(hours=1)

    history = [
        {"pnl": Decimal("100"), "slippage": Decimal("0.01"), "timestamp": now - timedelta(minutes=5)},
        {"pnl": Decimal("9999"), "slippage": Decimal("0.99"), "timestamp": future_ts},  # 미래 데이터
    ]
    summary = agent.generate_summary(history)
    # 미래 데이터(9999)는 집계 제외 → 과거 100만 합산
    assert summary["total_pnl"] == Decimal("100")

def test_mdd_calculation_precision() -> None:
    """[목표 C + 방어 지령 검증] 100배 int 스케일링 기반 MDD 정밀 연산 증명"""
    agent = ReportAgent(EventBus())
    # 수익 100 → 손실 -200 → 수익 50 : MDD = 200
    history = [
        {"pnl": Decimal("100"), "slippage": Decimal("0.01")},
        {"pnl": Decimal("-200"), "slippage": Decimal("0.01")},
        {"pnl": Decimal("50"),  "slippage": Decimal("0.01")},
    ]
    summary = agent.generate_summary(history)
    # cumulative: [100, -100, -50], running_max: [100, 100, 100]
    # drawdown:   [  0,  200, 150] → MDD = 200
    assert summary["mdd"] == Decimal("200")

def test_embargo_chronological_order_guard() -> None:
    """[목표 B 검증] 타임스탬프가 역순인 데이터 입력 시 AssertionError 발생으로 엠바고 보안 증명"""
    agent = ReportAgent(EventBus())
    now = datetime.now()
    history = [
        {"pnl": Decimal("100"), "timestamp": now},
        {"pnl": Decimal("50"),  "timestamp": now - timedelta(hours=1)},  # 역순!
    ]
    with pytest.raises(AssertionError, match="Embargo violation"):
        agent.generate_summary(history)
