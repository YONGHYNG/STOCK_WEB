# 역할: 자동매매 시작, 중지, 새로고침을 제어하는 서비스.
import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import WebSocket, WebSocketDisconnect

from backend.strategy.multi_timeframe_strategy import TradingAIEngine
from backend.strategy.volume_event_strategy import VolumeEventStrategy
from backend.strategy.entry_timing import timing_entry_check, scheduled_timing_check
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
    get_last_closed_trade,
    insert_candles,
    insert_signal,
    get_scheduled_entry_session,
    record_scheduled_entry_session,
    open_trade,
    purge_unaligned_candles,
)
from backend.scheduled_entries import (
    active_scheduled_session,
    build_forced_entry_result,
    choose_consensus_direction,
    choose_forced_direction,
    reprice_scheduled_result,
    scheduled_volume_ratio,
    scheduled_session_bounds,
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
volume_event_engine = VolumeEventStrategy()
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
# 5분봉 하나가 더 열리기 전에 마지막 확정봉으로 의무 진입한다.
SCHEDULED_FORCE_ENTRY_BEFORE_END_SECONDS = 5 * 60
SCHEDULED_IMPULSE_VOLUME_RATIO = 1.5
SCHEDULED_PULLBACK_MIN_RATIO = 0.25
SCHEDULED_PULLBACK_MAX_RATIO = 0.60
SCHEDULED_PULLBACK_VOLUME_CONTRACTION = 0.70
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
    entered = datetime.strptime(str(row["entry_time"]), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
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


def _paper_risk_position_size(entry_price: float, stop_loss: float) -> float:
    """20배 레버리지는 유지하되 설정된 계좌 위험액으로 총 수량을 계산한다."""
    entry = float(entry_price or 0)
    stop = float(stop_loss or 0)
    risk_per_btc = abs(entry - stop)
    if entry <= 0 or stop <= 0 or risk_per_btc <= 0:
        return 0.0
    account = get_paper_account(PAPER_ACCOUNT_INITIAL_BALANCE, PAPER_ACCOUNT_LEVERAGE)
    balance = max(0.0, float(account["balance"]))
    risk_amount = balance * max(0.0, float(risk_cfg.risk_per_trade_pct)) / 100
    # 손절은 시장가 체결될 수 있으므로 진입 maker + 청산 taker 수수료를 최악값으로 반영한다.
    fee_per_btc = entry * (float(MAKER_FEE_RATE) + float(TAKER_FEE_RATE))
    size = risk_amount / (risk_per_btc + fee_per_btc)
    leverage_cap = balance * PAPER_ACCOUNT_LEVERAGE / entry
    return round(max(0.0, min(size, leverage_cap)), 8)


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
        "position_size_percent": data.get("position_size_percent", 100),
        "entry_stage": data.get("entry_stage", 2),
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
    reset_after = int(get_paper_account().get("reset_after_trade_id") or 0)
    for trade in get_recent_trades(SYMBOL, limit=None, trade_type="PAPER"):
        if int(trade.get("id") or 0) <= reset_after:
            continue
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
        "round_name": account.get("round_name", ""),
        "reset_after_trade_id": int(account.get("reset_after_trade_id") or 0),
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
    emoji = "익절" if result_code.startswith("TP") or result_code == "TRAILING_EXIT" else "손절"
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
    t = paper_trader.open_data
    if not result_code and t and t.get("tp2_taken"):
        ema20 = float(((state.last_result or {}).get("diagnostics") or {}).get("metrics", {}).get("ema20") or 0)
        if ema20 > 0:
            if (t["direction"] == "LONG" and price < ema20) or (t["direction"] == "SHORT" and price > ema20):
                result_code = "TRAILING_EXIT"
    if not result_code:
        return
    entry, direction = t["entry"], t["direction"]
    if result_code in ("TP1_PARTIAL", "TP2_PARTIAL"):
        partial_code = "TP1" if result_code == "TP1_PARTIAL" else "TP2"
        target = float(t.get("tp1") if partial_code == "TP1" else t.get("tp2"))
        tid, amount, remaining = paper_trader.take_partial(target, partial_code, 0.35)
        await _cancel_scheduled_scale_in_after_exit(tid, result_code)
        msg = state.add_log(
            f"[모의매매 분할익절] #{tid} {partial_code} · "
            f"+${amount:,.4f} · 잔여 {remaining:.8f} BTC"
        )
        await manager.broadcast({"type": "log", "data": {"message": msg}})
        await manager.broadcast({"type": "trade_update"})
        await manager.broadcast({"type": "status", "data": _status_payload()})
        return
    limit_exit_price = (
        float(price) if result_code == "TRAILING_EXIT"
        else float(t.get("sl"))
    )
    pnl_pct = _pnl_pct(direction, entry, limit_exit_price)
    sign = "+" if pnl_pct >= 0 else ""
    profit_reason = f"[모의 지정가] {result_code} 체결: ${entry:,.2f} → ${limit_exit_price:,.2f}  ({sign}{pnl_pct:.2f}%)" if result_code == "TRAILING_EXIT" else ""
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
    emoji = "익절" if result_code.startswith("TP") or result_code == "TRAILING_EXIT" else "손절"
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


# ── Auto trade ─────────────────────────────────────────────────────────────────


async def _check_auto_trade(result: dict):
    if not state.auto_trade_enabled:
        return
    if state.trading_mode == "SIGNAL_ONLY":
        return
    # 신규 전략은 지정된 활성 시간대에서만 실행되며, 진입 결정은
    # scheduled_entry_loop의 Volume Event 상태 머신이 전담한다. 일반 신호
    # 루프가 세션 밖이나 세션 중에 별도 주문을 내지 않도록 한다.
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
        timing_ok, timing_reason = _entry_timing_check(result, str(pending.get("direction")))
        if not timing_ok:
            await _cancel_pending_order(f"타점 무효: {timing_reason}")
            return
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

    timing_ok, timing_reason = _entry_timing_check(result, direction)
    if direction in ("LONG", "SHORT") and not timing_ok:
        msg = state.add_log(f"[타점 대기] {timing_reason}")
        await manager.broadcast({"type": "log", "data": {"message": msg}})
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


def _entry_timing_check(result: dict, direction: str, price: Optional[float] = None) -> tuple[bool, str]:
    trade_type = "PAPER" if state.trading_mode == "PAPER_TRADING" else "LIVE"
    return timing_entry_check(
        (result.get("entry_timing") or {}).get(direction) or {},
        float(price if price is not None else state.last_price or result.get("entry_price") or 0),
        int(time.time() * 1000),
        get_last_closed_trade(SYMBOL, trade_type),
    )


def _is_order_eligible(result: dict) -> bool:
    return (
        result.get("direction") in ("LONG", "SHORT")
        and result.get("entry_grade") in ("A", "B")
        and float(result.get("confidence") or 0) >= risk_cfg.confidence_threshold
        and not result.get("risk_warnings")
        and _entry_timing_check(result, result.get("direction"))[0]
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
        and _entry_timing_check(latest, direction, price)[0]
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

    pending_result = _pending_result(pending)
    if pending_result.get("entry_timing") and not str(pending_result.get("strategy_signal", "")).startswith("SCHEDULED_"):
        valid, reason = _entry_timing_check(pending_result, str(pending.get("direction")))
        if not valid:
            return await _cancel_pending_order(f"확인 타점 만료: {reason}")

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


def _scheduled_candle_snapshot(result: Optional[dict]) -> Optional[dict]:
    """분할 진입 판단에 필요한 최신 완성 5분봉 지표만 정규화한다."""
    result = result or {}
    metrics = (result.get("diagnostics") or {}).get("metrics") or {}
    try:
        snapshot = {
            "timestamp": int(metrics.get("timestamp") or result.get("timestamp") or 0),
            "open": float(metrics.get("open") or 0),
            "high": float(metrics.get("high") or 0),
            "low": float(metrics.get("low") or 0),
            "close": float(metrics.get("close") or 0),
            "volume_ratio": float(metrics.get("volume_ratio") or 0),
            "ema20": float(metrics.get("ema20") or 0),
            "vwap": float(metrics.get("vwap") or 0),
            "atr14": float(metrics.get("atr14") or 0),
        }
    except (TypeError, ValueError, OverflowError):
        return None
    if (
        snapshot["timestamp"] <= 0
        or min(snapshot[key] for key in ("open", "high", "low", "close")) <= 0
        or snapshot["high"] < snapshot["low"]
    ):
        return None
    return snapshot


def _is_directional_volume_impulse(snapshot: dict, direction: str) -> bool:
    return (
        snapshot["volume_ratio"] >= SCHEDULED_IMPULSE_VOLUME_RATIO
        and (
            snapshot["close"] > snapshot["open"]
            if direction == "LONG"
            else snapshot["close"] < snapshot["open"]
        )
    )


def _initial_scheduled_impulse(results: list[dict], direction: str) -> tuple[Optional[dict], int]:
    """세션 분석 중 발생한 가장 최근의 방향성 거래량 급증 봉을 찾는다."""
    snapshots = {}
    for result in results:
        snapshot = _scheduled_candle_snapshot(result)
        if snapshot:
            snapshots[snapshot["timestamp"]] = snapshot
    ordered = [snapshots[key] for key in sorted(snapshots)]
    qualifying = [item for item in ordered if _is_directional_volume_impulse(item, direction)]
    impulse = dict(qualifying[-1]) if qualifying else None
    if impulse:
        following = [item for item in ordered if item["timestamp"] >= impulse["timestamp"]]
        impulse["origin"] = impulse["low"] if direction == "LONG" else impulse["high"]
        impulse["favorable_extreme"] = (
            max(item["high"] for item in following)
            if direction == "LONG"
            else min(item["low"] for item in following)
        )
    last_timestamp = ordered[-1]["timestamp"] if ordered else 0
    return impulse, last_timestamp


def _advance_scheduled_pullback(split: dict, result: Optional[dict], price: float) -> tuple[str, str]:
    """새 완성봉으로 거래량 급증→조정→재출발 상태를 한 단계 진행한다."""
    snapshot = _scheduled_candle_snapshot(result)
    if not snapshot or snapshot["timestamp"] <= int(split.get("last_candle_timestamp") or 0):
        return "WAIT", "새 완성 5분봉 대기"
    split["last_candle_timestamp"] = snapshot["timestamp"]
    direction = str(split.get("direction") or "HOLD")
    long = direction == "LONG"
    impulse = split.get("impulse")
    if not impulse:
        if not _is_directional_volume_impulse(snapshot, direction):
            return "WAIT", f"거래량 {SCHEDULED_IMPULSE_VOLUME_RATIO:.1f}배 방향성 급증 대기"
        impulse = dict(snapshot)
        impulse["origin"] = snapshot["low"] if long else snapshot["high"]
        impulse["favorable_extreme"] = snapshot["high"] if long else snapshot["low"]
        split["impulse"] = impulse
        return "WAIT", f"거래량 {snapshot['volume_ratio']:.2f}배 충격봉 확인 · 조정 대기"

    impulse["favorable_extreme"] = (
        max(float(impulse["favorable_extreme"]), snapshot["high"])
        if long
        else min(float(impulse["favorable_extreme"]), snapshot["low"])
    )
    origin = float(impulse["origin"])
    favorable_extreme = float(impulse["favorable_extreme"])
    impulse_move = favorable_extreme - origin if long else origin - favorable_extreme
    if impulse_move <= 0:
        return "WAIT", "거래량 급증 파동 확장 대기"

    adverse_extreme = snapshot["low"] if long else snapshot["high"]
    pullback_move = favorable_extreme - adverse_extreme if long else adverse_extreme - favorable_extreme
    pullback_ratio = max(0.0, pullback_move / impulse_move)
    structure_broken = snapshot["close"] <= origin if long else snapshot["close"] >= origin
    if structure_broken or pullback_ratio > SCHEDULED_PULLBACK_MAX_RATIO:
        # 한 번 정한 잔여 50% 계획은 포지션이 끝날 때까지 유지한다. 기존
        # 충격 파동만 폐기하고 이후의 더 좋은 거래량 파동을 다시 탐색한다.
        split["impulse"] = None
        split["pullback"] = None
        if _is_directional_volume_impulse(snapshot, direction):
            replacement = dict(snapshot)
            replacement["origin"] = snapshot["low"] if long else snapshot["high"]
            replacement["favorable_extreme"] = snapshot["high"] if long else snapshot["low"]
            split["impulse"] = replacement
            return "WAIT", (
                f"기존 조정 {pullback_ratio * 100:.1f}% 파동 무효 · 2차 계획 유지 · "
                f"거래량 {snapshot['volume_ratio']:.2f}배 새 충격봉으로 갱신"
            )
        return "WAIT", (
            f"기존 조정 {pullback_ratio * 100:.1f}% 파동 무효 · "
            "2차 계획 유지, 새 방향성 거래량 급증 대기"
        )

    pullback = split.get("pullback")
    if pullback and snapshot["timestamp"] > int(pullback["timestamp"]):
        resumed = (
            snapshot["close"] > float(pullback["high"]) and snapshot["close"] > snapshot["open"]
            if long
            else snapshot["close"] < float(pullback["low"]) and snapshot["close"] < snapshot["open"]
        )
        volume_reexpanded = snapshot["volume_ratio"] > float(pullback["volume_ratio"])
        average_improves = price < float(split["first_entry_price"]) if long else price > float(split["first_entry_price"])
        if resumed and volume_reexpanded and average_improves:
            return "FILL", (
                f"조정 {float(pullback['ratio']) * 100:.1f}% · 거래량 재확대 "
                f"{float(pullback['volume_ratio']):.2f}→{snapshot['volume_ratio']:.2f}"
            )

    contracted = snapshot["volume_ratio"] <= float(impulse["volume_ratio"]) * SCHEDULED_PULLBACK_VOLUME_CONTRACTION
    if SCHEDULED_PULLBACK_MIN_RATIO <= pullback_ratio <= SCHEDULED_PULLBACK_MAX_RATIO and contracted:
        current_pullback = split.get("pullback")
        candidate_is_better = (
            not current_pullback
            or (long and snapshot["close"] < float(current_pullback["close"]))
            or (not long and snapshot["close"] > float(current_pullback["close"]))
        )
        if candidate_is_better:
            split["pullback"] = {**snapshot, "ratio": pullback_ratio}
            candidate_text = "2차 후보가 갱신"
        else:
            candidate_text = (
                f"기존의 더 좋은 2차 후보 ${float(current_pullback['close']):,.2f} 유지"
            )
        return "WAIT", (
            f"조정 {pullback_ratio * 100:.1f}% · 거래량 축소 "
            f"{float(impulse['volume_ratio']):.2f}→{snapshot['volume_ratio']:.2f} · "
            f"{candidate_text} · 재출발 대기"
        )
    return "WAIT", f"조정 {pullback_ratio * 100:.1f}% · 거래량 축소 조건 대기"


async def _complete_scheduled_paper_scale_in(
    session_date: str,
    session_key: str,
    run_key: str,
    analysis_run: dict,
) -> bool:
    """거래량 급증 후 조정·재출발이 확인되면 PAPER 잔여 50%를 체결한다."""
    split = analysis_run.get("scale_in") or {}
    if not split or not paper_trader.is_open or not paper_trader.open_data:
        return False
    price = float(state.last_price or 0)
    direction = str(split.get("direction") or "HOLD")
    action, reason = _advance_scheduled_pullback(split, state.last_result, price)
    if action != "FILL":
        return False

    current = paper_trader.open_data
    fill_price = price
    added_size = float(split.get("second_size_btc") or 0)
    current_size = float(current.get("size") or 0)
    total_size = current_size + added_size
    average = (
        float(current.get("entry") or 0) * current_size + fill_price * added_size
    ) / total_size
    completed = dict(split["result"])
    original_entry = float(completed.get("entry_price") or current.get("entry") or 0)
    original_stop = float(completed.get("stop_loss") or 0)
    stop_gap = float(completed.get("scheduled_stop_gap") or 0)
    if stop_gap <= 0 and original_entry > 0 and original_stop > 0:
        stop_gap = abs(original_entry - original_stop)
    completed["scheduled_stop_gap"] = stop_gap
    # SL·TP는 1차 가격으로 미리 확정하지 않는다. 2차 체결가를 합친 실제
    # 평균단가가 정해진 이 시점에 동일 위험 간격으로 처음 계산한다.
    completed = reprice_scheduled_result(completed, average)
    completed["position_size_btc"] = total_size
    completed["position_size_percent"] = 100.0
    completed["entry_stage"] = 2
    completed["second_entry_price"] = fill_price
    completed["average_entry_price"] = average
    # 평단을 개선하더라도 기존 손절가를 더 멀리 늘리지 않는다.
    trade_id, average = paper_trader.scale_in(fill_price, added_size, completed)
    detail = (
        f"PAPER 조정 50%+50% 완료 #{trade_id} · {reason} · 2차 ${fill_price:,.2f} · "
        f"평균단가 ${average:,.2f} · SL ${completed['stop_loss']:,.2f} · "
        f"TP1 ${completed['take_profit_1']:,.2f}"
    )
    record_scheduled_entry_session(session_date, session_key, "ENTERED", "PAPER_TRADING", direction, detail)
    _scheduled_analysis_runs.pop(run_key, None)
    msg = state.add_log(f"[고정 진입 {session_key}] {detail}")
    await manager.broadcast({"type": "log", "data": {"message": msg}})
    await manager.broadcast({"type": "trade_update"})
    await manager.broadcast({"type": "status", "data": _status_payload()})
    await _send_filled_position_email(completed, "PAPER")
    return True


async def _cancel_scheduled_scale_in_after_exit(trade_id: int, result_code: str) -> None:
    """청산/익절이 시작되면 남은 수익 방향 추가 진입 계획을 제거한다."""
    for run_key, analysis_run in list(_scheduled_analysis_runs.items()):
        split = analysis_run.get("pyramid") or analysis_run.get("scale_in") or {}
        if int(split.get("trade_id") or 0) != int(trade_id):
            continue
        session_date, session_key = run_key.split(":", 1)
        direction = str(split.get("direction") or "HOLD")
        state.pending_paper_order = None
        detail = (
            f"PAPER 1차 50% #{trade_id} {result_code} 종료 · "
            "미체결 수익 방향 25%+25% 추가 계획 취소"
        )
        record_scheduled_entry_session(
            session_date, session_key, "ENTERED", "PAPER_TRADING", direction, detail
        )
        _scheduled_analysis_runs.pop(run_key, None)
        msg = state.add_log(f"[고정 진입 {session_key}] {detail}")
        await manager.broadcast({"type": "log", "data": {"message": msg}})
        return


async def _complete_scheduled_profit_add(
    session_date: str,
    session_key: str,
    run_key: str,
    analysis_run: dict,
) -> bool:
    """1차 진입이 수익 방향으로 진행했을 때만 25%씩 최대 두 번 추가한다."""
    pyramid = analysis_run.get("pyramid") or {}
    if not pyramid or not paper_trader.is_open or not paper_trader.open_data:
        return False
    current = paper_trader.open_data
    if int(pyramid.get("trade_id") or 0) != int(paper_trader.open_id or 0):
        analysis_run.pop("pyramid", None)
        return False

    metrics = (state.last_result or {}).get("diagnostics", {}).get("metrics", {})
    timestamp = int(metrics.get("timestamp") or 0)
    if timestamp <= int(pyramid.get("last_candle_timestamp") or 0):
        return False
    pyramid["last_candle_timestamp"] = timestamp

    price = float(state.last_price or metrics.get("close") or 0)
    close = float(metrics.get("close") or price)
    ema20 = float(metrics.get("ema20") or 0)
    volume_ratio = float(metrics.get("volume_ratio") or 0)
    direction = str(pyramid.get("direction") or "NO_TRADE")
    first_entry = float(pyramid.get("first_entry_price") or 0)
    risk = float(pyramid.get("risk_per_btc") or 0)
    stage = int(pyramid.get("next_stage") or 2)
    threshold = first_entry + risk * (0.5 if stage == 2 else 1.0) * (1 if direction == "LONG" else -1)
    favorable = price >= threshold if direction == "LONG" else price <= threshold
    trend_held = (
        close > ema20 if direction == "LONG" and ema20 > 0
        else close < ema20 if direction == "SHORT" and ema20 > 0
        else False
    )
    last_add = float(pyramid.get("last_add_price") or first_entry)
    renewed_extreme = (
        price >= last_add + risk * 0.25
        if direction == "LONG"
        else price <= last_add - risk * 0.25
    )
    if not (favorable and trend_held and renewed_extreme and volume_ratio >= 0.65):
        return False

    added_size = min(
        float(pyramid.get("add_size_btc") or 0),
        max(0.0, float(pyramid.get("target_size_btc") or 0) - float(current.get("size") or 0)),
    )
    if added_size <= 0:
        analysis_run.pop("pyramid", None)
        return False
    current_size = float(current.get("size") or 0)
    new_total = current_size + added_size
    new_percent = 75.0 if stage == 2 else 100.0
    average = (float(current["entry"]) * current_size + price * added_size) / new_total
    plan = dict(pyramid.get("result") or {})
    # 수익 확인 후 추가하므로 보호가를 더 멀리 늘리지 않는다.
    old_stop = float(current.get("sl") or pyramid.get("original_stop") or 0)
    if direction == "LONG":
        protected_stop = max(old_stop, first_entry if stage == 2 else float(current["entry"]))
    else:
        protected_stop = min(old_stop, first_entry if stage == 2 else float(current["entry"]))
    plan.update({
        "stop_loss": protected_stop,
        "position_size_percent": new_percent,
        "entry_stage": stage,
        "second_entry_price" if stage == 2 else "third_entry_price": price,
        "average_entry_price": average,
    })
    trade_id, actual_average = paper_trader.scale_in(price, added_size, plan)
    pyramid["last_add_price"] = price
    pyramid["result"] = plan
    if stage == 2:
        pyramid["next_stage"] = 3
        detail = (
            f"PAPER 수익 확인 2차 25% #{trade_id} · 총 75% · "
            f"평단 ${actual_average:,.2f} · SL ${protected_stop:,.2f}"
        )
    else:
        analysis_run.pop("pyramid", None)
        detail = (
            f"PAPER 추세 지속 3차 25% #{trade_id} · 총 100% · "
            f"평단 ${actual_average:,.2f} · SL ${protected_stop:,.2f}"
        )
    record_scheduled_entry_session(session_date, session_key, "ENTERED", "PAPER_TRADING", direction, detail)
    msg = state.add_log(f"[고정 세션 {session_key}] {detail}")
    await manager.broadcast({"type": "log", "data": {"message": msg}})
    await manager.broadcast({"type": "trade_update"})
    await manager.broadcast({"type": "status", "data": _status_payload()})
    await _send_filled_position_email(plan, "PAPER")
    return True


async def _check_active_scheduled_scale_in() -> None:
    """가격 루프에서 수익 방향 50/25/25 추가 진입을 갱신한다."""
    for run_key, analysis_run in list(_scheduled_analysis_runs.items()):
        if analysis_run.get("pyramid"):
            session_date, session_key = run_key.split(":", 1)
            await _complete_scheduled_profit_add(
                session_date, session_key, run_key, analysis_run
            )
            return
        if not analysis_run.get("scale_in"):
            continue
        session_date, session_key = run_key.split(":", 1)
        await _complete_scheduled_paper_scale_in(
            session_date, session_key, run_key, analysis_run
        )
        return


def _restore_open_scheduled_scale_in() -> bool:
    """재시작 후에도 수익 방향 50/25/25 추가 진입 계획을 복구한다."""
    if not paper_trader.is_open or not paper_trader.open_data:
        return False
    current = paper_trader.open_data
    position_percent = float(current.get("position_size_percent") or 100)
    entry_stage = int(current.get("entry_stage") or 3)
    if position_percent >= 100 or entry_stage not in (1, 2):
        return False

    row = get_open_trade(SYMBOL, trade_type="PAPER") or {}
    reason = str(row.get("entry_reason") or "")
    session_key = next(
        (key for key in ("MORNING", "EVENING") if f"고정 진입 세션 {key}" in reason),
        "RECOVERY",
    )
    try:
        entered_utc = datetime.strptime(
            str(row.get("entry_time")), "%Y-%m-%d %H:%M:%S"
        ).replace(tzinfo=timezone.utc)
        entered_kst = entered_utc.astimezone(KST)
        session_day = entered_kst.date()
        session_date = session_day.isoformat()
    except (TypeError, ValueError):
        session_date = datetime.now(KST).date().isoformat()

    direction = str(current.get("direction") or row.get("direction") or "HOLD").upper()
    entry = float(current.get("entry") or row.get("entry_price") or 0)
    tp1 = float(current.get("tp1") or row.get("take_profit_1") or 0)
    risk_gap = abs(tp1 - entry) if tp1 > 0 and entry > 0 else 0.0
    planned_stop = float(current.get("sl") or row.get("stop_loss") or 0)
    if planned_stop <= 0 and risk_gap > 0:
        planned_stop = entry - risk_gap if direction == "LONG" else entry + risk_gap
    if direction not in ("LONG", "SHORT") or entry <= 0 or planned_stop <= 0:
        return False

    try:
        timeframe_directions = json.loads(row.get("tf_directions") or "{}")
    except (TypeError, json.JSONDecodeError):
        timeframe_directions = {}
    result = {
        "direction": direction,
        "entry_price": entry,
        "stop_loss": planned_stop,
        "take_profit_1": tp1 or None,
        "take_profit_2": current.get("tp2") or row.get("take_profit_2"),
        "scheduled_stop_gap": risk_gap,
        "scheduled_tp1_ratio": 1.0,
        "scheduled_tp2_ratio": 1.5,
        "risk_reward_ratio": row.get("risk_reward"),
        "confidence": float(row.get("confidence") or 0),
        "long_probability": float(row.get("long_prob") or 50),
        "short_probability": float(row.get("short_prob") or 50),
        "timeframe_directions": timeframe_directions,
        "strategy_signal": f"SCHEDULED_{session_key}_{direction}",
        "reasons": ["재시작 후 기존 잔여 50% 계획 복구"],
    }
    run_key = f"{session_date}:{session_key}"
    analysis_run = _scheduled_analysis_runs.setdefault(
        run_key, {"samples": [], "attempts": 0, "last_analysis_at": 0.0}
    )
    if analysis_run.get("pyramid"):
        return True
    current_size = float(current.get("size") or row.get("size_btc") or 0)
    if current_size <= 0 or position_percent <= 0:
        return False
    target_size = current_size / (position_percent / 100)
    add_size = target_size * 0.25
    analysis_run["pyramid"] = {
        "trade_id": int(paper_trader.open_id or row.get("id") or 0),
        "direction": direction,
        "first_entry_price": entry,
        "original_stop": planned_stop,
        "risk_per_btc": abs(entry - planned_stop),
        "add_size_btc": add_size,
        "target_size_btc": target_size,
        "next_stage": 2 if position_percent <= 50 else 3,
        "last_add_price": entry,
        "result": result,
        "last_candle_timestamp": 0,
        "restored": True,
    }
    return True


async def _execute_legacy_scheduled_entry(session_date: str, session_key: str) -> bool:
    """최신 분석을 여러 번 확인한 뒤 고정 세션 의무 진입을 한 번 실행한다."""
    run_key = f"{session_date}:{session_key}"
    existing_run = _scheduled_analysis_runs.get(run_key) or {}
    if existing_run.get("scale_in"):
        return await _complete_scheduled_paper_scale_in(
            session_date, session_key, run_key, existing_run
        )
    if get_scheduled_entry_session(session_date, session_key):
        return True
    mode = state.trading_mode
    if not state.auto_trade_enabled or state.emergency_stopped or mode == "SIGNAL_ONLY":
        return False

    analysis_run = _scheduled_analysis_runs.setdefault(
        run_key,
        {"samples": [], "attempts": 0, "last_analysis_at": 0.0},
    )
    has_position = (
        paper_trader.is_open
        if mode == "PAPER_TRADING"
        else bool(state.open_trade_id) or bool(
            [p for p in state.cached_positions if p.get("symbol") == SYMBOL]
        )
    )
    if has_position and mode != "PAPER_TRADING":
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

    # 분석 중 일반 루프에서 먼저 포지션을 열었으면 세션은 정상 완료로 기록한다.
    position_opened_during_analysis = mode != "PAPER_TRADING" and (
        bool(state.open_trade_id) or bool(
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
    # 고정 세션 진입은 기존처럼 마감 1분 이내에만 실행한다.
    # 세션 중 조기 신호는 방향·파동 판단에만 사용한다.
    analysis_complete = force_entry_due
    if not analysis_complete or not latest:
        return False

    consensus_inputs = samples or [latest]
    direction, consensus_score = choose_consensus_direction(consensus_inputs)
    if confirmed:
        direction = confirmed_direction
    # 고정 세션은 합의·상위 시간봉 필터와 무관하게 반드시 진입한다.
    # 방향이 HOLD인 경우 choose_consensus_direction()이 최신 지표 투표로
    # LONG/SHORT를 선택한다.
    if direction not in ("LONG", "SHORT"):
        direction = choose_forced_direction(latest)
    if direction not in ("LONG", "SHORT"):
        record_scheduled_entry_session(
            session_date, session_key, "SKIPPED", mode,
            detail="강제 진입 방향 계산 실패",
        )
        return False
    current_price = float(state.last_price or 0)
    if mode == "PAPER_TRADING" and paper_trader.is_open and paper_trader.open_data:
        current_position = dict(paper_trader.open_data)
        current_direction = str(current_position.get("direction") or "HOLD").upper()
        if current_direction == direction:
            detail = (
                f"기존 {current_direction} 포지션과 새 세션 방향 일치 · "
                "청산·재진입 없이 계속 보유"
            )
            record_scheduled_entry_session(
                session_date, session_key, "CARRIED_POSITION", mode, direction, detail
            )
            _scheduled_analysis_runs.pop(run_key, None)
            msg = state.add_log(f"[고정 진입 {session_key}] {detail}")
            await manager.broadcast({"type": "log", "data": {"message": msg}})
            await manager.broadcast({"type": "status", "data": _status_payload()})
            return True

        previous_entry = float(current_position.get("entry") or 0)
        previous_size = float(current_position.get("size") or 0)
        trade_id, pnl = paper_trader.force_close(current_price)
        await _cancel_scheduled_scale_in_after_exit(trade_id, "SESSION_DIRECTION_CHANGE")
        risk_mgr.record_trade_result(pnl, "SESSION_DIRECTION_CHANGE")
        msg = state.add_log(
            f"[고정 진입 {session_key}] {current_direction}→{direction} 방향 전환 · "
            f"기존 #{trade_id} {pnl:+.2f}% 청산"
        )
        await manager.broadcast({"type": "log", "data": {"message": msg}})
        await manager.broadcast({"type": "trade_update"})
        await _send_trade_event_notification(
            "SESSION_DIRECTION_CHANGE",
            {
                "direction": current_direction,
                "entry_price": previous_entry,
                "stop_loss": current_position.get("sl"),
                "take_profit_1": current_position.get("tp1"),
                "take_profit_2": current_position.get("tp2"),
                "exit_price": current_price,
                "pnl_pct": pnl,
                "position_size_btc": previous_size,
                "position_size_percent": current_position.get("position_size_percent", 100),
            },
            "PAPER",
        )

    timing = (latest.get("entry_timing") or {}).get(direction) or {}
    trade_type = "PAPER" if mode == "PAPER_TRADING" else "LIVE"
    timing_ok, timing_status, timing_reason = scheduled_timing_check(
        timing, current_price, force_entry_due, int(time.time() * 1000),
        get_last_closed_trade(SYMBOL, trade_type),
    )
    if not timing_ok:
        msg = state.add_log(f"[고정 진입 {session_key} 타점 대기] {timing_reason}")
        await manager.broadcast({"type": "log", "data": {"message": msg}})
        return False
    volume_ratio = scheduled_volume_ratio(latest)
    if volume_ratio < 0.65 and not force_entry_due:
        return False
    if state.pending_paper_order or state.pending_live_order:
        if not await _cancel_pending_order(f"고정 진입 {session_key} 확인 타점 주문 우선"):
            return False
    forced = build_forced_entry_result(latest, current_price, direction, session_key, risk_cfg)
    # Execution follows confirmation (or the explicit deadline exception),
    # never a historical EMA price that the market has not actually filled.
    forced = reprice_scheduled_result(forced, current_price)
    forced["entry_timing_status"] = timing_status
    forced["reasons"] = [
        f"고정 진입 세션 {session_key}: 최신 분석 {len(consensus_inputs)}회 후 의무 진입",
        f"타점 판정: {timing_status} · {timing_reason}",
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
        if force_entry_due:
            # 마감 시 50%만 진입하고, 완성 5분봉에서 거래량 급증 후
            # 25~60% 조정·거래량 축소·재출발이 확인될 때 잔여 50%를 추가한다.
            first_size = round(full_size * 0.5, 8)
            second_size = round(full_size - first_size, 8)
            first_plan = dict(forced)
            first_plan.update({
                "entry_price": float(forced["entry_price"]),
                "stop_loss": None,
                "position_size_btc": first_size,
                "position_size_percent": 50.0,
                "entry_stage": 1,
            })
            first_plan["reasons"] = list(forced["reasons"]) + [
                "마감 1차 50% 진입, 거래량 급증 후 25~60% 조정·재출발 시 2차 50%",
                "1차 50%는 손절 없이 익절가만 활성화, 2차 체결 후 최초 손절가 활성화",
            ]
            trade_id = paper_trader.open_trade(direction, first_plan)
            if state.paper_account_start_trade_id is None:
                state.paper_account_start_trade_id = trade_id
            impulse, last_candle_timestamp = _initial_scheduled_impulse(consensus_inputs, direction)
            analysis_run["scale_in"] = {
                "trade_id": trade_id,
                "direction": direction,
                "first_entry_price": float(forced["entry_price"]),
                "second_size_btc": second_size,
                "result": forced,
                "impulse": impulse,
                "pullback": None,
                "last_candle_timestamp": last_candle_timestamp,
            }
            risk_mgr.record_order_placed()
            msg = state.add_log(
                f"[고정 진입 {session_key}] {direction} 1차 50% #{trade_id} "
                f"${forced['entry_price']:,.2f} · 2차 동적 조정·재출발 대기 · "
                f"1차는 손절 없음 · TP1만 활성화"
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


async def _execute_scheduled_entry(session_date: str, session_key: str) -> bool:
    """하루 두 세션에서 정상 신호를 우선하고 마감에는 반드시 방향을 정한다."""
    run_key = f"{session_date}:{session_key}"
    if get_scheduled_entry_session(session_date, session_key):
        return True
    mode = state.trading_mode
    if not state.auto_trade_enabled or state.emergency_stopped or mode == "SIGNAL_ONLY":
        return False
    if mode == "LIVE_TRADING" and (not private_client or not risk_cfg.live_trading_allowed):
        return False

    run = _scheduled_analysis_runs.setdefault(
        run_key,
        {
            "processed_event_ids": set(), "last_analysis_at": 0.0,
            "attempts": 0, "samples": [],
        },
    )
    # 이미 시작한 50/25/25 피라미딩은 세션 종료 후에도 별도 루프가 추적한다.
    if run.get("pyramid"):
        return False

    # 오전·저녁 거래를 서로 독립된 두 번의 거래로 만들기 위해 새 세션의
    # 첫 분석 전에 이전 PAPER 포지션을 정리한다. LIVE는 거래소 청산 확인
    # 전에는 새 주문을 내지 않는다.
    if mode == "PAPER_TRADING" and paper_trader.is_open:
        if not state.last_price:
            return False
        previous = dict(paper_trader.open_data or {})
        trade_id, pnl = paper_trader.force_close(float(state.last_price))
        await _cancel_scheduled_scale_in_after_exit(trade_id, "SESSION_ROTATION")
        risk_mgr.record_trade_result(pnl, "SESSION_ROTATION")
        msg = state.add_log(
            f"[고정 세션 {session_key}] 이전 {previous.get('direction', '포지션')} "
            f"#{trade_id} 세션 교대 청산 · {pnl:+.2f}%"
        )
        await manager.broadcast({"type": "log", "data": {"message": msg}})
        await manager.broadcast({"type": "trade_update"})
    elif mode == "LIVE_TRADING":
        positions = [
            p for p in getattr(state, "cached_positions", [])
            if p.get("symbol") == SYMBOL
        ]
        if positions:
            if not run.get("rotation_close_requested"):
                for position in positions:
                    try:
                        await asyncio.to_thread(
                            private_client.close_position,
                            position.get("holdSide", "long"),
                        )
                    except Exception as exc:
                        msg = state.add_log(f"[고정 세션 {session_key}] 이전 LIVE 청산 실패: {exc}")
                        await manager.broadcast({"type": "log", "data": {"message": msg}})
                        return False
                run["rotation_close_requested"] = True
                msg = state.add_log(f"[고정 세션 {session_key}] 이전 LIVE 포지션 청산 요청")
                await manager.broadcast({"type": "log", "data": {"message": msg}})
            return False

    now = time.monotonic()
    remaining_seconds = seconds_until_session_end(session_date, session_key)
    force_entry_due = remaining_seconds <= SCHEDULED_FORCE_ENTRY_BEFORE_END_SECONDS
    if (
        not force_entry_due
        and run["last_analysis_at"]
        and now - run["last_analysis_at"] < SCHEDULED_ANALYSIS_INTERVAL_SECONDS
    ):
        return False
    run["last_analysis_at"] = now
    run["attempts"] += 1

    latest, errors = await asyncio.to_thread(_worker_analyze)
    for error in errors:
        msg = state.add_log(f"[고정 세션 {session_key} 분석 경고] {error}")
        await manager.broadcast({"type": "log", "data": {"message": msg}})
    if latest:
        state.last_result = latest
        run["samples"].append(latest)
        run["samples"] = run["samples"][-120:]

    # 가장 마지막 항목은 진행 중인 봉이므로 제외하고 확정봉만 판단한다.
    candles_5m = get_recent_candles(SYMBOL, "5m", 260)
    candles_15m = get_recent_candles(SYMBOL, "15m", 260)
    candles_1h = get_recent_candles(SYMBOL, "1H", 260)
    decision = volume_event_engine.evaluate(
        candles_5m[:-1] if len(candles_5m) > 1 else [],
        candles_15m[:-1] if len(candles_15m) > 1 else [],
        candles_1h[:-1] if len(candles_1h) > 1 else [],
    )
    result = decision.to_result(latest)
    event_id = int(result.get("event_id") or 0)
    session_start, _ = scheduled_session_bounds(session_date, session_key)
    if event_id and event_id < int(session_start.timestamp() * 1000):
        result["direction"] = "NO_TRADE"
        result["reasons"] = ["활성 시간 시작 전에 발생한 Volume Event · 진입 제외"]
    if event_id and event_id in run["processed_event_ids"]:
        result["direction"] = "NO_TRADE"
        result["reasons"] = ["이미 판단한 Volume Event · 중복 진입 차단"]

    direction = str(result.get("direction") or "NO_TRADE")
    mandatory_fallback = False
    if direction not in ("LONG", "SHORT"):
        if not force_entry_due:
            state.last_result = result
            await manager.broadcast({"type": "signal", "data": result})
            msg = state.add_log(
                f"[고정 세션 {session_key}] 정상 신호 대기 · "
                f"{'; '.join(result.get('reasons') or ['확정 신호 없음'])}"
            )
            await manager.broadcast({"type": "log", "data": {"message": msg}})
            return False
        if not latest or not state.last_price:
            msg = state.add_log(
                f"[고정 세션 {session_key}] 의무 진입 대기 · 최신 분석/현재가 없음"
            )
            await manager.broadcast({"type": "log", "data": {"message": msg}})
            return False
        direction, consensus_score = choose_consensus_direction(run["samples"] or [latest])
        if direction not in ("LONG", "SHORT"):
            direction = choose_forced_direction(latest)
        result = build_forced_entry_result(
            latest, float(state.last_price), direction, session_key, risk_cfg,
        )
        result = reprice_scheduled_result(result, float(state.last_price))
        result.update({
            "direction": direction,
            "planned_direction": direction,
            "risk_reward_ratio": 2.0,
            "forced_session_entry": True,
            "event_state": "MANDATORY_FALLBACK",
            "entry_grade": "SCHEDULED_MANDATORY",
            "confidence": 100.0,
        })
        result["reasons"] = [
            f"{session_key} 세션 정상 Volume Event 미확정 · 마감 의무 진입",
            f"누적 1H·15m·5m 방향 점수 {consensus_score:+.2f} → {direction}",
            *list(result.get("reasons") or []),
        ]
        mandatory_fallback = True
        event_id = 0

    state.last_result = result
    await manager.broadcast({"type": "signal", "data": result})

    if event_id:
        run["processed_event_ids"].add(event_id)
    if not mandatory_fallback and float(result.get("risk_reward_ratio") or 0) < 1.5:
        return False

    tf_directions = result.get("timeframe_directions") or {}
    if mandatory_fallback:
        allowed, block_reason = risk_mgr.check_mandatory_session_entry(
            direction=direction,
            mode=TradingMode(mode),
            cached_positions=getattr(state, "cached_positions", []),
            private_client=private_client,
        )
    else:
        allowed, block_reason = risk_mgr.check_entry(
            direction=direction,
            confidence=float(result.get("confidence") or 0),
            mode=TradingMode(mode),
            cached_positions=getattr(state, "cached_positions", []),
            private_client=private_client,
            entry_price=result.get("entry_price"),
            stop_loss=result.get("stop_loss"),
            entry_grade=result.get("entry_grade"),
            risk_warnings=[],
            strategy_signal=result.get("strategy_signal"),
            timeframe_directions={key: tf_directions.get(key, "HOLD") for key in ("15m", "1H")},
        )
    if not allowed:
        msg = state.add_log(f"[고정 세션 {session_key}] 안전 차단 · {block_reason}")
        await manager.broadcast({"type": "log", "data": {"message": msg}})
        if remaining_seconds <= 0:
            record_scheduled_entry_session(
                session_date, session_key, "SAFETY_BLOCKED", mode,
                direction, block_reason,
            )
            _scheduled_analysis_runs.pop(run_key, None)
            return True
        return False

    if mode == "PAPER_TRADING":
        full_size = _paper_risk_position_size(result["entry_price"], result["stop_loss"])
        first_size = round(full_size * 0.50, 8)
        add_size = round(full_size * 0.25, 8)
        if first_size <= 0 or add_size <= 0:
            return False
        plan = dict(result)
        plan.update({
            "position_size_btc": first_size,
            "position_size_percent": 50.0,
            "entry_stage": 1,
        })
        plan["reasons"] = [
            f"고정 진입 세션 {session_key}: 하루 2회 중 1회",
            *list(result.get("reasons") or []),
            "1차 50% 진입 · 손실 방향 추가 진입 금지",
            "+0.5R 논리 유지 시 25%, +1.0R 고점/저점 갱신 시 25% 추가",
        ]
        trade_id = paper_trader.open_trade(direction, plan)
        if state.paper_account_start_trade_id is None:
            state.paper_account_start_trade_id = trade_id
        run["pyramid"] = {
            "trade_id": trade_id,
            "direction": direction,
            "first_entry_price": float(plan["entry_price"]),
            "original_stop": float(plan["stop_loss"]),
            "risk_per_btc": abs(float(plan["entry_price"]) - float(plan["stop_loss"])),
            "add_size_btc": add_size,
            "target_size_btc": full_size,
            "next_stage": 2,
            "last_add_price": float(plan["entry_price"]),
            "last_candle_timestamp": int((result.get("diagnostics") or {}).get("metrics", {}).get("timestamp") or 0),
            "result": plan,
        }
        risk_mgr.record_order_placed()
        detail = f"PAPER {direction} 1차 50% #{trade_id} @ ${float(plan['entry_price']):,.2f}"
        record_scheduled_entry_session(session_date, session_key, "ENTERED", mode, direction, detail)
        msg = state.add_log(f"[고정 세션 {session_key}] {detail}")
        await manager.broadcast({"type": "log", "data": {"message": msg}})
        await manager.broadcast({"type": "trade_update"})
        await manager.broadcast({"type": "status", "data": _status_payload()})
        await _send_filled_position_email(plan, "PAPER")
        return True

    # LIVE는 실거래 허용이 명시적으로 켜진 경우에도 위험기반 전체 수량의 50%만 첫 주문한다.
    full_size = max(0.0, float(result.get("position_size_btc") or risk_cfg.order_size_btc))
    first_size = full_size * 0.50
    if first_size <= 0:
        return False
    side = "buy" if direction == "LONG" else "sell"
    size = f"{first_size:.8f}".rstrip("0").rstrip(".")
    try:
        response = await asyncio.to_thread(private_client.place_market_order, side, size, "open")
    except Exception as exc:
        msg = state.add_log(f"[고정 세션 {session_key}] LIVE 1차 주문 실패: {exc}")
        await manager.broadcast({"type": "log", "data": {"message": msg}})
        return False
    record_scheduled_entry_session(
        session_date, session_key, "ENTERED", mode, direction,
        f"LIVE 1차 50% 시장가 주문 {response.get('orderId') or 'submitted'}",
    )
    return True


async def scheduled_entry_loop():
    while True:
        try:
            active = active_scheduled_session()
            if active:
                await _execute_scheduled_entry(*active)
            else:
                # 종료 직전 틱을 놓쳤더라도 NO_TRADE로 끝내지 않고 마지막
                # 분석값으로 의무 진입을 한 번 더 시도한다.
                now_kst = datetime.now(KST)
                for run_key, run in list(_scheduled_analysis_runs.items()):
                    if run.get("pyramid") or run.get("scale_in"):
                        continue
                    session_date, session_key = run_key.split(":", 1)
                    _, end_at = scheduled_session_bounds(session_date, session_key)
                    if now_kst <= end_at:
                        continue
                    await _execute_scheduled_entry(session_date, session_key)
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
    stop_loss = row.get("stop_loss")
    sl_hit = bool(stop_loss is not None) and (
        candle["low"] <= stop_loss if direction == "LONG" else candle["high"] >= stop_loss
    )
    tp_hit = bool(row.get("take_profit_1")) and (
        candle["high"] >= row["take_profit_1"] if direction == "LONG" else candle["low"] <= row["take_profit_1"]
    )
    if sl_hit and tp_hit:
        # 1분봉 내부 순서는 알 수 없으므로 시가에서 더 가까운 주문이 먼저 체결된 것으로 봅니다.
        sl_hit = abs(candle["open"] - stop_loss) <= abs(candle["open"] - row["take_profit_1"])
        tp_hit = not sl_hit
    return ("SL", float(stop_loss), candle) if sl_hit else ("TP1", float(row["take_profit_1"]), candle)


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
            await _cancel_scheduled_scale_in_after_exit(tid, result_code)
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
    if _restore_open_scheduled_scale_in():
        state.add_log("[자동 복구] 기존 잔여 50% 계획 유지 · 더 좋은 가격 조건 계속 추적")
    await _reconcile_missed_exits()
    # 복구한 포지션의 실제 체결 수량을 유지한다. 재시작이 50%를 100%로 늘리면 안 된다.
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
        pullback = split.get("pullback") or {}
        candidate_price = float(pullback.get("close") or 0)
        current = paper_trader.open_data or {}
        current_size = float(current.get("size") or 0)
        second_size = float(split.get("second_size_btc") or 0)
        total_size = current_size + second_size
        average = None
        if candidate_price > 0 and total_size > 0:
            average = (
                float(current.get("entry") or 0) * current_size + candidate_price * second_size
            ) / total_size
        mode = (
            "PAPER · 거래량 급증 대기"
            if not split.get("impulse")
            else "PAPER · 조정 대기"
            if not pullback
            else "PAPER · 재출발 대기"
        )
        return {
            "mode": mode,
            "direction": split.get("direction"),
            "entry_price": candidate_price or None,
            # 1차 50% 상태에서는 SL이 아직 정해지지 않았다. 2차 체결 후
            # 최종 평균단가를 기준으로 계산한 값만 활성 SL로 표시한다.
            "stop_loss": None,
            "take_profit_1": result.get("take_profit_1"),
            "take_profit_2": result.get("take_profit_2"),
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
    # 고정 세션의 메모리상 2차 분할진입도 함께 제거한다.
    # 원 포지션을 청산한 뒤 예상 체결 대기가 화면에 남지 않게 한다.
    _scheduled_analysis_runs.clear()
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
    if state.trading_mode == "PAPER_TRADING":
        if not paper_trader.is_open or not state.last_price:
            return {"ok": False, "error": "진행 중인 모의 포지션이 없습니다"}
        state.pending_paper_order = None
        _scheduled_analysis_runs.clear()
        tid, pnl = paper_trader.force_close(state.last_price)
        risk_mgr.record_trade_result(pnl, "MANUAL_CLOSE")
        msg = state.add_log(f"[모의매매 수동청산] #{tid} PnL={pnl:+.2f}%")
        await manager.broadcast({"type": "log", "data": {"message": msg}})
        await manager.broadcast({"type": "trade_update"})
        await manager.broadcast({"type": "status", "data": _status_payload()})
        return {"ok": True, "trade_id": tid, "pnl_pct": pnl}
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
