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
    """Validates RealBrokerAdapter OAuth2 token issuance, order placement, cancellation, and balance sync via explicit MockTransport."""
    # 1. Define Explicit In-Memory Mock Transport (Zero network calls)
    network_calls = []

    def mock_transport(method: str, path: str, headers: dict, body: dict) -> dict:
        network_calls.append({"method": method, "path": path, "body": body})
        if path == "/oauth2/tokenP":
            return {"access_token": "MOCK_BEARER_TOKEN", "token_type": "Bearer", "expires_in": 86400}
        elif "order-rvsecncl" in path:
            return {"rt_cd": "0", "msg1": "정상 취소되었습니다."}
        elif "order" in path:
            return {"rt_cd": "0", "output": {"ODNO": "ORD-123456"}}
        elif "inquire-balance" in path:
            return {"rt_cd": "0", "output1": {"dnca_tot_amt": "50000000", "tot_evlu_amt": "50000000"}}
        return {"rt_cd": "0"}

    config = RealBrokerConfig(
        broker_name="KIS_OPENAPI",
        app_key="TEST_APP_KEY",
        app_secret="TEST_APP_SECRET",
        account_no="50012345-01",
        is_simulation=True
    )
    client = RealBrokerHttpClient(config=config, transport=mock_transport)
    broker = RealBrokerAdapter(config=config, http_client=client)
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
    assert exec_rep.exec_id == "EXEC-REAL-ORD-123456"

    # 3. Cancel Order
    assert broker.cancel_order("REAL-LIVE-001") is True
    assert broker.cancel_order("UNKNOWN_ORD") is False

    # 4. Inquire Live Balance
    summary = broker.get_account_summary()
    assert summary.account_id == "50012345-01"
    assert summary.total_balance == 50_000_000.0

    # 5. Factory Integration
    factory_broker = BrokerFactory.create_broker(mode=BrokerMode.REAL, broker_config=config)
    assert isinstance(factory_broker, RealBrokerAdapter)

def test_real_broker_safety_interlock_guard():
    """Validates that real live orders are hard-blocked without ARM_REAL_TRADING_ORDERS safety key."""
    config_locked = RealBrokerConfig(
        broker_name="KIS_OPENAPI",
        app_key="TEST_KEY",
        app_secret="TEST_SECRET",
        is_simulation=False,
        safety_arm_key=""  # Not confirmed
    )
    broker_locked = RealBrokerAdapter(config=config_locked)
    broker_locked._connected = True

    cmd = CanonicalOrderCommand(
        client_order_id="REAL-HAZARD-001",
        track_id="Track1",
        asset_type=CanonicalAssetType.FUTURES,
        side=CanonicalOrderSide.BUY,
        qty=1,
        price=350.0,
        option_type=CanonicalOptionType.CALL,
        strike=350.0,
        tag_id="hazard"
    )
    # Must be safely blocked
    assert broker_locked.send_order(cmd) is None
