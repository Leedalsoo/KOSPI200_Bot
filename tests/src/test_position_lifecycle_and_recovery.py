import pytest

from virtual_securities_firm.account.paper_account import PaperTradingAccount
from virtual_securities_firm.recovery.state_recovery import StateRecoveryEngine


MULTIPLIER = 250000.0


def test_position_lifecycle_and_recovery():
    account = PaperTradingAccount()
    recovery = StateRecoveryEngine(account)
    symbol = "TEST"

    # 1. BUY 1 @100: Position 생성
    account.apply_execution(
        "Track1", side="BUY", qty=1, price=100.0, fee=0.0, symbol=symbol
    )
    pos = account.positions[symbol]
    assert pos["qty"] == 1
    assert pos["avg_price"] == pytest.approx(100.0)
    assert pos["side"] == "BUY"

    # 2. BUY 2 @120: Position 증가 + weighted average
    account.apply_execution(
        "Track1", side="BUY", qty=2, price=120.0, fee=0.0, symbol=symbol
    )
    pos = account.positions[symbol]
    expected_avg = 340.0 / 3.0
    assert pos["qty"] == 3
    assert pos["avg_price"] == pytest.approx(expected_avg)
    assert pos["side"] == "BUY"

    # 3. SELL 1 @130: 부분 감소
    account.apply_execution(
        "Track1", side="SELL", qty=1, price=130.0, fee=0.0, symbol=symbol
    )
    pos = account.positions[symbol]
    assert pos["qty"] == 2
    assert pos["avg_price"] == pytest.approx(expected_avg)
    assert pos["side"] == "BUY"
    assert account.realized_pnl == pytest.approx(
        (130.0 - expected_avg) * 1 * MULTIPLIER
    )

    # 4. SELL 2 @110: 완전 청산
    account.apply_execution(
        "Track1", side="SELL", qty=2, price=110.0, fee=0.0, symbol=symbol
    )
    assert symbol not in account.positions
    expected_total_realized = (
        (130.0 - expected_avg) * 1 * MULTIPLIER
        + (110.0 - expected_avg) * 2 * MULTIPLIER
    )
    assert account.realized_pnl == pytest.approx(expected_total_realized)

    # 5. 복구 대상 Position 생성
    account.apply_execution(
        "Track1", side="BUY", qty=2, price=100.0, fee=0.0, symbol=symbol
    )

    # 6. 실제 StateRecoveryEngine snapshot 생성
    snapshot = recovery.create_snapshot(sequence_id=1)
    snapshot_positions = {k: dict(v) for k, v in snapshot["positions"].items()}
    snapshot_balance = snapshot["balance"]
    snapshot_realized_pnl = snapshot["realized_pnl"]

    # 7. snapshot 이후 상태 변경
    account.apply_execution(
        "Track1", side="SELL", qty=1, price=120.0, fee=0.0, symbol=symbol
    )
    assert account.positions[symbol]["qty"] == 1

    # 8. 실제 StateRecoveryEngine을 통한 복구
    assert recovery.restore_from_snapshot(snapshot) is True

    # 9. Position / balance / realized_pnl 복구 검증
    assert account.positions == snapshot_positions
    assert account.balance == pytest.approx(snapshot_balance)
    assert account.realized_pnl == pytest.approx(snapshot_realized_pnl)

    # 10. VSSF Position 단일 권위(identity) 유지
    assert account.positions is account.position_mgr.positions
    assert account.get_positions() is account.position_mgr.positions
