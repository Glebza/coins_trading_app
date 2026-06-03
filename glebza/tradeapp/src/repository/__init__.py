"""PostgreSQL adapters: live market data, T-Invest instruments, Carver portfolios and backtests."""

__all__ = [
    "BacktestRepository",
    "BacktestRun",
    "ExchangeRepository",
    "FundingRateRepository",
    "InstrumentDividendRepository",
    "PortfolioRepository",
    "RUN_STATUS_COMPLETED",
    "RUN_STATUS_FAILED",
    "RUN_STATUS_PENDING",
    "RUN_STATUS_RUNNING",
]


def __getattr__(name: str):
    if name in {
        "BacktestRepository",
        "BacktestRun",
        "RUN_STATUS_COMPLETED",
        "RUN_STATUS_FAILED",
        "RUN_STATUS_PENDING",
        "RUN_STATUS_RUNNING",
    }:
        from repository.backtest_repository import (
            BacktestRepository,
            BacktestRun,
            RUN_STATUS_COMPLETED,
            RUN_STATUS_FAILED,
            RUN_STATUS_PENDING,
            RUN_STATUS_RUNNING,
        )

        return {
            "BacktestRepository": BacktestRepository,
            "BacktestRun": BacktestRun,
            "RUN_STATUS_COMPLETED": RUN_STATUS_COMPLETED,
            "RUN_STATUS_FAILED": RUN_STATUS_FAILED,
            "RUN_STATUS_PENDING": RUN_STATUS_PENDING,
            "RUN_STATUS_RUNNING": RUN_STATUS_RUNNING,
        }[name]
    if name == "ExchangeRepository":
        from repository.exchange_repository import ExchangeRepository

        return ExchangeRepository
    if name == "FundingRateRepository":
        from repository.funding_rate_repository import FundingRateRepository

        return FundingRateRepository
    if name == "InstrumentDividendRepository":
        from repository.instrument_dividend_repository import InstrumentDividendRepository

        return InstrumentDividendRepository
    if name == "PortfolioRepository":
        from repository.portfolio_repository import PortfolioRepository

        return PortfolioRepository
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
