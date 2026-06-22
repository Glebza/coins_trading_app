"""Load portfolio, strategy, and frozen FDM from the database."""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

from framework.account import TradingAccount
from framework.portfolio import Portfolio
from live_trading.config import DEFAULT_EXCHANGE_CODE, DEFAULT_FDM_MULTIPLIER
from repository.exchange_repository import ExchangeRepository
from repository.live_deployment_repository import LiveDeploymentRepository
from repository.portfolio_repository import PortfolioRepository
from repository.tinvest_repository import TinvestRepository


@dataclass(frozen=True)
class StrategyRuleBinding:
    rule_code: str
    rule_name: str
    variation_name: str
    weight: float
    rule_group: Optional[str]
    params: dict[str, Any]


@dataclass(frozen=True)
class StreamInstrument:
    ticker: str
    class_code: str
    figi: str
    instrument_id: int
    weight: float
    block_value: float
    lot_size: int
    short_enabled: bool


@dataclass(frozen=True)
class DeploymentConfig:
    strategy_id: int
    portfolio_id: int
    backtest_run_id: Optional[int]
    strategy_name: str
    portfolio: Portfolio
    account: TradingAccount
    exchange: dict[str, Any]
    stream_instruments: tuple[StreamInstrument, ...]
    strategy_rules: tuple[StrategyRuleBinding, ...]
    fdm_multiplier: float
    forecast_average_correlation: Optional[float]
    forecast_correlations: Optional[dict[str, dict[str, float]]]
    position_inertia: float
    trailing_stop_multiplier: float
    kline_interval: str


def resolve_strategy_id(
    strategy_id: Optional[int] = None,
    *,
    env_var: str = "LIVE_STRATEGY_ID",
) -> int:
    if strategy_id is not None:
        return strategy_id
    raw = os.environ.get(env_var, "").strip()
    if not raw:
        raise ValueError(f"strategy id is required (--strategy-id or {env_var})")
    return int(raw)


def resolve_backtest_run_id(
    backtest_run_id: Optional[int] = None,
    *,
    env_var: str = "LIVE_BACKTEST_RUN_ID",
) -> Optional[int]:
    if backtest_run_id is not None:
        return backtest_run_id
    raw = os.environ.get(env_var, "").strip()
    return int(raw) if raw else None


def resolve_exchange_code(
    exchange_code: Optional[str] = None,
    *,
    env_var: str = "LIVE_EXCHANGE_CODE",
    default: str = DEFAULT_EXCHANGE_CODE,
) -> str:
    if exchange_code is not None:
        code = exchange_code.strip()
        if not code:
            raise ValueError("exchange code must not be empty")
        return code
    raw = os.environ.get(env_var, "").strip()
    return raw or default


def _parse_rule_binding(row: dict[str, Any]) -> StrategyRuleBinding:
    params = row.get("params") or {}
    if not isinstance(params, dict):
        params = dict(params)
    return StrategyRuleBinding(
        rule_code=str(row["rule_code"]),
        rule_name=str(row["rule_name"]),
        variation_name=str(row["variation_name"]),
        weight=float(row["weight"]),
        rule_group=row.get("rule_group"),
        params=params,
    )


def _enrich_stream_instruments(
    portfolio: Portfolio,
    *,
    tinvest_repository: TinvestRepository | None = None,
) -> tuple[StreamInstrument, ...]:
    tickers = [item.ticker for item in portfolio.instruments]
    share_repo = tinvest_repository or TinvestRepository()
    share_rows = share_repo.list_shares_by_tickers(tickers)
    share_by_ticker = {row["instruments_ticker"]: row for row in share_rows}
    missing = set(tickers) - set(share_by_ticker)
    if missing:
        raise ValueError(f"no share rows in DB for tickers: {', '.join(sorted(missing))}")

    items: list[StreamInstrument] = []
    for sleeve in portfolio.instruments:
        share = share_by_ticker[sleeve.ticker]
        figi = str(share.get("figi") or "").strip()
        if not figi:
            raise ValueError(f"share row for ticker={sleeve.ticker} has no figi")
        items.append(
            StreamInstrument(
                ticker=sleeve.ticker,
                class_code=str(share["class_code"]),
                figi=figi,
                instrument_id=sleeve.instrument_id,
                weight=sleeve.weight,
                block_value=sleeve.block_value,
                lot_size=sleeve.lot_size,
                short_enabled=bool(share.get("short_enabled_flag")) and sleeve.short_enabled,
            )
        )
    return tuple(items)


