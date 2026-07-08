# 역할: Bitget 선물 API 연동을 담당하는 파일.
import random
import time
from dataclasses import dataclass, asdict
from typing import Optional

import requests

from backend.config import API_TIMEOUT_SECONDS, BITGET_REST_BASE, PRODUCT_TYPE, SYMBOL, TIMEFRAME, USE_DEMO_DATA


def now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class MarketSnapshot:
    last_price: Optional[float] = None
    mark_price: Optional[float] = None
    index_price: Optional[float] = None
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None
    funding_rate: Optional[float] = None
    next_funding_time: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)


class BitgetClient:
    """Bitget public market client.

    Demo candles are used only when demo_mode=True. API failures are raised so
    the UI can show that live market data is unavailable.
    """

    def __init__(
        self,
        symbol: str = SYMBOL,
        product_type: str = PRODUCT_TYPE,
        timeframe: str = TIMEFRAME,
        demo_mode: bool = USE_DEMO_DATA,
    ):
        self.symbol = symbol
        self.product_type = product_type
        self.timeframe = timeframe
        self.demo_mode = demo_mode
        self.demo_price = 100000.0

    def fetch_recent_candles_rest(self, limit: int = 200) -> list[dict]:
        """
        Fetch recent history candles from Bitget REST API.
        Bitget returns up to 200 candles per request, so this method paginates
        backward when a larger limit is requested.
        """
        if self.demo_mode:
            return self.generate_demo_candles(limit)

        candles_by_ts: dict[int, dict] = {}
        remaining = max(1, limit)
        end_time: Optional[int] = None

        while remaining > 0:
            batch_limit = min(remaining, 200)
            batch = self._fetch_history_batch(batch_limit, end_time=end_time)
            if not batch:
                break

            for candle in batch:
                candles_by_ts[candle["timestamp"]] = candle

            oldest_ts = min(candle["timestamp"] for candle in batch)
            next_end_time = oldest_ts - 1
            if end_time is not None and next_end_time >= end_time:
                break
            end_time = next_end_time
            remaining = limit - len(candles_by_ts)
            time.sleep(0.08)

        return sorted(candles_by_ts.values(), key=lambda x: x["timestamp"])[-limit:]

    def _fetch_history_batch(self, limit: int, end_time: Optional[int] = None) -> list[dict]:
        granularity = self._to_bitget_granularity(self.timeframe)
        path = "/api/v2/mix/market/history-candles"
        params = {
            "symbol": self.symbol,
            "productType": self.product_type,
            "granularity": granularity,
            "limit": str(min(limit, 200)),
        }
        if end_time is not None:
            params["endTime"] = str(end_time)

        res = requests.get(BITGET_REST_BASE + path, params=params, timeout=API_TIMEOUT_SECONDS)
        res.raise_for_status()
        payload = res.json()
        if payload.get("code") not in (None, "00000"):
            raise RuntimeError(f"Bitget API error: {payload.get('code')} {payload.get('msg')}")

        candles = []
        # Bitget candle item: [timestamp, open, high, low, close, volume, ...]
        for item in payload.get("data", []):
            candles.append(
                {
                    "timestamp": int(item[0]),
                    "open": float(item[1]),
                    "high": float(item[2]),
                    "low": float(item[3]),
                    "close": float(item[4]),
                    "volume": float(item[5]),
                }
            )
        return sorted(candles, key=lambda x: x["timestamp"])

    def fetch_latest_candle_rest(self) -> Optional[dict]:
        candles = self.fetch_recent_candles_rest(2)
        if not candles:
            return None
        return candles[-1]

    def fetch_ticker_price(self) -> Optional[float]:
        """현재 마크가(mark price)를 빠르게 조회합니다. 데모 모드면 내부 데모 가격을 반환합니다."""
        if self.demo_mode:
            drift = random.uniform(-50, 55)
            self.demo_price = max(1.0, self.demo_price + drift)
            return round(self.demo_price, 2)

        path = "/api/v2/mix/market/ticker"
        params = {
            "symbol": self.symbol,
            "productType": self.product_type,
        }
        res = requests.get(
            BITGET_REST_BASE + path,
            params=params,
            timeout=API_TIMEOUT_SECONDS,
        )
        res.raise_for_status()
        payload = res.json()
        if payload.get("code") not in (None, "00000"):
            raise RuntimeError(f"Bitget ticker error: {payload.get('msg')}")
        data = payload.get("data", [])
        if not data:
            return None
        item = data[0] if isinstance(data, list) else data
        # lastPr = 최근 체결가, markPrice = 마크가
        raw = item.get("lastPr") or item.get("markPrice") or item.get("last")
        return float(raw) if raw else None

    def fetch_market_snapshot(self) -> MarketSnapshot:
        if self.demo_mode:
            last = self.fetch_ticker_price() or self.demo_price
            return MarketSnapshot(
                last_price=last,
                mark_price=last,
                index_price=last,
                best_bid=round(last * 0.99995, 2),
                best_ask=round(last * 1.00005, 2),
                funding_rate=0.00005,
                next_funding_time=now_ms() + 4 * 60 * 60 * 1000,
            )

        ticker = self._fetch_ticker_item()
        orderbook = self._fetch_orderbook()
        funding = self._fetch_current_funding()

        def f(value):
            return float(value) if value not in (None, "") else None

        return MarketSnapshot(
            last_price=f(ticker.get("lastPr") or ticker.get("last")),
            mark_price=f(ticker.get("markPrice")),
            index_price=f(ticker.get("indexPrice")),
            best_bid=orderbook.get("best_bid"),
            best_ask=orderbook.get("best_ask"),
            funding_rate=f(funding.get("fundingRate")),
            next_funding_time=int(funding["nextFundingTime"]) if funding.get("nextFundingTime") else None,
        )

    def _fetch_ticker_item(self) -> dict:
        path = "/api/v2/mix/market/ticker"
        params = {"symbol": self.symbol, "productType": self.product_type}
        res = requests.get(BITGET_REST_BASE + path, params=params, timeout=API_TIMEOUT_SECONDS)
        res.raise_for_status()
        payload = res.json()
        if payload.get("code") not in (None, "00000"):
            raise RuntimeError(f"Bitget ticker error: {payload.get('msg')}")
        data = payload.get("data", [])
        if not data:
            return {}
        return data[0] if isinstance(data, list) else data

    def _fetch_orderbook(self) -> dict:
        path = "/api/v2/mix/market/orderbook"
        params = {"symbol": self.symbol, "productType": self.product_type, "limit": "1"}
        res = requests.get(BITGET_REST_BASE + path, params=params, timeout=API_TIMEOUT_SECONDS)
        res.raise_for_status()
        payload = res.json()
        if payload.get("code") not in (None, "00000"):
            raise RuntimeError(f"Bitget orderbook error: {payload.get('msg')}")
        data = payload.get("data") or {}
        bids = data.get("bids") or []
        asks = data.get("asks") or []
        return {
            "best_bid": float(bids[0][0]) if bids else None,
            "best_ask": float(asks[0][0]) if asks else None,
        }

    def _fetch_current_funding(self) -> dict:
        path = "/api/v2/mix/market/current-fund-rate"
        params = {"symbol": self.symbol, "productType": self.product_type}
        res = requests.get(BITGET_REST_BASE + path, params=params, timeout=API_TIMEOUT_SECONDS)
        res.raise_for_status()
        payload = res.json()
        if payload.get("code") not in (None, "00000"):
            raise RuntimeError(f"Bitget funding error: {payload.get('msg')}")
        data = payload.get("data") or []
        return data[0] if isinstance(data, list) and data else data

    def fetch_recent_or_demo(self, limit: int = 200) -> tuple[list[dict], Optional[str]]:
        try:
            return self.fetch_recent_candles_rest(limit), None
        except Exception as exc:
            if not self.demo_mode:
                return [], str(exc)
            return self.generate_demo_candles(limit), str(exc)

    def generate_demo_candles(self, limit: int = 300) -> list[dict]:
        candles = []
        interval_ms = self._timeframe_to_ms(self.timeframe)
        ts = now_ms() - limit * interval_ms
        price = self.demo_price
        for _ in range(limit):
            drift = random.uniform(-250, 260)
            open_price = price
            close = max(1, open_price + drift)
            high = max(open_price, close) + random.uniform(10, 120)
            low = min(open_price, close) - random.uniform(10, 120)
            volume = random.uniform(50, 600)
            candles.append(
                {
                    "timestamp": ts,
                    "open": round(open_price, 2),
                    "high": round(high, 2),
                    "low": round(low, 2),
                    "close": round(close, 2),
                    "volume": round(volume, 4),
                }
            )
            price = close
            ts += interval_ms
        self.demo_price = price
        return candles

    def generate_next_demo_candle(self, last_price: Optional[float] = None) -> dict:
        if last_price is not None:
            self.demo_price = float(last_price)
        candle = self.generate_demo_candles(1)[0]
        candle["timestamp"] = now_ms()
        return candle

    @staticmethod
    def _to_bitget_granularity(timeframe: str) -> str:
        mapping = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "30m": "30m",
            "1h": "1H",
            "1H": "1H",
            "2h": "2H",
            "4h": "4H",
            "4H": "4H",
            "6H": "6H",
            "1d": "1D",
            "1D": "1D",
            "1W": "1W",
            "1M": "1M",
        }
        return mapping.get(timeframe, timeframe)

    @staticmethod
    def _timeframe_to_ms(timeframe: str) -> int:
        mapping = {
            "1m": 60_000,
            "5m": 5 * 60_000,
            "15m": 15 * 60_000,
            "30m": 30 * 60_000,
            "1H": 60 * 60_000,
            "4H": 4 * 60 * 60_000,
            "6H": 6 * 60 * 60_000,
            "1D": 24 * 60 * 60_000,
            "1W": 7 * 24 * 60 * 60_000,
            "1M": 30 * 24 * 60 * 60_000,
        }
        return mapping.get(timeframe, 5 * 60_000)
