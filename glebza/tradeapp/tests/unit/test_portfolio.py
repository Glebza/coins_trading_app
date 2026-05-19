from datetime import datetime, timedelta, timezone
import math
import unittest

import pandas as pd

from glebza.tradeapp.src.framework.backtest.result import BacktestResult
from glebza.tradeapp.src.framework.backtest.portfolio_engine import run_weighted_portfolio_backtest
from glebza.tradeapp.src.framework.portfolio import (
    Portfolio,
    PortfolioInstrument,
    create_equal_weight_portfolio,
)


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
        annualized_return=0.0,
        annualized_volatility=0.0,
        sharpe=0.0,
        max_drawdown=0.0,
    )


class TestPortfolio(unittest.TestCase):
    def test_equal_weight_portfolio(self):
        portfolio = create_equal_weight_portfolio(["WUSH", "EUTR", "SBER"])

        self.assertEqual([instrument.ticker for instrument in portfolio.instruments], ["WUSH", "EUTR", "SBER"])
        for instrument in portfolio.instruments:
            self.assertAlmostEqual(instrument.weight, 1 / 3)

    def test_portfolio_rejects_invalid_weights(self):
        with self.assertRaises(ValueError):
            Portfolio(
                [
                    PortfolioInstrument("WUSH", 0.50),
                    PortfolioInstrument("EUTR", 0.25),
                ]
            )

    def test_portfolio_rejects_duplicate_tickers(self):
        with self.assertRaises(ValueError):
            Portfolio(
                [
                    PortfolioInstrument("WUSH", 0.50),
                    PortfolioInstrument("WUSH", 0.50),
                ]
            )

    def test_portfolio_instrument_rejects_invalid_lot_size(self):
        with self.assertRaises(ValueError):
            PortfolioInstrument("WUSH", 1.0, lot_size=0)

    def test_run_weighted_portfolio_backtest(self):
        portfolio = Portfolio(
            [
                PortfolioInstrument("WUSH", 0.75),
                PortfolioInstrument("EUTR", 0.25),
            ]
        )
        result = run_weighted_portfolio_backtest(
            {
                "WUSH": result_with_returns([0.01, 0.02, -0.01]),
                "EUTR": result_with_returns([0.02, -0.01, 0.03]),
            },
            portfolio,
        )

        expected_returns = pd.Series([0.0125, 0.0125, 0.0], name="portfolio_return")
        pd.testing.assert_series_equal(result.rows["portfolio_return"].reset_index(drop=True), expected_returns)
        self.assertAlmostEqual(result.total_return, (1.0125 * 1.0125 * 1.0) - 1.0)
        self.assertTrue(math.isfinite(result.sharpe))

    def test_run_weighted_portfolio_backtest_requires_all_tickers(self):
        portfolio = create_equal_weight_portfolio(["WUSH", "EUTR"])

        with self.assertRaises(ValueError):
            run_weighted_portfolio_backtest({"WUSH": result_with_returns([0.01])}, portfolio)


if __name__ == "__main__":
    unittest.main()
