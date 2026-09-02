"""Virtual Securities Firm - Authoritative ExecutionReport Factory."""
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from shared.contracts.canonical import (
    CanonicalExecutionReport,
    CanonicalAssetType,
    CanonicalOrderSide,
    CanonicalOptionType,
)

class ExecutionReportFactory:
    @staticmethod
    def create_report(
        order_id: str,
        symbol: str,
        side: CanonicalOrderSide,
        price: float,
        quantity: int,
        track_id: str = "Track1",
        asset_type: CanonicalAssetType = CanonicalAssetType.OPTION,
        fee: float = 0.0,
        slippage: float = 0.0,
        option_type: Optional[CanonicalOptionType] = None,
        strike: float = 0.0,
        expiry: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CanonicalExecutionReport:
        exec_id = f"EXEC-{uuid.uuid4().hex[:8].upper()}"
        return CanonicalExecutionReport(
            exec_id=exec_id,
            client_order_id=order_id,
            track_id=track_id,
            asset_type=asset_type,
            side=side,
            executed_qty=quantity,
            executed_price=price,
            fee=fee,
            slippage=slippage,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            symbol=symbol,
            option_type=option_type,
            strike=strike,
            expiry=expiry,
        )
