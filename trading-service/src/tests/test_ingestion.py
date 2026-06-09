import asyncio
import pytest

from trading_service.ingestion.ingestion_gateway import IngestionGateway, WSConfig


def test_ingestion_gateway_config():
    cfg = WSConfig(symbols=["ETHUSDT"], kline_interval="1m", speed="100ms")
    expected_streams = [
        "spot@public.limit.depth.v3.api.pb@100ms@ETHUSDT",
        "spot@public.aggre.deals.v3.api.pb@100ms@ETHUSDT",
        "spot@public.kline.v3.api.pb@ETHUSDT@Min1",
    ]
    assert cfg.all_streams == expected_streams


@pytest.mark.asyncio
async def test_gateway_initialisation():
    q: asyncio.Queue[bytes] = asyncio.Queue()
    cfg = WSConfig(symbols=["BTCUSDT"])
    gw = IngestionGateway(cfg, q)

    assert gw.orderbooks["BTCUSDT"].symbol == "BTCUSDT"
    assert not gw._stop.is_set()
