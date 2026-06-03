import unittest
from unittest.mock import MagicMock, patch

from glebza.tradeapp.src.framework.instruments.instruments import (
    InstrumentsService,
    _is_dividend_not_found_error,
)


class _FakeStatusCode:
    def __init__(self, name: str) -> None:
        self.name = name


class TestDividendNotFoundHandling(unittest.TestCase):
    def test_detects_not_found_request_error(self):
        exc = Exception("ignored")
        exc.code = _FakeStatusCode("NOT_FOUND")
        exc.details = "50002"
        self.assertTrue(_is_dividend_not_found_error(exc))

    def test_ignores_other_errors(self):
        exc = Exception("rate limited")
        exc.code = _FakeStatusCode("RESOURCE_EXHAUSTED")
        self.assertFalse(_is_dividend_not_found_error(exc))
        self.assertFalse(_is_dividend_not_found_error(ValueError("bad input")))

    @patch("glebza.tradeapp.src.framework.instruments.instruments.TInvestInstrumentApiService")
    @patch("glebza.tradeapp.src.framework.instruments.instruments.TinvestRepository")
    @patch("glebza.tradeapp.src.framework.instruments.instruments.HistoryRepository")
    @patch("glebza.tradeapp.src.framework.instruments.instruments.InstrumentDividendRepository")
    def test_skips_ticker_when_dividends_not_found(
        self,
        dividend_repo_cls,
        history_repo_cls,
        tinvest_repo_cls,
        api_service_cls,
    ):
        api_service = api_service_cls.return_value
        not_found = Exception("not found")
        not_found.code = _FakeStatusCode("NOT_FOUND")
        not_found.details = "50002"
        api_service.fetch_dividends_by_share.side_effect = not_found

        svc = InstrumentsService(token="test-token")
        share = {"instruments_ticker": "MISSING", "instrument_id": 1, "class_code": "TQBR"}
        result = svc._load_dividends_for_share(
            share,
            start_dt=MagicMock(),
            end_dt=MagicMock(),
        )

        self.assertTrue(result["skipped"])
        self.assertEqual(result["skip_reason"], "not_found")
        self.assertEqual(result["fetched_dividends"], 0)
        dividend_repo_cls.return_value.upsert_dividends.assert_not_called()


if __name__ == "__main__":
    unittest.main()
