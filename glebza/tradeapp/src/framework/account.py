"""Trading account configuration for sizing, risk, and execution."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class TradingAccount:
    """Trading account: initial capital at risk and portfolio risk targets.

    In compounding backtests, live capital at risk each bar is
    ``trading_capital * equity`` (see ``capital_at_risk`` in backtest rows).
    """

    trading_capital: Decimal
    annualized_volatility_target: float
    commission_rate: float = 0.0
    max_capital_multiple: float = 1.0
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
        if self.max_capital_multiple <= 0:
            raise ValueError("max_capital_multiple must be positive")

        object.__setattr__(self, "capital", capital)
        object.__setattr__(self, "trading_capital", trading_capital)

    def max_notional(self, capital_at_risk: float | None = None) -> float:
        """Maximum abs(position * close * block_value) for a capital sleeve."""
        capital = float(self.trading_capital) if capital_at_risk is None else capital_at_risk
        return capital * self.max_capital_multiple

    def allocate_capital(self, weight: float) -> TradingAccount:
        """Return a sub-account with ``trading_capital`` scaled by portfolio weight."""
        if weight <= 0 or weight > 1:
            raise ValueError("weight must be in (0, 1]")
        allocated = self.trading_capital * Decimal(str(weight))
        return TradingAccount(
            trading_capital=allocated,
            annualized_volatility_target=self.annualized_volatility_target,
            commission_rate=self.commission_rate,
            max_capital_multiple=self.max_capital_multiple,
            capital=allocated,
        )
