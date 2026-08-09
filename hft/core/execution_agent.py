from .state import SessionContext

class ExecutionAgent:
    """
    체결 및 리스크 관리 계층 (ExecutionAgent)
    순수 주문 정보를 받아 증거금, 슬리피지, 3중 방어막을 적용한 후 Context 업데이트
    """
    def __init__(self):
        self.futures_multiplier = 250000
        self.options_multiplier = 250000
        
    def execute_orders(self, ctx: SessionContext, orders: list) -> None:
        """
        주문 리스트를 처리하고 ctx.account, ctx.portfolio 에 반영.
        기존 mock_ws_server에서는 선물(FUTURES)을 단순히 current_position_qty 정수로 더하고 뺐지만,
        새로운 아키텍처에서는 옵션과 마찬가지로 상세 태그를 달아 portfolio.options에 객체로 관리합니다.
        """
        for order in orders:
            track = order.get("track", "Unknown")
            asset_type = order.get("type")
            side = order.get("side")
            qty = order.get("qty", 1)
            tag_id = order.get("tag_id")
            
            # 가상 체결 (실제로는 ExecutionAgent가 슬리피지/마진을 체크한 후 잔고를 갱신)
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
            
            # TODO: 실제로는 롱/숏 상계(Netting) 로직이 필요하지만, 가시성을 위해 일단 append
            ctx.portfolio.options.append(new_pos)
            
            if asset_type == "FUTURES":
                # 호환성을 위해 기존 정수 필드도 일단 업데이트
                if side == "BUY":
                    ctx.portfolio.current_position_qty += qty
                elif side == "SELL":
                    ctx.portfolio.current_position_qty -= qty
                    
        # 주문 처리 후 마진/증거금 즉시 재계산
        self._recalc_margin(ctx)

    def check_risk_lockdown(self, ctx: SessionContext) -> bool:
        """
        -75% 마진콜 방어선, 일간 -35% 셧다운 등 3중 방어막 검사
        """
        if ctx.account.total_equity <= ctx.account.initial_capital * 0.25:
            ctx.risk.main_engine_broken = True
            return True
            
        # 매 틱마다 증거금 재계산
        self._recalc_margin(ctx)
        return False

    def _recalc_margin(self, ctx: SessionContext, margin_haircut=1.0) -> None:
        """
        옵션 및 선물 포지션에 대한 실시간 증거금 및 비율 재계산 (mock_ws_server.py 이식)
        """
        options_portfolio = ctx.portfolio.options
        price = ctx.current_price
        capital = ctx.account.current_capital
        futures_qty = ctx.portfolio.current_position_qty
        
        sell_call_qty = sum(int(p.get("qty", 0)) for p in options_portfolio if p.get("side") == "SELL" and p.get("type") == "CALL")
        buy_call_qty = sum(int(p.get("qty", 0)) for p in options_portfolio if p.get("side") == "BUY" and p.get("type") == "CALL")
        net_short_call = max(0, sell_call_qty - buy_call_qty)
        
        sell_put_qty = sum(int(p.get("qty", 0)) for p in options_portfolio if p.get("side") == "SELL" and p.get("type") == "PUT")
        buy_put_qty = sum(int(p.get("qty", 0)) for p in options_portfolio if p.get("side") == "BUY" and p.get("type") == "PUT")
        net_short_put = max(0, sell_put_qty - buy_put_qty)
        
        net_naked_qty = net_short_call + net_short_put
        hedged_spread_qty = (sell_call_qty - net_short_call) + (sell_put_qty - net_short_put)
        
        naked_margin = net_naked_qty * price * self.options_multiplier * 0.075 * margin_haircut
        spread_margin = hedged_spread_qty * 1250000 * margin_haircut
        options_margin = naked_margin + spread_margin
        
        used_m = (abs(futures_qty) * price * self.futures_multiplier * 0.09 * margin_haircut) + options_margin
        ratio = (used_m / max(1000000.0, capital)) * 100.0
        
        ctx.account.used_margin = used_m
        ctx.account.margin_ratio = ratio

    def process_settlement(self, ctx: SessionContext, is_expiry: bool = False) -> None:
        """
        15:45 마감 시 일일 정산 및 만기 롤오버 처리
        """
        # 아주 단순화된 가상 PnL 합산 (실제로는 블랙숄즈 내재가치 평가 필요)
        # 테스트용으로 보유 포지션당 일정 수익을 엎어치는 로직 모사
        daily_pnl = 0.0
        if ctx.portfolio.options:
            import random
            # 옵션 포지션이 있으면 하루 지날 때마다 소량의 세타 수익(또는 손실) 발생 모사
            daily_pnl += len(ctx.portfolio.options) * random.gauss(50000, 200000)
            
        if ctx.portfolio.current_position_qty != 0:
            daily_pnl += ctx.portfolio.current_position_qty * random.gauss(100000, 500000)

        # 자본금에 PnL 엎어치기
        ctx.account.current_capital += daily_pnl
        ctx.account.total_equity += daily_pnl
        
        if is_expiry:
            # 만기일이면 포지션 전량 청산 (초기화)
            ctx.portfolio.options = []
            ctx.portfolio.current_position_qty = 0
            
        self._recalc_margin(ctx)
