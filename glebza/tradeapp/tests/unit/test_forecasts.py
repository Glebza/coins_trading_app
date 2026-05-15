from datetime import datetime, timedelta, timezone
import unittest

import pandas as pd

from glebza.tradeapp.src.framework.forecasts.combined_forecast import (
    DEFAULT_EWMAC_VARIATIONS,
    combine_forecast_series,
    combine_weighted_forecasts,
    combined_ewmac_forecast_series,
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

    def test_ewmac_forecast_batch_uses_variation_names(self):
        klines = klines_dataframe([100 + i + (0.5 if i % 2 else 0.0) for i in range(300)])
        forecasts = ewmac_forecast_batch(klines, DEFAULT_EWMAC_VARIATIONS)
        self.assertEqual(set(forecasts), {ewmac_variation_name(config) for config in DEFAULT_EWMAC_VARIATIONS})

    def test_combined_ewmac_forecast_series(self):
        klines = klines_dataframe([100 + i + (0.5 if i % 2 else 0.0) for i in range(300)])
        combined = combined_ewmac_forecast_series(klines)
        self.assertEqual(len(combined), len(klines))
        self.assertLessEqual(combined.max(), FORECAST_CAP)
        self.assertGreaterEqual(combined.min(), -FORECAST_CAP)


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


if __name__ == "__main__":
    unittest.main()
