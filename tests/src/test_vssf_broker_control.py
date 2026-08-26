import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

# 프로젝트 루트 디렉토리를 sys.path에 추가하여 직접 스크립트 실행 시 모듈 경로 인식
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from option_program.broker.broker_interface import PaperBrokerAdapter  # noqa: E402
from shared.contracts.canonical import (  # noqa: E402
    CanonicalAssetType,
    CanonicalOrderCommand,
    CanonicalOrderSide,
)
from virtual_securities_firm.runtime.firm_runtime import (  # noqa: E402
    VirtualSecuritiesFirmRuntime,
)
from web_interface.server import TargetArchitectureUIServer  # noqa: E402





def make_order(order_id="CTRL-001", price=2.0, qty=1):
    return CanonicalOrderCommand(
        client_order_id=order_id,
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=CanonicalOrderSide.BUY,
        qty=qty,
        price=price,
    )


class TestVSSFBrokerControl(unittest.TestCase):
    def test_margin_controls_and_one_shot_injections(self):
        vssf = VirtualSecuritiesFirmRuntime(initial_capital=25_000_000.0)
        normal = vssf.margin_engine.calculate_order_margin(make_order())
        self.assertEqual(normal, 500_000.0)

        vssf.set_margin_mode("TIGHT")
        tight = vssf._controlled_order_margin(make_order())
        self.assertEqual(tight, 750_000.0)

        vssf.set_leverage(2.0)
        leveraged = vssf._controlled_order_margin(make_order())
        self.assertEqual(leveraged, 375_000.0)

        vssf.inject_margin_call()
        self.assertIsNone(vssf.process_order(make_order("CTRL-CALL")))
        self.assertFalse(vssf.control_snapshot()["margin_call_pending"])

        vssf.inject_margin_shortage()
        self.assertIsNone(vssf.process_order(make_order("CTRL-SHORTAGE")))
        self.assertFalse(vssf.control_snapshot()["margin_shortage_pending"])

    def test_broker_controls(self):
        vssf = VirtualSecuritiesFirmRuntime(initial_capital=25_000_000.0)
        broker = PaperBrokerAdapter(vssf_runtime=vssf)

        broker.set_connection(False)
        self.assertFalse(broker.is_connected())
        self.assertIsNone(broker.send_order(make_order("CTRL-DISCONNECTED")))

        broker.set_connection(True)
        broker.set_execution_behavior("REJECT")
        self.assertIsNone(broker.send_order(make_order("CTRL-REJECT")))

        broker.set_execution_behavior("NORMAL")
        broker.set_latency(0)
        report = broker.send_order(make_order("CTRL-NORMAL"))
        self.assertIsNotNone(report)

        state = broker.control_snapshot()
        self.assertTrue(state["connected"])
        self.assertEqual(state["latency_ms"], 0.0)
        self.assertEqual(state["execution_behavior"], "NORMAL")

    def test_dispatcher_round_trip_to_vssf_and_broker(self):
        vssf = VirtualSecuritiesFirmRuntime(initial_capital=25_000_000.0)
        broker = PaperBrokerAdapter(vssf_runtime=vssf)
        system = SimpleNamespace(vssf=vssf, broker=broker)
        server = TargetArchitectureUIServer(system)

        async def run():
            result = await server.handle_command({"action": "set_margin_mode", "mode": "TIGHT"})
            self.assertEqual(result["status"], "APPLIED")
            self.assertEqual(vssf.control_snapshot()["margin_mode"], "TIGHT")

            result = await server.handle_command({"action": "set_leverage", "leverage": 2})
            self.assertEqual(result["status"], "APPLIED")
            self.assertEqual(vssf.control_snapshot()["leverage"], 2.0)

            result = await server.handle_command({"action": "set_broker_connection", "connected": False})
            self.assertEqual(result["status"], "APPLIED")
            self.assertFalse(broker.is_connected())

            result = await server.handle_command({"action": "set_execution_behavior", "mode": "REJECT"})
            self.assertEqual(result["status"], "APPLIED")
            self.assertEqual(broker.control_snapshot()["execution_behavior"], "REJECT")

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
