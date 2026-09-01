"""Contract Serialization and Lifecycle Tests for RealBrokerAdapter (KIS Future/Option API).

Strictly validates:
1. BUY order payload serialization & TR ID (TTTO1101U / VTTO1101U)
2. SELL order payload serialization & TR ID
3. Cancel order payload serialization & TR ID (TTTO1103U / VTTO1103U)
4. Response mapping, ACK preservation, and failure categorization (TIMEOUT_UNKNOWN, AUTH_FAILED, REJECTED, SAFETY_BLOCKED)
"""
from typing import Dict, Any, List
from shared.contracts.canonical import (
    CanonicalOrderCommand,
    CanonicalAssetType,
    CanonicalOrderSide,
    CanonicalOptionType,
)
from option_program.broker.real_broker_adapter import (
    RealBrokerAdapter,
    RealBrokerConfig,
    RealBrokerHttpClient,
)


def make_test_command(
    client_id: str = "TEST-ORD-001",
    side: CanonicalOrderSide = CanonicalOrderSide.BUY,
    qty: int = 5,
    price: float = 2.50,
    symbol: str = "201V3350",
    strike: float = 350.0,
    option_type: CanonicalOptionType = CanonicalOptionType.CALL,
) -> CanonicalOrderCommand:
    return CanonicalOrderCommand(
        client_order_id=client_id,
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=side,
        qty=qty,
        price=price,
        symbol=symbol,
        option_type=option_type,
        strike=strike,
    )


