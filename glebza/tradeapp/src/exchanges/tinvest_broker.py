"""T‑Invest (T‑Bank) instruments: listed shares the API reports as tradable for your access.

Imports assume ``tradeapp/src`` is on ``sys.path`` (sibling packages ``repository``, etc.).
Bulk share sync CLI: ``python -m manutil sync-shares`` (see ``manutil/instruments_cli.py``).
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict
from decimal import Decimal
from typing import Any, Callable, Iterator, List, Optional

from t_tech.invest import (
    CandleInstrument,
    InstrumentStatus,
    OrderDirection,
    OrderType,
    SubscriptionInterval,
)

from exchanges.tinvest_grpc import TInvestGrpcClient
from t_tech.invest.schemas import Candle, Quotation, Share

from repository.tinvest_repository import TinvestRepository

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


_COMMISSION_ENV = "T_INVEST_COMMISSION_RATE"
_COMMISSION_TARIFF_PREFIX = "T_INVEST_COMMISSION_RATE_"
SANDBOX_GRPC_TARGET = "sandbox-invest-public-api.tbank.ru:443"


def resolve_grpc_target(*, sandbox: bool, target: Optional[str] = None) -> Optional[str]:
    if target:
        return target
    return SANDBOX_GRPC_TARGET if sandbox else None


def _account_to_dict(account: Any) -> dict[str, Any]:
    return {
        "id": account.id,
        "name": account.name,
        "type": str(account.type),
        "status": str(account.status),
        "opened_date": str(getattr(account, "opened_date", "")),
    }


def _account_opened_at(account: Any) -> int:
    opened = getattr(account, "opened_date", None)
    if opened is None:
        return 0
    seconds = getattr(opened, "seconds", None)
    if seconds is not None:
        return int(seconds)
    return 0


def pick_latest_open_account_id(accounts: list[Any]) -> Optional[str]:
    """Return the most recently opened account with OPEN status."""
    open_accounts = [
        account for account in accounts if "OPEN" in str(getattr(account, "status", ""))
    ]
    if not open_accounts:
        return None
    latest = max(open_accounts, key=_account_opened_at)
    return latest.id


def resolve_production_account_id(
    token: str,
    *,
    target: Optional[str] = None,
) -> str:
    """Return the latest open production account for the token (``UsersService/GetAccounts``).

    TODO: replace API auto-pick with the production account id stored in our DB
    (e.g. live deployment / carver_strategy config) once live trading uses ``public`` schema.
    """
    with TInvestGrpcClient(token, target=target) as client:
        response = client.users.get_accounts()
        account_id = pick_latest_open_account_id(list(response.accounts))
    if not account_id:
        raise ValueError("no open account found for token")
    return account_id


def resolve_sandbox_account_id(
    token: str,
    *,
    target: Optional[str] = None,
    open_if_missing: bool = True,
) -> str:
    """
    Return the latest open sandbox account id.

    Uses ``GetSandboxAccounts``; opens a new account via ``OpenSandboxAccount`` when none exist.
    """
    grpc_target = resolve_grpc_target(sandbox=True, target=target)
    with TInvestGrpcClient(token, target=grpc_target) as client:
        response = client.sandbox.get_sandbox_accounts()
        account_id = pick_latest_open_account_id(list(response.accounts))
        if account_id:
            return account_id
        if not open_if_missing:
            raise ValueError("no open sandbox account; use OpenSandboxAccount to create one")
        opened = client.sandbox.open_sandbox_account()
        return opened.account_id


def instruments_ticker(share: Share) -> str:
    """Value stored in ``instruments.ticker`` (API listing ticker only; ``class_code`` stays on ``instrument_share``)."""
    return share.ticker


def build_instrument_id(ticker: str, class_code: str) -> str:
    """T-Invest instrument id format used by market data and orders."""
    return f"{ticker}_{class_code}"


def decimal_to_quotation(value: Decimal | float) -> Quotation:
    decimal_value = Decimal(str(value))
    sign = -1 if decimal_value < 0 else 1
    absolute = abs(decimal_value)
    units = int(absolute)
    nano = int((absolute - Decimal(units)) * Decimal("1000000000"))
    return Quotation(units=sign * units, nano=sign * nano)


def quotation_to_decimal(value: Quotation | None) -> Decimal:
    if value is None:
        return Decimal("0")
    units = Decimal(getattr(value, "units", 0) or 0)
    nano = Decimal(getattr(value, "nano", 0) or 0)
    return units + nano / Decimal("1000000000")


def money_to_decimal(value) -> Decimal:
    if value is None:
        return Decimal("0")
    units = getattr(value, "units", 0) or 0
    nano = getattr(value, "nano", 0) or 0
    return Decimal(units) + Decimal(nano) / Decimal("1000000000")


def candle_to_bar(candle: Candle) -> dict[str, Any]:
    """Normalize a T-Invest stream candle to a backtest-compatible kline row."""
    interval = candle.time
    return {
        "k_interval": interval,
        "open_price": float(quotation_to_decimal(candle.open)),
        "high_price": float(quotation_to_decimal(candle.high)),
        "low_price": float(quotation_to_decimal(candle.low)),
        "close_price": float(quotation_to_decimal(candle.close)),
        "volume": int(getattr(candle, "volume", 0) or 0),
        "is_complete": bool(getattr(candle, "is_complete", False)),
        "figi": getattr(candle, "figi", None),
        "tinvest_instrument_id": getattr(candle, "instrument_id", None),
        "instrument_uid": getattr(candle, "instrument_uid", None),
    }


class TInvestBrokerClient:
    """T-Invest accounts, portfolio, and order placement (production or sandbox)."""

    def __init__(
        self,
        token: str,
        account_id: str,
        *,
        sandbox: bool = True,
        target: Optional[str] = None,
    ) -> None:
        if not token:
            raise ValueError("token is required")
        if not account_id:
            raise ValueError("account_id is required")
        self._token = token
        self._account_id = account_id
        self._sandbox = sandbox
        self._target = target

    def _with_client(self):
        return TInvestGrpcClient(self._token, target=self._target)

    def list_accounts(self) -> list[dict[str, Any]]:
        with self._with_client() as client:
            if self._sandbox:
                response = client.sandbox.get_sandbox_accounts()
            else:
                response = client.users.get_accounts()
        return [_account_to_dict(account) for account in response.accounts]

    def get_portfolio(self) -> dict[str, Any]:
        with self._with_client() as client:
            if self._sandbox:
                portfolio = client.sandbox.get_sandbox_portfolio(account_id=self._account_id)
            else:
                portfolio = client.operations.get_portfolio(account_id=self._account_id)
        positions = [
            {
                "figi": position.figi,
                "instrument_type": str(position.instrument_type),
                "quantity": quotation_to_decimal(position.quantity),
                "average_position_price": money_to_decimal(position.average_position_price),
                "expected_yield": money_to_decimal(position.expected_yield),
                "current_price": money_to_decimal(position.current_price),
                "ticker": getattr(position, "ticker", None),
            }
            for position in portfolio.positions
        ]
        return {
            "account_id": self._account_id,
            "sandbox": self._sandbox,
            "total_amount_shares": money_to_decimal(portfolio.total_amount_shares),
            "expected_yield": money_to_decimal(portfolio.expected_yield),
            "positions": positions,
        }

    def get_positions(self) -> list[dict[str, Any]]:
        with self._with_client() as client:
            if self._sandbox:
                response = client.sandbox.get_sandbox_positions(account_id=self._account_id)
            else:
                response = client.operations.get_positions(account_id=self._account_id)
        securities = [
            {
                "figi": item.figi,
                "instrument_type": str(item.instrument_type),
                "balance": quotation_to_decimal(item.balance),
                "blocked": quotation_to_decimal(item.blocked),
                "ticker": getattr(item, "ticker", None),
            }
            for item in response.securities
        ]
        return securities

    def post_limit_order(
        self,
        *,
        instrument_id: str,
        quantity: int,
        price: Decimal | float,
        direction: OrderDirection,
        order_id: str = "",
    ) -> dict[str, Any]:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        with self._with_client() as client:
            if self._sandbox:
                response = client.sandbox.post_sandbox_order(
                    account_id=self._account_id,
                    instrument_id=instrument_id,
                    quantity=quantity,
                    price=decimal_to_quotation(price),
                    direction=direction,
                    order_type=OrderType.ORDER_TYPE_LIMIT,
                    order_id=order_id,
                )
            else:
                response = client.orders.post_order(
                    account_id=self._account_id,
                    instrument_id=instrument_id,
                    quantity=quantity,
                    price=decimal_to_quotation(price),
                    direction=direction,
                    order_type=OrderType.ORDER_TYPE_LIMIT,
                    order_id=order_id,
                )
        return {
            "order_id": response.order_id,
            "execution_report_status": str(response.execution_report_status),
            "lots_requested": response.lots_requested,
            "lots_executed": response.lots_executed,
            "initial_order_price": money_to_decimal(response.initial_order_price),
            "total_order_amount": money_to_decimal(response.total_order_amount),
        }

    def list_open_orders(self) -> list[dict[str, Any]]:
        with self._with_client() as client:
            if self._sandbox:
                response = client.sandbox.get_sandbox_orders(account_id=self._account_id)
            else:
                response = client.orders.get_orders(account_id=self._account_id)
        return [
            {
                "order_id": order.order_id,
                "figi": order.figi,
                "direction": str(order.direction),
                "order_type": str(order.order_type),
                "lots_requested": order.lots_requested,
                "lots_executed": order.lots_executed,
                "order_state": str(order.execution_report_status),
                "instrument_id": getattr(order, "instrument_id", None),
            }
            for order in response.orders
        ]

    def cancel_order(self, order_id: str) -> None:
        with self._with_client() as client:
            if self._sandbox:
                client.sandbox.cancel_sandbox_order(
                    account_id=self._account_id,
                    order_id=order_id,
                )
            else:
                client.orders.cancel_order(
                    account_id=self._account_id,
                    order_id=order_id,
                )


class TInvestMarketDataStream:
    """Subscribe to closed daily candles via T-Invest gRPC market data stream."""

    def __init__(
        self,
        token: str,
        *,
        target: Optional[str] = None,
    ) -> None:
        self._token = token
        self._target = target
        self._client: Optional[TInvestGrpcClient] = None
        self._services = None
        self._stream_manager = None

    def __enter__(self) -> "TInvestMarketDataStream":
        self._client = TInvestGrpcClient(self._token, target=self._target)
        self._services = self._client.__enter__()
        self._stream_manager = self._services.create_market_data_stream()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if self._stream_manager is not None:
            self._stream_manager.stop()
        if self._client is not None:
            self._client.__exit__(exc_type, exc_val, exc_tb)
        self._client = None
        self._services = None
        self._stream_manager = None
        return False

    def subscribe_daily_candles(
        self,
        instruments: list[dict[str, str]],
        *,
        waiting_close: bool = True,
    ) -> None:
        if self._stream_manager is None:
            raise RuntimeError("stream is not open; use TInvestMarketDataStream as a context manager")
        candle_instruments = [
            CandleInstrument(
                instrument_id=build_instrument_id(item["ticker"], item["class_code"]),
                interval=SubscriptionInterval.SUBSCRIPTION_INTERVAL_ONE_DAY,
            )
            for item in instruments
        ]
        manager = self._stream_manager.candles
        if waiting_close:
            manager = manager.waiting_close(True)
        manager.subscribe(candle_instruments)

    def iter_closed_candles(self):
        if self._stream_manager is None:
            raise RuntimeError("stream is not open; use TInvestMarketDataStream as a context manager")
        for event in self._stream_manager:
            candle = getattr(event, "candle", None)
            if candle is None:
                continue
            if waiting_close := getattr(candle, "is_complete", None):
                if not waiting_close:
                    continue
            yield candle_to_bar(candle)


class TBankInstrumentService:
    """
    Fetches shares via Invest API ``InstrumentsService.Shares`` and filters by availability flags.

    This reflects what the **broker API** exposes for the authenticated token (e.g. API trading,
    buy availability). It is **not** a legal “NQ investor” list—that comes from regulation and
    product rules; use this as the operational tradable set for T‑Invest API.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        *,
        target: Optional[str] = None,
    ) -> None:
        self._token = token or os.environ.get("INVEST_TOKEN") or os.environ.get("T_INVEST_TOKEN")
        if not self._token:
            raise ValueError(
                "T‑Invest token required: pass token= or set INVEST_TOKEN / T_INVEST_TOKEN"
            )
        self._target = target

    def iter_tradeable_shares(
        self,
        *,
        instrument_status: InstrumentStatus = InstrumentStatus.INSTRUMENT_STATUS_BASE,

    ) -> Iterator[Share]:
        with TInvestGrpcClient(self._token, target=self._target) as client:
            response = client.instruments.shares(instrument_status=instrument_status)
            for share in response.instruments:
                if not share.buy_available_flag:
                    continue
                if not share.sell_available_flag:
                    continue
                if not share.api_trade_available_flag:
                    continue
                yield share

    def list_tradeable_shares(self, **kwargs: Any) -> List[Share]:
        """All matching shares as ``Share`` dataclass instances."""
        return list(self.iter_tradeable_shares(**kwargs))

    def list_tradeable_shares_as_dicts(self, **kwargs: Any) -> List[dict[str, Any]]:
        """Same as ``list_tradeable_shares``, each row as a plain ``dict`` (``dataclasses.asdict``)."""
        rows: List[dict[str, Any]] = []
        for s in self.iter_tradeable_shares(**kwargs):
            rows.append(asdict(s))
        return rows

    def get_tariff_name(self) -> str:
        """Return the broker tariff name exposed by T-Invest UsersService.GetInfo."""
        with TInvestGrpcClient(self._token, target=self._target) as client:
            return client.users.get_info().tariff

    def get_commission_rate(self) -> Decimal:
        """Return configured T-Invest commission rate as a decimal fraction.

        T-Invest API exposes the tariff name, but not the exact brokerage
        commission percentage. Configure it manually with either:
        - ``T_INVEST_COMMISSION_RATE`` for all tariffs, or
        - ``T_INVEST_COMMISSION_RATE_<TARIFF>`` for a specific tariff name.

        Example: ``0.0005`` means 0.05% of traded notional.
        """
        tariff = self.get_tariff_name()
        tariff_key = "".join(ch if ch.isalnum() else "_" for ch in tariff.upper())
        specific_env = f"{_COMMISSION_TARIFF_PREFIX}{tariff_key}"
        raw_rate = os.environ.get(specific_env) or os.environ.get(_COMMISSION_ENV)
        if raw_rate is None:
            raise ValueError(
                "T-Invest API does not expose brokerage commission rates. "
                f"Set {specific_env} or {_COMMISSION_ENV}, e.g. 0.0005 for 0.05%."
            )
        rate = Decimal(raw_rate)
        if rate < 0:
            raise ValueError("Commission rate must be non-negative")
        return rate

    def persist_tradeable_shares_to_db(
        self,
        *,
        instruments_ticker_fn: Callable[[Share], str] = instruments_ticker,
    ) -> int:
        """
        Load tradeable shares from the API and upsert into ``DATABASE_URL``:
        ``instruments`` (``instrument_type = share``) + ``instrument_share``.

        Requires ``DATABASE_URL`` and ``DATABASE_DEFAULT_SCHEMA`` (same as other tradeapp repositories).
        """
        shares = self.list_tradeable_shares()
        repo = TinvestRepository()
        return repo.upsert_shares_batch(shares, instruments_ticker_fn=instruments_ticker_fn)


