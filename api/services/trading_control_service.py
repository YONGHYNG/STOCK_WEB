# 역할: 자동매매 시작, 중지, 새로고침을 제어하는 서비스.
import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import WebSocket, WebSocketDisconnect

from backend.strategy.multi_timeframe_strategy import TradingAIEngine
from backend.strategy.backtester import Backtester, BacktestConfig
from backend.bitget.market_api import BitgetClient
from backend.bitget.client import BitgetPrivateClient
import backend.credentials as creds_store
from backend.order.paper_trader import PaperTrader
from backend.notifications import gmail_is_configured, send_trade_event_email
from backend.power_keepawake import keep_awake
from backend.risk.risk_manager import RiskManager
import backend.risk.settings as risk_settings_store
from backend.risk.settings import RiskSettings
from backend.trading_modes import TradingMode
from backend.config import (
    DEFAULT_TIMEFRAME,
    INITIAL_CANDLE_LIMIT,
    RECENT_CANDLE_LIMIT_BY_TIMEFRAME,
    REFRESH_CANDLE_LIMIT,
    REFRESH_INTERVAL_MS,
    SYMBOL,
    MAKER_FEE_RATE,
    TAKER_FEE_RATE,
    TIMEFRAMES,
    USE_DEMO_DATA,
)
from backend.database import (
    close_trade,
    get_all_time_high,
    get_all_time_low,
    get_open_trade,
    get_first_trade_trigger_candle,
    get_trade,
    get_paper_account,
    get_recent_candles,
    get_recent_trades,
    insert_candles,
    insert_signal,
    get_scheduled_entry_session,
    record_scheduled_entry_session,
    open_trade,
    purge_unaligned_candles,
)
from backend.scheduled_entries import (
    SCHEDULED_SPLIT_ENTRY_BEFORE_END_SECONDS,
    active_scheduled_session,
    build_forced_entry_result,
    choose_consensus_direction,
    reprice_scheduled_result,
    seconds_until_session_end,
)
from backend.server_state import state
from api.schemas.trading_schema import (
    AutoTradePayload,
    BacktestPayload,
    CredentialsPayload,
    ModePayload,
    OrderPayload,
    PaperPendingOrderPayload,
    RiskSettingsPayload,
)

# ── Singletons ─────────────────────────────────────────────────────────────────

clients = {tf: BitgetClient(timeframe=tf, demo_mode=USE_DEMO_DATA) for tf in TIMEFRAMES}
engine = TradingAIEngine()
executor = ThreadPoolExecutor(max_workers=8)
paper_trader = PaperTrader()
risk_cfg = risk_settings_store.load()
risk_mgr = RiskManager(risk_cfg)
PAPER_ACCOUNT_INITIAL_BALANCE = 100.0
PAPER_ACCOUNT_LEVERAGE = 20
PENDING_ORDER_TTL_SECONDS = 10 * 60
RANGE_PENDING_ORDER_TTL_SECONDS = 10 * 60
PENDING_CANCEL_RETRY_SECONDS = 60
SCHEDULED_ANALYSIS_INTERVAL_SECONDS = 20
SCHEDULED_STABLE_SIGNAL_SAMPLES = 3
SCHEDULED_REQUIRED_MATCHING_SAMPLES = 2
SCHEDULED_FORCE_ENTRY_BEFORE_END_SECONDS = 60
KST = ZoneInfo("Asia/Seoul")
_scheduled_analysis_runs: dict[str, dict] = {}


def _automatic_loss_analysis(trade_id: Optional[int], elapsed_seconds: Optional[int] = None) -> str:
    """거래 당시 기록만으로 재현 가능한 짧은 손실 원인 요약을 만듭니다."""
    if not risk_cfg.auto_stop_loss_analysis or not trade_id:
        return ""
    row = get_trade(trade_id) or {}
    try:
        directions = json.loads(row.get("tf_directions") or "{}")
    except (TypeError, json.JSONDecodeError):
        directions = {}
    direction = str(row.get("direction") or "").upper()
    weak_frames = [tf for tf in ("5m", "1H", "4H", "6H") if directions.get(tf) in (None, "HOLD")]
    opposite_frames = [tf for tf, value in directions.items() if value not in (direction, "HOLD", None)]
    reasons = str(row.get("entry_reason") or "")
    signal = next((line.split(":", 1)[1].strip() for line in reasons.splitlines() if line.startswith("전략 신호:")), "미분류")
    parts = [f"자동 손실 분석: {signal}"]
    if weak_frames:
        parts.append(f"상위/핵심 시간대 미확정({', '.join(weak_frames)} HOLD)")
    if opposite_frames:
        parts.append(f"반대 방향 시간대 존재({', '.join(opposite_frames)})")
    if "조기 진입" in reasons:
        parts.append("장세 전환 확정 전 조기 진입")
    if elapsed_seconds is not None and elapsed_seconds <= 300:
        parts.append(f"진입 후 {max(1, elapsed_seconds)}초 내 손절로 반대 모멘텀 즉시 발생")
    return " · ".join(parts)


def _append_loss_analysis(base: str, trade_id: Optional[int], elapsed_seconds: Optional[int] = None) -> str:
    analysis = _automatic_loss_analysis(trade_id, elapsed_seconds)
    return f"{base}\n{analysis}" if analysis else base


def _entry_timestamp_ms(row: dict) -> int:
    entered = datetime.strptime(str(row["entry_time"]), "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
    return int(entered.timestamp() * 1000)


def _elapsed_since_entry(row: dict, timestamp_ms: Optional[int] = None) -> int:
    end_ms = int(timestamp_ms if timestamp_ms is not None else time.time() * 1000)
    return max(0, int((end_ms - _entry_timestamp_ms(row)) / 1000))


def _paper_full_leverage_size(entry_price: float) -> float:
    """현재 모의 잔액 전부를 고정 20배 명목금액으로 환산한 BTC 수량."""
    entry = float(entry_price or 0)
    if entry <= 0:
        return 0.0
    account = get_paper_account(PAPER_ACCOUNT_INITIAL_BALANCE, PAPER_ACCOUNT_LEVERAGE)
    notional = max(0.0, float(account["balance"])) * PAPER_ACCOUNT_LEVERAGE
    return round(notional / entry, 8)


def _is_range_result(result: Optional[dict]) -> bool:
    result = result or {}
    return (
        result.get("market_mode") == "RANGE"
        or "RANGE_REVERSION" in str(result.get("strategy_signal") or "")
    )


def _pending_result(pending: Optional[dict]) -> dict:
    return dict((pending or {}).get("result") or {})


def _pending_order_timestamps(
    now: Optional[float] = None,
    result: Optional[dict] = None,
) -> dict:
    created_at = float(now if now is not None else time.time())
    ttl = (
        RANGE_PENDING_ORDER_TTL_SECONDS
        if _is_range_result(result)
        else PENDING_ORDER_TTL_SECONDS
    )
    return {
        "created_at": created_at,
        "expires_at": created_at + ttl,
    }


def _make_private_client() -> Optional[BitgetPrivateClient]:
    c = creds_store.load()
    if c.is_set():
        return BitgetPrivateClient(c.api_key, c.secret_key, c.passphrase)
    return None


private_client: Optional[BitgetPrivateClient] = _make_private_client()

# ── WebSocket manager ──────────────────────────────────────────────────────────


class ConnectionManager:
    def __init__(self):
        self._connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.add(ws)

    def disconnect(self, ws: WebSocket):
        self._connections.discard(ws)

    async def broadcast(self, data: dict):
        dead = set()
        for ws in self._connections.copy():
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)
        self._connections -= dead


manager = ConnectionManager()

# ── Background thread workers ──────────────────────────────────────────────────


def _worker_seed() -> list[str]:
    logs = []
    if not USE_DEMO_DATA:
        for tf in TIMEFRAMES:
            n = purge_unaligned_candles(SYMBOL, tf)
            if n:
                logs.append(f"{tf}: 비정렬 캔들 {n}개 제거")

    fetch_limits = {}
    for tf in TIMEFRAMES:
        required = RECENT_CANDLE_LIMIT_BY_TIMEFRAME.get(tf, INITIAL_CANDLE_LIMIT)
        if len(get_recent_candles(SYMBOL, tf, required)) >= required:
            continue
        fetch_limits[tf] = required

    if fetch_limits:
        fmap = {
            executor.submit(clients[tf].fetch_recent_or_demo, lim): tf
            for tf, lim in fetch_limits.items()
        }
        for future in as_completed(fmap):
            tf = fmap[future]
            try:
                candles, err = future.result()
            except Exception as exc:
                candles, err = [], str(exc)
            if candles:
                insert_candles(SYMBOL, tf, candles)
                logs.append(f"{tf}: {len(candles)}개 초기 저장")
            else:
                logs.append(f"{tf}: 로드 실패 — {err}")
    return logs


def _worker_analyze() -> tuple[Optional[dict], list[str]]:
    errors = []
    fmap = {
        executor.submit(clients[tf].fetch_recent_or_demo, REFRESH_CANDLE_LIMIT): tf
        for tf in TIMEFRAMES
    }
    for future in as_completed(fmap):
        tf = fmap[future]
        try:
            candles, err = future.result()
        except Exception as exc:
            candles, err = [], str(exc)
        if candles:
            insert_candles(SYMBOL, tf, candles)
        elif err:
            errors.append(f"{tf}: {err}")

    candles_by_tf = {
        tf: get_recent_candles(SYMBOL, tf, RECENT_CANDLE_LIMIT_BY_TIMEFRAME.get(tf, INITIAL_CANDLE_LIMIT))
        for tf in TIMEFRAMES
    }
    usable = {tf: c for tf, c in candles_by_tf.items() if c}
    if not usable:
        return None, errors

    ath = get_all_time_high(SYMBOL, DEFAULT_TIMEFRAME)
    atl = get_all_time_low(SYMBOL, DEFAULT_TIMEFRAME)
    market = None
    try:
        market = clients["5m"].fetch_market_snapshot().to_dict()
    except Exception as exc:
        errors.append(f"market: {exc}")
        # OI/호가 같은 보조 데이터 실패는 캔들 분석 전체를 중단하지 않는다.
        market = {"last_price": float((usable.get("5m") or usable[next(iter(usable))])[-1]["close"])}
    result = engine.analyze_multi_timeframe(
        usable,
        all_time_high=ath,
        all_time_low=atl,
        market=market,
        account_equity=_analysis_account_equity(),
    ).to_dict()
    insert_signal(SYMBOL, DEFAULT_TIMEFRAME, result)
    return result, errors


def _worker_price() -> Optional[float]:
    try:
        snap = clients["5m"].fetch_market_snapshot()
        state.last_result = {**state.last_result, **snap.to_dict()} if state.last_result else state.last_result
        return snap.last_price or snap.mark_price
    except Exception:
        return None


