"""Backfill gaps in the existing Bitget candle ranges."""

from __future__ import annotations

import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.bitget.market_api import BitgetClient  # noqa: E402
from backend.config import DB_PATH, PRODUCT_TYPE, SYMBOL  # noqa: E402
from backend.database import insert_candles  # noqa: E402


INTERVAL_MS = {
    "1m": 60_000,
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "30m": 30 * 60_000,
    "1H": 60 * 60_000,
    "4H": 4 * 60 * 60_000,
    "6H": 6 * 60 * 60_000,
    "1D": 24 * 60 * 60_000,
    "1W": 7 * 24 * 60 * 60_000,
    # Used only to size the request. Exchange timestamps determine actual months.
    "1M": 30 * 24 * 60 * 60_000,
}


def stored_ranges() -> dict[str, int]:
    with sqlite3.connect(DB_PATH) as conn:
        return dict(
            conn.execute(
                "SELECT timeframe, MIN(timestamp) FROM candles "
                "WHERE symbol=? GROUP BY timeframe",
                (SYMBOL,),
            ).fetchall()
        )


def backfill(timeframe: str, first_timestamp: int, now_ms: int) -> tuple:
    interval = INTERVAL_MS[timeframe]
    limit = max(2, int((now_ms - first_timestamp) // interval) + 3)
    client = BitgetClient(
        symbol=SYMBOL,
        product_type=PRODUCT_TYPE,
        timeframe=timeframe,
        demo_mode=False,
    )
    fetched = client.fetch_recent_candles_rest(limit)
    rows = [row for row in fetched if row["timestamp"] >= first_timestamp]
    inserted = insert_candles(SYMBOL, timeframe, rows)
    return timeframe, limit, len(fetched), inserted


def main() -> int:
    ranges = stored_ranges()
    unknown = sorted(set(ranges) - set(INTERVAL_MS))
    if unknown:
        raise RuntimeError(f"Unsupported stored timeframes: {', '.join(unknown)}")

    failures = []
    now_ms = int(time.time() * 1000)
    with ThreadPoolExecutor(max_workers=min(5, len(ranges))) as executor:
        futures = {
            executor.submit(backfill, timeframe, first_ts, now_ms): timeframe
            for timeframe, first_ts in ranges.items()
        }
        for future in as_completed(futures):
            timeframe = futures[future]
            try:
                tf, requested, fetched, saved = future.result()
                print(f"{tf}: requested={requested}, fetched={fetched}, saved={saved}")
            except Exception as exc:
                failures.append((timeframe, str(exc)))
                print(f"{timeframe}: ERROR: {exc}", file=sys.stderr)

    if failures:
        print(f"Failed timeframes: {failures}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
