"""Trade decision module."""

from trading_service.models.predictor import predict


def decide(orderbook: list) -> str:
    features = orderbook
    return predict(features)
