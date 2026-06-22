import unittest
from decimal import Decimal

from types import SimpleNamespace

from glebza.tradeapp.src.exchanges.tinvest_broker import (
    build_instrument_id,
    decimal_to_quotation,
    pick_latest_open_account_id,
    quotation_to_decimal,
)


class TestTinvestBrokerHelpers(unittest.TestCase):
    def test_build_instrument_id(self):
        self.assertEqual(build_instrument_id("SBER", "TQBR"), "SBER_TQBR")

    def test_decimal_quotation_roundtrip(self):
        value = Decimal("123.456789123")
        quotation = decimal_to_quotation(value)
        restored = quotation_to_decimal(quotation)
        self.assertAlmostEqual(float(restored), float(value), places=6)

    def test_pick_latest_open_account_id(self):
        accounts = [
            SimpleNamespace(
                id="older",
                status="ACCOUNT_STATUS_OPEN",
                opened_date=SimpleNamespace(seconds=100),
            ),
            SimpleNamespace(
                id="newer",
                status="ACCOUNT_STATUS_OPEN",
                opened_date=SimpleNamespace(seconds=200),
            ),
            SimpleNamespace(
                id="closed",
                status="ACCOUNT_STATUS_CLOSED",
                opened_date=SimpleNamespace(seconds=300),
            ),
        ]
        self.assertEqual(pick_latest_open_account_id(accounts), "newer")


if __name__ == "__main__":
    unittest.main()
