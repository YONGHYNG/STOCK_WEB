"""Read-only audit of recorded entries, not a counterfactual PnL backtest.

Run from frontend with PYTHONPATH pointing to the workspace root.
"""
import argparse
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from backend.strategy.entry_timing import BAR_MS, assess_entry_timing, timing_entry_check
from backend.strategy.indicator import add_indicators


def replay(db_path, start, end):
    with sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        trades = [dict(r) for r in conn.execute(
            "SELECT *,datetime(entry_time,'+9 hours') AS entry_kst FROM trades "
            "WHERE trade_type='PAPER' AND datetime(entry_time,'+9 hours')>=? "
            "AND datetime(entry_time,'+9 hours')<? ORDER BY entry_time,id", (start, end))]
        rows = []
        for trade in trades:
            now = int(datetime.fromisoformat(trade["entry_time"]).replace(tzinfo=timezone.utc).timestamp() * 1000)
            candles = [dict(r) for r in conn.execute(
                "SELECT * FROM candles WHERE symbol=? AND timeframe='5m' "
                "AND timestamp+?<=? ORDER BY timestamp DESC LIMIT 660",
                (trade["symbol"], BAR_MS, now))][::-1]
            frame = add_indicators(candles)
            timing = assess_entry_timing(frame, trade["direction"], json.loads(trade["tf_directions"] or "{}"))
            previous = conn.execute(
                "SELECT * FROM trades WHERE symbol=? AND trade_type='PAPER' AND exit_time<=? "
                "AND id!=? ORDER BY exit_time DESC,id DESC LIMIT 1",
                (trade["symbol"], trade["entry_time"], trade["id"])).fetchone()
            allowed, reason = timing_entry_check(timing, trade["entry_price"], now, dict(previous) if previous else None)
            rows.append(dict(id=trade["id"], entry_kst=trade["entry_kst"], direction=trade["direction"],
                actual_result=trade["result"], actual_pnl=trade["realized_pnl_amount"],
                scheduled="고정 진입 세션" in (trade["entry_reason"] or ""),
                timing_allowed=allowed, reason=reason, timing=timing))
    return dict(start_kst=start, end_kst_exclusive=end,
        limitation="Stored final entry prices can include scale-ins. Historical entry-time feed availability is unknown. "
                   "This audits the original entry, not subsequent alternative fills or profitability. "
                   "Scheduled deadline exceptions remain enabled; a failed filter does not imply an avoided loss.",
        counts=dict(Counter("allowed" if r["timing_allowed"] else "wait" for r in rows)), entries=rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="../data/trading.db")
    parser.add_argument("--start", default="2026-09-11")
    parser.add_argument("--end", default="2026-09-15")
    parser.add_argument("--output", default="reports/entry-timing-september-11-14.json")
    args = parser.parse_args()
    result = replay(args.db, args.start, args.end)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"counts": result["counts"], "output": str(path)}, ensure_ascii=True))
