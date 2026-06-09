from datetime import datetime, timedelta, timezone
import math
import unittest

import pandas as pd

from decimal import Decimal

from glebza.tradeapp.src.framework.account import TradingAccount
from glebza.tradeapp.src.framework.backtest.result import BacktestResult
from glebza.tradeapp.src.framework.backtest.portfolio_engine import run_weighted_portfolio_backtest
from glebza.tradeapp.src.framework.portfolio import (
    Portfolio,
    PortfolioInstrument,
    create_equal_weight_portfolio,
)

BACKTEST_START = datetime(2025, 1, 1, tzinfo=timezone.utc)
BACKTEST_END = datetime(2025, 1, 10, tzinfo=timezone.utc)
BACKTEST_INTERVAL = "1d"

FAKE_EXCHANGE = {
    "id": 1,
    "code": "tinvest",
    "brokerage_rate_spot": 0.0005,
    "brokerage_rate_futures": 0.0004,
    "max_capital_multiple": 5.0,
}


class _FakeBacktestRepository:
    def get_first_carver_strategy_id(self):
        return 1

    def store_run_start_for_portfolio_backtest(self, **kwargs) -> int:
        return 1

    def save_portfolio_run_result(self, run_id, result, *, ticker_to_instrument_id):
        pass

    def fail_run(self, run_id, message: str) -> None:
        pass


def result_with_returns(returns: list[float]) -> BacktestResult:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = pd.DataFrame(
        {
            "k_interval": [start + timedelta(days=i) for i in range(len(returns))],
            "strategy_return": returns,
        }
    )
    return BacktestResult(
        rows=rows,
        total_return=0.0,
        cagr=0.0,
        annualized_return=0.0,
        annualized_volatility=0.0,
        sharpe=0.0,
        max_drawdown=0.0,
    )


def result_with_oos_returns(returns: list[float], stages: list[int]) -> BacktestResult:
    result = result_with_returns(returns)
    rows = result.rows.copy()
    rows["oos_stage"] = stages
    rows["train_start_dt"] = [datetime(2023, 1, 1, tzinfo=timezone.utc) for _ in stages]
    rows["train_end_dt"] = [
        datetime(2024 if stage == 1 else 2025, 1, 1, tzinfo=timezone.utc) for stage in stages
    ]
    rows["test_start_dt"] = [
        datetime(2024 if stage == 1 else 2025, 1, 1, tzinfo=timezone.utc) for stage in stages
    ]
    rows["test_end_dt"] = [
        datetime(2025 if stage == 1 else 2026, 1, 1, tzinfo=timezone.utc) for stage in stages
    ]
    return BacktestResult(
        rows=rows,
        total_return=result.total_return,
        cagr=result.cagr,
        annualized_return=result.annualized_return,
        annualized_volatility=result.annualized_volatility,
        sharpe=result.sharpe,
        max_drawdown=result.max_drawdown,
    )


class TestPortfolio(unittest.TestCase):
    def test_equal_weight_portfolio(self):
        portfolio = create_equal_weight_portfolio(["WUSH", "EUTR", "SBER"])

        self.assertEqual(
            {instrument.ticker for instrument in portfolio.instruments},
            {"WUSH", "EUTR", "SBER"},
        )
        for instrument in portfolio.instruments:
            self.assertAlmostEqual(instrument.weight, 1 / 3)

    def test_portfolio_rejects_invalid_weights(self):
        with self.assertRaises(ValueError):
            Portfolio(
                [
                    PortfolioInstrument("WUSH", 1, 0.50),
                    PortfolioInstrument("EUTR", 2, 0.25),
                ]
            )

    def test_portfolio_rejects_duplicate_tickers(self):
        with self.assertRaises(ValueError):
            Portfolio(
                [
                    PortfolioInstrument("WUSH", 1, 0.50),
                    PortfolioInstrument("WUSH", 1, 0.50),
                ]
            )

    def test_portfolio_instrument_rejects_invalid_lot_size(self):
        with self.assertRaises(ValueError):
            PortfolioInstrument("WUSH", 1, 1.0, lot_size=0)

    def test_run_weighted_portfolio_backtest(self):
        portfolio = Portfolio(
            [
                PortfolioInstrument("WUSH", 1, 0.75),
                PortfolioInstrument("EUTR", 2, 0.25),
            ],
            id=1,
        )
        account = TradingAccount(trading_capital=Decimal("100000"), annualized_volatility_target=0.25)
        result = run_weighted_portfolio_backtest(
            portfolio,
            account,
            interval=BACKTEST_INTERVAL,
            start_dt=BACKTEST_START,
            end_dt=BACKTEST_END,
            instrument_results={
                "WUSH": result_with_returns([0.01, 0.02, -0.01]),
                "EUTR": result_with_returns([0.02, -0.01, 0.03]),
            },
            backtest_repository=_FakeBacktestRepository(),
            exchange=FAKE_EXCHANGE,
        )

        expected_returns = pd.Series([0.0125, 0.0125, 0.0], name="portfolio_return")
        pd.testing.assert_series_equal(result.rows["portfolio_return"].reset_index(drop=True), expected_returns)
        self.assertAlmostEqual(result.total_return, (1.0125 * 1.0125 * 1.0) - 1.0)
        self.assertTrue(math.isfinite(result.sharpe))

    def test_portfolio_backtest_preserves_oos_stage_metadata(self):
        portfolio = Portfolio(
            [
                PortfolioInstrument("WUSH", 1, 0.75),
                PortfolioInstrument("EUTR", 2, 0.25),
            ],
            id=1,
        )
        account = TradingAccount(trading_capital=Decimal("100000"), annualized_volatility_target=0.25)

        result = run_weighted_portfolio_backtest(
            portfolio,
            account,
            interval=BACKTEST_INTERVAL,
            start_dt=BACKTEST_START,
            end_dt=BACKTEST_END,
            instrument_results={
                "WUSH": result_with_oos_returns([0.01, 0.02, -0.01], [1, 1, 2]),
                "EUTR": result_with_oos_returns([0.02, -0.01, 0.03], [1, 1, 2]),
            },
            backtest_repository=_FakeBacktestRepository(),
            exchange=FAKE_EXCHANGE,
        )

        self.assertEqual(result.rows["oos_stage"].tolist(), [1, 1, 2])
        self.assertIn("train_start_dt", result.rows.columns)
        self.assertIn("test_end_dt", result.rows.columns)

    def test_run_weighted_portfolio_backtest_requires_all_tickers(self):
        portfolio = create_equal_weight_portfolio(["WUSH", "EUTR"])

        account = TradingAccount(trading_capital=Decimal("100000"), annualized_volatility_target=0.25)
        with self.assertRaises(ValueError):
            run_weighted_portfolio_backtest(
                portfolio,
                account,
                interval=BACKTEST_INTERVAL,
                start_dt=BACKTEST_START,
                end_dt=BACKTEST_END,
                instrument_results={"WUSH": result_with_returns([0.01])},
                backtest_repository=_FakeBacktestRepository(),
                exchange=FAKE_EXCHANGE,
            )


if __name__ == "__main__":
    unittest.main()
