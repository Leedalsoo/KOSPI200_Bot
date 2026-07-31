# -*- coding: utf-8 -*-
import pytest
from sensor.trade_replay_analyzer import TradeReplayAnalyzer

def test_trade_replay_analyzer_capture():
    analyzer = TradeReplayAnalyzer(max_history=10)
    
    sensor_snap = {"zScore": 1.5, "activeVol": 1.0, "vpin": 0.12}
    state_snap = {"capital": 25000000, "equity": 25000000, "marginRatio": 30.0, "slippageMs": 50}
    
    record = analyzer.capture_trade_event(
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
        entry_reason=" 시가 괴리(Z-Score) 회귀 저격 진입"
    )
    
    assert record["tradeType"] == "EXIT"
    assert record["trackName"] == "Track 5 (Gap)"
    assert record["realizedPnL"] == 66549.0
    assert record["ruleCompliance"]["status"] == "VALID_COMPLIANT"
    assert "AI Counterfactual Advice" in record["aiTimingAnalysis"] or "rating" in record["aiTimingAnalysis"]
    
    recent = analyzer.get_recent_records()
    assert len(recent) == 1
    assert recent[0]["tradeId"] == record["tradeId"]
