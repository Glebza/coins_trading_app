from datetime import datetime, timedelta, timezone
import unittest

import pandas as pd

from glebza.tradeapp.src.framework.forecasts.carry_forecast import (
    add_carry_forecast_columns,
    calculate_annual_dividend_yield_series,
    calculate_equity_carry_forecast,
    calculate_equity_carry_raw,
    calculate_funding_rate_series,
)
from glebza.tradeapp.src.framework.forecasts.combined_forecast import (
    DEFAULT_EWMAC_VARIATIONS,
    attach_ewmac_forecast_columns,
    calculate_combined_ewmac_forecast_series,
    combine_ewmac_and_carry_forecast_series,
    combine_forecast_series,
    combine_weighted_forecasts,
    equal_weights,
    ewmac_forecast_batch,
    ewmac_variation_name,
)
from glebza.tradeapp.src.framework.forecasts.ewmac_forecast import (
    EWMAC_FORECAST_SCALARS,
    EWMACConfig,
    FORECAST_CAP,
    bucket_forecast,
    cap_forecast,
    ewmac_forecast_last,
    ewmac_forecast_series,
    price_volatility_series,
)
from glebza.tradeapp.src.framework.forecasts.forecast_diversification import (
    calculate_forecast_correlation,
    calculate_forecast_diversification_multiplier,
)


def klines_dataframe(closes):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    rows = [
        {
            "k_interval": start + timedelta(days=i),
            "open_price": close,
            "high_price": close * 1.01,
            "low_price": close * 0.99,
            "close_price": close,
            "volume": 1000,
        }
        for i, close in enumerate(closes)
    ]
    return pd.DataFrame(rows)


class TestCombineWeightedForecasts(unittest.TestCase):
    def test_weighted_sum(self):
        out = combine_weighted_forecasts(
            {"a": 10.0, "b": -10.0},
            {"a": 0.5, "b": 0.5},
        )
        self.assertAlmostEqual(out, 0.0)

    def test_cap(self):
        out = combine_weighted_forecasts(
            {"a": 20.0, "b": 20.0},
            {"a": 0.5, "b": 0.5},
            cap=FORECAST_CAP,
        )
        self.assertEqual(out, FORECAST_CAP)

    def test_missing_component_zero(self):
        out = combine_weighted_forecasts(
            {"a": 10.0},
            {"a": 0.5, "b": 0.5},
        )
        self.assertAlmostEqual(out, 5.0)

    def test_equal_weights(self):
        self.assertEqual(equal_weights(["a", "b"]), {"a": 0.5, "b": 0.5})

    def test_combine_forecast_series(self):
        forecasts = {
            "a": pd.Series([10.0, 20.0, 30.0]),
            "b": pd.Series([-10.0, 0.0, 10.0]),
        }
        combined = combine_forecast_series(forecasts, {"a": 0.5, "b": 0.5})
        self.assertEqual(combined.tolist(), [0.0, 10.0, 20.0])

    def test_combine_forecast_series_applies_fdm_before_cap(self):
        forecasts = {
            "a": pd.Series([5.0, 10.0]),
            "b": pd.Series([5.0, 10.0]),
        }

        combined = combine_forecast_series(
            forecasts,
            {"a": 0.5, "b": 0.5},
            diversification_multiplier=2.0,
        )

        self.assertEqual(combined.tolist(), [10.0, 20.0])

    def test_forecast_diversification_multiplier_uses_correlation(self):
        uncorrelated = pd.DataFrame(
            [[1.0, 0.0], [0.0, 1.0]],
            index=["a", "b"],
            columns=["a", "b"],
        )

        fdm = calculate_forecast_diversification_multiplier(uncorrelated, {"a": 0.5, "b": 0.5})

        self.assertAlmostEqual(fdm, 2 ** 0.5)

    def test_combine_ewmac_and_carry_forecast_series(self):
        combined = combine_ewmac_and_carry_forecast_series(
            pd.Series([10.0, 20.0]),
            pd.Series([-10.0, 20.0]),
        )

        self.assertEqual(combined.tolist(), [0.0, 20.0])

    def test_ewmac_forecast_batch_uses_variation_names(self):
        klines = klines_dataframe([100 + i + (0.5 if i % 2 else 0.0) for i in range(300)])
        forecasts = ewmac_forecast_batch(klines, DEFAULT_EWMAC_VARIATIONS)
        self.assertEqual(set(forecasts), {ewmac_variation_name(config) for config in DEFAULT_EWMAC_VARIATIONS})

    def test_calculate_combined_ewmac_forecast_series(self):
        klines = klines_dataframe([100 + i + (0.5 if i % 2 else 0.0) for i in range(300)])
        combined = calculate_combined_ewmac_forecast_series(klines)
        self.assertEqual(len(combined), len(klines))
        self.assertLessEqual(combined.max(), FORECAST_CAP)
        self.assertGreaterEqual(combined.min(), -FORECAST_CAP)

    def test_attach_ewmac_forecast_columns_adds_three_variations(self):
        klines = klines_dataframe([100 + i + (0.5 if i % 2 else 0.0) for i in range(300)])
        rows = attach_ewmac_forecast_columns(klines)

        expected_names = {f"forecast_{ewmac_variation_name(config)}" for config in DEFAULT_EWMAC_VARIATIONS}
        self.assertEqual(expected_names, {column for column in rows.columns if column.startswith("forecast_ewmac_")})

        weights = equal_weights([name.removeprefix("forecast_") for name in expected_names])
        components = {name.removeprefix("forecast_"): rows[name] for name in expected_names}
        correlation = calculate_forecast_correlation(components)
        fdm = calculate_forecast_diversification_multiplier(correlation, weights)
        expected_combined = combine_forecast_series(
            components,
            weights,
            diversification_multiplier=fdm,
        )
        pd.testing.assert_series_equal(rows["combined_forecast"], expected_combined, check_names=False)
        self.assertIn("combined_forecast_before_fdm", rows.columns)
        self.assertIn("combined_forecast_fdm", rows.columns)


