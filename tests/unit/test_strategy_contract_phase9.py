# -*- coding: utf-8 -*-
from typing import Dict, Any, List
from strategy.strategy_contract import StrategyContract
from core.contracts import OrderRequest

class MockStrategy(StrategyContract):
    def on_market_data(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "OK"}

    def generate_signals(self, market_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [{"action": "ENTRY"}]

def test_strategy_contract_interface() -> None:
    strat = MockStrategy()
    data_res = strat.on_market_data({"price": 350.0})
    assert data_res["status"] == "OK"
    
    signals = strat.generate_signals({"price": 350.0})
    assert len(signals) == 1
    assert signals[0]["action"] == "ENTRY"
    
    orders = strat.generate_orders(signals)
    assert isinstance(orders, list)
