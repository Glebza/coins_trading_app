from datetime import datetime, timedelta, timezone
import math
import unittest

import pandas as pd

from glebza.tradeapp.src.framework.backtest import (
    BacktestAccount,
    BacktestResult,
    run_single_instrument_backtest,
)


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
                "price_volatility",
                "position",
                "return",
                "price_change",
                "strategy_return",
                "equity",
                "drawdown",
            }.issubset(result.rows.columns)
        )

    def test_strategy_return_uses_previous_position(self):
        klines = klines_dataframe([100 + i + (0.5 if i % 2 else 0.0) for i in range(300)])

        rows = run_single_instrument_backtest(klines).rows

        expected = rows["position"].shift(1).fillna(0.0) * rows["price_change"] / 100_000.0
        pd.testing.assert_series_equal(rows["strategy_return"], expected, check_names=False)

    def test_position_size_uses_account_volatility_target(self):
        klines = klines_dataframe([100 + i + (0.5 if i % 2 else 0.0) for i in range(300)])
        low_risk = BacktestAccount(trading_capital=100_000.0, annualized_volatility_target=0.10)
        high_risk = BacktestAccount(trading_capital=100_000.0, annualized_volatility_target=0.20)

        low_risk_position = run_single_instrument_backtest(klines, account=low_risk).rows["position"].abs().iloc[-1]
        high_risk_position = run_single_instrument_backtest(klines, account=high_risk).rows["position"].abs().iloc[-1]

        self.assertAlmostEqual(high_risk_position, low_risk_position * 2.0)

    def test_commission_reduces_strategy_return(self):
        klines = klines_dataframe([100 + i + (0.5 if i % 2 else 0.0) for i in range(300)])
        without_commission = BacktestAccount(
            trading_capital=100_000.0,
            annualized_volatility_target=0.20,
            commission_rate=0.0,
        )
        with_commission = BacktestAccount(
            trading_capital=100_000.0,
            annualized_volatility_target=0.20,
            commission_rate=0.001,
        )

        no_cost_result = run_single_instrument_backtest(klines, account=without_commission)
        cost_result = run_single_instrument_backtest(klines, account=with_commission)

        self.assertGreater(cost_result.rows["commission"].sum(), 0.0)
        self.assertLess(cost_result.total_return, no_cost_result.total_return)

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
