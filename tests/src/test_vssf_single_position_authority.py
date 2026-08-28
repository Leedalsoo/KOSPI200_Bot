import unittest

from shared.contracts.canonical import (
    CanonicalAssetType,
    CanonicalOrderCommand,
    CanonicalOrderSide,
)
from virtual_securities_firm.runtime.firm_runtime import VirtualSecuritiesFirmRuntime


def make_order(order_id: str, side: CanonicalOrderSide, qty: int = 1, price: float = 2.0):
    return CanonicalOrderCommand(
        client_order_id=order_id,
        track_id="Track1",
        asset_type=CanonicalAssetType.OPTION,
        side=side,
        qty=qty,
        price=price,
    )


class TestVssfSinglePositionAuthority(unittest.TestCase):
    def test_account_positions_is_position_manager_authoritative_store(self):
        vssf = VirtualSecuritiesFirmRuntime()
        self.assertIs(vssf.account.positions, vssf.account.position_mgr.positions)

        vssf.account.positions["MANUAL"] = {
            "qty": 1,
            "avg_price": 2.0,
            "side": "BUY",
        }
        self.assertIn("MANUAL", vssf.account.position_mgr.positions)

    def test_execution_pipeline_mutates_only_vssf_position_manager_store(self):
        vssf = VirtualSecuritiesFirmRuntime(initial_capital=25_000_000.0)
        before_store = vssf.account.position_mgr.positions

        report = vssf.process_order(
            make_order("VSSF-AUTH-001", CanonicalOrderSide.BUY, qty=2, price=2.0)
        )

        self.assertIsNotNone(report)
        self.assertIs(vssf.account.positions, before_store)
        self.assertEqual(vssf.account.get_positions(), before_store)
        self.assertGreater(len(before_store), 0)

    def test_canonical_snapshot_is_copy_not_second_mutable_authority(self):
        vssf = VirtualSecuritiesFirmRuntime(initial_capital=25_000_000.0)
        report = vssf.process_order(
            make_order("VSSF-AUTH-002", CanonicalOrderSide.BUY, qty=1, price=2.0)
        )
        self.assertIsNotNone(report)

        snapshot = vssf.get_account_snapshot()
        self.assertEqual(snapshot.positions, vssf.account.position_mgr.positions)
        self.assertIsNot(snapshot.positions, vssf.account.position_mgr.positions)

        key = next(iter(snapshot.positions))
        snapshot.positions[key]["qty"] = 999
        self.assertNotEqual(
            vssf.account.position_mgr.positions[key]["qty"],
            snapshot.positions[key]["qty"],
        )

    def test_duplicate_execution_report_does_not_create_second_position_mutation(self):
        vssf = VirtualSecuritiesFirmRuntime(initial_capital=25_000_000.0)
        report = vssf.process_order(
            make_order("VSSF-AUTH-003", CanonicalOrderSide.BUY, qty=1, price=2.0)
        )
        self.assertIsNotNone(report)

        positions_before = {
            key: dict(value)
            for key, value in vssf.account.position_mgr.positions.items()
        }
        vssf.account.apply_execution(report)

        self.assertEqual(vssf.account.position_mgr.positions, positions_before)


if __name__ == "__main__":
    unittest.main()
