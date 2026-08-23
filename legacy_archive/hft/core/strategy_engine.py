from typing import Dict, Any, List
import logging

# 전략 플러그인 임포트 (mock_ws_server.py 에서 복사)
from strategy.plugins.track1 import Track1
from strategy.plugins.track2 import Track2
from strategy.plugins.track3 import Track3
from strategy.plugins.track4 import Track4
from strategy.plugins.track5 import Track5
from strategy.plugins.track6 import Track6
from strategy.plugins.track7 import Track7
from strategy.plugins.track8 import Track8

from .state import SessionContext

logger = logging.getLogger(__name__)

class StrategyOrchestrator:
    """
    모든 Track1~Track8 전략 플러그인을 로드하고 관리하며, 
    매 틱마다 시그널을 수집하여 주문 목록을 반환하는 계층
    """
    def __init__(self):
        self.strategies = {
            "Track1": Track1(config={}),
            "Track2": Track2(config={}),
            "Track3": Track3(config={}),
            "Track4": Track4(config={}),
            "Track5": Track5(config={}),
            "Track6": Track6(config={}),
            "Track7": Track7(config={}),
            "Track8": Track8(config={})
        }
        logger.info(f"StrategyOrchestrator initialized. Loaded {len(self.strategies)} track plugins.")

    def process_tick(self, ctx: SessionContext) -> List[Dict[str, Any]]:
        """모든 전략을 평가하고 실행할 주문 리스트를 취합"""
        orders = []

        # -----------------------------------------------------------
        # [이식] Track 1: 100% 방어막 유지 (양매도)
        # -----------------------------------------------------------
        track1 = self.strategies.get("Track1")
        if track1:
            eval_result = track1.evaluate_strategy(
                current_price=ctx.current_price,
                regime=ctx.current_regime,
                portfolio_options=ctx.portfolio.options,
                futures_qty=ctx.portfolio.current_position_qty,
                capital=ctx.account.current_capital,
                dte=getattr(ctx, 'days_to_expiry', 15.0)
            )
            if eval_result.get("action") == "ENTRY":
                orders.append({
                    "track": "Track1", "type": "CALL", "side": "SELL",
                    "qty": eval_result.get("qty", 1),
                    "strike": eval_result.get("call_strike", ctx.current_price + 2.5),
                    "price": 2.50, "tag_id": "T1_ENTRY_C"
                })
                orders.append({
                    "track": "Track1", "type": "PUT", "side": "SELL",
                    "qty": eval_result.get("qty", 1),
                    "strike": eval_result.get("put_strike", ctx.current_price - 2.5),
                    "price": 2.50, "tag_id": "T1_ENTRY_P"
                })
            elif eval_result.get("action") == "HEDGE":
                side = eval_result.get("side", "BUY")
                orders.append({
                    "track": "Track1", "type": "FUTURES", "side": side,
                    "qty": 1, "tag_id": f"T1_HEDGE_{side}"
                })

        # -----------------------------------------------------------
        # [예시] Track 5: 시가 갭 회귀 전략 (Gap Protocol) 이식부
        # -----------------------------------------------------------
        track5 = self.strategies.get("Track5")
        if track5:
            # 1) 진입 로직: 아침 개장 직후 갭 발생 평가
            gap_res = track5.evaluate_gap_divergence(
                current_price=ctx.current_price,
                prev_close=ctx.prev_price,
                market_vol=1.0,  # TODO: get from ctx.telemetry
                current_regime=ctx.current_regime
            )
            
            if gap_res.get("trigger"):
                # Track 5는 갭 방향의 반대로 선물을 매매함
                side = "SELL" if gap_res["direction"] == "SHORT" else "BUY"
                qty = int((ctx.account.current_capital * 0.02) / (ctx.current_price * 250000))
                qty = max(1, qty)
                
                orders.append({
                    "track": "Track5",
                    "type": "FUTURES",
                    "side": side,
                    "qty": qty,
                    "price": ctx.current_price,
                    "tag_id": f"GAP_{side}_{int(ctx.current_price)}"
                })
                
                logger.info(f"Track 5 Order generated: {orders[-1]}")
                
            # 2) 청산 로직: 갭이 메워졌거나 타임아웃 시
            if track5.gap_state.get("is_active"):
                eval_res = track5.evaluate_mean_reversion(ctx.current_price)
                if eval_res.get("close_signal"):
                    # 청산 주문 생성
                    close_side = "BUY" if track5.gap_state["direction"] == "SHORT" else "SELL"
                    orders.append({
                        "track": "Track5",
                        "type": "FUTURES",
                        "side": close_side,
                        "qty": track5.gap_state.get("entry_qty", 1),
                        "price": ctx.current_price,
                        "tag_id": f"GAP_CLOSE_{close_side}"
                    })
                    logger.info(f"Track 5 Close Order generated: {orders[-1]}")

        # -----------------------------------------------------------
        # [이식] Track 1: 100% 방어막 유지 (양매도)
        # -----------------------------------------------------------
        track1 = self.strategies.get("Track1")
        if track1:
            eval_result = track1.evaluate_strategy(
                current_price=ctx.current_price,
                regime=ctx.current_regime,
                # mock 서버에서는 포트폴리오 상태를 직접 넘겨 평가했음
                portfolio_options=ctx.portfolio.options,
                futures_qty=ctx.portfolio.current_position_qty
            )
            if eval_result.get("action") == "ENTRY":
                # 진입 주문 생성
                orders.append({
                    "track": "Track1",
                    "type": "CALL",
                    "side": "SELL",
                    "qty": eval_result.get("qty", 1),
                    "strike": eval_result.get("call_strike", ctx.current_price + 2.5),
                    "price": 2.50,
                    "tag_id": "T1_ENTRY_C"
                })
                orders.append({
                    "track": "Track1",
                    "type": "PUT",
                    "side": "SELL",
                    "qty": eval_result.get("qty", 1),
                    "strike": eval_result.get("put_strike", ctx.current_price - 2.5),
                    "price": 2.50,
                    "tag_id": "T1_ENTRY_P"
                })
            elif eval_result.get("action") == "HEDGE":
                # 헷지 선물 주문
                side = eval_result.get("side", "BUY")
                orders.append({
                    "track": "Track1",
                    "type": "FUTURES",
                    "side": side,
                    "qty": 1,
                    "tag_id": f"T1_HEDGE_{side}"
                })

        # -----------------------------------------------------------
        # [이식] Track 6: 0DTE 당일 옵션 보험
        # -----------------------------------------------------------
        track6 = self.strategies.get("Track6")
        if track6 and not track6.insurance_state.get("is_active"):
            # TODO: 실제로는 특정 시간(14:00 이후 등)에 평가
            t6_res = track6.evaluate_insurance_buy(
                current_price=ctx.current_price,
                volatility=1.0,
                regime=ctx.current_regime
            )
            if t6_res.get("trigger"):
                qty = t6_res.get("qty", 1)
                for side_opt in ["CALL", "PUT"]:
                    orders.append({
                        "track": "Track6",
                        "type": side_opt,
                        "side": "BUY",
                        "qty": qty,
                        "strike": t6_res.get(f"{side_opt.lower()}_strike", ctx.current_price),
                        "price": 0.50,
                        "tag_id": f"T6_BUY_{side_opt}"
                    })

        # -----------------------------------------------------------
        # [이식] Track 8: 월물 초입 DTE 15일 이상 자본 2% 예산 양매수
        # -----------------------------------------------------------
        track8 = self.strategies.get("Track8")
        if track8 and not track8.strangle_state.get("is_active"):
            t8_res = track8.evaluate_strangle_entry(
                current_price=ctx.current_price,
                regime=ctx.current_regime
            )
            if t8_res.get("trigger"):
                for side_opt in ["CALL", "PUT"]:
                    orders.append({
                        "track": "Track8",
                        "type": side_opt,
                        "side": "BUY",
                        "qty": t8_res.get("qty", 1),
                        "strike": t8_res.get(f"{side_opt.lower()}_strike", ctx.current_price),
                        "tag_id": f"T8_ENTRY_{side_opt}"
                    })

        # -----------------------------------------------------------
        # [이식] Track 2: 비대칭 휩소 트랩 방어
        # -----------------------------------------------------------
        track2 = self.strategies.get("Track2")
        if track2:
            t2_res = track2.evaluate_hedge(
                current_price=ctx.current_price,
                regime=ctx.current_regime
            )
            if t2_res.get("trigger"):
                side = t2_res.get("side", "SELL")
                orders.append({
                    "track": "Track2",
                    "type": "FUTURES",
                    "side": side,
                    "qty": t2_res.get("qty", 1),
                    "price": ctx.current_price,
                    "tag_id": f"T2_HEDGE_{side}"
                })

        # -----------------------------------------------------------
        # [이식] Track 3: 통계적 차익거래 (보류/대기)
        # -----------------------------------------------------------
        track3 = self.strategies.get("Track3")
        if track3 and track3.arb_state.get("is_active"):
            t3_res = track3.evaluate_arbitrage(
                current_price=ctx.current_price,
                fair_value=ctx.current_price, # mock
                regime=ctx.current_regime
            )
            if t3_res.get("trigger"):
                orders.append({
                    "track": "Track3",
                    "type": "FUTURES",
                    "side": t3_res.get("side", "BUY"),
                    "qty": t3_res.get("qty", 1),
                    "tag_id": "T3_ARB_EXEC"
                })

        # -----------------------------------------------------------
        # [이식] Track 4: 감마 스캘핑
        # -----------------------------------------------------------
        track4 = self.strategies.get("Track4")
        if track4:
            t4_res = track4.evaluate_gamma_scalping(
                current_price=ctx.current_price,
                portfolio_delta=0.0, # mock
                regime=ctx.current_regime
            )
            if t4_res.get("trigger"):
                orders.append({
                    "track": "Track4",
                    "type": "FUTURES",
                    "side": t4_res.get("side", "BUY"),
                    "qty": t4_res.get("qty", 1),
                    "tag_id": "T4_GAMMA_SCALP"
                })

        # -----------------------------------------------------------
        # [이식] Track 7: 위클리 옵션 테일 리스크 방어
        # -----------------------------------------------------------
        track7 = self.strategies.get("Track7")
        if track7 and not track7.insurance_state.get("is_active"):
            t7_res = track7.evaluate_insurance_buy(
                current_price=ctx.current_price,
                volatility=1.0,
                regime=ctx.current_regime
            )
            if t7_res.get("trigger"):
                for side_opt in ["CALL", "PUT"]:
                    orders.append({
                        "track": "Track7",
                        "type": side_opt,
                        "side": "BUY",
                        "qty": t7_res.get("qty", 1),
                        "strike": t7_res.get(f"{side_opt.lower()}_strike", ctx.current_price),
                        "tag_id": f"T7_ENTRY_{side_opt}"
                    })

        return orders
