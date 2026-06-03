"""Reusable portfolio definitions for backtesting and live trading."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from repository.portfolio_repository import PortfolioRepository
from repository.tinvest_repository import TinvestRepository

@dataclass(frozen=True)
class PortfolioInstrument:
    """One instrument in a portfolio and its target capital weight.

    ``block_value`` — Carver sizing unit (currency value of one price point); usually 1.0 for shares.
    ``lot_size`` — exchange lot for rounding positions (from ``instrument_share.lot``).
    """

    ticker: str
    instrument_id: int
    weight: float
    block_value: float = 1.0
    lot_size: int = 1
    short_enabled: bool = True

    def __post_init__(self) -> None:
        if self.lot_size <= 0:
            raise ValueError("lot_size must be positive")

@dataclass(frozen=True)
class Portfolio:
    """Target portfolio definition.

    Weights are capital weights and must sum to 1.0. The first MVP uses fixed
    weights; rebalancing and IDM can be layered on top later.
    """

    instruments: list[PortfolioInstrument]
    id: Optional[int] = None

    def __post_init__(self) -> None:

        tickers = [instrument.ticker for instrument in self.instruments]
        if len(tickers) != len(set(tickers)):
            raise ValueError("portfolio tickers must be unique")

        total_weight = sum(instrument.weight for instrument in self.instruments)
        if abs(total_weight - 1.0) > 1e-9:
            raise ValueError("portfolio weights must sum to 1.0")


_PORTFOLIO_NAME_MAX_LEN = 500


def _resolve_portfolio_name(name: Optional[str], tickers: list[str]) -> str:
    resolved = name or f"equal_weight:{','.join(sorted(tickers))}"
    if len(resolved) > _PORTFOLIO_NAME_MAX_LEN:
        raise ValueError(
            f"portfolio name length {len(resolved)} exceeds maximum {_PORTFOLIO_NAME_MAX_LEN} "
            f"({len(tickers)} tickers) — use fewer tickers or pass a shorter name="
        )
    return resolved


def create_equal_weight_portfolio(
    tickers: list[str],
    *,
    block_value: float = 1.0,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> Portfolio:
    """Create an equal-weight portfolio from stored shares and persist it to the database."""
    if not tickers:
        raise ValueError("tickers must not be empty")

    rows = TinvestRepository().list_shares_by_tickers(tickers)
    missing = set(tickers) - {row["instruments_ticker"] for row in rows}
    if missing:
        raise ValueError(f"No share instruments found for tickers: {', '.join(sorted(missing))}")

    weight = 1.0 / len(rows)
    instruments = [
        PortfolioInstrument(
            ticker=row["instruments_ticker"],
            instrument_id=int(row["instrument_id"]),
            weight=weight,
            block_value=block_value,
            lot_size=int(row["lot"]) if row.get("lot") is not None else 1,
            short_enabled=bool(row.get("short_enabled_flag")),
        )
        for row in rows
    ]
    portfolio_name = _resolve_portfolio_name(name, tickers)
    sleeves = [
        (item.instrument_id, item.weight, item.block_value, item.lot_size) for item in instruments
    ]
    portfolio_id = PortfolioRepository().store_portfolio(
        name=portfolio_name,
        description=description,
        instruments=sleeves,
    )
    return Portfolio(instruments=instruments, id=portfolio_id)
