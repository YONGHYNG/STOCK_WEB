"""
Download helper for Bitget BTCUSDT 5m history.
This script is intentionally separated from the GUI because 6 years of data can take time.
"""
import csv
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

from backend.app.bitget_client import BitgetClient
from backend.app.config import API_TIMEOUT_SECONDS, BITGET_REST_BASE, PRODUCT_TYPE, SYMBOL


def _timeframe_to_step_ms(timeframe: str, limit: int) -> int:
    base_ms = {
        "1m": 60_000,
        "5m": 5 * 60_000,
        "15m": 15 * 60_000,
        "30m": 30 * 60_000,
        "1H": 60 * 60_000,
        "6H": 6 * 60 * 60_000,
        "1D": 24 * 60 * 60_000,
        "1W": 7 * 24 * 60 * 60_000,
        "1M": 30 * 24 * 60 * 60_000,
    }.get(timeframe, 5 * 60_000)
    return limit * base_ms


def download_history_csv(years: int = 6, timeframe: str = "5m", out_file: str | None = None):
    granularity = BitgetClient._to_bitget_granularity(timeframe)
    limit = 200
    if out_file is None:
        out_file = f"data/bitget_{SYMBOL}_{timeframe}_{years}y.csv"
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=365 * years)
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    step_ms = _timeframe_to_step_ms(timeframe, limit)
    rows = []
    cur = start_ms

    while cur < end_ms:
        nxt = min(cur + step_ms, end_ms)
        params = {
            "symbol": SYMBOL,
            "productType": PRODUCT_TYPE,
            "granularity": granularity,
            "startTime": str(cur),
            "endTime": str(nxt),
            "limit": str(limit),
        }
        try:
            res = requests.get(
                BITGET_REST_BASE + "/api/v2/mix/market/history-candles",
                params=params,
                timeout=API_TIMEOUT_SECONDS,
            )
            res.raise_for_status()
            payload = res.json()
            if payload.get("code") not in (None, "00000"):
                raise RuntimeError(f"{payload.get('code')} {payload.get('msg')}")
            data = payload.get("data", [])
            for item in data:
                rows.append([item[0], item[1], item[2], item[3], item[4], item[5]])
        except Exception as e:
            print(f"download error: {e}")
        cur = nxt
        print(f"progress: {datetime.fromtimestamp(cur / 1000, tz=timezone.utc)} rows={len(rows)}")
        time.sleep(0.15)

    rows = sorted({r[0]: r for r in rows}.values(), key=lambda x: int(x[0]))
    with open(out_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        writer.writerows(rows)
    print(f"saved: {out_file}, rows={len(rows)}")


if __name__ == "__main__":
    tf = sys.argv[1] if len(sys.argv) > 1 else "5m"
    yrs = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    download_history_csv(years=yrs, timeframe=tf)