def _worker_account() -> tuple[Optional[dict], object]:
    if not private_client:
        return None, []
    try:
        acct = private_client.get_account()
        pos = private_client.get_positions()
        return acct, pos
    except Exception as exc:
        return None, str(exc)


def _account_equity_from_cache() -> Optional[float]:
    account = getattr(state, "cached_account", None)
    if not isinstance(account, dict):
        return None
    for key in ("accountEquity", "equity", "usdtEquity", "available"):
        value = account.get(key)
        try:
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _analysis_account_equity() -> Optional[float]:
    if state.trading_mode == "PAPER_TRADING":
        try:
            return float(get_paper_account(PAPER_ACCOUNT_INITIAL_BALANCE, PAPER_ACCOUNT_LEVERAGE)["balance"])
        except Exception:
            return PAPER_ACCOUNT_INITIAL_BALANCE
    return _account_equity_from_cache()


def _paper_position_payload() -> Optional[dict]:
    if not paper_trader.is_open or not paper_trader.open_data:
        paper_trader.restore_from_db()
    if not paper_trader.is_open or not paper_trader.open_data:
        return None
    data = paper_trader.open_data
    row = get_open_trade(SYMBOL, trade_type="PAPER")
    entry = float(data.get("entry") or 0)
    current = float(state.last_price or entry or 0)
    direction = data.get("direction")
    gross_pnl_pct = 0.0
    if entry > 0 and current > 0:
        gross_pnl_pct = (
            (current - entry) / entry * 100
            if direction == "LONG"
            else (entry - current) / entry * 100
        )
    fee_pct = float(MAKER_FEE_RATE) * 2 * 100
    net_pnl_pct = gross_pnl_pct - fee_pct
    return {
        "id": paper_trader.open_id,
        "symbol": SYMBOL,
        "trade_type": "PAPER",
        "direction": direction,
        "entry_price": entry,
        "current_price": current,
        "stop_loss": data.get("sl"),
        "take_profit_1": data.get("tp1"),
        "take_profit_2": data.get("tp2"),
        "gross_pnl_pct": gross_pnl_pct,
        "fee_pct": fee_pct,
        "pnl_pct": net_pnl_pct,
        "size_btc": data.get("size") or risk_cfg.order_size_btc,
        "entry_reason": row.get("entry_reason") if row else "",
    }


def _ensure_paper_account_start_id() -> Optional[int]:
    if state.paper_account_start_trade_id is not None:
        return state.paper_account_start_trade_id
    open_row = get_open_trade(SYMBOL, trade_type="PAPER")
    if open_row:
        state.paper_account_start_trade_id = int(open_row["id"])
        return state.paper_account_start_trade_id
    paper_trades = [t for t in get_recent_trades(SYMBOL, limit=None, trade_type="PAPER") if t.get("id") is not None]
    if paper_trades:
        state.paper_account_start_trade_id = max(int(t["id"]) for t in paper_trades) + 1
    else:
        state.paper_account_start_trade_id = 1
    return state.paper_account_start_trade_id


def _recent_consecutive_paper_losses() -> int:
    """Restore the current PAPER loss streak from newest closed trades."""
    count = 0
    for trade in get_recent_trades(SYMBOL, limit=None, trade_type="PAPER"):
        if trade.get("result") == "OPEN" or trade.get("pnl_pct") is None:
            continue
        try:
            pnl_pct = float(trade["pnl_pct"])
        except (TypeError, ValueError):
            continue
        if pnl_pct < 0:
            count += 1
        else:
            break
    return count


def _paper_account_payload() -> dict:
    account = get_paper_account(PAPER_ACCOUNT_INITIAL_BALANCE, PAPER_ACCOUNT_LEVERAGE)
    initial_balance = float(account["initial_balance"])
    balance = float(account["balance"])
    leverage = float(account["leverage"])
    realized_pnl = balance - initial_balance
    paper_position = _paper_position_payload()
    unrealized_pnl = 0.0
    if paper_position:
        position_notional = (
            float(paper_position.get("size_btc") or 0)
            * float(paper_position.get("entry_price") or 0)
        )
        unrealized_pnl = position_notional * (float(paper_position.get("pnl_pct") or 0) / 100)
        unrealized_pnl = max(unrealized_pnl, -balance)
    equity = balance + unrealized_pnl
    return {
        "initial_balance": initial_balance,
        "balance": balance,
        "leverage": leverage,
        "notional": balance * leverage,
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized_pnl,
        "equity": equity,
        "return_pct": ((equity - initial_balance) / initial_balance * 100) if initial_balance else 0.0,
    }


# ── TP/SL checks ───────────────────────────────────────────────────────────────


def _trade_data_from_row(row: dict) -> dict:
    return {
        "direction": row["direction"],
        "entry": row["entry_price"],
        "sl": row["stop_loss"],
        "tp1": row["take_profit_1"],
        "tp2": row["take_profit_2"],
        "size": row.get("size_btc"),
    }


def _trade_data_from_signal(result: dict) -> dict:
    return {
        "direction": result["direction"],
        "entry": result["entry_price"],
        "sl": result.get("stop_loss"),
        "tp1": result.get("take_profit_1"),
        "tp2": result.get("take_profit_2"),
        "size": result.get("position_size_btc"),
    }


def _plan_signature(result: dict) -> tuple:
    return (
        int(result.get("timestamp") or 0),
        result.get("direction"),
        round(float(result.get("entry_price") or 0), 2),
        round(float(result.get("stop_loss") or 0), 2),
        round(float(result.get("take_profit_1") or 0), 2),
        round(float(result.get("take_profit_2") or 0), 2),
    )


def _tp_sl_result(t: dict, price: float) -> Optional[str]:
    direction = t["direction"]
    sl, tp1 = t.get("sl"), t.get("tp1")

    if direction == "LONG":
        if tp1 and price >= tp1:
            return "TP1"
        if sl and price <= sl:
            return "SL"
    elif direction == "SHORT":
        if tp1 and price <= tp1:
            return "TP1"
        if sl and price >= sl:
            return "SL"
    return None


def _pnl_pct(direction: str, entry: float, exit_price: float, exit_fee_rate: float = MAKER_FEE_RATE) -> float:
    gross = (exit_price - entry) / entry * 100 if direction == "LONG" else (entry - exit_price) / entry * 100
    return gross - (float(MAKER_FEE_RATE) + float(exit_fee_rate)) * 100


async def _ensure_signal_plan(result: dict):
    direction = result.get("direction", "HOLD")
    if direction not in ("LONG", "SHORT"):
        return
    required = ("entry_price", "stop_loss", "take_profit_1")
    if any(result.get(k) in (None, 0) for k in required):
        return
    signature = _plan_signature(result)
    if state.plan_signature == signature and not state.plan_trade_id:
        return
    if state.plan_trade_id and state.plan_trade_data:
        return

    existing = get_open_trade(SYMBOL, trade_type="PLAN")
    if existing:
        state.plan_trade_id = existing["id"]
        state.plan_trade_data = _trade_data_from_row(existing)
        state.plan_signature = signature
        return

    trade_id = open_trade(
        symbol=SYMBOL,
        direction=direction,
        entry_price=result["entry_price"],
        stop_loss=result.get("stop_loss"),
        take_profit_1=result.get("take_profit_1"),
        take_profit_2=result.get("take_profit_2"),
        risk_reward=result.get("risk_reward_ratio"),
        confidence=result.get("confidence", 0),
        long_prob=result.get("long_probability", 50),
        short_prob=result.get("short_probability", 50),
        tf_directions=result.get("timeframe_directions", {}),
        entry_reason="\n".join(result.get("reasons", [])),
        trade_type="PLAN",
    )
    state.plan_trade_id = trade_id
    state.plan_trade_data = _trade_data_from_signal(result)
    state.plan_signature = signature
    msg = state.add_log(
        f"[리스크 플랜] {direction} 계획 기록 #{trade_id}  "
        f"진입=${result['entry_price']:,.2f}  SL=${result.get('stop_loss'):,.2f}  TP1=${result.get('take_profit_1'):,.2f}"
    )
    await manager.broadcast({"type": "log", "data": {"message": msg}})
    await manager.broadcast({"type": "trade_update"})


async def _check_plan_tp_sl(price: float):
    t = state.plan_trade_data
    if not t:
        return

    result_code = _tp_sl_result(t, price)
    if not result_code:
        return

    entry = t["entry"]
    direction = t["direction"]
    pnl_pct = _pnl_pct(direction, entry, price)
    sign = "+" if pnl_pct >= 0 else ""
    profit_reason = (
        f"[리스크 플랜] {result_code} 적중: 진입 ${entry:,.2f} → 확인가 ${price:,.2f}  ({sign}{pnl_pct:.2f}%)"
        if result_code.startswith("TP") else ""
    )
    loss_reason = (
        f"[리스크 플랜] 손절 확인: 진입 ${entry:,.2f} → 확인가 ${price:,.2f}  ({sign}{pnl_pct:.2f}%)"
        if result_code == "SL" else ""
    )

    if result_code == "SL":
        row = get_trade(state.plan_trade_id) or {}
        loss_reason = _append_loss_analysis(loss_reason, state.plan_trade_id, _elapsed_since_entry(row) if row else None)

    tid = state.plan_trade_id
    close_trade(
        trade_id=tid,
        exit_price=price,
        result=result_code,
        pnl_pct=pnl_pct,
        profit_reason=profit_reason,
        loss_reason=loss_reason,
    )
    label = "익절" if result_code.startswith("TP") else "손실"
    msg = state.add_log(f"[리스크 플랜 {label}] #{tid}  {result_code}  {sign}{pnl_pct:.2f}%")
    state.plan_trade_id = None
    state.plan_trade_data = None
    await manager.broadcast({"type": "log", "data": {"message": msg}})
    await manager.broadcast({"type": "trade_update"})


async def _check_tp_sl(price: float):
    t = state.open_trade_data
    direction = t["direction"]
    entry = t["entry"]
    result_code = _tp_sl_result(t, price)

    if not result_code:
        return

    pnl_pct = _pnl_pct(direction, entry, price)
    sign = "+" if pnl_pct >= 0 else ""
    profit_reason = f"{result_code} 적중: 진입 ${entry:,.2f} → 청산 ${price:,.2f}  ({sign}{pnl_pct:.2f}%)" if result_code.startswith("TP") else ""
    loss_reason = f"손절 발동: 진입 ${entry:,.2f} → 청산 ${price:,.2f}  ({sign}{pnl_pct:.2f}%)" if result_code == "SL" else ""

    if result_code == "SL":
        row = get_trade(state.open_trade_id) or {}
        loss_reason = _append_loss_analysis(loss_reason, state.open_trade_id, _elapsed_since_entry(row) if row else None)

    tid = state.open_trade_id
    close_trade(trade_id=tid, exit_price=price, result=result_code, pnl_pct=pnl_pct,
                profit_reason=profit_reason, loss_reason=loss_reason)
    emoji = "익절" if result_code.startswith("TP") else "손절"
    msg = state.add_log(f"[{emoji}] TRADE #{tid}  {result_code}  {sign}{pnl_pct:.2f}%")
    state.open_trade_id = None
    state.open_trade_data = None
    await manager.broadcast({"type": "log", "data": {"message": msg}})
    await manager.broadcast({"type": "trade_update"})
    await _send_trade_event_notification(
        result_code,
        {
            "direction": direction,
            "entry_price": entry,
            "stop_loss": t.get("sl"),
            "take_profit_1": t.get("tp1"),
            "take_profit_2": t.get("tp2"),
            "exit_price": price,
            "pnl_pct": pnl_pct,
        },
        "LIVE",
    )


