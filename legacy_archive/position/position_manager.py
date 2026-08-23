# -*- coding: utf-8 -*-
from decimal import Decimal
from typing import Dict, List, Any, Optional
from datetime import datetime

from core.contracts import ExecutionReport, PositionRecord, calculate_weighted_average_price, OrderPurpose

class PositionManager:
    """[Phase 4 Virtual Broker Position Manager]
    
    Gross/Net Position 분리, Strategy Attribution 및 이동평균 평단가(WAP)를
    전담 관리하는 포지션 엔진.
    """
    def __init__(self) -> None:
        self.positions: Dict[str, PositionRecord] = {}
        self.strategy_positions: Dict[str, List[PositionRecord]] = {}

    def apply_execution(self, report: ExecutionReport) -> Optional[PositionRecord]:
        """ExecutionReport를 처리하여 포지션 신규 오픈, 수량 증감, 평단가 갱신 및 청산 처리"""
        if report.filled_qty <= 0:
            return None

        pos_id = f"POS_{report.strategy_id}_{report.broker_order_id}"
        
        # 1. 기존 오픈 포지션 검색 (동일 전략)
        existing_pos: Optional[PositionRecord] = None
        for p in self.positions.values():
            if p.strategy_id == report.strategy_id and p.status in ("OPEN", "PARTIALLY_CLOSED"):
                existing_pos = p
                break

        if existing_pos is None:
            # 2. 신규 포지션 오픈
            new_pos = PositionRecord(
                position_id=pos_id,
                strategy_id=report.strategy_id,
                symbol="KOSPI200_OPT",
                side="BUY" if report.order_purpose in (OrderPurpose.STRATEGY_ENTRY, OrderPurpose.RISK_HEDGE) else "SELL",
                qty=report.filled_qty,
                remaining_qty=report.filled_qty,
                entry_price=report.execution_price,
                status="OPEN",
                entry_time=report.timestamp,
                order_purpose=report.order_purpose
            )
            self.positions[pos_id] = new_pos
            if report.strategy_id not in self.strategy_positions:
                self.strategy_positions[report.strategy_id] = []
            self.strategy_positions[report.strategy_id].append(new_pos)
            return new_pos
        else:
            # 3. 포지션 청산 또는 증량
            if report.order_purpose == OrderPurpose.STRATEGY_EXIT:
                reduced_qty = min(existing_pos.remaining_qty, report.filled_qty)
                new_remaining = existing_pos.remaining_qty - reduced_qty
                
                updated_pos = PositionRecord(
                    position_id=existing_pos.position_id,
                    strategy_id=existing_pos.strategy_id,
                    symbol=existing_pos.symbol,
                    side=existing_pos.side,
                    qty=existing_pos.qty,
                    remaining_qty=new_remaining,
                    entry_price=existing_pos.entry_price,
                    status="CLOSED" if new_remaining == 0 else "PARTIALLY_CLOSED",
                    tag=existing_pos.tag,
                    entry_time=existing_pos.entry_time,
                    order_purpose=existing_pos.order_purpose,
                    parent_position_id=existing_pos.parent_position_id,
                    hedge_ref_id=existing_pos.hedge_ref_id
                )
            else:
                new_wap = calculate_weighted_average_price(
                    current_qty=existing_pos.remaining_qty,
                    current_avg_price=existing_pos.entry_price,
                    new_qty=report.filled_qty,
                    new_fill_price=report.execution_price
                )
                total_remaining = existing_pos.remaining_qty + report.filled_qty
                updated_pos = PositionRecord(
                    position_id=existing_pos.position_id,
                    strategy_id=existing_pos.strategy_id,
                    symbol=existing_pos.symbol,
                    side=existing_pos.side,
                    qty=existing_pos.qty + report.filled_qty,
                    remaining_qty=total_remaining,
                    entry_price=new_wap,
                    status="OPEN",
                    tag=existing_pos.tag,
                    entry_time=existing_pos.entry_time,
                    order_purpose=existing_pos.order_purpose
                )

            # 포지션 Dict 및 strategy_positions 배열 갱신
            self.positions[existing_pos.position_id] = updated_pos
            if report.strategy_id in self.strategy_positions:
                for idx, p in enumerate(self.strategy_positions[report.strategy_id]):
                    if p.position_id == existing_pos.position_id:
                        self.strategy_positions[report.strategy_id][idx] = updated_pos
                        break

            return updated_pos

    def get_net_qty(self, strategy_id: Optional[str] = None) -> int:
        """전체 또는 특정 전략 귀속 Net 수량 계산"""
        net_qty = 0
        target_positions = self.positions.values() if strategy_id is None else self.strategy_positions.get(strategy_id, [])
        for p in target_positions:
            if p.status in ("OPEN", "PARTIALLY_CLOSED"):
                if p.side == "BUY":
                    net_qty += p.remaining_qty
                else:
                    net_qty -= p.remaining_qty
        return net_qty

    def get_gross_qty(self) -> int:
        """전체 Gross 수량(총 보유 계약 수 절대값 합) 계산"""
        return sum(p.remaining_qty for p in self.positions.values() if p.status in ("OPEN", "PARTIALLY_CLOSED"))

    def calculate_used_margin(self, multiplier: Decimal = Decimal("250000.0")) -> Decimal:
        """[PositionManager 책임] 현재 오픈 포지션의 총 사용 증거금 산출 순수 함수"""
        total_margin = Decimal("0.00")
        for p in self.positions.values():
            if p.status in ("OPEN", "PARTIALLY_CLOSED"):
                total_margin += Decimal(str(p.entry_price)) * Decimal(str(p.remaining_qty)) * multiplier
        return total_margin.quantize(Decimal("0.01"))

    def calculate_unrealized_pnl(self, current_price: Decimal, multiplier: Decimal = Decimal("250000.0")) -> Decimal:
        """[PositionManager 책임] 현재 오픈 포지션의 총 MTM 미실현 평가손익 산출 순수 함수"""
        total_unrealized = Decimal("0.00")
        for p in self.positions.values():
            if p.status in ("OPEN", "PARTIALLY_CLOSED"):
                if p.side == "BUY":
                    pnl_diff = current_price - Decimal(str(p.entry_price))
                else:
                    pnl_diff = Decimal(str(p.entry_price)) - current_price
                total_unrealized += pnl_diff * Decimal(str(p.remaining_qty)) * multiplier
        return total_unrealized.quantize(Decimal("0.01"))

    @staticmethod
    def calculate_order_margin(price: Decimal, qty: int, multiplier: Decimal = Decimal("250000.0")) -> Decimal:
        """[PositionManager/Margin 책임] 신규 주문 시 요구되는 주문 증거금 산출 순수 함수"""
        safe_price = min(price, Decimal("50.0")) if price < Decimal("50.0") else Decimal("2.5")
        return (safe_price * Decimal(str(qty)) * multiplier).quantize(Decimal("0.01"))

    def calculate_close_realized_pnl(self, report: ExecutionReport, multiplier: Decimal = Decimal("250000.0")) -> Decimal:
        """[PositionManager 책임] 청산 주문 체결 시 포지션 잔여수량/진입가 기준 실현 손익(Realized PnL) 산출 순수 함수"""
        if report.filled_qty <= 0:
            return Decimal("0.00")
            
        for p in self.positions.values():
            if p.strategy_id == report.strategy_id and p.status in ("OPEN", "PARTIALLY_CLOSED"):
                close_qty = min(p.remaining_qty, report.filled_qty)
                if p.side == "BUY":
                    pnl = (report.execution_price - Decimal(str(p.entry_price))) * Decimal(str(close_qty)) * multiplier
                else:
                    pnl = (Decimal(str(p.entry_price)) - report.execution_price) * Decimal(str(close_qty)) * multiplier
                return Decimal(str(round(float(pnl), 2)))
        return Decimal("0.00")


