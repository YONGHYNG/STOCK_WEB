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
                market_regime      TEXT,
                strategy_signal    TEXT,
                entry_grade        TEXT,
                diagnostics_json   TEXT,
                block_reason       TEXT,
                reason              TEXT,
                created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for migration in (
            "ALTER TABLE signals ADD COLUMN market_regime TEXT",
            "ALTER TABLE signals ADD COLUMN strategy_signal TEXT",
            "ALTER TABLE signals ADD COLUMN entry_grade TEXT",
            "ALTER TABLE signals ADD COLUMN diagnostics_json TEXT",
            "ALTER TABLE signals ADD COLUMN block_reason TEXT",
        ):
            try:
                conn.execute(migration)
            except sqlite3.OperationalError:
                pass
        # 이전 버전이 15초마다 같은 확정 5분봉을 INSERT한 중복 기록을 정리합니다.
        # 가장 최근 분석만 남긴 뒤 동일 봉이 다시 늘어나지 않도록 고유 인덱스를 둡니다.
        conn.execute(
            """
            DELETE FROM signals
            WHERE id NOT IN (
                SELECT MAX(id)
                FROM signals
                GROUP BY symbol, timeframe, timestamp
            )
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_signals_unique_bar
            ON signals (symbol, timeframe, timestamp)
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
                notes         TEXT,
                size_btc      REAL
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
        try:
            conn.execute("ALTER TABLE trades ADD COLUMN size_btc REAL")
        except Exception:
            pass
        for migration in (
            "ALTER TABLE trades ADD COLUMN entry_order_id TEXT",
            "ALTER TABLE trades ADD COLUMN exchange_position_id TEXT",
            "ALTER TABLE trades ADD COLUMN entry_fee REAL",
            "ALTER TABLE trades ADD COLUMN exit_fee REAL",
            "ALTER TABLE trades ADD COLUMN funding_fee REAL",
            "ALTER TABLE trades ADD COLUMN net_profit REAL",
            "ALTER TABLE trades ADD COLUMN synced_at DATETIME",
        ):
            try:
                conn.execute(migration)
            except sqlite3.OperationalError:
                pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS live_execution_state (
                symbol            TEXT PRIMARY KEY,
                order_id          TEXT,
                client_oid        TEXT,
                direction         TEXT NOT NULL,
                planned_entry     REAL NOT NULL,
                stop_loss         REAL NOT NULL,
                take_profit       REAL NOT NULL,
                order_created_ms  INTEGER NOT NULL,
                position_ctime    TEXT,
                status            TEXT NOT NULL DEFAULT 'PENDING',
                updated_at        DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS live_risk_state (
                id                INTEGER PRIMARY KEY CHECK (id = 1),
                emergency_stopped INTEGER NOT NULL DEFAULT 0,
                reason            TEXT,
                updated_at        DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO live_risk_state (id, emergency_stopped) VALUES (1, 0)"
        )
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
            SELECT id, entry_price, pnl_pct, size_btc FROM trades
            WHERE trade_type='PAPER' AND result != 'OPEN' AND pnl_pct IS NOT NULL
            ORDER BY id ASC
            """
        ).fetchall()
        for row in rows:
            if row["size_btc"] is not None:
                pnl_amount = (
                    float(row["size_btc"])
                    * float(row["entry_price"])
                    * (float(row["pnl_pct"]) / 100)
                )
            else:
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
    size_btc: Optional[float] = None,
) -> int:
    """새 거래를 열고 trade ID를 반환합니다. trade_type: 'LIVE' | 'PAPER' | 'PLAN'"""
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO trades
            (symbol, trade_type, direction, entry_price, stop_loss, take_profit_1, take_profit_2,
             risk_reward, confidence, long_prob, short_prob, tf_directions, entry_reason, size_btc, result)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN')
            """,
            (
                symbol, trade_type, direction, entry_price, stop_loss, take_profit_1, take_profit_2,
                risk_reward, confidence, long_prob, short_prob,
                json.dumps(tf_directions, ensure_ascii=False),
                entry_reason,
                size_btc,
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


def get_trade(trade_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM trades WHERE id=?", (int(trade_id),)).fetchone()
        return dict(row) if row else None


def get_first_trade_trigger_candle(
    symbol: str,
    entry_timestamp_ms: int,
    direction: str,
    stop_loss: float,
    take_profit_1: float | None = None,
) -> dict | None:
    """진입 후 1분봉에서 TP1 또는 SL을 최초로 건드린 캔들을 반환합니다."""
    direction = str(direction).upper()
    if direction == "LONG":
        trigger_sql = "low <= ? OR (? IS NOT NULL AND high >= ?)"
    else:
        trigger_sql = "high >= ? OR (? IS NOT NULL AND low <= ?)"
    with get_connection() as conn:
        row = conn.execute(
            f"""
            SELECT timestamp, open, high, low, close
            FROM candles
            WHERE symbol=? AND timeframe='1m' AND timestamp >= ?
              AND ({trigger_sql})
            ORDER BY timestamp ASC
            LIMIT 1
            """,
            (symbol, int(entry_timestamp_ms), float(stop_loss), take_profit_1, take_profit_1),
        ).fetchone()
        return dict(row) if row else None


def update_trade_size(trade_id: int, size_btc: float) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE trades SET size_btc=? WHERE id=? AND trade_type='PAPER' AND result='OPEN'",
            (float(size_btc), int(trade_id)),
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


def save_live_execution_state(
    symbol: str,
    order_id: Optional[str],
    client_oid: Optional[str],
    direction: str,
    planned_entry: float,
    stop_loss: float,
    take_profit: float,
    order_created_ms: int,
    status: str = "PENDING",
    position_ctime: Optional[str] = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO live_execution_state
            (symbol, order_id, client_oid, direction, planned_entry, stop_loss,
             take_profit, order_created_ms, position_ctime, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                order_id=excluded.order_id,
                client_oid=excluded.client_oid,
                direction=excluded.direction,
                planned_entry=excluded.planned_entry,
                stop_loss=excluded.stop_loss,
                take_profit=excluded.take_profit,
                order_created_ms=excluded.order_created_ms,
                position_ctime=COALESCE(excluded.position_ctime, live_execution_state.position_ctime),
                status=excluded.status,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                symbol, order_id, client_oid, direction, float(planned_entry),
                float(stop_loss), float(take_profit), int(order_created_ms),
                position_ctime, status,
            ),
        )
        conn.commit()


def get_live_execution_state(symbol: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM live_execution_state WHERE symbol=?",
            (symbol,),
        ).fetchone()
    return dict(row) if row else None


def clear_live_execution_state(symbol: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM live_execution_state WHERE symbol=?", (symbol,))
        conn.commit()


def sync_live_position(
    symbol: str,
    position: dict,
    plan: dict,
    entry_order_id: Optional[str] = None,
) -> dict:
    """거래소의 실제 평균 진입가·수량·수수료를 LIVE 거래 기록에 동기화합니다."""
    direction = str(position.get("holdSide") or plan.get("direction") or "").upper()
    entry_price = float(position.get("openPriceAvg") or plan.get("planned_entry") or 0)
    size_btc = float(position.get("total") or 0)
    entry_fee = abs(float(position.get("deductedFee") or 0))
    position_ctime = str(position.get("cTime") or plan.get("position_ctime") or "")

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM trades
            WHERE symbol=? AND trade_type='LIVE' AND result='OPEN'
            ORDER BY id DESC LIMIT 1
            """,
            (symbol,),
        ).fetchone()
        if row:
            trade_id = int(row["id"])
            conn.execute(
                """
                UPDATE trades SET direction=?, entry_price=?, size_btc=?,
                    stop_loss=?, take_profit_1=?, entry_order_id=?,
                    exchange_position_id=?, entry_fee=?, synced_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (
                    direction, entry_price, size_btc, plan.get("stop_loss"),
                    plan.get("take_profit"),
                    entry_order_id or row["entry_order_id"], position_ctime,
                    entry_fee, trade_id,
                ),
            )
        else:
            cur = conn.execute(
                """
                INSERT INTO trades
                (symbol, trade_type, direction, entry_price, stop_loss, take_profit_1,
                 entry_reason, size_btc, result, entry_order_id, exchange_position_id,
                 entry_fee, synced_at)
                VALUES (?, 'LIVE', ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    symbol, direction, entry_price, plan.get("stop_loss"),
                    plan.get("take_profit"), "거래소 실체결 동기화", size_btc,
                    entry_order_id, position_ctime, entry_fee,
                ),
            )
            trade_id = int(cur.lastrowid)
        conn.commit()
        synced = conn.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
    return dict(synced)