async def _check_paper_tp_sl(price: float):
    result_code = paper_trader.check_tp_sl(price)
    if not result_code:
        return
    t = paper_trader.open_data
    entry, direction = t["entry"], t["direction"]
    limit_exit_price = (
        float(t.get("tp1")) if result_code == "TP1"
        else float(t.get("sl"))
    )
    pnl_pct = _pnl_pct(direction, entry, limit_exit_price)
    sign = "+" if pnl_pct >= 0 else ""
    profit_reason = f"[모의 지정가] {result_code} 체결: ${entry:,.2f} → ${limit_exit_price:,.2f}  ({sign}{pnl_pct:.2f}%)" if result_code.startswith("TP") else ""
    loss_reason = f"[모의 지정가] 손절 체결: ${entry:,.2f} → ${limit_exit_price:,.2f}  ({sign}{pnl_pct:.2f}%)" if result_code == "SL" else ""
    if result_code == "SL":
        row = get_trade(paper_trader.open_id) or {}
        loss_reason = _append_loss_analysis(loss_reason, paper_trader.open_id, _elapsed_since_entry(row) if row else None)
    tid, pnl = paper_trader.close_trade(exit_price=limit_exit_price, result=result_code,
                                        profit_reason=profit_reason, loss_reason=loss_reason)
    await _cancel_scheduled_scale_in_after_exit(tid, result_code)
    risk_mgr.record_trade_result(pnl, result_code)
    if (
        state.trading_mode != "PAPER_TRADING"
        and risk_mgr.consecutive_losses >= risk_cfg.consecutive_loss_limit
    ):
        await _activate_consecutive_loss_stop()
    emoji = "익절" if result_code.startswith("TP") else "손절"
    msg = state.add_log(f"[모의매매 {emoji}] #{tid}  {result_code}  {sign}{pnl:.2f}%")
    await manager.broadcast({"type": "log", "data": {"message": msg}})
    await manager.broadcast({"type": "trade_update"})
    await manager.broadcast({"type": "status", "data": _status_payload()})
    await _send_trade_event_notification(
        result_code,
        {
            "direction": direction,
            "entry_price": entry,
            "stop_loss": t.get("sl"),
            "take_profit_1": t.get("tp1"),
            "take_profit_2": t.get("tp2"),
            "exit_price": limit_exit_price,
            "pnl_pct": pnl,
            "position_size_btc": t.get("size"),
            "position_size_percent": t.get("position_size_percent", 100),
        },
        "PAPER",
    )


async def _check_paper_scalp_time_exit(price: float) -> bool:
    """고정 세션 단타가 진행되지 않거나 45분을 넘기면 시장가로 정리한다."""
    if not paper_trader.is_open or not paper_trader.open_data:
        return False
    trade_id = paper_trader.open_id
    row = get_trade(trade_id) or {}
    if "고정 진입 세션" not in str(row.get("entry_reason") or ""):
        return False
    elapsed = _elapsed_since_entry(row)
    t = paper_trader.open_data
    stop_gap = abs(float(t.get("entry") or 0) - float(t.get("sl") or 0))
    current_favorable = (
        float(price) - float(t.get("entry") or 0)
        if t.get("direction") == "LONG"
        else float(t.get("entry") or 0) - float(price)
    )
    max_favorable = max(float(t.get("max_favorable_move") or 0), current_favorable)
    t["max_favorable_move"] = max_favorable
    no_progress_seconds = int(t.get("scalp_no_progress_seconds") or 15 * 60)
    max_hold_seconds = int(t.get("scalp_max_hold_seconds") or 45 * 60)
    min_progress = stop_gap * float(t.get("scalp_min_progress_ratio") or 0.3)
    reason = None
    if elapsed >= max_hold_seconds:
        reason = f"단타 최대 보유 {max_hold_seconds // 60}분 도달"
    elif elapsed >= no_progress_seconds and max_favorable < min_progress:
        reason = f"{no_progress_seconds // 60}분 동안 +0.3R 진행 없음"
    if not reason:
        return False
    tid, pnl = paper_trader.close_trade(
        exit_price=price,
        result="TIME_EXIT",
        profit_reason=f"[단타 시간청산] {reason}" if _pnl_pct(t["direction"], t["entry"], price) >= 0 else "",
        loss_reason=f"[단타 시간청산] {reason}" if _pnl_pct(t["direction"], t["entry"], price) < 0 else "",
        exit_fee_rate=TAKER_FEE_RATE,
    )
    await _cancel_scheduled_scale_in_after_exit(tid, "TIME_EXIT")
    risk_mgr.record_trade_result(pnl, "TIME_EXIT")
    msg = state.add_log(f"[모의매매 시간청산] #{tid} {pnl:+.2f}% · {reason}")
    await manager.broadcast({"type": "log", "data": {"message": msg}})
    await manager.broadcast({"type": "trade_update"})
    await manager.broadcast({"type": "status", "data": _status_payload()})
    return True


# ── Auto trade ─────────────────────────────────────────────────────────────────


async def _check_auto_trade(result: dict):
    if not state.auto_trade_enabled:
        return
    if state.trading_mode == "SIGNAL_ONLY":
        return
    # 고정 세션 중에는 15초 일반 루프가 먼저 진입하지 않도록 하고,
    # 1분 단위 다회 분석을 수행하는 scheduled_entry_loop에 진입 결정을 맡긴다.
    if active_scheduled_session():
        return

    direction = result.get("direction", "HOLD")
    confidence = result.get("confidence", 0.0)
    mode = TradingMode(state.trading_mode)

    if (
        state.trading_mode != "PAPER_TRADING"
        and risk_mgr.consecutive_losses >= risk_cfg.consecutive_loss_limit
    ):
        if state.pending_paper_order or state.pending_live_order:
            await _cancel_pending_for_risk(
                f"연속 손실 {risk_mgr.consecutive_losses}회로 신규 대기 주문 취소"
            )
        return

    pending = (
        state.pending_paper_order
        if state.trading_mode == "PAPER_TRADING"
        else state.pending_live_order
        if state.trading_mode == "LIVE_TRADING"
        else None
    )
    if pending:
        pending_direction = str(pending.get("direction") or "HOLD")
        pending_is_range = _is_range_result(_pending_result(pending))
        opposite_signal = (
            _is_order_eligible(result)
            and direction in ("LONG", "SHORT")
            and direction != pending_direction
        )
        range_ended = pending_is_range and result.get("market_mode") != "RANGE"
        if opposite_signal or range_ended:
            reason = (
                f"반대 방향 {direction} 확정 신호"
                if opposite_signal
                else "ADX·밴드 조건 이탈로 횡보장 종료"
            )
            cancelled = await _cancel_pending_order(reason)
            if not cancelled or direction not in ("LONG", "SHORT"):
                return
        elif state.trading_mode == "PAPER_TRADING":
            await _refresh_pending_paper_order(direction, result)
            return
        else:
            await _refresh_pending_live_order(direction, result)
            return

    allowed, reason = risk_mgr.check_entry(
        direction=direction, confidence=confidence, mode=mode,
        cached_positions=state.cached_positions, private_client=private_client,
        entry_price=result.get("entry_price"), stop_loss=result.get("stop_loss"),
        entry_grade=result.get("entry_grade"), risk_warnings=result.get("risk_warnings", []),
        strategy_signal=result.get("strategy_signal"),
        timeframe_directions=result.get("timeframe_directions", {}),
    )
    if not allowed:
        if reason and "이미" not in reason:
            msg = state.add_log(f"[자동매매 차단] {reason}")
            await manager.broadcast({"type": "log", "data": {"message": msg}})
        return

    if state.trading_mode == "PAPER_TRADING":
        created = await _auto_paper_trade(direction, result)
    elif state.trading_mode == "LIVE_TRADING":
        created = await _auto_live_trade(direction, result)
    else:
        created = False
    if created:
        engine.consume_signal(direction, int(result.get("timestamp") or 0))


async def _cancel_pending_for_risk(reason: str):
    if private_client and state.pending_live_order_id and state.pending_live_order_id != "pending":
        try:
            await asyncio.to_thread(private_client.cancel_order, state.pending_live_order_id)
        except Exception as exc:
            msg = state.add_log(f"[자동매매 차단] LIVE 대기 주문 취소 실패: {exc}")
            await manager.broadcast({"type": "log", "data": {"message": msg}})
            return
    state.pending_paper_order = None
    state.pending_live_order_id = None
    state.pending_live_order = None
    state.auto_trade_enabled = False
    keep_awake.disable()
    msg = state.add_log(f"[자동매매 차단] {reason} · 자동매매 OFF")
    await manager.broadcast({"type": "log", "data": {"message": msg}})
    await manager.broadcast({"type": "status", "data": _status_payload()})


async def _cancel_pending_order(reason: str) -> bool:
    """자동매매는 유지하면서 현재 미체결 지정가만 취소합니다."""
    mode = "PAPER" if state.pending_paper_order else "LIVE"
    if mode == "LIVE":
        order_id = str(state.pending_live_order_id or "")
        if order_id and order_id != "pending":
            if not private_client:
                msg = state.add_log(f"[LIVE 대기 주문 취소 실패] API 연결 없음 · {reason}")
                await manager.broadcast({"type": "log", "data": {"message": msg}})
                return False
            try:
                await asyncio.to_thread(private_client.cancel_order, order_id)
            except Exception as exc:
                msg = state.add_log(f"[LIVE 대기 주문 취소 실패] {reason}: {exc}")
                await manager.broadcast({"type": "log", "data": {"message": msg}})
                return False
        state.pending_live_order_id = None
        state.pending_live_order = None
    else:
        state.pending_paper_order = None

    msg = state.add_log(f"[{mode} 대기 주문 취소] {reason}")
    await manager.broadcast({"type": "log", "data": {"message": msg}})
    await manager.broadcast({"type": "status", "data": _status_payload()})
    return True


def _is_better_entry(direction: str, current_entry, new_entry) -> bool:
    try:
        current_price = float(current_entry)
        new_price = float(new_entry)
    except (TypeError, ValueError):
        return False
    if direction == "LONG":
        return new_price < current_price
    if direction == "SHORT":
        return new_price > current_price
    return False


