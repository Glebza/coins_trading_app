from datetime import datetime, timedelta, timezone
import math
import unittest

import pandas as pd

from glebza.tradeapp.src.framework.backtest import (
    TradingAccount,
    BacktestResult,
    run_single_instrument_backtest,
)
from glebza.tradeapp.src.framework.backtest.engine import (
    _run_compounding_backtest_rows,
    calculate_single_instrument_forecast_diversification,
)
from glebza.tradeapp.src.framework.sizing import apply_position_inertia, cap_position_to_max_notional


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
                "forecast_ewmac_4_16",
                "forecast_ewmac_16_64",
                "forecast_ewmac_64_256",
                "price_volatility",
                "annualized_return_volatility",
                "target_position",
                "position",
                "trade",
                "return",
                "price_change",
                "strategy_return",
                "equity",
                "drawdown",
                "capital_at_risk",
            }.issubset(result.rows.columns)
        )

    def test_single_instrument_backtest_adds_carry_when_funding_rates_exist(self):
        klines = klines_dataframe([100 + i + (0.5 if i % 2 else 0.0) for i in range(300)])
        dividends = [
            {
                "record_date": datetime(2024, 2, 1, tzinfo=timezone.utc),
                "dividend_net": 10.0,
                "declared_date": datetime(2024, 2, 1, tzinfo=timezone.utc),
            }
        ]
        funding_rates = [
            {
                "rate_date": datetime(2023, 12, 31, tzinfo=timezone.utc),
                "annual_rate": 0.05,
                "published_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
            }
        ]

        rows = run_single_instrument_backtest(
            klines,
            dividends=dividends,
            funding_rates=funding_rates,
        ).rows

        self.assertIn("forecast_carry", rows.columns)
        self.assertIn("combined_ewmac_forecast", rows.columns)

    def test_single_instrument_backtest_keeps_ewmac_when_carry_inputs_are_absent(self):
        klines = klines_dataframe([100 + i + (0.5 if i % 2 else 0.0) for i in range(300)])

        base_rows = run_single_instrument_backtest(klines).rows
        rows = run_single_instrument_backtest(klines, dividends=[], funding_rates=[]).rows

        self.assertNotIn("forecast_carry", rows.columns)
        pd.testing.assert_series_equal(
            rows["combined_forecast"],
            base_rows["combined_forecast"],
            check_names=False,
        )

    def test_single_instrument_backtest_can_use_frozen_fdm(self):
        train_klines = klines_dataframe([100 + i + (0.5 if i % 2 else 0.0) for i in range(300)])
        test_klines = klines_dataframe([120 + i + (0.5 if i % 2 else 0.0) for i in range(120)])

        diagnostics = calculate_single_instrument_forecast_diversification(train_klines)
        rows = run_single_instrument_backtest(
            test_klines,
            forecast_diversification_diagnostics=diagnostics,
        ).rows

        self.assertAlmostEqual(rows["combined_forecast_fdm"].iloc[0], diagnostics.multiplier)

    def test_strategy_return_uses_previous_position(self):
        klines = klines_dataframe([100 + i + (0.5 if i % 2 else 0.0) for i in range(300)])

        rows = run_single_instrument_backtest(klines).rows

        expected = (
            rows["position"].shift(1).fillna(0.0) * rows["price_change"] / rows["capital_at_risk"]
        ).fillna(0.0) - rows["commission"] / rows["capital_at_risk"]
        pd.testing.assert_series_equal(rows["strategy_return"], expected, check_names=False)

    def test_position_size_scales_with_allocated_capital(self):
        klines = klines_dataframe([100 + i + (0.5 if i % 2 else 0.0) for i in range(300)])
        full_account = TradingAccount(
            trading_capital=100_000.0, annualized_volatility_target=0.20, max_capital_multiple=100.0
        )
        quarter_account = full_account.allocate_capital(0.25)

        full_position = run_single_instrument_backtest(
            klines, account=full_account
        ).rows["position"].abs().iloc[-1]
        quarter_position = run_single_instrument_backtest(
            klines, account=quarter_account
        ).rows["position"].abs().iloc[-1]

        self.assertAlmostEqual(quarter_position, full_position * 0.25, delta=1.0)

    def test_position_size_uses_account_volatility_target(self):
        klines = klines_dataframe([100 + i + (0.5 if i % 2 else 0.0) for i in range(300)])
        low_risk = TradingAccount(
            trading_capital=100_000.0, annualized_volatility_target=0.10, max_capital_multiple=100.0
        )
        high_risk = TradingAccount(
            trading_capital=100_000.0, annualized_volatility_target=0.20, max_capital_multiple=100.0
        )

        low_risk_position = run_single_instrument_backtest(
            klines, account=low_risk
        ).rows["position"].abs().iloc[-1]
        high_risk_position = run_single_instrument_backtest(
            klines, account=high_risk
        ).rows["position"].abs().iloc[-1]

        self.assertAlmostEqual(high_risk_position, low_risk_position * 2.0, delta=1.0)

    def test_position_size_is_rounded_to_lot(self):
        klines = klines_dataframe([100 + i + (0.5 if i % 2 else 0.0) for i in range(300)])

        rows = run_single_instrument_backtest(klines, lot_size=10).rows

        rounded_positions = rows["target_position"].dropna()
        self.assertTrue(((rounded_positions % 10) == 0).all())

    def test_cap_position_to_max_notional(self):
        position = pd.Series([1000.0, -1000.0])
        close = pd.Series([100.0, 100.0])

        capped = cap_position_to_max_notional(position, close, max_notional=50_000.0)

        self.assertEqual(capped.tolist(), [500.0, -500.0])

    def test_position_respects_max_notional_in_backtest(self):
        klines = klines_dataframe([100 + i + (0.5 if i % 2 else 0.0) for i in range(300)])
        account = TradingAccount(
            trading_capital=100_000.0,
            annualized_volatility_target=0.35,
            max_capital_multiple=1.0,
        )

        rows = run_single_instrument_backtest(klines, account=account).rows
        notionals = (rows["position"] * rows["close_price"]).abs()
        max_notionals = rows["capital_at_risk"] * account.max_capital_multiple

        lot_size = 1
        tolerance = float(rows["close_price"].max()) * lot_size
        self.assertTrue((notionals <= max_notionals + tolerance).all())

    def test_non_shortable_instrument_can_close_but_not_short(self):
        rows = pd.DataFrame(
            {
                "close_price": [100.0, 99.0, 101.0, 102.0],
                "combined_forecast": [-20.0, -20.0, 20.0, 20.0],
                "price_volatility": [1.0, 1.0, 1.0, 1.0],
            }
        )
        account = TradingAccount(
            trading_capital=100_000.0,
            annualized_volatility_target=0.20,
            max_capital_multiple=100.0,
        )

        result_rows = _run_compounding_backtest_rows(
            rows,
            account,
            periods_per_year=252,
            block_value=1.0,
            lot_size=1,
            short_enabled=False,
            position_inertia=0.0,
            trailing_stop_multiplier=0.0,
        )

        self.assertEqual(result_rows["position"].iloc[:2].tolist(), [0.0, 0.0])
        self.assertGreater(result_rows["position"].iloc[-1], 0.0)
        self.assertTrue((result_rows["position"] >= 0.0).all())

    def test_capital_at_risk_compounds_with_equity(self):
        klines = klines_dataframe([100.0, 90.0, 80.0, 70.0, 60.0, 50.0])
        account = TradingAccount(trading_capital=100_000.0, annualized_volatility_target=0.20, max_capital_multiple=100.0)

        rows = run_single_instrument_backtest(
            klines,
            account=account,
            trailing_stop_multiplier=0.0,
        ).rows

        initial_capital = float(account.trading_capital)
        expected_capital = initial_capital * rows["equity"].shift(1).fillna(1.0)
        pd.testing.assert_series_equal(rows["capital_at_risk"], expected_capital, check_names=False)
        if float(rows["equity"].iloc[-1]) < 1.0:
            self.assertLess(float(rows["capital_at_risk"].iloc[-1]), initial_capital)

    def test_position_inertia_skips_small_adjusting_trades(self):
        target_position = pd.Series([50.0, 54.0, 55.0, 42.0, 50.0])

        position = apply_position_inertia(target_position, threshold=0.10)

        self.assertEqual(position.tolist(), [50.0, 50.0, 50.0, 42.0, 50.0])

    def test_trade_is_position_change_after_inertia(self):
        klines = klines_dataframe([100 + i + (0.5 if i % 2 else 0.0) for i in range(300)])

        rows = run_single_instrument_backtest(klines).rows

        expected = rows["position"].diff().fillna(rows["position"])
        pd.testing.assert_series_equal(rows["trade"], expected, check_names=False)

    def test_commission_reduces_strategy_return(self):
        klines = klines_dataframe([100 + i + (0.5 if i % 2 else 0.0) for i in range(300)])
        without_commission = TradingAccount(
            trading_capital=100_000.0,
            annualized_volatility_target=0.20,
            commission_rate=0.0,
        )
        with_commission = TradingAccount(
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
        self.assertTrue(math.isfinite(result.cagr))
        self.assertTrue(math.isfinite(result.annualized_return))
        self.assertTrue(math.isfinite(result.annualized_volatility))
        self.assertTrue(math.isfinite(result.sharpe))
        self.assertTrue(math.isfinite(result.max_drawdown))


if __name__ == "__main__":
    unittest.main()
