# 역할: 캔들, 호가, 펀딩비 같은 시장 데이터를 수집하는 파일.
import csv
import sys

from backend.config import SYMBOL, TIMEFRAME
from backend.database import init_db, insert_candles


def import_csv(path: str, timeframe: str = TIMEFRAME):
    init_db()
    candles = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            candles.append(row)
    count = insert_candles(SYMBOL, timeframe, candles)
    print(f"imported {count} {timeframe} candles from {path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m backend.market.import_csv_to_sqlite data/bitget_BTCUSDT_5m_6y.csv 5m")
        sys.exit(1)
    tf = sys.argv[2] if len(sys.argv) > 2 else TIMEFRAME
    import_csv(sys.argv[1], tf)