def _is_order_eligible(result: dict) -> bool:
    return (
        result.get("direction") in ("LONG", "SHORT")
        and result.get("entry_grade") in ("A", "B")
        and float(result.get("confidence") or 0) >= risk_cfg.confidence_threshold
        and not result.get("risk_warnings")
    )


async def _refresh_pending_paper_order(direction: str, result: dict):
    pending = state.pending_paper_order
    if not pending or direction != pending.get("direction") or not _is_order_eligible(result):
        return
    previous = pending.get("result") or {}
    better_entry = _is_better_entry(direction, previous.get("entry_price"), result.get("entry_price"))
    if not better_entry:
        return

    old_entry = float(previous.get("entry_price") or 0)
    new_entry = float(result.get("entry_price") or 0)
    if old_entry == new_entry:
        return
    paper_result = dict(result)
    paper_result["position_size_btc"] = _paper_full_leverage_size(new_entry)
    state.pending_paper_order = {
        "direction": direction,
        "result": paper_result,
        "created_at": pending.get("created_at"),
        "expires_at": pending.get("expires_at"),
    }
    msg = state.add_log(
        f"[모의 대기 주문 개선] {direction} ${old_entry:,.2f} → ${new_entry:,.2f}  "
        "진입 조건 개선, 손절·익절 조건도 최신 신호로 갱신"
    )
    await manager.broadcast({"type": "log", "data": {"message": msg}})
    await manager.broadcast({"type": "status", "data": _status_payload()})
    await _send_trade_event_notification("PENDING", result, "PAPER")


async def _refresh_pending_live_order(direction: str, result: dict):
    pending = state.pending_live_order
    if (
        not private_client
        or not pending
        or direction != pending.get("direction")
        or not _is_order_eligible(result)
    ):
        return
    better_entry = _is_better_entry(direction, pending.get("entry_price"), result.get("entry_price"))
    if not better_entry:
        return

    old_order_id = str(pending.get("order_id") or "")
    old_entry = float(pending.get("entry_price") or 0)
    new_entry = float(result.get("entry_price") or 0)
    original_created_at = pending.get("created_at")
    original_expires_at = pending.get("expires_at")
    if old_entry == new_entry:
        return
    if not old_order_id or old_order_id == "pending":
        return
    try:
        await asyncio.to_thread(private_client.cancel_order, old_order_id)
        state.pending_live_order_id = None
        state.pending_live_order = None
        await _auto_live_trade(direction, result)
        if state.pending_live_order:
            state.pending_live_order["created_at"] = original_created_at
            state.pending_live_order["expires_at"] = original_expires_at
            msg = state.add_log(
                f"[LIVE 대기 주문 개선] {direction} ${old_entry:,.2f} → ${new_entry:,.2f}  진입 조건 개선"
            )
        else:
            msg = state.add_log("[LIVE 대기 주문 갱신 실패] 기존 주문 취소 후 새 주문 생성 실패")
    except Exception as exc:
        msg = state.add_log(f"[LIVE 대기 주문 갱신 실패] 기존 주문 유지: {exc}")
    await manager.broadcast({"type": "log", "data": {"message": msg}})
    await manager.broadcast({"type": "status", "data": _status_payload()})


async def _auto_paper_trade(direction: str, r: dict):
    if paper_trader.is_open or state.pending_paper_order:
        return False

    paper_result = dict(r)
    paper_result["position_size_btc"] = _paper_full_leverage_size(
        float(paper_result.get("entry_price") or 0)
    )
    state.pending_paper_order = {
        "direction": direction,
        "result": paper_result,
        **_pending_order_timestamps(result=paper_result),
    }
    risk_mgr.record_order_placed()
    msg = state.add_log(
        f"[모의 지정가 대기] {direction} ${float(r.get('entry_price') or 0):,.2f}  "
        f"전략신호={r.get('strategy_signal', direction)}"
    )
    await manager.broadcast({"type": "log", "data": {"message": msg}})
    await manager.broadcast({"type": "status", "data": _status_payload()})
    await _send_trade_event_notification(
        "PENDING",
        {**paper_result, "direction": direction},
        "PAPER",
    )
    return True


async def _send_trade_event_notification(event: str, result: dict, mode: Optional[str] = None):
    if not gmail_is_configured():
        email_log = state.add_log("[Gmail 알림 실패] Gmail 설정이 없어 자동 연동할 수 없습니다")
        await manager.broadcast({"type": "log", "data": {"message": email_log}})
        return
    payload = dict(result)
    if mode:
        payload["mode"] = mode
    event_labels = {
        "PENDING": "예상 진입가",
        "ENTRY": "진입 체결",
        "TP1": "1차 익절",
        "TP2": "2차 익절",
        "SL": "손절",
    }
    label = event_labels.get(event, event)
    try:
        sent, detail = await asyncio.to_thread(send_trade_event_email, event, payload)
        email_log = state.add_log(
            f"[Gmail 알림] {label} 메일 발송 완료 → {detail}"
            if sent else f"[Gmail 알림 실패] {label}: {detail}"
        )
    except Exception as exc:
        email_log = state.add_log(f"[Gmail 알림 실패] {label}: {exc}")
    await manager.broadcast({"type": "log", "data": {"message": email_log}})


async def _send_filled_position_email(result: dict, mode: Optional[str] = None):
    await _send_trade_event_notification("ENTRY", result, mode)


async def _check_pending_paper_entry(price: float):
    pending = state.pending_paper_order
    if not pending or paper_trader.is_open:
        return
    direction = pending["direction"]
    result = pending["result"]
    latest = state.last_result or {}
    latest_directions = latest.get("timeframe_directions") or {}
    opposite = "SHORT" if direction == "LONG" else "LONG"
    still_valid = (
        latest.get("direction") == direction
        and _is_order_eligible(latest)
        and latest_directions.get("1H", "HOLD") != opposite
    )
    if not still_valid:
        state.pending_paper_order = None
        msg = state.add_log(f"[모의 대기 주문 취소] {direction} 체결 직전 최신 신호 재검증 실패")
        await manager.broadcast({"type": "log", "data": {"message": msg}})
        await manager.broadcast({"type": "status", "data": _status_payload()})
        return
    limit_price = float(result.get("entry_price") or 0)
    filled = (direction == "LONG" and price <= limit_price) or (direction == "SHORT" and price >= limit_price)
    if not filled:
        return
    trade_id = paper_trader.open_trade(direction, result)
    state.pending_paper_order = None
    if state.paper_account_start_trade_id is None:
        state.paper_account_start_trade_id = trade_id
    msg = state.add_log(f"[모의 지정가 체결] {direction} #{trade_id}  ${limit_price:,.2f}")
    await manager.broadcast({"type": "log", "data": {"message": msg}})
    await _send_filled_position_email(result, "PAPER")
    await manager.broadcast({"type": "trade_update"})
    await manager.broadcast({"type": "status", "data": _status_payload()})


async def _expire_pending_order_if_needed(now: Optional[float] = None) -> bool:
    """전략별 유효시간이 지난 미체결 주문을 취소하고 다시 평가합니다."""
    checked_at = float(now if now is not None else time.time())
    pending = state.pending_paper_order or state.pending_live_order
    if not pending:
        return False

    expires_at = float(pending.get("expires_at") or 0)
    if expires_at <= 0:
        timestamps = _pending_order_timestamps(
            checked_at,
            _pending_result(pending),
        )
        pending.update(timestamps)
        await manager.broadcast({"type": "status", "data": _status_payload()})
        return False
    if checked_at < expires_at:
        return False

    mode = "PAPER" if state.pending_paper_order else "LIVE"
    direction = str(pending.get("direction") or "HOLD")
    old_entry_value = (
        (pending.get("result") or {}).get("entry_price")
        if mode == "PAPER"
        else pending.get("entry_price")
    )
    old_entry = float(old_entry_value or 0)
    ttl_minutes = max(
        1,
        round(
            (
                float(pending.get("expires_at") or checked_at)
                - float(pending.get("created_at") or checked_at)
            )
            / 60
        ),
    )

    if mode == "LIVE":
        order_id = str(pending.get("order_id") or "")
        if private_client and order_id and order_id != "pending":
            try:
                await asyncio.to_thread(private_client.cancel_order, order_id)
            except Exception as exc:
                pending["expires_at"] = checked_at + PENDING_CANCEL_RETRY_SECONDS
                msg = state.add_log(
                    f"[LIVE 대기 주문 {ttl_minutes}분 만료] 취소 실패, "
                    f"{PENDING_CANCEL_RETRY_SECONDS}초 후 재시도: {exc}"
                )
                await manager.broadcast({"type": "log", "data": {"message": msg}})
                await manager.broadcast({"type": "status", "data": _status_payload()})
                return False
        state.pending_live_order_id = None
        state.pending_live_order = None
    else:
        state.pending_paper_order = None

    msg = state.add_log(
        f"[{mode} 대기 주문 {ttl_minutes}분 만료] {direction} ${old_entry:,.2f} 취소 · "
        "최신 확정 신호로 재계산"
    )
    await manager.broadcast({"type": "log", "data": {"message": msg}})
    await manager.broadcast({"type": "status", "data": _status_payload()})

    latest = state.last_result
    if latest and state.auto_trade_enabled and not state.emergency_stopped:
        await _check_auto_trade(latest)
    return True


async def _auto_live_trade(direction: str, r: dict):
    if not private_client:
        return False
    btc_positions = [p for p in state.cached_positions if p.get("symbol") == SYMBOL]
    if btc_positions or state.pending_live_order_id:
        return False

    size_value = float(r.get("position_size_btc") or risk_cfg.order_size_btc)
    size = f"{size_value:.8f}".rstrip("0").rstrip(".")
    side = "buy" if direction == "LONG" else "sell"
    try:
        limit_price = f"{float(r.get('entry_price') or 0):.1f}"
        res = private_client.place_limit_order(side, size, limit_price, "open")
        state.pending_live_order_id = str(res.get("orderId") or "pending")
        state.pending_live_order = {
            "direction": direction,
            "entry_price": float(limit_price),
            "order_id": state.pending_live_order_id,
            "result": dict(r),
            **_pending_order_timestamps(result=r),
        }
        risk_mgr.record_order_placed()
        msg = state.add_log(
            f"[자동매매 LIVE 지정가] {direction} {size} BTC @ ${limit_price}  "
            f"전략신호={r.get('strategy_signal', direction)}  orderId={res.get('orderId', '?')}"
        )
        await manager.broadcast({"type": "log", "data": {"message": msg}})
        await manager.broadcast({"type": "status", "data": _status_payload()})
        await _send_trade_event_notification(
            "PENDING",
            {**r, "direction": direction, "entry_price": float(limit_price)},
            "LIVE",
        )
        return True
    except Exception as exc:
        msg = state.add_log(f"[자동매매] 주문 실패: {exc}")
        await manager.broadcast({"type": "log", "data": {"message": msg}})
        return False


# ── Background loops ───────────────────────────────────────────────────────────


