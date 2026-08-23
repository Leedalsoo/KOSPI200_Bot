from .state import SessionContext
from virtual_securities_firm.margin.margin_engine import MarginEngine

class ExecutionAgent:
    """
    체결 및 리스크 관리 계층 (ExecutionAgent)
    [M5 책임 이관] 임의의 가우시안 랜덤 조작을 완전 제거하고, MarginEngine 기반 결정론적 마진 계산 적용
    """
    def __init__(self):
        self.futures_multiplier = 250000.0
        self.options_multiplier = 250000.0
        self.margin_engine = MarginEngine()
        
    def execute_orders(self, ctx: SessionContext, orders: list) -> None:
        """주문 리스트를 수신하여 포지션에 반영 후 마진 재계산"""
        for order in orders:
            track = order.get("track", "Unknown")
            asset_type = order.get("type")
            side = order.get("side")
            qty = order.get("qty", 1)
            tag_id = order.get("tag_id")
            
            new_pos = {
                "track": track,
                "type": asset_type,
                "side": side,
                "qty": qty,
                "strike": order.get("strike", 0.0),
                "price": order.get("price", ctx.current_price),
                "tag_id": tag_id,
                "is_insurance": order.get("is_insurance", False)
            }
            ctx.portfolio.options.append(new_pos)
            
            if asset_type == "FUTURES":
                if side == "BUY":
                    ctx.portfolio.current_position_qty += qty
                elif side == "SELL":
                    ctx.portfolio.current_position_qty -= qty
                    
        self._recalc_margin(ctx)

    def check_risk_lockdown(self, ctx: SessionContext) -> bool:
        """3중 방어막 검사"""
        if ctx.account.total_equity <= ctx.account.initial_capital * 0.25:
            ctx.risk.main_engine_broken = True
            return True
            
        self._recalc_margin(ctx)
        return False

    def _recalc_margin(self, ctx: SessionContext, margin_haircut: float = 1.0) -> None:
        """옵션 및 선물 포지션에 대한 실시간 증거금 및 비율 재계산 (결정론적 산출)"""
        price = ctx.current_price
        capital = ctx.account.current_capital
        futures_qty = ctx.portfolio.current_position_qty
        
        # 포지션 기반 마진 계산
        pos_dict = {}
        for idx, p in enumerate(ctx.portfolio.options):
            pos_dict[f"OPT_{idx}"] = {
                "avg_price": float(p.get("price", price)),
                "qty": int(p.get("qty", 1)),
                "side": p.get("side", "BUY")
            }
        options_margin = self.margin_engine.calculate_used_margin(pos_dict, multiplier=self.options_multiplier) * margin_haircut
        futures_margin = abs(futures_qty) * price * self.futures_multiplier * 0.10 * margin_haircut
        
        used_m = futures_margin + options_margin
        ratio = (used_m / max(1000000.0, capital)) * 100.0
        
        ctx.account.used_margin = used_m
        ctx.account.margin_ratio = ratio

    def process_settlement(self, ctx: SessionContext, is_expiry: bool = False) -> None:
        """15:45 마감 시 일일 정산 및 만기 롤오버 처리 (랜덤 제거, 결정론적 정산)"""
        daily_pnl = 0.0
        if is_expiry:
            # 만기일이면 포지션 전량 청산
            ctx.portfolio.options = []
            ctx.portfolio.current_position_qty = 0
            
        self._recalc_margin(ctx)

