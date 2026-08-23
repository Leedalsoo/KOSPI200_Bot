"""Settlement Engine for M5 (EOD & Expiry Settlement)."""
import logging
from typing import Dict, Any
from virtual_securities_firm.account.paper_account import PaperTradingAccount

logger = logging.getLogger(__name__)

class SettlementEngine:
    """[M5 정산 엔진: 일일 정산 (EOD Settlement) 및 만기 정산 (Expiry Settlement) 전담]"""
    def __init__(self, account: PaperTradingAccount):
        self.account = account
        self.settlement_history = []

    def perform_eod_settlement(self, final_settlement_price: float) -> Dict[str, Any]:
        """일일 장마감 MTM 정산 및 증거금 재계산 -> LedgerEngine에 정산 분개 기록"""
        pnl = self.account.unrealized_pnl
        record = {
            "type": "EOD",
            "balance": self.account.balance,
            "margin": self.account.used_margin,
            "realized_pnl": self.account.realized_pnl,
            "unrealized_pnl": pnl,
            "settlement_price": final_settlement_price
        }
        self.settlement_history.append(record)
        
        # [Settlement -> Ledger Authoritative Chain]
        if hasattr(self.account, "ledger_engine"):
            self.account.ledger_engine.record_settlement(
                settlement_type="EOD",
                realized_pnl=self.account.realized_pnl,
                unrealized_pnl=pnl,
                balance_after=self.account.balance
            )
            
        logger.info(f"[SettlementEngine] EOD Settlement Completed: {record}")
        return record

    def perform_expiry_settlement(self, option_symbol: str, final_index_price: float) -> float:
        """만기 옵션 잔고 청산 정산 -> LedgerEngine에 정산 분개 기록"""
        settled_cash = 0.0
        if option_symbol in self.account.positions:
            pos = self.account.positions[option_symbol]
            qty = pos.get("qty", 1) if isinstance(pos, dict) else pos
            strike = 350.0 # Standard strike
            if "CALL" in option_symbol:
                payoff = max(0.0, final_index_price - strike) * 250000.0 * qty
            else:
                payoff = max(0.0, strike - final_index_price) * 250000.0 * qty
            self.account.balance += payoff
            del self.account.positions[option_symbol]
            settled_cash = payoff
            
            if hasattr(self.account, "ledger_engine"):
                self.account.ledger_engine.record_settlement(
                    settlement_type=f"EXPIRY_{option_symbol}",
                    realized_pnl=payoff,
                    unrealized_pnl=0.0,
                    balance_after=self.account.balance
                )
            logger.info(f"[SettlementEngine] Expiry Settlement for {option_symbol}: Payoff={payoff}")
        return settled_cash

