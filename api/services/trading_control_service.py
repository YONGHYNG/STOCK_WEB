# 역할: 자동매매 시작, 중지, 새로고침을 제어하는 서비스.
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect

from backend.strategy.multi_timeframe_strategy import TradingAIEngine
from backend.strategy.backtester import Backtester, BacktestConfig
from backend.bitget.market_api import BitgetClient
from backend.bitget.client import BitgetPrivateClient
import backend.credentials as creds_store
from backend.order.paper_trader import PaperTrader
from backend.notifications import send_trade_plan_email
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
    TAKER_FEE_RATE,
    TIMEFRAMES,
    USE_DEMO_DATA,
)
from backend.database import (
    close_trade,
    get_all_time_high,
    get_all_time_low,
    get_open_trade,
    get_paper_account,
    get_recent_candles,
    get_recent_trades,
    insert_candles,
    insert_signal,
    open_trade,
    purge_unaligned_candles,
)
from backend.server_state import state
from api.schemas.trading_schema import (
    AutoTradePayload,
    BacktestPayload,
    CredentialsPayload,
    ModePayload,
    OrderPayload,
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
    result = engine.analyze_multi_timeframe(
        usable,
        all_time_high=ath,
        all_time_low=atl,
        market=market,
        account_equity=_account_equity_from_cache(),
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
    fee_pct = float(TAKER_FEE_RATE) * 2 * 100
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
        "size_btc": risk_cfg.order_size_btc,
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


def _paper_account_payload() -> dict:
    account = get_paper_account(PAPER_ACCOUNT_INITIAL_BALANCE, PAPER_ACCOUNT_LEVERAGE)
    initial_balance = float(account["initial_balance"])
    balance = float(account["balance"])
    leverage = float(account["leverage"])
    realized_pnl = balance - initial_balance
    paper_position = _paper_position_payload()
    unrealized_pnl = 0.0
    if paper_position:
        unrealized_pnl = balance * leverage * (float(paper_position.get("pnl_pct") or 0) / 100)
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
    }


def _trade_data_from_signal(result: dict) -> dict:
    return {
        "direction": result["direction"],
        "entry": result["entry_price"],
        "sl": result.get("stop_loss"),
        "tp1": result.get("take_profit_1"),
        "tp2": result.get("take_profit_2"),
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
    sl, tp1, tp2 = t.get("sl"), t.get("tp1"), t.get("tp2")

    if direction == "LONG":
        if tp2 and price >= tp2:
            return "TP2"
        if tp1 and price >= tp1:
            return "TP1"
        if sl and price <= sl:
            return "SL"
    elif direction == "SHORT":
        if tp2 and price <= tp2:
            return "TP2"
        if tp1 and price <= tp1:
            return "TP1"
        if sl and price >= sl:
            return "SL"
    return None


def _pnl_pct(direction: str, entry: float, exit_price: float) -> float:
    gross = (exit_price - entry) / entry * 100 if direction == "LONG" else (entry - exit_price) / entry * 100
    return gross - float(TAKER_FEE_RATE) * 2 * 100


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

    tid = state.open_trade_id
    close_trade(trade_id=tid, exit_price=price, result=result_code, pnl_pct=pnl_pct,
                profit_reason=profit_reason, loss_reason=loss_reason)
    emoji = "익절" if result_code.startswith("TP") else "손절"
    msg = state.add_log(f"[{emoji}] TRADE #{tid}  {result_code}  {sign}{pnl_pct:.2f}%")
    state.open_trade_id = None
    state.open_trade_data = None
    await manager.broadcast({"type": "log", "data": {"message": msg}})
    await manager.broadcast({"type": "trade_update"})


async def _check_paper_tp_sl(price: float):
    result_code = paper_trader.check_tp_sl(price)
    if not result_code:
        return
    t = paper_trader.open_data
    entry, direction = t["entry"], t["direction"]
    pnl_pct = _pnl_pct(direction, entry, price)
    sign = "+" if pnl_pct >= 0 else ""
    profit_reason = f"[모의] {result_code} 적중: ${entry:,.2f} → ${price:,.2f}  ({sign}{pnl_pct:.2f}%)" if result_code.startswith("TP") else ""
    loss_reason = f"[모의] 손절: ${entry:,.2f} → ${price:,.2f}  ({sign}{pnl_pct:.2f}%)" if result_code == "SL" else ""
    tid, pnl = paper_trader.close_trade(exit_price=price, result=result_code,
                                        profit_reason=profit_reason, loss_reason=loss_reason)
    risk_mgr.record_trade_result(pnl)
    emoji = "익절" if result_code.startswith("TP") else "손절"
    msg = state.add_log(f"[모의매매 {emoji}] #{tid}  {result_code}  {sign}{pnl:.2f}%")
    await manager.broadcast({"type": "log", "data": {"message": msg}})
    await manager.broadcast({"type": "trade_update"})
    await manager.broadcast({"type": "status", "data": _status_payload()})


# ── Auto trade ─────────────────────────────────────────────────────────────────


async def _check_auto_trade(result: dict):
    if not state.auto_trade_enabled:
        return
    if state.trading_mode == "SIGNAL_ONLY":
        return

    direction = result.get("direction", "HOLD")
    confidence = result.get("confidence", 0.0)
    mode = TradingMode(state.trading_mode)

    # 미체결 지정가는 같은 방향에서 더 유리한 진입가가 확정되면 갱신한다.
    # LONG은 더 낮은 가격, SHORT은 더 높은 가격만 더 좋은 조건으로 본다.
    if state.trading_mode == "PAPER_TRADING" and state.pending_paper_order:
        await _refresh_pending_paper_order(direction, result)
        return
    if state.trading_mode == "LIVE_TRADING" and state.pending_live_order:
        await _refresh_pending_live_order(direction, result)
        return

    allowed, reason = risk_mgr.check_entry(
        direction=direction, confidence=confidence, mode=mode,
        cached_positions=state.cached_positions, private_client=private_client,
        entry_price=result.get("entry_price"), stop_loss=result.get("stop_loss"),
        entry_grade=result.get("entry_grade"), risk_warnings=result.get("risk_warnings", []),
    )
    if not allowed:
        if reason and "이미" not in reason:
            msg = state.add_log(f"[자동매매 차단] {reason}")
            await manager.broadcast({"type": "log", "data": {"message": msg}})
        return

    if state.trading_mode == "PAPER_TRADING":
        await _auto_paper_trade(direction, result)
    elif state.trading_mode == "LIVE_TRADING":
        await _auto_live_trade(direction, result)


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


def _is_strong_trend_entry(direction: str, result: dict) -> bool:
    """A등급 확정 신호만 불리한 가격을 감수한 추격 진입으로 허용한다."""
    return (
        direction in ("LONG", "SHORT")
        and result.get("entry_grade") == "A"
        and float(result.get("confidence") or 0) >= risk_cfg.confidence_threshold
        and not result.get("risk_warnings")
    )


async def _refresh_pending_paper_order(direction: str, result: dict):
    pending = state.pending_paper_order
    if not pending or direction != pending.get("direction"):
        return
    previous = pending.get("result") or {}
    better_entry = _is_better_entry(direction, previous.get("entry_price"), result.get("entry_price"))
    strong_trend = _is_strong_trend_entry(direction, result)
    if not better_entry and not strong_trend:
        return

    old_entry = float(previous.get("entry_price") or 0)
    new_entry = float(result.get("entry_price") or 0)
    if old_entry == new_entry:
        return
    state.pending_paper_order = {"direction": direction, "result": dict(result)}
    update_reason = "강한 추세 추격" if strong_trend and not better_entry else "진입 조건 개선"
    msg = state.add_log(
        f"[모의 대기 주문 개선] {direction} ${old_entry:,.2f} → ${new_entry:,.2f}  "
        f"{update_reason}, 손절·익절 조건도 최신 신호로 갱신"
    )
    await manager.broadcast({"type": "log", "data": {"message": msg}})
    await manager.broadcast({"type": "status", "data": _status_payload()})


async def _refresh_pending_live_order(direction: str, result: dict):
    pending = state.pending_live_order
    if not private_client or not pending or direction != pending.get("direction"):
        return
    better_entry = _is_better_entry(direction, pending.get("entry_price"), result.get("entry_price"))
    strong_trend = _is_strong_trend_entry(direction, result)
    if not better_entry and not strong_trend:
        return

    old_order_id = str(pending.get("order_id") or "")
    old_entry = float(pending.get("entry_price") or 0)
    new_entry = float(result.get("entry_price") or 0)
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
            update_reason = "강한 추세 추격" if strong_trend and not better_entry else "진입 조건 개선"
            msg = state.add_log(
                f"[LIVE 대기 주문 개선] {direction} ${old_entry:,.2f} → ${new_entry:,.2f}  {update_reason}"
            )
        else:
            msg = state.add_log("[LIVE 대기 주문 갱신 실패] 기존 주문 취소 후 새 주문 생성 실패")
    except Exception as exc:
        msg = state.add_log(f"[LIVE 대기 주문 갱신 실패] 기존 주문 유지: {exc}")
    await manager.broadcast({"type": "log", "data": {"message": msg}})
    await manager.broadcast({"type": "status", "data": _status_payload()})


async def _auto_paper_trade(direction: str, r: dict):
    if paper_trader.is_open or state.pending_paper_order:
        return

    state.pending_paper_order = {"direction": direction, "result": dict(r)}
    risk_mgr.record_order_placed()
    msg = state.add_log(
        f"[모의 지정가 대기] {direction} ${float(r.get('entry_price') or 0):,.2f}  "
        f"전략신호={r.get('strategy_signal', direction)}"
    )
    await manager.broadcast({"type": "log", "data": {"message": msg}})
    await manager.broadcast({"type": "status", "data": _status_payload()})


async def _send_filled_position_email(result: dict):
    try:
        sent, detail = await asyncio.to_thread(send_trade_plan_email, result)
        email_log = state.add_log(
            f"[Gmail 알림] 포지션 체결 메일 발송 완료 → {detail}"
            if sent else f"[Gmail 알림 실패] {detail}"
        )
    except Exception as exc:
        email_log = state.add_log(f"[Gmail 알림 실패] {exc}")
    await manager.broadcast({"type": "log", "data": {"message": email_log}})


async def _check_pending_paper_entry(price: float):
    pending = state.pending_paper_order
    if not pending or paper_trader.is_open:
        return
    direction = pending["direction"]
    result = pending["result"]
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
    await _send_filled_position_email(result)
    await manager.broadcast({"type": "trade_update"})
    await manager.broadcast({"type": "status", "data": _status_payload()})


async def _auto_live_trade(direction: str, r: dict):
    if not private_client:
        return
    btc_positions = [p for p in state.cached_positions if p.get("symbol") == SYMBOL]
    if btc_positions or state.pending_live_order_id:
        return

    size = f"{risk_cfg.order_size_btc:.3f}"
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
        }
        risk_mgr.record_order_placed()
        msg = state.add_log(
            f"[자동매매 LIVE 지정가] {direction} {size} BTC @ ${limit_price}  "
            f"전략신호={r.get('strategy_signal', direction)}  orderId={res.get('orderId', '?')}"
        )
        await manager.broadcast({"type": "log", "data": {"message": msg}})
        await manager.broadcast({"type": "status", "data": _status_payload()})
    except Exception as exc:
        msg = state.add_log(f"[자동매매] 주문 실패: {exc}")
        await manager.broadcast({"type": "log", "data": {"message": msg}})


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
                            await _send_filled_position_email(filled_result)
                        await manager.broadcast({"type": "status", "data": _status_payload()})
        except Exception:
            pass
        await asyncio.sleep(10)


# ── Startup ────────────────────────────────────────────────────────────────────


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
    if state.paper_account_start_trade_id is None and paper_trader.is_open:
        state.paper_account_start_trade_id = paper_trader.open_id
    asyncio.create_task(signal_loop())
    asyncio.create_task(price_loop())
    asyncio.create_task(account_loop())


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
        "paper_position": _paper_position_payload(),
        "paper_account": _paper_account_payload(),
        "pending_entry": _pending_entry_payload(),
    }


