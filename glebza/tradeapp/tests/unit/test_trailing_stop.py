import unittest

import pandas as pd

from glebza.tradeapp.src.framework.risk.trailing_stop import apply_trailing_stop
from glebza.tradeapp.src.framework.sizing import apply_position_inertia


class TestTrailingStop(unittest.TestCase):
    def test_trailing_stop_exits_long_and_blocks_same_side_reentry(self):
        target = pd.Series([100.0, 100.0, 100.0, 100.0, 100.0])
        close = pd.Series([100.0, 105.0, 103.0, 98.0, 101.0])
        volatility = pd.Series([1.0, 1.0, 1.0, 1.0, 1.0])

        position = apply_trailing_stop(
            target,
            close,
            volatility,
            multiplier=4.0,
            inertia_threshold=0.0,
        )

        self.assertEqual(position.tolist(), [100.0, 100.0, 100.0, 0.0, 0.0])

    def test_trailing_stop_exits_short(self):
        target = pd.Series([-50.0, -50.0, -50.0, -50.0])
        close = pd.Series([100.0, 95.0, 97.0, 102.0])
        volatility = pd.Series([1.0, 1.0, 1.0, 1.0])

        position = apply_trailing_stop(
            target,
            close,
            volatility,
            multiplier=4.0,
            inertia_threshold=0.0,
        )

        self.assertEqual(position.tolist(), [-50.0, -50.0, -50.0, 0.0])

    def test_trailing_stop_allows_reentry_after_target_flips(self):
        target = pd.Series([100.0, 100.0, 0.0, -50.0])
        close = pd.Series([100.0, 90.0, 89.0, 88.0])
        volatility = pd.Series([1.0, 1.0, 1.0, 1.0])

        position = apply_trailing_stop(
            target,
            close,
            volatility,
            multiplier=4.0,
            inertia_threshold=0.0,
        )

        self.assertEqual(position.tolist(), [100.0, 0.0, 0.0, -50.0])

    def test_trailing_stop_with_inertia_matches_standalone_inertia_when_price_never_hits_stop(self):
        target = pd.Series([50.0, 54.0, 55.0, 42.0, 50.0])
        close = pd.Series([100.0, 100.0, 100.0, 100.0, 100.0])
        volatility = pd.Series([10.0, 10.0, 10.0, 10.0, 10.0])

        with_stop = apply_trailing_stop(target, close, volatility, multiplier=4.0, inertia_threshold=0.10)
        without_stop = apply_position_inertia(target, threshold=0.10)

        pd.testing.assert_series_equal(with_stop, without_stop)


if __name__ == "__main__":
    unittest.main()
