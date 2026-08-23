# -*- coding: utf-8 -*-
from decimal import Decimal
from typing import Tuple

from core.contracts import AccountSnapshot, calculate_available_funds, calculate_available_margin, verify_account_integrity

class AccountEngine:
    """[Phase 5 Virtual Broker Account & Margin Engine]
    
    자산, 가용 자금, 증거금 한도, 총 계산 평가액(Equity) 및 계좌 무결성을
    독립적으로 연산하는 회계 전담 엔진.
    """
    def __init__(self, initial_capital: Decimal = Decimal("25000000.00")) -> None:
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.realized_pnl = Decimal("0.00")
        self.total_fee = Decimal("0.00")
        self.total_slippage = Decimal("0.00")
        self.used_margin = Decimal("0.00")
        self.pending_order_reservation = Decimal("0.00")
        self.unrealized_pnl = Decimal("0.00")

    def apply_realized_trade(self, pnl: Decimal, fee: Decimal, slippage: Decimal) -> None:
        """실현 손익, 수수료, 슬리피지를 반영하여 Cash 회계 잔액 갱신"""
        self.realized_pnl += pnl
        self.total_fee += fee
        self.total_slippage += slippage
        # Cash = Initial Capital + Realized PnL - Fee - Slippage
        self.cash = self.initial_capital + self.realized_pnl - self.total_fee - self.total_slippage

    def update_margin_and_unrealized(self, used_margin: Decimal, unrealized_pnl: Decimal) -> None:
        """증거금 사용액 및 미실현 평가손익 갱신"""
        self.used_margin = max(Decimal("0.00"), used_margin)
        self.unrealized_pnl = unrealized_pnl

    def get_snapshot(self) -> AccountSnapshot:
        """현재 계좌의 AccountSnapshot DTO 생성"""
        avail_funds = calculate_available_funds(self.cash, self.pending_order_reservation, self.used_margin)
        avail_margin = calculate_available_margin(self.cash, self.used_margin)
        total_equity = self.cash + self.unrealized_pnl

        return AccountSnapshot(
            initial_capital=self.initial_capital,
            cash=self.cash,
            available_funds=avail_funds,
            used_margin=self.used_margin,
            available_margin=avail_margin,
            total_equity=total_equity,
            pending_order_reservation=self.pending_order_reservation
        )

    def verify_integrity(self) -> Tuple[bool, str]:
        """계좌 무결성 방정식 검증"""
        return verify_account_integrity(
            cash_balance=self.cash,
            initial_capital=self.initial_capital,
            realized_pnl=self.realized_pnl,
            total_fees=self.total_fee,
            total_slippage=self.total_slippage
        )
