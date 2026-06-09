"""Pure framework backtesting helpers."""

from glebza.tradeapp.src.framework.account import TradingAccount
from glebza.tradeapp.src.framework.backtest.engine import run_single_instrument_backtest
from glebza.tradeapp.src.framework.backtest.portfolio_engine import (
    run_expanding_oos_portfolio_backtest,
    run_weighted_portfolio_backtest,
)
from glebza.tradeapp.src.framework.backtest.result import BacktestResult, PortfolioBacktestResult
from glebza.tradeapp.src.framework.backtest.streaming_engine import (
    InstrumentStreamingBacktest,
    run_streaming_expanding_oos_portfolio_backtest,
    run_streaming_oos_stages_for_klines,
    run_streaming_portfolio_backtest,
    run_streaming_single_instrument_backtest,
)

__all__ = [
    "TradingAccount",
    "BacktestResult",
    "PortfolioBacktestResult",
    "run_single_instrument_backtest",
    "run_weighted_portfolio_backtest",
    "run_expanding_oos_portfolio_backtest",
    "InstrumentStreamingBacktest",
    "run_streaming_single_instrument_backtest",
    "run_streaming_portfolio_backtest",
    "run_streaming_expanding_oos_portfolio_backtest",
    "run_streaming_oos_stages_for_klines",
]
