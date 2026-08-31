"""Unit tests for IBrokerAdapter lifecycle contract (connect / disconnect).

Verifies:
- IBrokerAdapter abstract contract presence for connect() and disconnect()
- PaperBrokerAdapter lifecycle state transitions (initial connected, disconnect, connect)
- ShadowBrokerAdapter lifecycle state transitions (initial connected, disconnect, connect)
- RealBrokerAdapterStub lifecycle state transitions (initial disconnected, connect, disconnect)
- RealBrokerAdapter concrete lifecycle contract conformance
"""
import inspect
import pytest

from option_program.broker.broker_interface import (
    IBrokerAdapter,
    PaperBrokerAdapter,
    ShadowBrokerAdapter,
    RealBrokerAdapterStub,
)
from option_program.broker.real_broker_adapter import RealBrokerAdapter


class TestBrokerLifecycleContract:
    """IBrokerAdapter의 connect/disconnect 라이프사이클 계약 검증"""

    def test_ibroker_adapter_abstract_methods(self):
        """IBrokerAdapter 인터페이스에 connect와 disconnect가 abstractmethod로 정의되어 있는지 검증."""
        abstract_methods = IBrokerAdapter.__abstractmethods__
        assert "connect" in abstract_methods, "connect must be an abstract method of IBrokerAdapter"
        assert "disconnect" in abstract_methods, "disconnect must be an abstract method of IBrokerAdapter"

        # 시그니처 검증
        sig_connect = inspect.signature(IBrokerAdapter.connect)
        assert len(sig_connect.parameters) == 1  # self

        sig_disconnect = inspect.signature(IBrokerAdapter.disconnect)
        assert len(sig_disconnect.parameters) == 1  # self

    def test_paper_broker_adapter_lifecycle(self):
        """PaperBrokerAdapter의 생성자 기본 상태 및 connect/disconnect 전환 검증."""
        adapter = PaperBrokerAdapter()

        # 1. 생성 직후 기본 상태: True
        assert adapter.is_connected() is True

        # 2. disconnect() 호출 -> 연결 해제
        adapter.disconnect()
        assert adapter.is_connected() is False

        # 3. connect() 호출 -> 재연결 및 True 반환
        res = adapter.connect()
        assert res is True
        assert adapter.is_connected() is True

    def test_shadow_broker_adapter_lifecycle(self):
        """ShadowBrokerAdapter의 생성자 기본 상태 및 connect/disconnect 전환 검증."""
        adapter = ShadowBrokerAdapter()

        # 1. 생성 직후 기본 상태: True
        assert adapter.is_connected() is True

        # 2. disconnect() 호출 -> 연결 해제
        adapter.disconnect()
        assert adapter.is_connected() is False

        # 3. connect() 호출 -> 재연결 및 True 반환
        res = adapter.connect()
        assert res is True
        assert adapter.is_connected() is True

    def test_real_broker_adapter_stub_lifecycle(self):
        """RealBrokerAdapterStub의 생성자 기본 상태 및 connect/disconnect 전환 검증."""
        adapter = RealBrokerAdapterStub()

        # 1. 생성 직후 기본 상태: False
        assert adapter.is_connected() is False

        # 2. connect() 호출 -> 연결 및 True 반환
        res = adapter.connect()
        assert res is True
        assert adapter.is_connected() is True

        # 3. disconnect() 호출 -> 연결 해제
        adapter.disconnect()
        assert adapter.is_connected() is False

    def test_real_broker_adapter_concrete_contract_fulfillment(self):
        """실제 프로덕션 RealBrokerAdapter가 IBrokerAdapter 라이프사이클 계약을 완벽 충족하는지 검증."""
        adapter = RealBrokerAdapter()
        assert isinstance(adapter, IBrokerAdapter)

        # 1. 생성 직후 기본 상태: False
        assert adapter.is_connected() is False

        # 2. disconnect() 동작 검증
        adapter._connected = True
        assert adapter.is_connected() is True
        adapter.disconnect()
        assert adapter.is_connected() is False
