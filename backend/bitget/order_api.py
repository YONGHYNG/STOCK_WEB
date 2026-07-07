from backend.bitget.client import BitgetPrivateClient


class OrderApi:
    def __init__(self, client: BitgetPrivateClient):
        self.client = client

    def place_market_order(self, side: str, size: str, trade_side: str = "open") -> dict:
        return self.client.place_market_order(side, size, trade_side)


__all__ = ["OrderApi"]
