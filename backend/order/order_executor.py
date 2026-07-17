# 역할: 매매 주문 실행과 체결 흐름을 담당하는 파일.
from backend.bitget.client import BitgetPrivateClient


class OrderExecutor:
    def __init__(self, client: BitgetPrivateClient):
        self.client = client

    def open_limit(self, direction: str, size_btc: float, price: float) -> dict:
        side = "buy" if direction == "LONG" else "sell"
        return self.client.place_limit_order(side, f"{size_btc:.3f}", f"{price:.1f}", "open")


__all__ = ["OrderExecutor"]
