import unittest
from datetime import datetime, timezone

from daily_loader.dates import build_load_windows, build_period_windows


class BuildLoadWindowsTests(unittest.TestCase):
    def test_builds_one_day_kline_window(self):
        as_of = datetime(2026, 6, 10, 15, 30, tzinfo=timezone.utc)
        windows = build_load_windows(
            as_of=as_of,
            kline_lookback_days=1,
            dividend_lookback_days=365,
            ruonia_lookback_days=30,
            vol_lookback_period=252,
        )
        self.assertEqual(windows.kline_end, datetime(2026, 6, 10, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(windows.kline_start, datetime(2026, 6, 9, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(windows.dividend_end, windows.kline_end)
        self.assertEqual(windows.ruonia_end, windows.kline_end)
        self.assertEqual(windows.vol_end, windows.kline_end)
        self.assertLess(windows.vol_start, windows.kline_start)


class BuildPeriodWindowsTests(unittest.TestCase):
    def test_uses_same_bounds_for_klines_dividends_ruonia(self):
        start = datetime(2020, 1, 1, tzinfo=timezone.utc)
        end = datetime(2026, 6, 1, tzinfo=timezone.utc)
        windows = build_period_windows(start_dt=start, end_dt=end)
        self.assertEqual(windows.kline_start, start)
        self.assertEqual(windows.kline_end, end)
        self.assertEqual(windows.dividend_start, start)
        self.assertEqual(windows.dividend_end, end)
        self.assertEqual(windows.ruonia_start, start)
        self.assertEqual(windows.ruonia_end, end)


if __name__ == "__main__":
    unittest.main()
