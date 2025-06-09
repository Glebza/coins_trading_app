import asyncio

from trading_service.ingestion.ingestion_gateway import main


def test_ingestion_gateway(capsys):
    main()
    captured = capsys.readouterr()
    assert "Starting ingestion gateway" in captured.out
