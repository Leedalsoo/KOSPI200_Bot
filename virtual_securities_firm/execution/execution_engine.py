"""Virtual Securities Firm - Authoritative Execution Engine & Slippage Integration."""
import logging
import uuid
import random
from typing import Dict, Any, Optional, List
from shared.contracts.canonical import CanonicalExecutionReport, CanonicalOrderCommand, CanonicalAssetType
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
        total_slippage_pt = base_slippage + vol_impact + qty_impact

        direction = 1.0 if side.upper() in ("BUY", "BID") else -1.0
        executed_price = max(0.01, requested_price + (direction * total_slippage_pt))

        base_delay = 1.5
        jitter = random.uniform(0.1, 0.5)
        exec_delay_ms = base_delay + jitter

        return {
            "requested_price": requested_price,
            "executed_price": round(executed_price, 2),
            "slippage": round(total_slippage_pt, 4),
            "delay_ms": round(exec_delay_ms, 2)
        }


class ExecutionEngine:
    """[VSSF 소유] Authoritative Execution Engine
    
    호가 매칭 수신 ➔ SlippageEngine 연산 ➔ 수수료 및 슬리피지 확정 ➔ CanonicalExecutionReport 발급
    """
    def __init__(self, control_interface: Optional[VirtualBrokerControlInterface] = None):
        self.slippage_engine = SlippageEngine(control_interface=control_interface)
        self.reports: List[CanonicalExecutionReport] = []

    def execute_order(self, command: CanonicalOrderCommand, fill_price: float, fill_qty: int) -> CanonicalExecutionReport:
        """[Authoritative Order Execution Procedure]"""
        side_str = command.side.value if hasattr(command.side, "value") else str(command.side)
        
        # 1. Slippage Engine Invocation
        slip_res = self.slippage_engine.calculate_execution(
            order_type="LIMIT",
            side=side_str,
            requested_price=fill_price,
            qty=fill_qty
        )
        exec_price = float(slip_res.get("executed_price", fill_price))
        slippage = float(slip_res.get("slippage", 0.0))
        fee = exec_price * fill_qty * 250000 * 0.000015  # 1.5bps commission

        # 2. Issue Canonical Execution Report
        report = CanonicalExecutionReport(
            exec_id=f"EXEC-{uuid.uuid4().hex[:8].upper()}",
            client_order_id=getattr(command, "client_order_id", "ORD-001"),
            track_id=getattr(command, "track_id", "Track1"),
            asset_type=getattr(command, "asset_type", CanonicalAssetType.OPTION),
            side=command.side,
            executed_qty=fill_qty,
            executed_price=exec_price,
            fee=round(fee, 2),
            slippage=slippage,
            timestamp="2026-08-23 09:00:00"
        )
        self.reports.append(report)
        logger.debug(f"[ExecutionEngine Issued] Report: {report.exec_id} | Order: {report.client_order_id} | Price: {report.executed_price}")
        return report