async def signal_loop():
    while True:
        try:
            if not state.seeded:
                logs = await asyncio.to_thread(_worker_seed)
                for log in logs:
                    msg = state.add_log(log)
                    await manager.broadcast({"type": "log", "data": {"message": msg}})
                state.seeded = True

            result, errors = await asyncio.to_thread(_worker_analyze)

            if result:
                state.last_result = result
                for err in errors:
                    msg = state.add_log(f"[WARN] {err}")
                    await manager.broadcast({"type": "log", "data": {"message": msg}})
                for reason in result.get("reasons", []):
                    msg = state.add_log(f"  • {reason}")
                    await manager.broadcast({"type": "log", "data": {"message": msg}})
                await _ensure_signal_plan(result)
                await _check_auto_trade(result)
                await manager.broadcast({"type": "signal", "data": result})
            else:
                msg = state.add_log("[WARN] 캔들 데이터 없음. API/네트워크 확인 필요.")
                await manager.broadcast({"type": "log", "data": {"message": msg}})
        except Exception as exc:
            msg = state.add_log(f"[ERROR] 분석 루프: {exc}")
            await manager.broadcast({"type": "log", "data": {"message": msg}})

        await asyncio.sleep(REFRESH_INTERVAL_MS / 1000)


async def price_loop():
    while True:
        try:
            await _expire_pending_order_if_needed()
            price = await asyncio.to_thread(_worker_price)
            if price:
                state.last_price = price
                await manager.broadcast({"type": "price", "data": {"price": price}})
                if state.pending_paper_order:
                    await _check_pending_paper_entry(price)
                if state.plan_trade_id and state.plan_trade_data:
                    await _check_plan_tp_sl(price)
                if state.open_trade_id and state.open_trade_data:
                    await _check_tp_sl(price)
                if paper_trader.is_open:
                    await _check_active_scheduled_scale_in()
                if paper_trader.is_open:
                    time_exited = await _check_paper_scalp_time_exit(price)
                    if not time_exited:
                        await _check_paper_tp_sl(price)
                    if paper_trader.is_open:
                        await manager.broadcast({"type": "status", "data": _status_payload()})
        except Exception:
            pass
        await asyncio.sleep(2)


async def account_loop():
    while True:
        try:
            if private_client:
                acct, positions = await asyncio.to_thread(_worker_account)
                if acct:
                    state.cached_account = acct
                    state.cached_positions = positions if isinstance(positions, list) else []
                    cleared_pending = False
                    filled_result = None
                    if state.cached_positions:
                        cleared_pending = state.pending_live_order is not None
                        if state.pending_live_order:
                            filled_result = state.pending_live_order.get("result")
                        state.pending_live_order_id = None
                        state.pending_live_order = None
                    await manager.broadcast({"type": "account", "data": {
                        "account": acct,
                        "positions": state.cached_positions,
                    }})
                    if cleared_pending:
                        if filled_result:
                            await _place_live_limit_protection(state.cached_positions, filled_result)
                            await _send_filled_position_email(filled_result, "LIVE")
                        await manager.broadcast({"type": "status", "data": _status_payload()})
        except Exception:
            pass
        await asyncio.sleep(10)


async def _complete_scheduled_paper_scale_in(
    session_date: str,
    session_key: str,
    run_key: str,
    analysis_run: dict,
) -> bool:
    """미리 정한 2차 가격에 도달했을 때만 PAPER 잔여 50%를 체결한다."""
    split = analysis_run.get("scale_in") or {}
    if not split or not paper_trader.is_open or not paper_trader.open_data:
        return False
    price = float(state.last_price or 0)
    target = float(split.get("second_entry_price") or 0)
    direction = str(split.get("direction") or "HOLD")
    target_hit = (
        direction == "LONG" and price >= target
    ) or (
        direction == "SHORT" and price <= target
    )
    if not target_hit:
        return False

    fill_price = target
    added_size = float(split.get("second_size_btc") or 0)
    current = paper_trader.open_data
    current_size = float(current.get("size") or 0)
    total_size = current_size + added_size
    average = (
        float(current.get("entry") or 0) * current_size + fill_price * added_size
    ) / total_size
    repriced = reprice_scheduled_result(split["result"], average)
    repriced["position_size_btc"] = total_size
    repriced["position_size_percent"] = 100.0
    repriced["entry_stage"] = 2
    repriced["second_entry_price"] = fill_price
    repriced["average_entry_price"] = average
    trade_id, average = paper_trader.scale_in(fill_price, added_size, repriced)
    detail = (
        f"PAPER 50%+50% 완료 #{trade_id} · 2차 지정가 ${fill_price:,.2f} · "
        f"평균단가 ${average:,.2f} · SL ${repriced['stop_loss']:,.2f} · "
        f"TP1 ${repriced['take_profit_1']:,.2f}"
    )
    record_scheduled_entry_session(session_date, session_key, "ENTERED", "PAPER_TRADING", direction, detail)
    _scheduled_analysis_runs.pop(run_key, None)
    msg = state.add_log(f"[고정 진입 {session_key}] {detail}")
    await manager.broadcast({"type": "log", "data": {"message": msg}})
    await manager.broadcast({"type": "trade_update"})
    await manager.broadcast({"type": "status", "data": _status_payload()})
    await _send_filled_position_email(repriced, "PAPER")
    return True


async def _cancel_scheduled_scale_in_after_exit(trade_id: int, result_code: str) -> None:
    """1차 50%만 보유한 채 청산되면 미체결 2차 주문과 관련 상태를 전부 제거한다."""
    for run_key, analysis_run in list(_scheduled_analysis_runs.items()):
        split = analysis_run.get("scale_in") or {}
        if int(split.get("trade_id") or 0) != int(trade_id):
            continue
        session_date, session_key = run_key.split(":", 1)
        direction = str(split.get("direction") or "HOLD")
        target = float(split.get("second_entry_price") or 0)
        state.pending_paper_order = None
        detail = (
            f"PAPER 1차 50% #{trade_id} {result_code} 종료 · "
            f"미체결 2차 ${target:,.2f} 주문 취소"
        )
        record_scheduled_entry_session(
            session_date, session_key, "ENTERED", "PAPER_TRADING", direction, detail
        )
        _scheduled_analysis_runs.pop(run_key, None)
        msg = state.add_log(f"[고정 진입 {session_key}] {detail}")
        await manager.broadcast({"type": "log", "data": {"message": msg}})
        return


async def _check_active_scheduled_scale_in() -> None:
    """가격 루프에서 2차 진입가를 손절 검사보다 먼저 처리한다."""
    for run_key, analysis_run in list(_scheduled_analysis_runs.items()):
        if not analysis_run.get("scale_in"):
            continue
        session_date, session_key = run_key.split(":", 1)
        await _complete_scheduled_paper_scale_in(
            session_date, session_key, run_key, analysis_run
        )
        return


