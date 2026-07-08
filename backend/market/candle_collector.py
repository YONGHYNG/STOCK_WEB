# 역할: 1분봉/5분봉 캔들을 수집하고 테스트용 mock 데이터를 주입할 수 있게 합니다.
from collections.abc import Callable
from typing import Optional

from backend.bitget.market_api import BitgetClient


MockProvider = Callable[[str, int], list[dict]]


class CandleCollector:
    def __init__(self, client: Optional[BitgetClient] = None, mock_provider: MockProvider | None = None):
        self.client = client
        self.mock_provider = mock_provider

    def fetch_bitget_candles(self, timeframe: str, limit: int = 200) -> list[dict]:
        if self.client is None:
            raise RuntimeError("BitgetClient가 설정되지 않았습니다.")
        if getattr(self.client, "timeframe", None) != timeframe:
            self.client.timeframe = timeframe
        return self.client.fetch_recent_candles_rest(limit)

    def fetch_recent(self, timeframe: str = "5m", limit: int = 200) -> list[dict]:
        if self.mock_provider:
            return self.mock_provider(timeframe, limit)
        return self.fetch_bitget_candles(timeframe, limit)

    def fetch_recent_or_demo(self, limit: int = 200, timeframe: str = "5m") -> tuple[list[dict], str | None]:
        if self.mock_provider:
            return self.mock_provider(timeframe, limit), None
        if self.client is None:
            return [], "BitgetClient가 설정되지 않았습니다."
        if getattr(self.client, "timeframe", None) != timeframe:
            self.client.timeframe = timeframe
        return self.client.fetch_recent_or_demo(limit)

    def fetch_1m_5m(self, limit: int = 240) -> dict[str, list[dict]]:
        return {
            "1m": self.fetch_recent("1m", limit),
            "5m": self.fetch_recent("5m", limit),
        }


__all__ = ["CandleCollector"]