def _pending_entry_payload() -> Optional[dict]:
    if state.pending_paper_order:
        result = state.pending_paper_order.get("result") or {}
        return {
            "mode": "PAPER",
            "direction": state.pending_paper_order.get("direction"),
            "entry_price": result.get("entry_price"),
            "stop_loss": result.get("stop_loss"),
            "take_profit_1": result.get("take_profit_1"),
            "take_profit_2": result.get("take_profit_2"),
        }
    if state.pending_live_order:
        return {
            "mode": "LIVE",
            "direction": state.pending_live_order.get("direction"),
            "entry_price": state.pending_live_order.get("entry_price"),
            "order_id": state.pending_live_order.get("order_id"),
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
    risk_settings_store.save(s)
    risk_cfg = s
    risk_mgr = RiskManager(s)
    msg = state.add_log(f"[리스크 설정] 저장 완료  실거래허용={s.live_trading_allowed}")
    await manager.broadcast({"type": "log", "data": {"message": msg}})
    await manager.broadcast({"type": "status", "data": _status_payload()})
    return {"ok": True}




async def set_mode(payload: ModePayload):
    state.trading_mode = payload.mode
    if state.trading_mode == "PAPER_TRADING":
        state.auto_trade_enabled = True
        keep_awake.enable()
    msg = state.add_log(f"[모드변경] {state.trading_mode}")
    await manager.broadcast({"type": "log", "data": {"message": msg}})
    await manager.broadcast({"type": "status", "data": _status_payload()})
    return {"ok": True}




async def set_auto_trade(payload: AutoTradePayload):
    global risk_cfg
    enabled = True if state.trading_mode == "PAPER_TRADING" else payload.enabled
    state.auto_trade_enabled = enabled
    if payload.threshold is not None:
        risk_cfg.confidence_threshold = payload.threshold
        risk_mgr.settings.confidence_threshold = payload.threshold
    ok, power_msg = keep_awake.enable() if enabled else keep_awake.disable()
    msg = state.add_log(f"[자동매매] {'ON' if enabled else 'OFF'}  모드={state.trading_mode}")
    power_log = state.add_log(f"[전원관리] {power_msg}" if ok else f"[전원관리 경고] {power_msg}")
    await manager.broadcast({"type": "log", "data": {"message": msg}})
    await manager.broadcast({"type": "log", "data": {"message": power_log}})
    await manager.broadcast({"type": "status", "data": _status_payload()})
    return {"ok": True}


async def emergency_stop():
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


async def emergency_resume():
    risk_mgr.deactivate_emergency_stop()
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
        risk_mgr.record_trade_result(pnl)
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
        pnl_pct = _pnl_pct(t["direction"], t["entry"], price)
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
    limit_price = state.last_price - 150.0 if payload.side == "LONG" else state.last_price + 150.0
    try:
        result = private_client.place_limit_order(side, str(payload.size), f"{limit_price:.1f}", "open")
        state.pending_live_order_id = str(result.get("orderId") or "pending")
        state.pending_live_order = {
            "direction": payload.side,
            "entry_price": limit_price,
            "order_id": state.pending_live_order_id,
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