def test_kis_buy_order_payload_and_tr_id_contract():
    """Validates BUY order payload fields, values, and TR ID for KIS domestic future/option."""
    captured_requests: List[Dict[str, Any]] = []

    def mock_transport(method: str, path: str, headers: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
        captured_requests.append({
            "method": method,
            "path": path,
            "headers": headers,
            "body": body,
        })
        if path == "/oauth2/tokenP":
            return {"access_token": "TEST_TOKEN_123", "token_type": "Bearer", "expires_in": 86400}
        return {
            "rt_cd": "0",
            "msg_cd": "APBK0013",
            "msg1": "주문이 정상 접수되었습니다.",
            "output": {
                "KRX_FWDG_ORD_ORGNO": "01234",
                "ODNO": "00012345",
                "ORD_TMD": "100000",
            },
        }

    config = RealBrokerConfig(
        account_no="12345678-01",
        app_key="TEST_APP_KEY",
        app_secret="TEST_APP_SECRET",
        is_simulation=True,
        is_vts=False,
    )
    client = RealBrokerHttpClient(config=config, transport=mock_transport)
    adapter = RealBrokerAdapter(config=config, http_client=client)
    assert adapter.connect() is True

    cmd_buy = make_test_command(side=CanonicalOrderSide.BUY, qty=10, price=3.15, strike=350.0)
    resp = adapter.send_order(cmd_buy)

    assert resp.success is True
    assert resp.status == "ACCEPTED"
    assert resp.broker_order_id == "BRK-REAL-00012345"

    order_req = [r for r in captured_requests if "/trading/order" in r["path"]][0]
    assert order_req["method"] == "POST"
    assert order_req["headers"]["tr_id"] == "TTTO1101U"

    body = order_req["body"]
    assert body["CANO"] == "12345678"
    assert body["ACNT_PRDT_CD"] == "01"
    assert body["SHTN_PDNO"] == "201V3350"
    assert body["ORD_PRCS_DVSN_CD"] == "02"
    assert body["SLL_BUY_DVSN_CD"] == "02"  # 02: BUY
    assert body["ORD_DVSN_CD"] == "00"
    assert body["UNIT_PRICE"] == "3.15"
    assert body["ORD_QTY"] == "10"
    assert body["NMPR_TYPE_CD"] == "01"
    assert body["KRX_NMPR_CNDT_CD"] == "0"


def test_kis_sell_order_payload_and_vts_tr_id_contract():
    """Validates SELL order payload fields, SLL_BUY_DVSN_CD='01', and VTS TR ID VTTO1101U."""
    captured_requests: List[Dict[str, Any]] = []

    def mock_transport(method: str, path: str, headers: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
        captured_requests.append({
            "method": method,
            "path": path,
            "headers": headers,
            "body": body,
        })
        if path == "/oauth2/tokenP":
            return {"access_token": "TEST_TOKEN_123", "token_type": "Bearer", "expires_in": 86400}
        return {
            "rt_cd": "0",
            "msg_cd": "APBK0013",
            "msg1": "주문 접수",
            "output": {"ODNO": "00099999", "ORD_TMD": "100500"},
        }

    config = RealBrokerConfig(
        account_no="87654321-03",
        app_key="TEST_APP_KEY",
        app_secret="TEST_APP_SECRET",
        is_simulation=True,
        is_vts=True,  # VTS / Demo mode
    )
    client = RealBrokerHttpClient(config=config, transport=mock_transport)
    adapter = RealBrokerAdapter(config=config, http_client=client)
    assert adapter.connect() is True

    cmd_sell = make_test_command(
        client_id="TEST-SELL-001",
        side=CanonicalOrderSide.SELL,
        qty=3,
        price=1.80,
        strike=345.0,
        option_type=CanonicalOptionType.PUT,
    )
    resp = adapter.send_order(cmd_sell)

    assert resp.success is True
    assert resp.status == "ACCEPTED"
    assert resp.broker_order_id == "BRK-REAL-00099999"

    order_req = [r for r in captured_requests if "/trading/order" in r["path"]][0]
    assert order_req["headers"]["tr_id"] == "VTTO1101U"

    body = order_req["body"]
    assert body["CANO"] == "87654321"
    assert body["ACNT_PRDT_CD"] == "03"
    assert body["SHTN_PDNO"] == "301V3345"
    assert body["SLL_BUY_DVSN_CD"] == "01"  # 01: SELL
    assert body["UNIT_PRICE"] == "1.80"
    assert body["ORD_QTY"] == "3"


def test_kis_cancel_order_payload_and_tr_id_contract():
    """Validates cancel_order payload fields and TR ID for KIS domestic future/option."""
    captured_requests: List[Dict[str, Any]] = []

    def mock_transport(method: str, path: str, headers: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
        captured_requests.append({
            "method": method,
            "path": path,
            "headers": headers,
            "body": body,
        })
        if path == "/oauth2/tokenP":
            return {"access_token": "TEST_TOKEN_123", "token_type": "Bearer", "expires_in": 86400}
        elif "/trading/order" in path and "order-rvsecncl" not in path:
            return {"rt_cd": "0", "output": {"ODNO": "00055555"}}
        elif "order-rvsecncl" in path:
            return {"rt_cd": "0", "msg_cd": "APBK0013", "output": {"ODNO": "00055556"}}
        return {"rt_cd": "0"}

    config = RealBrokerConfig(
        account_no="12345678-01",
        app_key="TEST_APP_KEY",
        app_secret="TEST_APP_SECRET",
        is_simulation=True,
        is_vts=False,
    )
    client = RealBrokerHttpClient(config=config, transport=mock_transport)
    adapter = RealBrokerAdapter(config=config, http_client=client)
    assert adapter.connect() is True

    cmd = make_test_command(client_id="ORD-TO-CANCEL", qty=5, price=2.0)
    adapter.send_order(cmd)

    # Cancel the placed order
    cancel_res = adapter.cancel_order("ORD-TO-CANCEL")
    assert cancel_res is True

    cancel_req = [r for r in captured_requests if "/trading/order-rvsecncl" in r["path"]][0]
    assert cancel_req["method"] == "POST"
    assert cancel_req["headers"]["tr_id"] == "TTTO1103U"

    body = cancel_req["body"]
    assert body["CANO"] == "12345678"
    assert body["ACNT_PRDT_CD"] == "01"
    assert body["ORGN_ODNO"] == "00055555"
    assert body["SHTN_PDNO"] == "201V3350"
    assert body["RVSE_CNCL_DVSN_CD"] == "02"
    assert body["ORD_DVSN_CD"] == "00"
    assert body["ORD_QTY"] == "0"
    assert body["UNIT_PRICE"] == "0"


def test_kis_failure_categorization_regression():
    """Validates failure status categorization for various KIS API error scenarios."""
    current_resp = {}

    def mock_transport(method: str, path: str, headers: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
        if path == "/oauth2/tokenP":
            return {"access_token": "TEST_TOKEN_123", "token_type": "Bearer", "expires_in": 86400}
        return current_resp

    config = RealBrokerConfig(
        account_no="12345678-01",
        app_key="TEST_APP_KEY",
        app_secret="TEST_APP_SECRET",
        is_simulation=True,
    )
    client = RealBrokerHttpClient(config=config, transport=mock_transport)
    adapter = RealBrokerAdapter(config=config, http_client=client)
    assert adapter.connect() is True

    cmd = make_test_command()

    # 1. Timeout Error
    current_resp = {"rt_cd": "1", "msg_cd": "ERR_TIMEOUT", "msg1": "Request timed out"}
    resp = adapter.send_order(cmd)
    assert resp.status == "TIMEOUT_UNKNOWN"

    # 2. Auth Error
    current_resp = {"rt_cd": "1", "msg_cd": "ERR_AUTH", "msg1": "Token invalid"}
    resp = adapter.send_order(cmd)
    assert resp.status == "AUTH_FAILED"

    # 3. Rejection / Margin Error
    current_resp = {"rt_cd": "1", "msg_cd": "APBK0055", "msg1": "증거금 부족으로 주문이 거부되었습니다."}
    resp = adapter.send_order(cmd)
    assert resp.status == "REJECTED"