def sync_closed_live_position(symbol: str, history: dict) -> Optional[dict]:
    """거래소 포지션 이력으로 열린 LIVE 거래의 청산 결과를 확정합니다."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM trades
            WHERE symbol=? AND trade_type='LIVE' AND result='OPEN'
            ORDER BY id DESC LIMIT 1
            """,
            (symbol,),
        ).fetchone()
        if not row:
            return None
        trade = dict(row)
        expected_position = str(trade.get("exchange_position_id") or "")
        history_position = str(history.get("ctime") or history.get("positionId") or "")
        if expected_position and history_position and expected_position != history_position:
            return None

        entry = float(history.get("openAvgPrice") or trade["entry_price"])
        exit_price = float(history.get("closeAvgPrice") or 0)
        direction = str(history.get("holdSide") or trade["direction"]).upper()
        pnl_pct = (
            (exit_price - entry) / entry * 100
            if direction == "LONG"
            else (entry - exit_price) / entry * 100
        ) if entry > 0 and exit_price > 0 else 0.0
        net_profit = float(history.get("netProfit") or 0)
        result = "TP1" if net_profit >= 0 else "SL"
        conn.execute(
            """
            UPDATE trades SET entry_price=?, exit_price=?, exit_time=CURRENT_TIMESTAMP,
                result=?, pnl_pct=?, size_btc=?, entry_fee=?, exit_fee=?,
                funding_fee=?, net_profit=?, synced_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (
                entry, exit_price, result, round(pnl_pct, 4),
                float(history.get("openTotalPos") or trade.get("size_btc") or 0),
                abs(float(history.get("openFee") or trade.get("entry_fee") or 0)),
                abs(float(history.get("closeFee") or 0)),
                float(history.get("totalFunding") or 0),
                net_profit, trade["id"],
            ),
        )
        conn.commit()
        synced = conn.execute("SELECT * FROM trades WHERE id=?", (trade["id"],)).fetchone()
    return dict(synced)


def get_live_risk_snapshot() -> dict:
    """실제 LIVE 순손익으로 오늘 손익과 최근 연속 손실 횟수를 반환합니다."""
    with get_connection() as conn:
        today = conn.execute(
            """
            SELECT COALESCE(SUM(net_profit), 0) AS net_profit
            FROM trades
            WHERE trade_type='LIVE'
              AND result != 'OPEN'
              AND date(exit_time, 'localtime') = date('now', 'localtime')
            """
        ).fetchone()
        recent = conn.execute(
            """
            SELECT net_profit FROM trades
            WHERE trade_type='LIVE' AND result != 'OPEN' AND net_profit IS NOT NULL
            ORDER BY exit_time DESC, id DESC
            """
        ).fetchall()
        risk = conn.execute("SELECT * FROM live_risk_state WHERE id=1").fetchone()

    consecutive_losses = 0
    for row in recent:
        if float(row["net_profit"]) < 0:
            consecutive_losses += 1
        else:
            break
    return {
        "today_net_profit": float(today["net_profit"]),
        "consecutive_losses": consecutive_losses,
        "emergency_stopped": bool(risk["emergency_stopped"]) if risk else False,
        "emergency_reason": risk["reason"] if risk else "",
    }


def set_live_emergency_stop(stopped: bool, reason: str = "") -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO live_risk_state (id, emergency_stopped, reason)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                emergency_stopped=excluded.emergency_stopped,
                reason=excluded.reason,
                updated_at=CURRENT_TIMESTAMP
            """,
            (1 if stopped else 0, reason),
        )
        conn.commit()


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
             risk_reward_ratio, all_time_high_mode, all_time_low_mode, market_regime,
             strategy_signal, entry_grade, diagnostics_json, block_reason, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, timeframe, timestamp) DO UPDATE SET
                entry_price=excluded.entry_price,
                direction=excluded.direction,
                long_probability=excluded.long_probability,
                short_probability=excluded.short_probability,
                confidence=excluded.confidence,
                stop_loss=excluded.stop_loss,
                take_profit_1=excluded.take_profit_1,
                take_profit_2=excluded.take_profit_2,
                risk_reward_ratio=excluded.risk_reward_ratio,
                all_time_high_mode=excluded.all_time_high_mode,
                all_time_low_mode=excluded.all_time_low_mode,
                market_regime=excluded.market_regime,
                strategy_signal=excluded.strategy_signal,
                entry_grade=excluded.entry_grade,
                diagnostics_json=excluded.diagnostics_json,
                block_reason=excluded.block_reason,
                reason=excluded.reason,
                created_at=CURRENT_TIMESTAMP
            WHERE signals.direction NOT IN ('LONG', 'SHORT')
               OR (
                    excluded.direction IN ('LONG', 'SHORT')
                    AND (
                        CASE UPPER(COALESCE(excluded.entry_grade, ''))
                            WHEN 'A' THEN 4
                            WHEN 'B' THEN 3
                            WHEN 'C' THEN 2
                            WHEN 'F' THEN 1
                            ELSE 0
                        END
                        >
                        CASE UPPER(COALESCE(signals.entry_grade, ''))
                            WHEN 'A' THEN 4
                            WHEN 'B' THEN 3
                            WHEN 'C' THEN 2
                            WHEN 'F' THEN 1
                            ELSE 0
                        END
                        OR (
                            UPPER(COALESCE(excluded.entry_grade, ''))
                                = UPPER(COALESCE(signals.entry_grade, ''))
                            AND COALESCE(excluded.confidence, 0)
                                >= COALESCE(signals.confidence, 0)
                        )
                    )
               )
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
                result.get("market_mode"),
                result.get("strategy_signal"),
                result.get("entry_grade"),
                json.dumps(result.get("diagnostics") or {}, ensure_ascii=False),
                "\n".join(result.get("block_reasons") or []),
                "\n".join(result.get("reasons", [])),
            ),
        )
        conn.commit()
