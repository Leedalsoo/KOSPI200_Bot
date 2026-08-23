"""Unit Test: Production Real Broker Adapter Layer & Live Protocol Integration."""
import pytest
from shared.contracts.canonical import (
    CanonicalOrderCommand,
    CanonicalOrderSide,
    CanonicalAssetType,
    CanonicalOptionType
)
from option_program.broker.broker_interface import BrokerFactory, BrokerMode
from option_program.broker.real_broker_adapter import (
    RealBrokerAdapter,
    RealBrokerConfig,
    RealBrokerHttpClient
)

def test_real_broker_adapter_authentication_and_order_lifecycle():
    """Validates RealBrokerAdapter OAuth2 token issuance, order placement, cancellation, and balance sync."""
    config = RealBrokerConfig(
        broker_name="KIS_OPENAPI",
        app_key="TEST_APP_KEY",
        app_secret="TEST_APP_SECRET",
        account_no="50012345-01",
        is_simulation=True
    )
    broker = RealBrokerAdapter(config=config)
    assert broker.is_connected() is False

    # 1. Connect & OAuth2 Authenticate
    assert broker.connect() is True
    assert broker.is_connected() is True
    assert broker.client.is_token_valid() is True

    # 2. Send Real Derivative Order (Call Option)
    cmd = CanonicalOrderCommand(
        client_order_id="REAL-LIVE-001",
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=2,
        price=3.50,
        option_type=CanonicalOptionType.CALL,
        strike=350.0,
        tag_id="real_test"
    )
    exec_rep = broker.send_order(cmd)
    assert exec_rep is not None
    assert exec_rep.client_order_id == "REAL-LIVE-001"
    assert exec_rep.executed_qty == 2
    assert exec_rep.executed_price == 3.50
    assert exec_rep.exec_id.startswith("EXEC-REAL-")

    # 3. Cancel Order
    assert broker.cancel_order("REAL-LIVE-001") is True
    assert broker.cancel_order("UNKNOWN_ORD") is False

    # 4. Inquire Live Balance
    summary = broker.get_account_summary()
    assert summary.account_id == "50012345-01"
    assert summary.total_balance == 50_000_000.0
    assert summary.free_margin > 0

    # 5. Factory Integration
    factory_broker = BrokerFactory.create_broker(mode=BrokerMode.REAL, broker_config=config)
    assert isinstance(factory_broker, RealBrokerAdapter)
