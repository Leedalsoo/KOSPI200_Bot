"""[8단계-6] Paper/Shadow/Real 상태 격리 유지 검증.
검증 범위:
1. BrokerFactory가 PAPER/SHADOW/REAL을 올바른 adapter로 분리 선택한다.
2. 별도 TradingSystem의 PAPER/SHADOW VSSF/account/order 상태가 서로 독립이다.
3. PAPER 상태가 SHADOW로 누수되지 않는다.
4. SHADOW 상태가 PAPER로 누수되지 않는다.
5. REAL adapter가 simulated VSSF 상태를 사용/변경하지 않는다.
6. REAL mode는 safety interlock을 유지하며 실제 주문을 전송하지 않는다.
"""
import asyncio
from main import TradingSystem
from option_program.broker.broker_interface import (
    BrokerFactory,
    BrokerMode,
    PaperBrokerAdapter,
    ShadowBrokerAdapter,
)
from option_program.broker.real_broker_adapter import RealBrokerAdapter, RealBrokerConfig


def test_broker_factory_selects_distinct_mode_adapters():
    """PAPER/SHADOW/REAL 모드가 각각 올바른 adapter로 선택되는지 검증."""
    paper = BrokerFactory.create_broker(BrokerMode.PAPER)
    shadow = BrokerFactory.create_broker(BrokerMode.SHADOW)
    real = BrokerFactory.create_broker(BrokerMode.REAL)
    assert isinstance(paper, PaperBrokerAdapter)
    assert isinstance(shadow, ShadowBrokerAdapter)
    assert isinstance(real, RealBrokerAdapter)
    assert type(paper) is not type(shadow)
    assert type(shadow) is not type(real)
    assert type(paper) is not type(real)


def test_paper_and_shadow_use_independent_vssf_state():
    """PAPER와 SHADOW를 별도 TradingSystem으로 실행하면 VSSF/account 상태가 교차 오염되지 않음."""
    async def scenario() -> None:
        paper_system = TradingSystem(config={"broker_mode": "PAPER"})
        shadow_system = TradingSystem(config={"broker_mode": "SHADOW"})
        await paper_system.initialize()
        await shadow_system.initialize()
        assert paper_system.broker_mode == "PAPER"
        assert shadow_system.broker_mode == "SHADOW"
        assert paper_system.broker is not shadow_system.broker
        assert paper_system.vssf is not shadow_system.vssf
        assert paper_system.broker.vssf is paper_system.vssf
        assert shadow_system.broker.vssf is shadow_system.vssf
        paper_initial = paper_system.vssf.get_account_snapshot()
        shadow_initial = shadow_system.vssf.get_account_snapshot()
        initial_paper_balance = paper_initial.total_balance
        initial_shadow_balance = shadow_initial.total_balance
        assert initial_paper_balance == initial_shadow_balance
        # PAPER에만 계좌 상태 변화를 발생시키고 SHADOW가 영향을 받지 않는지 확인.
        paper_system.vssf.account.balance = initial_paper_balance - 12345.0
        paper_after = paper_system.vssf.get_account_snapshot()
        shadow_after = shadow_system.vssf.get_account_snapshot()
        assert paper_after.total_balance == initial_paper_balance - 12345.0
        assert shadow_after.total_balance == initial_shadow_balance
        await paper_system.shutdown()
        await shadow_system.shutdown()

    asyncio.run(scenario())


def test_real_adapter_does_not_share_simulated_vssf_state():
    """REAL adapter는 VSSF simulated state를 소유/공유하지 않음을 검증."""
    async def scenario() -> None:
        system = TradingSystem(config={"broker_mode": "PAPER"})
        await system.initialize()
        simulated_vssf = system.vssf
        real = RealBrokerAdapter(
            config=RealBrokerConfig(
                is_simulation=True,
                app_key="TEST_KEY",
                app_secret="TEST_SECRET",
            )
        )
        assert not hasattr(real, "vssf")
        assert real.config.is_simulation is True
        assert real._orders_history == {}
        assert real._pending_executions == []
        before = simulated_vssf.get_account_snapshot()
        assert real.connect() is True
        after = simulated_vssf.get_account_snapshot()
        assert after.total_balance == before.total_balance
        assert after.used_margin == before.used_margin
        assert after.free_margin == before.free_margin
        assert real._orders_history == {}
        assert real._pending_executions == []
        await system.shutdown()

    asyncio.run(scenario())


def test_real_mode_safety_interlock_blocks_live_order_without_arm():
    """REAL non-simulation 환경에서 명시적 ARM 없이는 실주문이 차단됨을 검증."""
    from shared.contracts.canonical import (
        CanonicalOrderCommand,
        CanonicalAssetType,
        CanonicalOrderSide,
    )
    real = RealBrokerAdapter(
        config=RealBrokerConfig(
            is_simulation=False,
            app_key="TEST_KEY",
            app_secret="TEST_SECRET",
            safety_arm_key="",
        )
    )
    real._connected = True
    command = CanonicalOrderCommand(
        client_order_id="MODE-ISOLATION-LIVE-BLOCK",
        track_id="Track1",
        asset_type=CanonicalAssetType.FUTURES,
        side=CanonicalOrderSide.BUY,
        qty=1,
        price=350.0,
        symbol="KOSPI200",
    )
    assert real.send_order(command) is None
    assert real._orders_history == {}
    assert real._pending_executions == []
