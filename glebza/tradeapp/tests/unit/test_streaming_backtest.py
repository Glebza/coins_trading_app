from datetime import datetime, timedelta, timezone
import unittest

import pandas as pd

from glebza.tradeapp.src.framework.backtest import TradingAccount
from glebza.tradeapp.src.framework.backtest.engine import (
    calculate_single_instrument_forecast_diversification,
    run_single_instrument_backtest,
)
from glebza.tradeapp.src.framework.backtest.portfolio_engine import (
    _add_months,
    _combine_stage_results,
)
from glebza.tradeapp.src.framework.backtest.streaming_engine import (
    InstrumentStreamingBacktest,
    _slice_klines_window,
    run_streaming_oos_stages_for_klines,
    run_streaming_single_instrument_backtest,
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


class TestStreamingBacktest(unittest.TestCase):
    def test_streaming_matches_batch_backtest(self):
        klines = klines_dataframe([100 + i + (0.5 if i % 2 else 0.0) for i in range(300)])
        batch = run_single_instrument_backtest(klines)
        streaming = run_streaming_single_instrument_backtest(klines)

        batch_rows = batch.rows.reset_index(drop=True)
        stream_rows = streaming.rows.reset_index(drop=True)

        compare_columns = [
            "combined_forecast",
            "price_volatility",
            "target_position",
            "position",
            "trade",
            "strategy_return",
            "equity",
        ]
        for column in compare_columns:
            pd.testing.assert_series_equal(
                batch_rows[column].astype("float64"),
                stream_rows[column].astype("float64"),
                check_names=False,
                atol=1e-9,
                rtol=1e-9,
                obj=column,
            )

        self.assertAlmostEqual(batch.total_return, streaming.total_return, places=9)
        self.assertAlmostEqual(batch.cagr, streaming.cagr, places=9)
        self.assertAlmostEqual(
            batch.forecast_diversification_multiplier,
            streaming.forecast_diversification_multiplier,
            places=9,
        )

    def test_streaming_uses_frozen_fdm_from_training_window(self):
        train_klines = klines_dataframe([100 + i for i in range(300)])
        test_klines = klines_dataframe([120 + i for i in range(120)])
        diagnostics = calculate_single_instrument_forecast_diversification(train_klines)

        replay = InstrumentStreamingBacktest(
            TradingAccount(trading_capital=100_000.0, annualized_volatility_target=0.35),
            frozen_fdm=diagnostics,
            periods_per_year=252,
        )
        for bar in test_klines.to_dict(orient="records"):
            row = replay.append_bar(bar)

        self.assertAlmostEqual(row["combined_forecast_fdm"], diagnostics.multiplier)

    def test_streaming_with_explicit_training_klines(self):
        train_klines = klines_dataframe([100 + i for i in range(300)])
        test_klines = klines_dataframe([120 + i for i in range(120)])

        batch = run_single_instrument_backtest(
            test_klines,
            forecast_diversification_diagnostics=calculate_single_instrument_forecast_diversification(
                train_klines
            ),
        )
        streaming = run_streaming_single_instrument_backtest(
            test_klines,
            training_klines=train_klines,
        )

        pd.testing.assert_series_equal(
            batch.rows.reset_index(drop=True)["combined_forecast"].astype("float64"),
            streaming.rows.reset_index(drop=True)["combined_forecast"].astype("float64"),
            check_names=False,
            atol=1e-9,
            rtol=1e-9,
        )


    def test_streaming_oos_matches_batch_oos(self):
        klines = klines_dataframe([100 + i + (0.5 if i % 2 else 0.0) for i in range(500)])
        account = TradingAccount(trading_capital=100_000.0, annualized_volatility_target=0.35)
        start_dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end_dt = datetime(2025, 6, 1, tzinfo=timezone.utc)
        step_months = 12

        streaming = run_streaming_oos_stages_for_klines(
            klines,
            account=account,
            start_dt=start_dt,
            end_dt=end_dt,
            step_months=step_months,
        )

        stage_results = []
        test_start = _add_months(start_dt, step_months)
        stage = 1
        while test_start < end_dt:
            test_end = min(_add_months(test_start, step_months), end_dt)
            training_klines = _slice_klines_window(klines, start_dt, test_start)
            test_klines = _slice_klines_window(klines, test_start, test_end)
            diagnostics = calculate_single_instrument_forecast_diversification(training_klines)
            stage_results.append(
                run_single_instrument_backtest(
                    test_klines,
                    account=account,
                    forecast_diversification_diagnostics=diagnostics,
                )
            )
            test_start = test_end
            stage += 1
        batch = _combine_stage_results(stage_results, periods_per_year=252)

        pd.testing.assert_series_equal(
            batch.rows.reset_index(drop=True)["combined_forecast"].astype("float64"),
            streaming.rows.reset_index(drop=True)["combined_forecast"].astype("float64"),
            check_names=False,
            atol=1e-9,
            rtol=1e-9,
        )
        pd.testing.assert_series_equal(
            batch.rows.reset_index(drop=True)["strategy_return"].astype("float64"),
            streaming.rows.reset_index(drop=True)["strategy_return"].astype("float64"),
            check_names=False,
            atol=1e-9,
            rtol=1e-9,
        )
        self.assertAlmostEqual(batch.total_return, streaming.total_return, places=9)


if __name__ == "__main__":
    unittest.main()