async def _execute_scheduled_entry(session_date: str, session_key: str) -> bool:
    """최신 분석을 여러 번 확인한 뒤 고정 세션 의무 진입을 한 번 실행한다."""
    run_key = f"{session_date}:{session_key}"
    if get_scheduled_entry_session(session_date, session_key):
        _scheduled_analysis_runs.pop(run_key, None)
        return True
    mode = state.trading_mode
    if not state.auto_trade_enabled or state.emergency_stopped or mode == "SIGNAL_ONLY":
        return False

    analysis_run = _scheduled_analysis_runs.setdefault(
        run_key,
        {"samples": [], "attempts": 0, "last_analysis_at": 0.0},
    )
    if analysis_run.get("scale_in"):
        return await _complete_scheduled_paper_scale_in(
            session_date, session_key, run_key, analysis_run
        )

    has_position = (
        paper_trader.is_open
        if mode == "PAPER_TRADING"
        else bool(state.open_trade_id) or bool(
            [p for p in state.cached_positions if p.get("symbol") == SYMBOL]
        )
    )
    if has_position:
        _scheduled_analysis_runs.pop(run_key, None)
        detail = "기존 포지션 보유로 세션 생략"
        record_scheduled_entry_session(session_date, session_key, "SKIPPED_POSITION", mode, detail=detail)
        msg = state.add_log(f"[고정 진입 {session_key}] {detail}")
        await manager.broadcast({"type": "log", "data": {"message": msg}})
        return True

    if mode == "LIVE_TRADING" and (not private_client or not risk_cfg.live_trading_allowed):
        return False
    if not state.last_price:
        return False

    now = time.monotonic()
    remaining_seconds = seconds_until_session_end(session_date, session_key)
    force_entry_due = remaining_seconds <= SCHEDULED_FORCE_ENTRY_BEFORE_END_SECONDS
    split_entry_due = remaining_seconds <= SCHEDULED_SPLIT_ENTRY_BEFORE_END_SECONDS
    if (
        not force_entry_due
        and
        analysis_run["last_analysis_at"]
        and now - analysis_run["last_analysis_at"] < SCHEDULED_ANALYSIS_INTERVAL_SECONDS
    ):
        return False

    analysis_run["last_analysis_at"] = now
    analysis_run["attempts"] += 1
    fresh_result, errors = await asyncio.to_thread(_worker_analyze)
    if fresh_result:
        state.last_result = fresh_result
        analysis_run["samples"].append(fresh_result)
        direction_label = str(fresh_result.get("direction") or "HOLD").upper()
        msg = state.add_log(
            f"[고정 진입 {session_key}] 최신 분석 "
            f"#{len(analysis_run['samples'])}: {direction_label} · "
            f"신뢰도 {float(fresh_result.get('confidence') or 0):.1f} · "
            f"종료까지 {max(0, int(remaining_seconds // 60))}분"
        )
        await manager.broadcast({"type": "log", "data": {"message": msg}})
        await manager.broadcast({"type": "signal", "data": fresh_result})
    else:
        msg = state.add_log(
            f"[고정 진입 {session_key}] 최신 분석 실패 "
            f"#{analysis_run['attempts']} · 종료까지 {max(0, int(remaining_seconds // 60))}분"
        )
        await manager.broadcast({"type": "log", "data": {"message": msg}})
    for error in errors:
        msg = state.add_log(f"[고정 진입 {session_key} 분석 경고] {error}")
        await manager.broadcast({"type": "log", "data": {"message": msg}})

    # 캔들 수집과 다중 시간봉 분석 자체가 수분 걸릴 수 있으므로,
    # 분석 완료 시점 기준으로 마감 의무 진입 여부를 다시 판단한다.
    remaining_seconds = seconds_until_session_end(session_date, session_key)
    force_entry_due = remaining_seconds <= SCHEDULED_FORCE_ENTRY_BEFORE_END_SECONDS
    split_entry_due = remaining_seconds <= SCHEDULED_SPLIT_ENTRY_BEFORE_END_SECONDS

    # 분석 중 일반 루프에서 먼저 포지션을 열었으면 세션은 정상 완료로 기록한다.
    position_opened_during_analysis = (
        paper_trader.is_open
        if mode == "PAPER_TRADING"
        else bool(state.open_trade_id) or bool(
            [p for p in state.cached_positions if p.get("symbol") == SYMBOL]
        )
    )
    if position_opened_during_analysis:
        _scheduled_analysis_runs.pop(run_key, None)
        detail = "분석 중 일반 전략 진입으로 세션 완료"
        record_scheduled_entry_session(session_date, session_key, "SKIPPED_POSITION", mode, detail=detail)
        return True

    samples = analysis_run["samples"]
    latest = samples[-1] if samples else state.last_result
    recent_samples = samples[-SCHEDULED_STABLE_SIGNAL_SAMPLES:]
    recent_directions = [
        str(sample.get("direction") or "HOLD").upper()
        for sample in recent_samples
    ]
    stable_direction = recent_directions[-1] if recent_directions else "HOLD"
    eligible_directions = [
        direction for sample, direction in zip(recent_samples, recent_directions)
        if direction in ("LONG", "SHORT") and _is_order_eligible(sample)
    ]
    long_matches = eligible_directions.count("LONG")
    short_matches = eligible_directions.count("SHORT")
    confirmed_direction = (
        "LONG" if long_matches >= SCHEDULED_REQUIRED_MATCHING_SAMPLES
        else "SHORT" if short_matches >= SCHEDULED_REQUIRED_MATCHING_SAMPLES
        else "HOLD"
    )
    confirmed = (
        len(recent_samples) == SCHEDULED_STABLE_SIGNAL_SAMPLES
        and confirmed_direction in ("LONG", "SHORT")
    )
    analysis_complete = confirmed or split_entry_due
    if not analysis_complete or not latest:
        return False

    if state.pending_paper_order or state.pending_live_order:
        if not await _cancel_pending_order(f"고정 진입 {session_key} 현재가 주문 우선"):
            return False

    consensus_inputs = samples or [latest]
    direction, consensus_score = choose_consensus_direction(consensus_inputs)
    if confirmed:
        direction = confirmed_direction
    forced = build_forced_entry_result(
        latest, float(state.last_price), direction, session_key, risk_cfg
    )
    forced["reasons"] = [
        f"고정 진입 세션 {session_key}: 최신 분석 {len(consensus_inputs)}회 후 의무 진입",
        f"다중 시간봉·확률·추세 합산 점수 {consensus_score:+.2f} → {direction}",
        "총 주문계획 100% (애매한 신호는 가격 기준 50%+50% 분할)",
        f"ATR 기반 손절, 목표 손익비 1:{float(forced.get('risk_reward_ratio') or 0):.1f}",
        (
            f"최근 {SCHEDULED_STABLE_SIGNAL_SAMPLES}회 중 {SCHEDULED_REQUIRED_MATCHING_SAMPLES}회 적격 신호가 {confirmed_direction}으로 일치해 단타 진입"
            if confirmed
            else "적격 신호 미확정: 누적 우세 방향으로 1차 50% 진입 후 가격 기준 2차 대기"
        ),
    ]
    if mode == "PAPER_TRADING":
        full_size = _paper_full_leverage_size(forced["entry_price"])
        if not confirmed and split_entry_due:
            # 불리한 방향 물타기 대신 +0.35R 진행을 확인한 뒤 잔여 50%를 추가한다.
            stop_gap = float(forced.get("scheduled_stop_gap") or 0)
            add_on_gap = stop_gap * float(forced.get("scheduled_add_on_ratio") or 0.35)
            second_entry = (
                float(forced["entry_price"]) + add_on_gap
                if direction == "LONG"
                else float(forced["entry_price"]) - add_on_gap
            )
            projected_average = (float(forced["entry_price"]) + second_entry) / 2
            projected = reprice_scheduled_result(forced, projected_average)
            first_size = round(full_size * 0.5, 8)
            second_size = round(full_size - first_size, 8)
            first_plan = dict(projected)
            first_plan.update({
                "entry_price": float(forced["entry_price"]),
                "take_profit_1": forced["take_profit_1"],
                "take_profit_2": forced["take_profit_2"],
                "position_size_btc": first_size,
                "position_size_percent": 50.0,
            })
            first_plan["reasons"] = list(forced["reasons"]) + [
                f"애매한 신호 1차 50% 진입, 유리하게 +0.35R 진행 시 2차 ${second_entry:,.2f}",
                "불리한 방향 물타기 금지, 1차 청산 시 미체결 잔량 취소",
            ]
            trade_id = paper_trader.open_trade(direction, first_plan)
            if state.paper_account_start_trade_id is None:
                state.paper_account_start_trade_id = trade_id
            analysis_run["scale_in"] = {
                "trade_id": trade_id,
                "direction": direction,
                "second_entry_price": second_entry,
                "second_size_btc": second_size,
                "result": forced,
            }
            risk_mgr.record_order_placed()
            msg = state.add_log(
                f"[고정 진입 {session_key}] {direction} 1차 50% #{trade_id} "
                f"${forced['entry_price']:,.2f} · 2차 ${second_entry:,.2f} 대기 · "
                f"1차 청산 시 미체결 잔량 전부 취소"
            )
            await manager.broadcast({"type": "log", "data": {"message": msg}})
            await _send_filled_position_email(first_plan, "PAPER")
            await manager.broadcast({"type": "trade_update"})
            await manager.broadcast({"type": "status", "data": _status_payload()})
            return False
        forced["position_size_btc"] = round(full_size, 8)
        trade_id = paper_trader.open_trade(direction, forced)
        if state.paper_account_start_trade_id is None:
            state.paper_account_start_trade_id = trade_id
        detail = f"PAPER 현재가 체결 #{trade_id} @ ${forced['entry_price']:,.2f}"
        await _send_filled_position_email(forced, "PAPER")
    elif mode == "LIVE_TRADING":
        size_value = float(risk_cfg.order_size_btc)
        size = f"{size_value:.8f}".rstrip("0").rstrip(".")
        side = "buy" if direction == "LONG" else "sell"
        try:
            response = await asyncio.to_thread(private_client.place_market_order, side, size, "open")
        except Exception as exc:
            msg = state.add_log(f"[고정 진입 {session_key}] LIVE 시장가 주문 실패: {exc}")
            await manager.broadcast({"type": "log", "data": {"message": msg}})
            return False
        order_id = str(response.get("orderId") or "market-pending")
        state.pending_live_order_id = order_id
        state.pending_live_order = {
            "direction": direction, "entry_price": forced["entry_price"],
            "order_id": order_id, "result": forced, **_pending_order_timestamps(result=forced),
        }
        detail = f"LIVE 시장가 주문 {order_id}"
    else:
        return False

    risk_mgr.record_order_placed()
    record_scheduled_entry_session(session_date, session_key, "ENTERED", mode, direction, detail)
    _scheduled_analysis_runs.pop(run_key, None)
    msg = state.add_log(f"[고정 진입 {session_key}] {direction} {detail}")
    await manager.broadcast({"type": "log", "data": {"message": msg}})
    await manager.broadcast({"type": "trade_update"})
    await manager.broadcast({"type": "status", "data": _status_payload()})
    return True


async def scheduled_entry_loop():
    while True:
        try:
            active = active_scheduled_session()
            if active:
                await _execute_scheduled_entry(*active)
        except Exception as exc:
            msg = state.add_log(f"[고정 진입 오류] {exc}")
            await manager.broadcast({"type": "log", "data": {"message": msg}})
        await asyncio.sleep(5)


async def _place_live_limit_protection(positions: list, result: dict):
    """LIVE 체결 직후 Bitget에 손절/익절 지정가 TPSL 주문을 등록한다."""
    if not private_client or not positions:
        return
    position = next((p for p in positions if p.get("symbol") == SYMBOL), None)
    if not position:
        return
    size = str(position.get("total") or risk_cfg.order_size_btc)
    hold_side = str(position.get("holdSide") or result.get("direction") or "").lower()
    hold_side = "long" if "long" in hold_side else "short"
    orders = (
        ("loss_plan", result.get("stop_loss"), "손절"),
        ("profit_plan", result.get("take_profit_1"), "1차 익절"),
    )
    for plan_type, target, label in orders:
        if not target:
            continue
        price = f"{float(target):.1f}"
        try:
            response = await asyncio.to_thread(
                private_client.place_tpsl_limit_order,
                plan_type, hold_side, size, price, price,
            )
            msg = state.add_log(
                f"[LIVE {label} 지정가 등록] {hold_side.upper()} {size} BTC @ ${float(target):,.1f}  "
                f"orderId={response.get('orderId', '?')}"
            )
        except Exception as exc:
            msg = state.add_log(f"[LIVE {label} 지정가 등록 실패] {exc}")
        await manager.broadcast({"type": "log", "data": {"message": msg}})


# ── Startup ────────────────────────────────────────────────────────────────────


def _historical_trigger(row: dict) -> tuple[str, float, dict] | None:
    candle = get_first_trade_trigger_candle(
        SYMBOL,
        _entry_timestamp_ms(row),
        row["direction"],
        row["stop_loss"],
        row.get("take_profit_1"),
    )
    if not candle:
        return None
    direction = str(row["direction"]).upper()
    sl_hit = candle["low"] <= row["stop_loss"] if direction == "LONG" else candle["high"] >= row["stop_loss"]
    tp_hit = bool(row.get("take_profit_1")) and (
        candle["high"] >= row["take_profit_1"] if direction == "LONG" else candle["low"] <= row["take_profit_1"]
    )
    if sl_hit and tp_hit:
        # 1분봉 내부 순서는 알 수 없으므로 시가에서 더 가까운 주문이 먼저 체결된 것으로 봅니다.
        sl_hit = abs(candle["open"] - row["stop_loss"]) <= abs(candle["open"] - row["take_profit_1"])
        tp_hit = not sl_hit
    return ("SL", float(row["stop_loss"]), candle) if sl_hit else ("TP1", float(row["take_profit_1"]), candle)


