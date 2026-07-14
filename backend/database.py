# 역할: 매매 기록과 상태 저장용 데이터베이스를 관리하는 파일.
import json
import sqlite3
from typing import Iterable, Optional

from backend.config import DB_PATH, DATA_DIR


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-32000")
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS candles (
                symbol    TEXT    NOT NULL,
                timeframe TEXT    NOT NULL,
                timestamp INTEGER NOT NULL,
                open      REAL    NOT NULL,
                high      REAL    NOT NULL,
                low       REAL    NOT NULL,
                close     REAL    NOT NULL,
                volume    REAL    NOT NULL,
                PRIMARY KEY (symbol, timeframe, timestamp)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_candles_lookup
            ON candles (symbol, timeframe, timestamp DESC)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS signals (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol              TEXT    NOT NULL,
                timeframe           TEXT    NOT NULL,
                timestamp           INTEGER NOT NULL,
                entry_price         REAL,
                direction           TEXT,
                long_probability    REAL,
                short_probability   REAL,
                confidence          REAL,
                stop_loss           REAL,
                take_profit_1       REAL,
                take_profit_2       REAL,
                risk_reward_ratio   REAL,
                all_time_high_mode  INTEGER DEFAULT 0,
                all_time_low_mode   INTEGER DEFAULT 0,
                reason              TEXT,
                created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol        TEXT    NOT NULL,
                trade_type    TEXT    NOT NULL DEFAULT 'LIVE',
                direction     TEXT    NOT NULL,
                entry_price   REAL    NOT NULL,
                stop_loss     REAL,
                take_profit_1 REAL,
                take_profit_2 REAL,
                risk_reward   REAL,
                confidence    REAL,
                long_prob     REAL,
                short_prob    REAL,
                tf_directions TEXT,
                entry_reason  TEXT,
                entry_time    DATETIME DEFAULT CURRENT_TIMESTAMP,
                exit_price    REAL,
                exit_time     DATETIME,
                result        TEXT DEFAULT 'OPEN',
                pnl_pct       REAL,
                profit_reason TEXT,
                loss_reason   TEXT,
                notes         TEXT
            )
            """
        )
        # 기존 trades 테이블에 trade_type 컬럼이 없으면 추가 (마이그레이션)
        try:
            conn.execute("ALTER TABLE trades ADD COLUMN trade_type TEXT NOT NULL DEFAULT 'LIVE'")
        except Exception:
            pass   # 이미 존재하면 무시
        try:
            conn.execute("ALTER TABLE trades ADD COLUMN realized_pnl_amount REAL")
        except Exception:
            pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_account (
                id              INTEGER PRIMARY KEY CHECK (id = 1),
                initial_balance REAL NOT NULL,
                balance         REAL NOT NULL,
                leverage        REAL NOT NULL,
                updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def reconcile_paper_account(initial_balance: float = 100.0, leverage: float = 20.0) -> dict:
    """모의 청산 내역을 시간순으로 복리 재계산하고 잔액과 수익금을 저장합니다."""
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT OR IGNORE INTO paper_account (id, initial_balance, balance, leverage) VALUES (1, ?, ?, ?)",
            (initial_balance, initial_balance, leverage),
        )
        account = conn.execute("SELECT * FROM paper_account WHERE id=1").fetchone()
        balance = float(account["initial_balance"])
        account_leverage = float(account["leverage"])
        rows = conn.execute(
            """
            SELECT id, pnl_pct FROM trades
            WHERE trade_type='PAPER' AND result != 'OPEN' AND pnl_pct IS NOT NULL
            ORDER BY id ASC
            """
        ).fetchall()
        for row in rows:
            pnl_amount = balance * account_leverage * (float(row["pnl_pct"]) / 100)
            pnl_amount = max(pnl_amount, -balance)
            balance += pnl_amount
            conn.execute(
                "UPDATE trades SET realized_pnl_amount=? WHERE id=?",
                (round(pnl_amount, 8), row["id"]),
            )
        conn.execute(
            "UPDATE paper_account SET balance=?, updated_at=CURRENT_TIMESTAMP WHERE id=1",
            (round(balance, 8),),
        )
        conn.commit()
        return dict(conn.execute("SELECT * FROM paper_account WHERE id=1").fetchone())


def get_paper_account(initial_balance: float = 100.0, leverage: float = 20.0) -> dict:
    return reconcile_paper_account(initial_balance, leverage)


def insert_candle(symbol: str, timeframe: str, candle: dict) -> None:
    insert_candles(symbol, timeframe, [candle])


def insert_candles(symbol: str, timeframe: str, candles: Iterable[dict]) -> int:
    rows = [
        (
            symbol,
            timeframe,
            int(c["timestamp"]),
            float(c["open"]),
            float(c["high"]),
            float(c["low"]),
            float(c["close"]),
            float(c["volume"]),
        )
        for c in candles
    ]
    if not rows:
        return 0
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO candles
            (symbol, timeframe, timestamp, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
    return len(rows)


def get_recent_candles(symbol: str, timeframe: str, limit: int = 300) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT timestamp, open, high, low, close, volume
            FROM candles
            WHERE symbol = ? AND timeframe = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (symbol, timeframe, limit),
        ).fetchall()
    return [dict(row) for row in reversed(rows)]


def get_candles_between(symbol: str, timeframe: str, start_ts: int, end_ts: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT timestamp, open, high, low, close, volume
            FROM candles
            WHERE symbol = ?
              AND timeframe = ?
              AND timestamp BETWEEN ? AND ?
            ORDER BY timestamp ASC
            """,
            (symbol, timeframe, start_ts, end_ts),
        ).fetchall()
    return [dict(row) for row in rows]


