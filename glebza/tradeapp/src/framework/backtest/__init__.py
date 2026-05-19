"""Pure framework backtesting helpers."""

from glebza.tradeapp.src.framework.account import TradingAccount
from glebza.tradeapp.src.framework.backtest.engine import run_single_instrument_backtest
from glebza.tradeapp.src.framework.backtest.portfolio_engine import run_weighted_portfolio_backtest
from glebza.tradeapp.src.framework.backtest.result import BacktestResult, PortfolioBacktestResult

__all__ = [
    "TradingAccount",
    "BacktestResult",
    "PortfolioBacktestResult",
    "run_single_instrument_backtest",
    "run_weighted_portfolio_backtest",
]
