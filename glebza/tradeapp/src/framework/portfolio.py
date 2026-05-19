"""Reusable portfolio definitions for backtesting and live trading."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PortfolioInstrument:
    """One instrument in a portfolio and its target capital weight."""

    ticker: str
    weight: float
    block_value: float = 1.0
    lot_size: int = 1

@dataclass(frozen=True)
class Portfolio:
    """Target portfolio definition.

    Weights are capital weights and must sum to 1.0. The first MVP uses fixed
    weights; rebalancing and IDM can be layered on top later.
    """

    instruments: list[PortfolioInstrument]

    def __post_init__(self) -> None:
        if not self.instruments:
            raise ValueError("portfolio must contain at least one instrument")

        tickers = [instrument.ticker for instrument in self.instruments]
        if len(tickers) != len(set(tickers)):
            raise ValueError("portfolio tickers must be unique")

        total_weight = sum(instrument.weight for instrument in self.instruments)
        if abs(total_weight - 1.0) > 1e-9:
            raise ValueError("portfolio weights must sum to 1.0")


def create_equal_weight_portfolio(tickers: list[str]) -> Portfolio:
    """Create a portfolio with equal target weights."""

    weight = 1.0 / len(tickers)
    return Portfolio([PortfolioInstrument(ticker=ticker, weight=weight) for ticker in tickers])
