"""T‑Invest (T‑Bank) instruments: listed shares the API reports as tradable for your access.

Imports assume ``tradeapp/src`` is on ``sys.path`` (sibling packages ``repository``, etc.).
Run as: ``cd glebza/tradeapp/src && python -m exchanges.instrument_service``,
or set ``PYTHONPATH`` to that ``src`` directory.
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict
from typing import Any, Callable, Iterator, List, Optional

from t_tech.invest import Client, InstrumentStatus
from t_tech.invest.schemas import Share

from repository.tinvest_repository import TinvestRepository

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def instruments_ticker(share: Share) -> str:
    """Value stored in ``instruments.ticker`` (API listing ticker only; ``class_code`` stays on ``instrument_share``)."""
    return share.ticker


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
        with Client(self._token, target=self._target) as client:
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


def main() -> None:
    """Load tradeable shares into PostgreSQL."""
    svc = TBankInstrumentService()
    n = svc.persist_tradeable_shares_to_db()
    print(f"persisted_shares={n}", flush=True)


if __name__ == "__main__":
    main()
