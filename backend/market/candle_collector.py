from backend.bitget.market_api import BitgetClient


class CandleCollector:
    def __init__(self, client: BitgetClient):
        self.client = client

    def fetch_recent(self, limit: int = 200) -> list[dict]:
        return self.client.fetch_recent_candles_rest(limit)

    def fetch_recent_or_demo(self, limit: int = 200) -> tuple[list[dict], str | None]:
        return self.client.fetch_recent_or_demo(limit)


__all__ = ["CandleCollector"]
