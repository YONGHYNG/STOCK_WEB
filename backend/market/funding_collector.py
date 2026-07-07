from backend.bitget.market_api import BitgetClient


class FundingCollector:
    def __init__(self, client: BitgetClient):
        self.client = client

    def fetch_current(self) -> dict:
        snap = self.client.fetch_market_snapshot()
        return {
            "funding_rate": snap.funding_rate,
            "next_funding_time": snap.next_funding_time,
            "mark_price": snap.mark_price,
        }


__all__ = ["FundingCollector"]
