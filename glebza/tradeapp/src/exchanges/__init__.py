"""Venue / broker adapters (e.g. T‑Invest)."""

__all__ = [
    "CbrRatesService",
    "TBankInstrumentService",
    "instruments_ticker",
]


def __getattr__(name: str):
    if name == "CbrRatesService":
        from .cbr_rates import CbrRatesService

        return CbrRatesService
    if name in {"TBankInstrumentService", "instruments_ticker"}:
        from .tinvest_broker import TBankInstrumentService, instruments_ticker

        return {"TBankInstrumentService": TBankInstrumentService, "instruments_ticker": instruments_ticker}[
            name
        ]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