async def _reconcile_missed_exits() -> None:
    """서버 중단 중 저장된 1분봉이 TP/SL을 통과했으면 열린 기록을 자동 마감합니다."""
    if not risk_cfg.auto_stop_loss_analysis:
        return
    paper_row = get_open_trade(SYMBOL, trade_type="PAPER")
    if paper_row and paper_trader.is_open:
        trigger = _historical_trigger(paper_row)
        if trigger:
            result_code, exit_price, candle = trigger
            elapsed = _elapsed_since_entry(paper_row, candle["timestamp"])
            pnl_pct = _pnl_pct(paper_row["direction"], paper_row["entry_price"], exit_price)
            sign = "+" if pnl_pct >= 0 else ""
            profit_reason = (
                f"[모의 지정가] {result_code} 체결(서버 중단 중 자동 복구): "
                f"${paper_row['entry_price']:,.2f} → ${exit_price:,.2f}  ({sign}{pnl_pct:.2f}%)"
                if result_code.startswith("TP") else ""
            )
            loss_reason = (
                f"[모의 지정가] 손절 체결(서버 중단 중 자동 복구): "
                f"${paper_row['entry_price']:,.2f} → ${exit_price:,.2f}  ({sign}{pnl_pct:.2f}%)"
                if result_code == "SL" else ""
            )
            if result_code == "SL":
                loss_reason = _append_loss_analysis(loss_reason, paper_row["id"], elapsed)
            tid, pnl = paper_trader.close_trade(exit_price, result_code, profit_reason, loss_reason)
            risk_mgr.record_trade_result(pnl, result_code)
            state.add_log(f"[자동 복구] 모의매매 #{tid} {result_code} {pnl:+.2f}%")

    plan_row = get_open_trade(SYMBOL, trade_type="PLAN")
    if plan_row:
        trigger = _historical_trigger(plan_row)
        if trigger:
            result_code, exit_price, candle = trigger
            elapsed = _elapsed_since_entry(plan_row, candle["timestamp"])
            pnl_pct = _pnl_pct(plan_row["direction"], plan_row["entry_price"], exit_price)
            sign = "+" if pnl_pct >= 0 else ""
            profit_reason = f"[리스크 플랜] {result_code} 적중(자동 복구): ${plan_row['entry_price']:,.2f} → ${exit_price:,.2f} ({sign}{pnl_pct:.2f}%)" if result_code.startswith("TP") else ""
            loss_reason = f"[리스크 플랜] 손절 확인(자동 복구): ${plan_row['entry_price']:,.2f} → ${exit_price:,.2f} ({sign}{pnl_pct:.2f}%)" if result_code == "SL" else ""
            if result_code == "SL":
                loss_reason = _append_loss_analysis(loss_reason, plan_row["id"], elapsed)
            close_trade(plan_row["id"], exit_price, result_code, pnl_pct, profit_reason, loss_reason)
            state.plan_trade_id = None
            state.plan_trade_data = None
            state.add_log(f"[자동 복구] 리스크 플랜 #{plan_row['id']} {result_code} {pnl_pct:+.2f}%")


async def startup_event():
    existing = get_open_trade(SYMBOL, trade_type="LIVE")
    if existing:
        state.open_trade_id = existing["id"]
        state.open_trade_data = _trade_data_from_row(existing)
    existing_plan = get_open_trade(SYMBOL, trade_type="PLAN")
    if existing_plan:
        state.plan_trade_id = existing_plan["id"]
        state.plan_trade_data = _trade_data_from_row(existing_plan)
    paper_trader.restore_from_db()
    await _reconcile_missed_exits()
    if paper_trader.is_open and paper_trader.open_data:
        paper_trader.update_open_size(
            _paper_full_leverage_size(float(paper_trader.open_data.get("entry") or 0))
        )
    restored_losses = _recent_consecutive_paper_losses()
    risk_mgr.restore_consecutive_losses(restored_losses)
    if restored_losses >= risk_cfg.consecutive_loss_limit:
        await _activate_consecutive_loss_stop(restored=True)
    if state.paper_account_start_trade_id is None and paper_trader.is_open:
        state.paper_account_start_trade_id = paper_trader.open_id
    asyncio.create_task(signal_loop())
    asyncio.create_task(price_loop())
    asyncio.create_task(account_loop())
    asyncio.create_task(scheduled_entry_loop())


# ── WebSocket ──────────────────────────────────────────────────────────────────


async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    if state.last_result:
        await ws.send_json({"type": "signal", "data": state.last_result})
    if state.last_price:
        await ws.send_json({"type": "price", "data": {"price": state.last_price}})
    await ws.send_json({"type": "status", "data": _status_payload()})
    if state.cached_account:
        await ws.send_json({"type": "account", "data": {
            "account": state.cached_account,
            "positions": state.cached_positions,
        }})
    for msg in state.get_logs(100):
        await ws.send_json({"type": "log", "data": {"message": msg}})
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


# ── REST API ───────────────────────────────────────────────────────────────────


def _status_payload() -> dict:
    return {
        "trading_mode": state.trading_mode,
        "auto_trade_enabled": state.auto_trade_enabled,
        "emergency_stopped": state.emergency_stopped,
        "demo_mode": USE_DEMO_DATA,
        "seeded": state.seeded,
        "last_price": state.last_price,
        "confidence_threshold": risk_cfg.confidence_threshold,
        "order_size_btc": risk_cfg.order_size_btc,
        "keep_awake_enabled": keep_awake.enabled,
        "api_configured": private_client is not None,
        "gmail_notification_enabled": state.auto_trade_enabled and gmail_is_configured(),
        "paper_position": _paper_position_payload(),
        "paper_account": _paper_account_payload(),
        "pending_entry": _pending_entry_payload(),
    }


def _pending_entry_payload() -> Optional[dict]:
    now = time.time()
    for analysis_run in _scheduled_analysis_runs.values():
        split = analysis_run.get("scale_in") or {}
        if not split:
            continue
        result = split.get("result") or {}
        target = float(split.get("second_entry_price") or 0)
        current = paper_trader.open_data or {}
        current_size = float(current.get("size") or 0)
        second_size = float(split.get("second_size_btc") or 0)
        total_size = current_size + second_size
        average = (
            (float(current.get("entry") or 0) * current_size + target * second_size) / total_size
            if total_size > 0 else target
        )
        repriced = reprice_scheduled_result(result, average)
        return {
            "mode": "PAPER · 2차 50%",
            "direction": split.get("direction"),
            "entry_price": target,
            "stop_loss": repriced.get("stop_loss"),
            "take_profit_1": repriced.get("take_profit_1"),
            "take_profit_2": repriced.get("take_profit_2"),
            "position_size_percent": 50,
            "filled_percent": 50,
            "pending_stage": 2,
            "expected_average_entry": average,
            "remaining_seconds": None,
        }
    if state.pending_paper_order:
        result = state.pending_paper_order.get("result") or {}
        expires_at = float(state.pending_paper_order.get("expires_at") or 0)
        return {
            "mode": "PAPER",
            "direction": state.pending_paper_order.get("direction"),
            "entry_price": result.get("entry_price"),
            "stop_loss": result.get("stop_loss"),
            "take_profit_1": result.get("take_profit_1"),
            "take_profit_2": result.get("take_profit_2"),
            "created_at": state.pending_paper_order.get("created_at"),
            "expires_at": expires_at or None,
            "remaining_seconds": max(0, int(expires_at - now)) if expires_at else None,
        }
    if state.pending_live_order:
        expires_at = float(state.pending_live_order.get("expires_at") or 0)
        result = state.pending_live_order.get("result") or {}
        return {
            "mode": "LIVE",
            "direction": state.pending_live_order.get("direction"),
            "entry_price": state.pending_live_order.get("entry_price"),
            "order_id": state.pending_live_order.get("order_id"),
            "stop_loss": result.get("stop_loss"),
            "take_profit_1": result.get("take_profit_1"),
            "take_profit_2": result.get("take_profit_2"),
            "created_at": state.pending_live_order.get("created_at"),
            "expires_at": expires_at or None,
            "remaining_seconds": max(0, int(expires_at - now)) if expires_at else None,
        }
    return None


async def get_signal():
    return state.last_result or {}


async def get_trades():
    return get_recent_trades(SYMBOL, limit=None)


async def get_status():
    return _status_payload()


async def get_risk_settings():
    from dataclasses import asdict
    return asdict(risk_settings_store.load())




async def save_risk_settings(payload: RiskSettingsPayload):
    global risk_cfg, risk_mgr
    s = RiskSettings(**payload.model_dump())
    s.consecutive_loss_limit = 3
    s.risk_per_trade_pct = 0.2
    s.stop_reentry_wait_seconds = 600
    s.take_profit_reentry_wait_seconds = 180
    s.two_loss_pause_seconds = 1800
    s.atr_stop_multiplier = 1.5
    s.max_ma_distance_atr = 2.5
    risk_settings_store.save(s)
    risk_cfg = s
    risk_mgr = RiskManager(s)
    risk_mgr.restore_consecutive_losses(_recent_consecutive_paper_losses())
    if risk_mgr.consecutive_losses >= s.consecutive_loss_limit:
        await _activate_consecutive_loss_stop(restored=True)
    msg = state.add_log(f"[리스크 설정] 저장 완료  실거래허용={s.live_trading_allowed}")
    await manager.broadcast({"type": "log", "data": {"message": msg}})
    await manager.broadcast({"type": "status", "data": _status_payload()})
    return {"ok": True}




async def set_mode(payload: ModePayload):
    state.trading_mode = payload.mode
    if state.trading_mode == "PAPER_TRADING":
        risk_mgr.deactivate_emergency_stop()
        risk_mgr.reset_consecutive_losses()
        state.emergency_stopped = False
        state.auto_trade_enabled_before_emergency = None
        state.auto_trade_enabled = True
        keep_awake.enable()
    msg = state.add_log(f"[모드변경] {state.trading_mode}")
    await manager.broadcast({"type": "log", "data": {"message": msg}})
    await manager.broadcast({"type": "status", "data": _status_payload()})
    return {"ok": True}




async def set_auto_trade(payload: AutoTradePayload):
    global risk_cfg
    was_disabled = not state.auto_trade_enabled
    enabled = True if state.trading_mode == "PAPER_TRADING" else payload.enabled
    if enabled and was_disabled:
        risk_mgr.reset_consecutive_losses()
    state.auto_trade_enabled = enabled
    if payload.threshold is not None:
        risk_cfg.confidence_threshold = payload.threshold
        risk_mgr.settings.confidence_threshold = payload.threshold
    ok, power_msg = keep_awake.enable() if enabled else keep_awake.disable()
    msg = state.add_log(f"[자동매매] {'ON' if enabled else 'OFF'}  모드={state.trading_mode}")
    gmail_log = state.add_log(
        "[Gmail 알림] 자동매매 ON · 대기/진입/익절/손절 메일 연동 완료"
        if enabled and gmail_is_configured()
        else "[Gmail 알림] 자동매매 ON · Gmail 설정 필요"
        if enabled
        else "[Gmail 알림] 자동매매 OFF · 거래 이벤트 메일 연동 해제"
    )
    power_log = state.add_log(f"[전원관리] {power_msg}" if ok else f"[전원관리 경고] {power_msg}")
    await manager.broadcast({"type": "log", "data": {"message": msg}})
    await manager.broadcast({"type": "log", "data": {"message": gmail_log}})
    await manager.broadcast({"type": "log", "data": {"message": power_log}})
    await manager.broadcast({"type": "status", "data": _status_payload()})
    return {"ok": True}