def purge_unaligned_candles(symbol: str, timeframe: str) -> int:
    interval_ms = {
        "1m":  60_000,
        "5m":  5  * 60_000,
        "15m": 15 * 60_000,
        "30m": 30 * 60_000,
        "1H":  60 * 60_000,
        "4H":  4  * 60 * 60_000,
        "6H":  6  * 60 * 60_000,
        "1D":  24 * 60 * 60_000,
        "1W":  24 * 60 * 60_000,
        "1M":  24 * 60 * 60_000,
    }.get(timeframe)
    if not interval_ms:
        return 0
    with get_connection() as conn:
        cur = conn.execute(
            """
            DELETE FROM candles
            WHERE symbol = ? AND timeframe = ? AND timestamp % ? != 0
            """,
            (symbol, timeframe, interval_ms),
        )
        conn.commit()
        return cur.rowcount


def get_all_time_high(symbol: str, timeframe: str) -> Optional[float]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(high) AS v FROM candles WHERE symbol = ? AND timeframe = ?",
            (symbol, timeframe),
        ).fetchone()
    return float(row["v"]) if row and row["v"] is not None else None


def get_all_time_low(symbol: str, timeframe: str) -> Optional[float]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MIN(low) AS v FROM candles WHERE symbol = ? AND timeframe = ?",
            (symbol, timeframe),
        ).fetchone()
    return float(row["v"]) if row and row["v"] is not None else None


# ── Trade journal ──────────────────────────────────────────────────────────────

def open_trade(
    symbol: str,
    direction: str,
    entry_price: float,
    stop_loss: Optional[float],
    take_profit_1: Optional[float],
    take_profit_2: Optional[float],
    risk_reward: Optional[float],
    confidence: float,
    long_prob: float,
    short_prob: float,
    tf_directions: dict,
    entry_reason: str,
    trade_type: str = "LIVE",
) -> int:
    """새 거래를 열고 trade ID를 반환합니다. trade_type: 'LIVE' | 'PAPER' | 'PLAN'"""
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO trades
            (symbol, trade_type, direction, entry_price, stop_loss, take_profit_1, take_profit_2,
             risk_reward, confidence, long_prob, short_prob, tf_directions, entry_reason, result)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN')
            """,
            (
                symbol, trade_type, direction, entry_price, stop_loss, take_profit_1, take_profit_2,
                risk_reward, confidence, long_prob, short_prob,
                json.dumps(tf_directions, ensure_ascii=False),
                entry_reason,
            ),
        )
        conn.commit()
        return cur.lastrowid


def close_trade(
    trade_id: int,
    exit_price: float,
    result: str,
    pnl_pct: float,
    profit_reason: str = "",
    loss_reason: str = "",
) -> None:
    """거래를 청산하고 결과를 기록합니다."""
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE trades
            SET exit_price=?, exit_time=CURRENT_TIMESTAMP,
                result=?, pnl_pct=?, profit_reason=?, loss_reason=?
            WHERE id=?
            """,
            (exit_price, result, round(pnl_pct, 4), profit_reason, loss_reason, trade_id),
        )
        conn.commit()


def get_open_trade(symbol: str, trade_type: str = "LIVE") -> Optional[dict]:
    """현재 오픈 중인 거래를 반환합니다. trade_type: 'LIVE' | 'PAPER' | 'PLAN'"""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM trades WHERE symbol=? AND trade_type=? AND result='OPEN' ORDER BY id DESC LIMIT 1",
            (symbol, trade_type),
        ).fetchone()
    return dict(row) if row else None


def get_recent_trades(symbol: str, limit: Optional[int] = 50, trade_type: Optional[str] = None) -> list[dict]:
    """거래 목록을 최신순으로 반환합니다. limit=None이면 전체를 반환합니다."""
    with get_connection() as conn:
        if trade_type and limit is None:
            rows = conn.execute(
                "SELECT * FROM trades WHERE symbol=? AND trade_type=? ORDER BY id DESC",
                (symbol, trade_type),
            ).fetchall()
        elif trade_type:
            rows = conn.execute(
                "SELECT * FROM trades WHERE symbol=? AND trade_type=? ORDER BY id DESC LIMIT ?",
                (symbol, trade_type, limit),
            ).fetchall()
        elif limit is None:
            rows = conn.execute(
                "SELECT * FROM trades WHERE symbol=? ORDER BY id DESC",
                (symbol,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM trades WHERE symbol=? ORDER BY id DESC LIMIT ?",
                (symbol, limit),
            ).fetchall()
    return [dict(r) for r in rows]


def insert_signal(symbol: str, timeframe: str, result: dict) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO signals
            (symbol, timeframe, timestamp, entry_price, direction, long_probability,
             short_probability, confidence, stop_loss, take_profit_1, take_profit_2,
             risk_reward_ratio, all_time_high_mode, all_time_low_mode, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                symbol,
                timeframe,
                int(result.get("timestamp") or 0),
                result.get("entry_price"),
                result.get("direction"),
                result.get("long_probability"),
                result.get("short_probability"),
                result.get("confidence"),
                result.get("stop_loss"),
                result.get("take_profit_1"),
                result.get("take_profit_2"),
                result.get("risk_reward_ratio"),
                1 if result.get("all_time_high_mode") else 0,
                1 if result.get("all_time_low_mode") else 0,
                "\n".join(result.get("reasons", [])),
            ),
        )
        conn.commit()