def _resolve_fdm_from_run(run: Optional[dict[str, Any]]) -> tuple[float, Optional[float], Optional[dict]]:
    if run is None:
        return DEFAULT_FDM_MULTIPLIER, None, None
    multiplier = run.get("forecast_diversification_multiplier")
    if multiplier is None:
        return DEFAULT_FDM_MULTIPLIER, None, run.get("forecast_correlations")
    return (
        float(multiplier),
        float(run["forecast_average_correlation"]) if run.get("forecast_average_correlation") is not None else None,
        run.get("forecast_correlations"),
    )


def load_deployment(
    strategy_id: int,
    *,
    backtest_run_id: Optional[int] = None,
    exchange_code: Optional[str] = None,
    trading_capital: Optional[float] = None,
    deployment_repository: LiveDeploymentRepository | None = None,
    portfolio_repository: PortfolioRepository | None = None,
    exchange_repository: ExchangeRepository | None = None,
    tinvest_repository: TinvestRepository | None = None,
) -> DeploymentConfig:
    deployment_repo = deployment_repository or LiveDeploymentRepository()
    portfolio_repo = portfolio_repository or PortfolioRepository()
    exchange_repo = exchange_repository or ExchangeRepository()

    strategy = deployment_repo.get_carver_strategy(strategy_id)
    if strategy is None:
        raise ValueError(f"carver_strategy id={strategy_id} not found")

    portfolio_id = deployment_repo.get_portfolio_id_for_strategy(strategy_id)
    if portfolio_id is None:
        raise ValueError(f"strategy_id={strategy_id} has no row in strategy_portfolio")

    portfolio = portfolio_repo.load_portfolio(portfolio_id)
    resolved_exchange_code = resolve_exchange_code(exchange_code)
    exchange = exchange_repo.get_exchange_by_code(resolved_exchange_code)
    if exchange is None:
        raise ValueError(f"exchange code={resolved_exchange_code!r} not found")

    capital = trading_capital if trading_capital is not None else float(strategy["initial_trading_capital"])
    account = TradingAccount(
        trading_capital=Decimal(str(capital)),
        annualized_volatility_target=float(strategy["annualized_volatility_target"]),
        exchange=exchange,
    )

    if backtest_run_id is not None:
        run = deployment_repo.get_completed_run(backtest_run_id)
        if run is None:
            raise ValueError(f"backtest_run_id={backtest_run_id} not found")
        if run.get("status") != "completed":
            raise ValueError(f"backtest_run_id={backtest_run_id} is not completed (status={run.get('status')})")
        if int(run["strategy_id"]) != strategy_id:
            raise ValueError(
                f"backtest_run_id={backtest_run_id} strategy_id={run['strategy_id']} "
                f"does not match requested strategy_id={strategy_id}"
            )
        if int(run["portfolio_id"]) != portfolio_id:
            raise ValueError(
                f"backtest_run_id={backtest_run_id} portfolio_id={run['portfolio_id']} "
                f"does not match strategy portfolio_id={portfolio_id}"
            )
        resolved_run_id = backtest_run_id
    else:
        run = deployment_repo.get_latest_completed_run(strategy_id=strategy_id, portfolio_id=portfolio_id)
        resolved_run_id = int(run["id"]) if run is not None else None

    fdm_multiplier, avg_corr, correlations = _resolve_fdm_from_run(run)
    rule_rows = deployment_repo.list_strategy_rules(strategy_id)
    strategy_rules = tuple(_parse_rule_binding(row) for row in rule_rows)
    stream_instruments = _enrich_stream_instruments(portfolio, tinvest_repository=tinvest_repository)
    kline_interval = str(run["kline_interval"]) if run and run.get("kline_interval") else "1d"

    return DeploymentConfig(
        strategy_id=strategy_id,
        portfolio_id=portfolio_id,
        backtest_run_id=resolved_run_id,
        strategy_name=str(strategy["name"]),
        portfolio=portfolio,
        account=account,
        exchange=exchange,
        stream_instruments=stream_instruments,
        strategy_rules=strategy_rules,
        fdm_multiplier=fdm_multiplier,
        forecast_average_correlation=avg_corr,
        forecast_correlations=correlations,
        position_inertia=float(strategy["position_inertia"]),
        trailing_stop_multiplier=float(strategy["trailing_stop_multiplier"]),
        kline_interval=kline_interval,
    )
