# -*- coding: utf-8 -*-
import pytest
from sensor.trade_replay_analyzer import TradeReplayAnalyzer

def test_trade_replay_analyzer_hierarchy():
    analyzer = TradeReplayAnalyzer(max_history=10)
    
    sensor_snap = {"zScore": 1.5, "activeVol": 1.0, "vpin": 0.12}
    state_snap = {"capital": 25000000, "equity": 25000000, "marginRatio": 30.0, "slippageMs": 50}
    
    # 2025년 1월 15일 거래 등록
    record1 = analyzer.capture_trade_event(
        trade_type="EXIT",
        track_name="Track 5 (Gap)",
        side="SELL",
        asset_type="FUTURES",
        price=350.0,
        qty=1,
        reason="Timeout elapsed",
        realized_pnl=66549.0,
        sensor_snapshot=sensor_snap,
        state_snapshot=state_snap,
        entry_reason="시가 괴리(Z-Score) 회귀 저격 진입",
        date_str="2025-01-15"
    )
    
    # 2025년 2월 03일 거래 등록
    record2 = analyzer.capture_trade_event(
        trade_type="ENTRY",
        track_name="Track 3 (Arb)",
        side="BUY",
        asset_type="FUTURES",
        price=352.5,
        qty=2,
        reason="Z-Score 1.8突破",
        realized_pnl=0.0,
        sensor_snapshot=sensor_snap,
        state_snapshot=state_snap,
        entry_reason="차익거래 임계치 도달",
        date_str="2025-02-03"
    )
    
    tree = analyzer.get_tree_archive()
    assert "2025-01" in tree
    assert "2025-02" in tree
    assert "2025-01-15" in tree["2025-01"]
    assert "2025-02-03" in tree["2025-02"]
    assert len(tree["2025-01"]["2025-01-15"]) == 1
    assert tree["2025-01"]["2025-01-15"][0]["tradeId"] == record1["tradeId"]


def test_trade_replay_analyzer_mode_date_routing():
    import time
    # LIVE 모드 테스트
    live_analyzer = TradeReplayAnalyzer(mode="LIVE")
    rec_live = live_analyzer.capture_trade_event(
        trade_type="ENTRY", track_name="Track 1", side="BUY", asset_type="FUTURES",
        price=350.0, qty=1, reason="Test", realized_pnl=0.0,
        sensor_snapshot={}, state_snapshot={}, date_str="2025-01-01" # LIVE 모드에서는 date_str 무시하고 실시간 시스템 날짜 사용
    )
    today_str = time.strftime("%Y-%m-%d")
    assert rec_live["dateStr"] == today_str

    # VIRTUAL 모드 테스트
    virtual_analyzer = TradeReplayAnalyzer(mode="VIRTUAL")
    rec_virt = virtual_analyzer.capture_trade_event(
        trade_type="ENTRY", track_name="Track 1", side="BUY", asset_type="FUTURES",
        price=350.0, qty=1, reason="Test", realized_pnl=0.0,
        sensor_snapshot={}, state_snapshot={}, date_str="2025-03-10"
    )
    assert rec_virt["dateStr"] == "2025-03-10"

