from datetime import datetime, timedelta, timezone
import math
import unittest

import pandas as pd

from glebza.tradeapp.src.framework.backtest import BacktestResult, run_single_instrument_backtest


def klines_dataframe(closes):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return pd.DataFrame(
        [
            {
                "k_interval": start + timedelta(days=i),
                "close_price": close,
            }
            for i, close in enumerate(closes)
        ]
    )


class TestFrameworkBacktest(unittest.TestCase):
    def test_single_instrument_backtest_returns_expected_columns(self):
        klines = klines_dataframe([100 + i + (0.5 if i % 2 else 0.0) for i in range(300)])

        result = run_single_instrument_backtest(klines)

        self.assertIsInstance(result, BacktestResult)
        self.assertEqual(len(result.rows), len(klines))
        self.assertTrue(
            {
                "combined_forecast",
                "position",
                "return",
                "strategy_return",
                "equity",
                "drawdown",
            }.issubset(result.rows.columns)
        )

    def test_strategy_return_uses_previous_position(self):
        klines = klines_dataframe([100 + i + (0.5 if i % 2 else 0.0) for i in range(300)])

        rows = run_single_instrument_backtest(klines).rows

        expected = rows["position"].shift(1).fillna(0.0) * rows["return"]
        pd.testing.assert_series_equal(rows["strategy_return"], expected, check_names=False)

    def test_summary_stats_are_finite(self):
        klines = klines_dataframe([100 + i + (0.5 if i % 2 else 0.0) for i in range(300)])

        result = run_single_instrument_backtest(klines)

        self.assertTrue(math.isfinite(result.total_return))
        self.assertTrue(math.isfinite(result.annualized_return))
        self.assertTrue(math.isfinite(result.annualized_volatility))
        self.assertTrue(math.isfinite(result.sharpe))
        self.assertTrue(math.isfinite(result.max_drawdown))


if __name__ == "__main__":
    unittest.main()
