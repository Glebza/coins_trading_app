import unittest

from services.rate_limit import (
    is_rate_limit_error,
    rate_limit_sleep_seconds,
)


class RateLimitHelpersTests(unittest.TestCase):
    def test_detects_resource_exhausted(self):
        self.assertTrue(is_rate_limit_error(Exception("RESOURCE_EXHAUSTED")))

    def test_parses_reset_seconds(self):
        exc = Exception("ratelimit_reset=12.5")
        self.assertEqual(rate_limit_sleep_seconds(exc, fallback=60.0), 13.5)

    def test_uses_fallback_when_reset_missing(self):
        self.assertEqual(rate_limit_sleep_seconds(Exception("busy"), fallback=60.0), 60.0)


if __name__ == "__main__":
    unittest.main()