class TestEWMACForecast(unittest.TestCase):
    def _klines(self, closes):
        return klines_dataframe(closes)

    def test_cap_forecast_preserves_continuous_values(self):
        self.assertEqual(cap_forecast(12.4, floor=-20, cap=20), 12.4)
        self.assertEqual(cap_forecast(28.0, floor=-20, cap=20), 20.0)
        self.assertEqual(cap_forecast(-28.0, floor=-20, cap=20), -20.0)

    def test_bucket_forecast_uses_requested_buckets(self):
        self.assertEqual(bucket_forecast(12.4, floor=-10, cap=20, step=5), 10.0)
        self.assertEqual(bucket_forecast(12.6, floor=-10, cap=20, step=5), 15.0)
        self.assertEqual(bucket_forecast(-18.0, floor=-20, cap=20, step=5), -20.0)
        self.assertEqual(bucket_forecast(28.0, floor=-10, cap=20, step=5), 20.0)

    def test_default_scalar_comes_from_carver_table(self):
        config = EWMACConfig(fast_span=4, slow_span=16)
        self.assertEqual(config.scalar, EWMAC_FORECAST_SCALARS[(4, 16)])

    def test_price_volatility_uses_price_changes(self):
        volatility = price_volatility_series(pd.Series([100, 102, 101, 105, 104]), span=3)
        self.assertGreater(volatility.iloc[-1], 0.0)

    def test_ewmac_last_matches_series_tail(self):
        klines = self._klines([100 + i for i in range(90)])
        config = EWMACConfig(fast_span=4, slow_span=16, volatility_span=10, forecast_scalar=2.0)
        series = ewmac_forecast_series(klines, config)
        self.assertEqual(ewmac_forecast_last(klines, config), float(series.iloc[-1]))

    def test_ewmac_positive_trend_gives_positive_quantified_forecast(self):
        klines = self._klines([100 + i + (0.5 if i % 2 else 0.0) for i in range(90)])
        config = EWMACConfig(fast_span=4, slow_span=16, volatility_span=10, forecast_scalar=2.0)
        self.assertGreater(ewmac_forecast_last(klines, config), 0.0)


class TestCarryForecast(unittest.TestCase):
    def test_raw_carry_is_excess_yield_divided_by_volatility(self):
        self.assertAlmostEqual(calculate_equity_carry_raw(0.12, 0.08, 0.20), 0.20)

    def test_carry_forecast_is_scaled_and_capped(self):
        self.assertEqual(calculate_equity_carry_forecast(0.30, 0.00, 0.10), FORECAST_CAP)
        self.assertEqual(calculate_equity_carry_forecast(0.00, 0.30, 0.10), -FORECAST_CAP)

    def test_dividend_yield_uses_only_known_dividends(self):
        klines = klines_dataframe([100, 100, 100])
        dividends = [
            {
                "record_date": datetime(2024, 1, 2, tzinfo=timezone.utc),
                "dividend_net": 10.0,
                "declared_date": datetime(2024, 1, 2, tzinfo=timezone.utc),
            },
            {
                "record_date": datetime(2024, 1, 3, tzinfo=timezone.utc),
                "dividend_net": 50.0,
                "declared_date": datetime(2024, 1, 10, tzinfo=timezone.utc),
            },
        ]

        series = calculate_annual_dividend_yield_series(klines, dividends)

        self.assertEqual(series.tolist(), [0.0, 0.10, 0.10])

    def test_funding_rate_uses_latest_published_rate(self):
        klines = klines_dataframe([100, 100, 100])
        rates = [
            {
                "rate_date": datetime(2023, 12, 31, tzinfo=timezone.utc),
                "annual_rate": 0.15,
                "published_at": datetime(2024, 1, 2, tzinfo=timezone.utc),
            },
            {
                "rate_date": datetime(2024, 1, 2, tzinfo=timezone.utc),
                "annual_rate": 0.16,
                "published_at": datetime(2024, 1, 3, tzinfo=timezone.utc),
            },
        ]

        series = calculate_funding_rate_series(klines, rates)

        self.assertEqual(series.tolist(), [0.0, 0.15, 0.16])

    def test_add_carry_forecast_columns(self):
        klines = klines_dataframe([100, 100])
        dividends = [
            {
                "record_date": datetime(2024, 1, 2, tzinfo=timezone.utc),
                "dividend_net": 10.0,
                "declared_date": datetime(2024, 1, 2, tzinfo=timezone.utc),
            }
        ]
        rates = [
            {
                "rate_date": datetime(2023, 12, 31, tzinfo=timezone.utc),
                "annual_rate": 0.05,
                "published_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
            }
        ]

        rows = add_carry_forecast_columns(klines, dividends, rates, annualized_volatility=0.25)

        self.assertIn("dividend_yield", rows.columns)
        self.assertIn("funding_rate", rows.columns)
        self.assertIn("forecast_carry", rows.columns)
        self.assertAlmostEqual(rows["forecast_carry"].iloc[-1], 6.0)


if __name__ == "__main__":
    unittest.main()
