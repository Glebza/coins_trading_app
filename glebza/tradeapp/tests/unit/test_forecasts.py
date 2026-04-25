import unittest

from glebza.tradeapp.src.framework.forecasts import FORECAST_CAP, combine_weighted_forecasts


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


if __name__ == "__main__":
    unittest.main()
