"""Write promoted Carver configuration to traderdb (public schema)."""

from __future__ import annotations

from typing import Any, Optional

import psycopg2
import psycopg2.extras

from repository.postgres_connection import connect
from transition_service.settings import Settings


class PublicWriteRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def upsert_exchange(self, exchange: dict[str, Any]) -> int:
        conn = connect(
            database_url=self._settings.live_database_url,
            schema=self._settings.live_schema,
        )
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO exchange (
                    code, name, currency, tariff_name,
                    brokerage_rate_spot, brokerage_min_fee_spot,
                    brokerage_rate_futures, brokerage_rate_futures_alt,
                    brokerage_min_fee_futures,
                    exchange_fee_rate_spot, exchange_fee_rate_futures,
                    monthly_fee, effective_from, notes, max_capital_multiple
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s,
                    %s, %s,
                    %s, %s, %s, %s
                )
                ON CONFLICT (code) DO UPDATE SET
                    name = EXCLUDED.name,
                    currency = EXCLUDED.currency,
                    tariff_name = EXCLUDED.tariff_name,
                    brokerage_rate_spot = EXCLUDED.brokerage_rate_spot,
                    brokerage_min_fee_spot = EXCLUDED.brokerage_min_fee_spot,
                    brokerage_rate_futures = EXCLUDED.brokerage_rate_futures,
                    brokerage_rate_futures_alt = EXCLUDED.brokerage_rate_futures_alt,
                    brokerage_min_fee_futures = EXCLUDED.brokerage_min_fee_futures,
                    exchange_fee_rate_spot = EXCLUDED.exchange_fee_rate_spot,
                    exchange_fee_rate_futures = EXCLUDED.exchange_fee_rate_futures,
                    monthly_fee = EXCLUDED.monthly_fee,
                    effective_from = EXCLUDED.effective_from,
                    notes = EXCLUDED.notes,
                    max_capital_multiple = EXCLUDED.max_capital_multiple
                RETURNING id
                """,
                (
                    exchange["code"],
                    exchange.get("name"),
                    exchange.get("currency"),
                    exchange.get("tariff_name"),
                    exchange.get("brokerage_rate_spot"),
                    exchange.get("brokerage_min_fee_spot"),
                    exchange.get("brokerage_rate_futures"),
                    exchange.get("brokerage_rate_futures_alt"),
                    exchange.get("brokerage_min_fee_futures"),
                    exchange.get("exchange_fee_rate_spot"),
                    exchange.get("exchange_fee_rate_futures"),
                    exchange.get("monthly_fee"),
                    exchange.get("effective_from"),
                    exchange.get("notes"),
                    exchange.get("max_capital_multiple"),
                ),
            )
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("upsert exchange did not return id")
            exchange_id = int(row[0])
            conn.commit()
            cur.close()
            return exchange_id
        except (Exception, psycopg2.DatabaseError):
            conn.rollback()
            raise
        finally:
            conn.close()

    def find_instrument_id_by_ticker(self, ticker: str) -> Optional[int]:
        conn = connect(
            database_url=self._settings.live_database_url,
            schema=self._settings.live_schema,
        )
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id FROM instruments WHERE ticker = %s",
                (ticker,),
            )
            row = cur.fetchone()
            cur.close()
            return int(row[0]) if row else None
        finally:
            conn.close()

    def copy_instrument_from_share(
        self,
        *,
        ticker: str,
        instrument_type: str,
        share: dict[str, Any],
    ) -> int:
        conn = connect(
            database_url=self._settings.live_database_url,
            schema=self._settings.live_schema,
        )
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO instruments (ticker, instrument_type)
                VALUES (%s, %s)
                RETURNING id
                """,
                (ticker, instrument_type),
            )
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("insert instruments did not return id")
            instrument_id = int(row[0])
            cur.execute(
                """
                INSERT INTO instrument_share (
                    instrument_id, figi, isin, ticker, class_code, lot, currency, name,
                    sector, buy_available_flag, sell_available_flag, short_enabled_flag,
                    api_trade_available_flag, for_qual_investor_flag, raw_payload
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    instrument_id,
                    share["figi"],
                    share.get("isin"),
                    share.get("ticker") or ticker,
                    share.get("class_code"),
                    share.get("lot"),
                    share.get("currency"),
                    share.get("name"),
                    share.get("sector"),
                    share.get("buy_available_flag"),
                    share.get("sell_available_flag"),
                    share.get("short_enabled_flag"),
                    share.get("api_trade_available_flag"),
                    share.get("for_qual_investor_flag"),
                    share.get("raw_payload"),
                ),
            )
            conn.commit()
            cur.close()
            return instrument_id
        except (Exception, psycopg2.DatabaseError):
            conn.rollback()
            raise
        finally:
            conn.close()

    def resolve_rule_variation_id(self, *, rule_code: str, variation_name: str) -> Optional[int]:
        conn = connect(
            database_url=self._settings.live_database_url,
            schema=self._settings.live_schema,
        )
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT rv.id
                FROM rule_variations rv
                JOIN rules r ON r.id = rv.rule_id
                WHERE r.code = %s AND rv.name = %s
                """,
                (rule_code, variation_name),
            )
            row = cur.fetchone()
            cur.close()
            return int(row[0]) if row else None
        finally:
            conn.close()

    def promote_bundle(
        self,
        *,
        strategy: dict[str, Any],
        portfolio: dict[str, Any],
        portfolio_instruments: list[tuple[int, Any, Any, Any]],
        strategy_rules: list[tuple[Any, int, Any]],
        exchange_id: int,
    ) -> dict[str, int]:
        """
        Insert strategy, portfolio, links, and rules in one transaction.

        ``portfolio_instruments`` tuples: (instrument_id, weight, block_value, lot_size)
        ``strategy_rules`` tuples: (rule_group, rule_variation_id, weight)
        """
        conn = connect(
            database_url=self._settings.live_database_url,
            schema=self._settings.live_schema,
        )
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO strategy (
                    name, description, exchange_id,
                    initial_trading_capital, annualized_volatility_target,
                    max_capital_multiple, position_inertia,
                    trailing_stop_multiplier, slippage_rate
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    strategy["name"],
                    strategy.get("description"),
                    exchange_id,
                    strategy.get("initial_trading_capital"),
                    strategy.get("annualized_volatility_target"),
                    strategy.get("max_capital_multiple"),
                    strategy.get("position_inertia"),
                    strategy.get("trailing_stop_multiplier"),
                    strategy.get("slippage_rate"),
                ),
            )
            strategy_row = cur.fetchone()
            if strategy_row is None:
                raise RuntimeError("insert strategy did not return id")
            strategy_id = int(strategy_row[0])

            cur.execute(
                """
                INSERT INTO portfolio (name, description)
                VALUES (%s, %s)
                RETURNING id
                """,
                (portfolio["name"], portfolio.get("description")),
            )
            portfolio_row = cur.fetchone()
            if portfolio_row is None:
                raise RuntimeError("insert portfolio did not return id")
            portfolio_id = int(portfolio_row[0])

            for instrument_id, weight, block_value, lot_size in portfolio_instruments:
                cur.execute(
                    """
                    INSERT INTO portfolio_instruments (
                        portfolio_id, instrument_id, weight, block_value, lot_size
                    ) VALUES (%s, %s, %s, %s, %s)
                    """,
                    (portfolio_id, instrument_id, weight, block_value, lot_size),
                )

            cur.execute(
                """
                INSERT INTO strategy_portfolio (strategy_id, portfolio_id)
                VALUES (%s, %s)
                """,
                (strategy_id, portfolio_id),
            )

            for rule_group, rule_variation_id, weight in strategy_rules:
                cur.execute(
                    """
                    INSERT INTO strategy_rules (strategy_id, rule_variation_id, rule_group, weight)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (strategy_id, rule_variation_id, rule_group, weight),
                )

            conn.commit()
            cur.close()
            return {"strategy_id": strategy_id, "portfolio_id": portfolio_id}
        except (Exception, psycopg2.DatabaseError):
            conn.rollback()
            raise
        finally:
            conn.close()
