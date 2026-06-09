from trading_service.decision.trade_logic import decide


def test_decide():
    signal = decide([1, 2, 3])
    assert signal == "BUY"
