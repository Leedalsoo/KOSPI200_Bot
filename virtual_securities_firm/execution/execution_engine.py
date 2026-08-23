"""Virtual Securities Firm - Authoritative Execution Engine & Slippage Engine."""
import logging
import random
from typing import Dict, Any, Optional
from shared.contracts.canonical import CanonicalExecutionReport, CanonicalOrderCommand
from virtual_securities_firm.execution.execution_report_factory import ExecutionReportFactory
from virtual_market_simulator.market.synthetic_market_generator import VirtualBrokerControlInterface

logger = logging.getLogger(__name__)

class SlippageEngine:
    """[VSSF 소유] 슬리피지 및 체결 지연 시뮬레이션 엔진"""
    def __init__(self, control_interface: Optional[VirtualBrokerControlInterface] = None) -> None:
        self.control = control_interface if control_interface is not None else VirtualBrokerControlInterface()

    def calculate_execution(self, 
                            order_type: str, 
                            side: str, 
                            requested_price: float, 
                            qty: int, 
                            current_volatility: Optional[float] = None,
                            current_spread: Optional[float] = None) -> Dict[str, Any]:
        cfg = self.control.config
        slip_mult = cfg.slippage_multiplier
        active_vol = current_volatility if current_volatility is not None else cfg.volatility_scale
        effective_spread = current_spread if current_spread is not None else cfg.base_spread

        base_slippage = effective_spread * 0.3 * slip_mult
        vol_impact = (active_vol - 1.0) * 0.08 * slip_mult if active_vol > 1.0 else 0.0
        qty_impact = (qty * 0.01) * slip_mult
        
        total_slippage = round(base_slippage + vol_impact + qty_impact + random.uniform(0.01, 0.05), 2)
        total_slippage = min(1.0, max(0.01, total_slippage))

        delay_ms = int(cfg.latency_ms + (active_vol * 80) + (qty * 5) + random.randint(10, 50))
        delay_ms = min(3000, delay_ms)

        final_execution_price = requested_price
        if side.upper() in ("BUY", "BID"):
            final_execution_price += total_slippage
        elif side.upper() in ("SELL", "ASK"):
            final_execution_price -= total_slippage
            
        final_execution_price = round(final_execution_price, 2)
        
        return {
            "execution_price": final_execution_price,
            "slippage_pts": total_slippage,
            "delay_ms": delay_ms
        }


class ExecutionEngine:
    """[VSSF 소유] Authoritative Execution Engine"""
    def __init__(self):
        self.slippage_engine = SlippageEngine()
        self.reports = []

    def execute_order(self, order: CanonicalOrderCommand, fill_price: Optional[float] = None) -> CanonicalExecutionReport:
        price = fill_price if fill_price is not None else order.price
        report = ExecutionReportFactory.create_report(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            price=price,
            quantity=order.quantity,
            fee=0.0,
            slippage=0.0,
            metadata=order.metadata
        )
        self.reports.append(report)
        return report
