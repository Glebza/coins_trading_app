import unittest
from decimal import Decimal

from framework.portfolio import Portfolio, PortfolioInstrument
from live_trading.deployment_config import load_deployment


class _FakeLiveDeploymentRepository:
    def get_carver_strategy(self, strategy_id: int):
        return {
            "id": strategy_id,
            "name": "tinvest_oos",
            "initial_trading_capital": Decimal("200000"),
            "annualized_volatility_target": 0.25,
            "position_inertia": 0.10,
            "trailing_stop_multiplier": 4.0,
        }

    def get_portfolio_id_for_strategy(self, strategy_id: int):
        return 42

    def get_completed_run(self, run_id: int):
        return {
            "id": run_id,
            "strategy_id": 1,
            "portfolio_id": 42,
            "status": "completed",
            "kline_interval": "1d",
            "forecast_diversification_multiplier": 1.29,
            "forecast_average_correlation": 0.12,
            "forecast_correlations": {"ewmac_4_16": {"carry": 0.1}},
        }

    def get_latest_completed_run(self, *, strategy_id: int, portfolio_id: int):
        return None

    def list_strategy_rules(self, strategy_id: int):
        return [
            {
                "rule_code": "ewmac",
                "rule_name": "EWMAC",
                "variation_name": "ewmac_4_16",
                "weight": 0.2,
                "rule_group": "ewmac",
                "params": {"fast_span": 4, "slow_span": 16},
            }
        ]


class _FakePortfolioRepository:
    def load_portfolio(self, portfolio_id: int) -> Portfolio:
        return Portfolio(
            id=portfolio_id,
            instruments=[
                PortfolioInstrument(
                    ticker="SBER",
                    instrument_id=10,
                    weight=0.5,
                    block_value=1.0,
                    lot_size=10,
                ),
                PortfolioInstrument(
                    ticker="GAZP",
                    instrument_id=11,
                    weight=0.5,
                    block_value=1.0,
                    lot_size=1,
                ),
            ],
        )


class _FakeExchangeRepository:
    def get_exchange_by_code(self, code: str):
        return {
            "id": 1,
            "code": code,
            "brokerage_rate_spot": 0.0005,
            "max_capital_multiple": 5.0,
        }


class _FakeTinvestRepository:
    def list_shares_by_tickers(self, ticker_list):
        return [
            {
                "instruments_ticker": "SBER",
                "class_code": "TQBR",
                "figi": "BBG004730N88",
                "short_enabled_flag": False,
                "lot": 10,
            },
            {
                "instruments_ticker": "GAZP",
                "class_code": "TQBR",
                "figi": "BBG004730RP0",
                "short_enabled_flag": True,
                "lot": 1,
            },
        ]


class DeploymentConfigTests(unittest.TestCase):
    def test_load_deployment_from_db(self):
        deployment = load_deployment(
            1,
            backtest_run_id=27,
            trading_capital=150000.0,
            deployment_repository=_FakeLiveDeploymentRepository(),
            portfolio_repository=_FakePortfolioRepository(),
            exchange_repository=_FakeExchangeRepository(),
            tinvest_repository=_FakeTinvestRepository(),
        )
        self.assertEqual(deployment.strategy_id, 1)
        self.assertEqual(deployment.portfolio_id, 42)
        self.assertEqual(deployment.backtest_run_id, 27)
        self.assertAlmostEqual(deployment.fdm_multiplier, 1.29)
        self.assertEqual(float(deployment.account.trading_capital), 150000.0)
        self.assertEqual(len(deployment.stream_instruments), 2)
        self.assertEqual(deployment.stream_instruments[0].figi, "BBG004730N88")


if __name__ == "__main__":
    unittest.main()
