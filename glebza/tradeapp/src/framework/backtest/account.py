"""Backtest account configuration."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class BacktestAccount:
    """Trading capital and desired annualized portfolio volatility."""

    trading_capital: Decimal
    annualized_volatility_target: float
    commission_rate: float = 0.0
    capital: Optional[Decimal] = None

    def __post_init__(self) -> None:
        trading_capital = Decimal(str(self.trading_capital))
        capital = trading_capital if self.capital is None else Decimal(str(self.capital))

        if capital <= 0:
            raise ValueError("capital must be positive")
        if trading_capital <= 0:
            raise ValueError("trading_capital must be positive")
        if self.annualized_volatility_target <= 0:
            raise ValueError("annualized_volatility_target must be positive")
        if self.commission_rate < 0:
            raise ValueError("commission_rate must be non-negative")

        object.__setattr__(self, "capital", capital)
        object.__setattr__(self, "trading_capital", trading_capital)

