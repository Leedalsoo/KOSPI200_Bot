"""Option Broker Client Interface for M3 Broker Boundary."""
from typing import Optional
from shared.contracts.canonical import CanonicalOrderCommand, CanonicalExecutionReport

class OptionBrokerClient:
    """[M3 옵션 브로커 클라이언트: OptionProgram 과 VSSF 가상 증권사 간 표준 주문/체결 통신 인터페이스]"""
    def __init__(self, vssf_runtime):
        self.vssf_runtime = vssf_runtime

    def submit_order(self, command: CanonicalOrderCommand) -> Optional[CanonicalExecutionReport]:
        return self.vssf_runtime.process_order(command)

    def get_account_summary(self):
        return self.vssf_runtime.account.canonical_summary()
