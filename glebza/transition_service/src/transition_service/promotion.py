"""Promote a completed backtest run from backtest DB to traderdb."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from repository.backtest_read_repository import RUN_STATUS_COMPLETED, BacktestReadRepository
from repository.public_write_repository import PublicWriteRepository
from transition_service.settings import Settings


@dataclass(frozen=True)
class PromoteResult:
    backtest_run_id: int
    backtest_strategy_id: int
    backtest_portfolio_id: int
    live_strategy_id: int
    live_portfolio_id: int
    live_exchange_id: int
    instrument_count: int
    rule_count: int
    instruments_copied: tuple[str, ...]


class PromotionService:
    def __init__(
        self,
        settings: Settings,
        *,
        backtest_repo: BacktestReadRepository | None = None,
        public_repo: PublicWriteRepository | None = None,
    ) -> None:
        self._backtest = backtest_repo or BacktestReadRepository(settings)
        self._public = public_repo or PublicWriteRepository(settings)

    def promote_run(self, run_id: int, *, dry_run: bool = False) -> PromoteResult:
        run = self._backtest.get_run(run_id)
        if run is None:
            raise ValueError(f"backtest run id={run_id} not found")
        if run["status"] != RUN_STATUS_COMPLETED:
            raise ValueError(
                f"backtest run id={run_id} has status={run['status']!r}; only completed runs can be promoted"
            )
        if run.get("strategy_id") is None or run.get("portfolio_id") is None:
            raise ValueError(f"backtest run id={run_id} is missing strategy_id or portfolio_id")

        strategy_id = int(run["strategy_id"])
        portfolio_id = int(run["portfolio_id"])

        strategy = self._backtest.get_carver_strategy(strategy_id)
        if strategy is None:
            raise ValueError(f"backtests.carver_strategy id={strategy_id} not found")

        portfolio = self._backtest.get_portfolio(portfolio_id)
        if portfolio is None:
            raise ValueError(f"backtests.portfolio id={portfolio_id} not found")

        exchange = self._backtest.get_exchange(int(strategy["exchange_id"]))
        if exchange is None:
            raise ValueError(f"backtests.exchange id={strategy['exchange_id']} not found")

        portfolio_rows = self._backtest.list_portfolio_instruments(portfolio_id)
        if not portfolio_rows:
            raise ValueError(f"backtests.portfolio id={portfolio_id} has no instruments")

        rule_rows = self._backtest.list_strategy_rules(strategy_id)
        if not rule_rows:
            raise ValueError(f"backtests.carver_strategy id={strategy_id} has no strategy_rules")

        mapped_instruments: list[tuple[int, Any, Any, Any]] = []
        copied_tickers: list[str] = []
        for row in portfolio_rows:
            ticker = str(row["ticker"])
            live_instrument_id = self._public.find_instrument_id_by_ticker(ticker)
            if live_instrument_id is None:
                share = self._backtest.get_instrument_share(int(row["instrument_id"]))
                if share is None:
                    raise ValueError(
                        f"ticker={ticker} missing in public.instruments and no instrument_share in backtests"
                    )
                if dry_run:
                    copied_tickers.append(ticker)
                    live_instrument_id = -1
                else:
                    live_instrument_id = self._public.copy_instrument_from_share(
                        ticker=ticker,
                        instrument_type=str(row["instrument_type"]),
                        share=share,
                    )
                    copied_tickers.append(ticker)
            mapped_instruments.append(
                (
                    live_instrument_id,
                    row["weight"],
                    row["block_value"],
                    row["lot_size"],
                )
            )

        mapped_rules: list[tuple[Any, int, Any]] = []
        for rule in rule_rows:
            variation_id = self._public.resolve_rule_variation_id(
                rule_code=str(rule["rule_code"]),
                variation_name=str(rule["variation_name"]),
            )
            if variation_id is None:
                raise ValueError(
                    f"public rule variation not found: code={rule['rule_code']!r} "
                    f"name={rule['variation_name']!r}"
                )
            mapped_rules.append((rule.get("rule_group"), variation_id, rule["weight"]))

        if dry_run:
            return PromoteResult(
                backtest_run_id=run_id,
                backtest_strategy_id=strategy_id,
                backtest_portfolio_id=portfolio_id,
                live_strategy_id=-1,
                live_portfolio_id=-1,
                live_exchange_id=-1,
                instrument_count=len(mapped_instruments),
                rule_count=len(mapped_rules),
                instruments_copied=tuple(copied_tickers),
            )

        live_exchange_id = self._public.upsert_exchange(exchange)
        strategy_payload = dict(strategy)
        strategy_payload["exchange_id"] = live_exchange_id

        ids = self._public.promote_bundle(
            strategy=strategy_payload,
            portfolio=portfolio,
            portfolio_instruments=mapped_instruments,
            strategy_rules=mapped_rules,
            exchange_id=live_exchange_id,
        )

        return PromoteResult(
            backtest_run_id=run_id,
            backtest_strategy_id=strategy_id,
            backtest_portfolio_id=portfolio_id,
            live_strategy_id=ids["strategy_id"],
            live_portfolio_id=ids["portfolio_id"],
            live_exchange_id=live_exchange_id,
            instrument_count=len(mapped_instruments),
            rule_count=len(mapped_rules),
            instruments_copied=tuple(copied_tickers),
        )
