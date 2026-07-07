from backend.bitget.market_api import BitgetClient


class OrderbookCollector:
    def __init__(self, client: BitgetClient):
        self.client = client

    def fetch_best_bid_ask(self) -> dict:
        snap = self.client.fetch_market_snapshot()
        return {"best_bid": snap.best_bid, "best_ask": snap.best_ask}


__all__ = ["OrderbookCollector"]
