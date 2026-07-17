# 역할: Bitget 선물 API 연동을 담당하는 파일.
from backend.bitget.client import BitgetPrivateClient


class OrderApi:
    def __init__(self, client: BitgetPrivateClient):
        self.client = client

    def place_market_order(self, side: str, size: str, trade_side: str = "open") -> dict:
        return self.client.place_market_order(side, size, trade_side)

    def place_limit_order(self, side: str, size: str, price: str, trade_side: str = "open") -> dict:
        return self.client.place_limit_order(side, size, price, trade_side)


__all__ = ["OrderApi"]