async def emergency_stop():
    if state.trading_mode == "PAPER_TRADING":
        risk_mgr.deactivate_emergency_stop()
        state.emergency_stopped = False
        state.auto_trade_enabled_before_emergency = None
        state.auto_trade_enabled = True
        keep_awake.enable()
        msg = state.add_log("[모의매매] 긴급정지는 적용하지 않음 · 자동매매 계속")
        await manager.broadcast({"type": "log", "data": {"message": msg}})
        await manager.broadcast({"type": "status", "data": _status_payload()})
        return {"ok": True, "ignored": True, "has_position": False}
    if not state.emergency_stopped:
        state.auto_trade_enabled_before_emergency = state.auto_trade_enabled
    risk_mgr.activate_emergency_stop()
    state.auto_trade_enabled = False
    state.emergency_stopped = True
    state.pending_paper_order = None
    if private_client and state.pending_live_order_id and state.pending_live_order_id != "pending":
        try:
            private_client.cancel_order(state.pending_live_order_id)
        except Exception as exc:
            cancel_msg = state.add_log(f"[긴급정지] 미체결 지정가 취소 실패: {exc}")
            await manager.broadcast({"type": "log", "data": {"message": cancel_msg}})
    state.pending_live_order_id = None
    state.pending_live_order = None
    keep_awake.disable()
    msg = state.add_log(f"[긴급정지] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} — 자동매매 차단됨")
    await manager.broadcast({"type": "log", "data": {"message": msg}})
    await manager.broadcast({"type": "status", "data": _status_payload()})
    has_pos = bool(state.open_trade_data or state.cached_positions or paper_trader.is_open)
    return {"ok": True, "has_position": has_pos}


async def _activate_consecutive_loss_stop(restored: bool = False):
    """연속 손실 한도 도달을 사용자가 직접 해제해야 하는 긴급정지로 전환한다."""
    if state.trading_mode == "PAPER_TRADING":
        return
    if state.emergency_stopped:
        return
    await emergency_stop()
    prefix = "리스크 복원" if restored else "연속 손실 정지"
    msg = state.add_log(
        f"[{prefix}] 연속 손실 {risk_mgr.consecutive_losses}회 — 긴급정지 ON"
    )
    await manager.broadcast({"type": "log", "data": {"message": msg}})


async def emergency_resume():
    risk_mgr.deactivate_emergency_stop()
    risk_mgr.reset_consecutive_losses()
    state.emergency_stopped = False
    previous_enabled = state.auto_trade_enabled_before_emergency
    state.auto_trade_enabled = previous_enabled if previous_enabled is not None else state.trading_mode == "PAPER_TRADING"
    state.auto_trade_enabled_before_emergency = None
    if state.auto_trade_enabled:
        keep_awake.enable()
    else:
        keep_awake.disable()
    msg = state.add_log(f"[긴급정지 해제] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} — 운영 재개")
    await manager.broadcast({"type": "log", "data": {"message": msg}})
    await manager.broadcast({"type": "status", "data": _status_payload()})
    return {"ok": True}


async def emergency_close():
    position_closed = False
    state.pending_paper_order = None
    if private_client and state.pending_live_order_id and state.pending_live_order_id != "pending":
        try:
            private_client.cancel_order(state.pending_live_order_id)
            position_closed = True
        except Exception as exc:
            msg = state.add_log(f"[긴급정지] 미체결 지정가 취소 실패: {exc}")
            await manager.broadcast({"type": "log", "data": {"message": msg}})
    state.pending_live_order_id = None
    state.pending_live_order = None
    if paper_trader.is_open and state.last_price:
        tid, pnl = paper_trader.force_close(state.last_price)
        risk_mgr.record_trade_result(pnl, "EMERGENCY_CLOSE")
        msg = state.add_log(f"[모의매매 긴급청산] #{tid}  PnL={pnl:+.2f}%")
        await manager.broadcast({"type": "log", "data": {"message": msg}})
        await manager.broadcast({"type": "trade_update"})
        await manager.broadcast({"type": "status", "data": _status_payload()})
        position_closed = True
    if private_client:
        for p in state.cached_positions:
            if p.get("symbol") == SYMBOL:
                try:
                    private_client.close_position(p.get("holdSide", "long"))
                    position_closed = True
                except Exception as exc:
                    msg = state.add_log(f"[긴급정지] 청산 실패: {exc}")
                    await manager.broadcast({"type": "log", "data": {"message": msg}})
    if state.open_trade_data and state.last_price:
        t = state.open_trade_data
        price = state.last_price
        pnl_pct = _pnl_pct(t["direction"], t["entry"], price, TAKER_FEE_RATE)
        close_trade(trade_id=state.open_trade_id, exit_price=price, result="SIGNAL_CHANGE",
                    pnl_pct=pnl_pct, profit_reason="", loss_reason="긴급정지 청산")
        state.open_trade_id = None
        state.open_trade_data = None
        await manager.broadcast({"type": "trade_update"})
        position_closed = True
    msg = state.add_log("[긴급정지] 포지션 청산 완료")
    await manager.broadcast({"type": "log", "data": {"message": msg}})
    if position_closed:
        state.cached_positions = []
        await manager.broadcast({"type": "account", "data": {
            "account": state.cached_account,
            "positions": state.cached_positions,
        }})
    await manager.broadcast({"type": "status", "data": _status_payload()})
    return {"ok": True}




async def place_order(payload: OrderPayload):
    if not private_client:
        return {"ok": False, "error": "API 키가 설정되지 않았습니다"}
    side = "buy" if payload.side == "LONG" else "sell"
    if not state.last_price:
        return {"ok": False, "error": "현재가를 확인할 수 없어 지정가를 계산하지 못했습니다"}
    limit_price = state.last_price - 250.0 if payload.side == "LONG" else state.last_price + 250.0
    try:
        result = private_client.place_limit_order(side, str(payload.size), f"{limit_price:.1f}", "open")
        state.pending_live_order_id = str(result.get("orderId") or "pending")
        state.pending_live_order = {
            "direction": payload.side,
            "entry_price": limit_price,
            "order_id": state.pending_live_order_id,
            **_pending_order_timestamps(),
        }
        msg = state.add_log(
            f"[수동 지정가 주문] {payload.side} {payload.size} BTC @ ${limit_price:,.1f}  "
            f"orderId={result.get('orderId', '?')}"
        )
        await manager.broadcast({"type": "log", "data": {"message": msg}})
        await manager.broadcast({"type": "status", "data": _status_payload()})
        return {"ok": True, "orderId": result.get("orderId")}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


async def place_paper_pending_order(payload: PaperPendingOrderPayload):
    direction = payload.direction.upper()
    if direction not in ("LONG", "SHORT"):
        return {"ok": False, "error": "방향은 LONG 또는 SHORT만 가능합니다"}
    if paper_trader.is_open:
        return {"ok": False, "error": "이미 진행 중인 모의 포지션이 있습니다"}
    result = {
        "direction": direction,
        "entry_price": payload.entry_price,
        "stop_loss": payload.stop_loss,
        "take_profit_1": payload.take_profit_1,
        "take_profit_2": payload.take_profit_2,
        "strategy_signal": f"MANUAL_{direction}_LIMIT",
        "entry_grade": "A",
        "reasons": ["사용자가 복원한 모의 지정가 대기 주문"],
        "position_size_btc": _paper_full_leverage_size(payload.entry_price),
    }
    state.pending_paper_order = {
        "direction": direction,
        "result": result,
        **_pending_order_timestamps(),
    }
    risk_mgr.record_order_placed()
    msg = state.add_log(
        f"[모의 지정가 대기 복원] {direction} ${payload.entry_price:,.2f}  "
        f"SL ${payload.stop_loss:,.2f}  TP1 ${payload.take_profit_1:,.2f}"
    )
    await manager.broadcast({"type": "log", "data": {"message": msg}})
    await manager.broadcast({"type": "status", "data": _status_payload()})
    await _send_trade_event_notification("PENDING", result, "PAPER")
    return {"ok": True, "pending_entry": _status_payload().get("pending_entry")}


async def close_position():
    if not private_client:
        return {"ok": False, "error": "API 키가 설정되지 않았습니다"}
    try:
        for p in state.cached_positions:
            if p.get("symbol") == SYMBOL:
                private_client.close_position(p.get("holdSide", "long"))
        msg = state.add_log("[수동청산] 포지션 청산 완료")
        await manager.broadcast({"type": "log", "data": {"message": msg}})
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


async def get_credentials():
    c = creds_store.load()
    return {"api_key": c.api_key, "has_secret": bool(c.secret_key), "has_passphrase": bool(c.passphrase)}




async def save_credentials(payload: CredentialsPayload):
    global private_client
    try:
        candidate = BitgetPrivateClient(payload.api_key, payload.secret_key, payload.passphrase)
        account, positions = await asyncio.to_thread(
            lambda: (candidate.get_account(), candidate.get_positions())
        )
        creds_store.save(payload.api_key, payload.secret_key, payload.passphrase)
        private_client = candidate
        state.cached_account = account
        state.cached_positions = positions
        msg = state.add_log("[API] Bitget 계정 연결 확인 및 자격증명 저장 완료")
        await manager.broadcast({"type": "log", "data": {"message": msg}})
        await manager.broadcast({"type": "account", "data": {
            "account": account,
            "positions": positions,
        }})
        return {"ok": True, "connected": True}
    except Exception as exc:
        msg = state.add_log(f"[API] Bitget 계정 연동 실패: {exc}")
        await manager.broadcast({"type": "log", "data": {"message": msg}})
        return {"ok": False, "connected": False, "error": str(exc)}


async def disconnect_credentials():
    global private_client
    if state.cached_positions:
        return {
            "ok": False,
            "error": "실거래 포지션을 보유 중입니다. 포지션을 먼저 청산한 뒤 연동을 종료해 주세요.",
        }
    try:
        if private_client and state.pending_live_order_id and state.pending_live_order_id != "pending":
            await asyncio.to_thread(private_client.cancel_order, state.pending_live_order_id)
        state.pending_live_order_id = None
        state.pending_live_order = None
        state.auto_trade_enabled = False
        creds_store.save("", "", "")
        private_client = None
        state.cached_account = None
        state.cached_positions = []
        msg = state.add_log("[API] Bitget 실거래 자동매매 연동 종료")
        await manager.broadcast({"type": "log", "data": {"message": msg}})
        await manager.broadcast({"type": "account", "data": {"account": None, "positions": []}})
        await manager.broadcast({"type": "status", "data": _status_payload()})
        return {"ok": True, "connected": False}
    except Exception as exc:
        return {"ok": False, "error": f"연동 종료 실패: {exc}"}




async def run_backtest(payload: BacktestPayload):
    cfg = BacktestConfig(
        start_ts=payload.start_ts, end_ts=payload.end_ts,
        timeframe=payload.timeframe, initial_capital=payload.initial_capital,
        fee_rate=payload.fee_rate, slippage=payload.slippage,
        order_size_pct=payload.order_size_pct,
    )
    try:
        result = await asyncio.to_thread(lambda: Backtester().run(cfg))
        return {"ok": True, "result": result.to_dict(), "trade_log": result.trade_log}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ── Serve React frontend (production build) ────────────────────────────────────
